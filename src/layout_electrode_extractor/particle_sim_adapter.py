"""Export extraction masks using the current particle-sim ProductManifest contract."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from .schema import ManifestError

_CONDUCTOR_ROLES = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}


def _stack_layers(meta: dict, layers: dict[str, dict], contacts: list[dict]) -> list[dict]:
    """Build assumed simulator stack rows from roles and explicit contact endpoints."""
    conductor_ids = meta.get("stack")
    if not isinstance(conductor_ids, list) or not conductor_ids:
        raise ManifestError("particle-sim export requires a non-empty conductor stack")
    for layer_id in conductor_ids:
        if layer_id not in layers or layers[layer_id].get("role") not in _CONDUCTOR_ROLES:
            raise ManifestError(
                f"unsupported particle-sim stack: '{layer_id}' is missing a conductor role"
            )

    by_role: dict[str, list[str]] = {}
    for layer_id in conductor_ids:
        by_role.setdefault(layers[layer_id]["role"], []).append(layer_id)
    active_ids = by_role.get("ACTIVE", [])
    oactive_ids = by_role.get("OACTIVE", [])
    upper_conductor_ids = [
        layer_id for layer_id in conductor_ids if layers[layer_id]["role"] in {"METAL", "CONDUCTOR"}
    ]
    if active_ids and len(active_ids) != 1:
        raise ManifestError(
            "unsupported assumed stack: multiple ACTIVE-role layers make the ACTIVE/OACTIVE "
            "dielectric placement ambiguous"
        )
    if oactive_ids and len(oactive_ids) != 1:
        raise ManifestError(
            "unsupported assumed stack: multiple OACTIVE-role layers make dielectric placement "
            "ambiguous"
        )

    order = {layer_id: index for index, layer_id in enumerate(conductor_ids)}
    before: dict[str, list[tuple[str, float, float | None]]] = {}
    if active_ids and oactive_ids:
        active, oactive = active_ids[0], oactive_ids[0]
        if order[active] >= order[oactive]:
            raise ManifestError(
                "unsupported assumed stack: ACTIVE role must precede OACTIVE role for ILD placement"
            )
        before.setdefault(oactive, []).append(("ILD_ACTIVE_OACTIVE", 0.2, 0.5))
    if oactive_ids and upper_conductor_ids:
        later_metals = [
            layer_id for layer_id in upper_conductor_ids if order[layer_id] > order[oactive_ids[0]]
        ]
        if not later_metals:
            raise ManifestError(
                "unsupported assumed stack: no METAL- or CONDUCTOR-role conductor follows "
                "OACTIVE for ILD placement"
            )
        before.setdefault(later_metals[0], []).append(("ILD_OACTIVE_METAL", 0.2, 0.5))
    elif oactive_ids:
        raise ManifestError(
            "unsupported assumed stack: OACTIVE role has no upper METAL or CONDUCTOR role "
            "for ILD placement"
        )

    contact_by_upper: dict[str, list[dict]] = {}
    for contact in contacts:
        lower, upper = contact.get("lower"), contact.get("upper")
        if lower not in order or upper not in order or order[lower] >= order[upper]:
            raise ManifestError(
                f"unsupported contact topology for '{contact.get('layer')}': declared lower/upper "
                "endpoints must be ordered conductor layers in the source stack"
            )
        contact_by_upper.setdefault(upper, []).append(contact)

    conductor_names = set(conductor_ids)
    used_names = conductor_names | {contact["layer"] for contact in contacts}

    def unique_name(base: str) -> str:
        candidate = base
        suffix = 2
        while candidate in used_names:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used_names.add(candidate)
        return candidate

    rows: list[dict] = []
    emitted_contacts: set[str] = set()
    for layer_id in conductor_ids:
        for base, thickness, planarization in before.get(layer_id, []):
            row = {
                "layer_name": unique_name(base),
                "process_order": len(rows),
                "material_type": "inorganic",
                "thickness_um": thickness,
                "patterned": False,
            }
            if planarization is not None:
                row["planarization_factor"] = planarization
            rows.append(row)
        for contact in contact_by_upper.get(layer_id, []):
            hole = contact["layer"]
            if hole in conductor_names or hole in emitted_contacts:
                raise ManifestError(f"unsupported contact topology: duplicate layer ID '{hole}'")
            used_names.add(hole)
            emitted_contacts.add(hole)
            rows.append(
                {
                    "layer_name": hole,
                    "process_order": len(rows),
                    "material_type": "inorganic",
                    "thickness_um": 0.02,
                    "patterned": False,
                }
            )
        role = layers[layer_id]["role"]
        rows.append(
            {
                "layer_name": layer_id,
                "process_order": len(rows),
                "material_type": "conductor",
                "thickness_um": 0.05 if role == "GAT" else 0.1,
                "patterned": True,
            }
        )
    if emitted_contacts != {contact["layer"] for contact in contacts}:
        missing = sorted({contact["layer"] for contact in contacts} - emitted_contacts)
        raise ManifestError(
            f"unsupported contact topology: upper endpoint not emitted for contact layers {missing}"
        )
    return rows


def export_particle_sim(extraction_dir: str | Path, output_dir: str | Path) -> dict:
    """Write a schema-2.0 JSON/YAML-compatible product manifest and masks."""
    source = Path(extraction_dir).resolve(strict=True)
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    meta = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    layers = {row["id"]: row for row in meta["layers"]}
    conductors = list(meta["stack"])
    contacts = [row for row in meta["contact_rules"]]
    # Resolve unsupported or ambiguous topology before creating any output files.
    contact_layers = [row["layer"] for row in contacts]
    if len(contact_layers) != len(set(contact_layers)):
        raise ManifestError(
            "unsupported contact topology: particle-sim export requires one endpoint pair "
            "per physical CNT/VIA layer; per-hole rules need separate validated masks"
        )
    product_layers = _stack_layers(meta, layers, contacts)
    source_layer = conductors[-1]
    electrode_rows = []
    electrode_masks: dict[str, Path] = {}
    electrode_by_layer: dict[str, list[dict]] = {name: [] for name in conductors}
    for electrode in meta["electrodes"]:
        for layer, info in electrode["layers"].items():
            if layer not in conductors:
                continue
            eid = f"{electrode['id']}_{layer}"
            path = f"masks/electrode_{eid}.png"
            row = {
                "electrode_id": eid,
                "layer_name": layer,
                "net_id": electrode["id"],
                "electrode_role": "SYNTHETIC_EXTRACTED",
                "path": path,
            }
            electrode_rows.append(row)
            electrode_by_layer[layer].append(row)
            electrode_masks[path] = source / info["path"]

    output.mkdir(parents=True)
    masks_dir = output / "masks"
    masks_dir.mkdir()
    layer_mask_rows = []
    for layer in conductors:
        path = f"masks/layer_{layer}.png"
        with Image.open(source / layers[layer]["raw_path"]) as image:
            tiled = np.tile(np.asarray(image.convert("L")), (2, 2))
            Image.fromarray(tiled.astype(np.uint8), mode="L").save(output / path)
        layer_mask_rows.append({"layer_name": layer, "path": path})
    for relative, input_path in electrode_masks.items():
        shutil.copyfile(input_path, output / relative)

    contact_rows = []
    for contact in contacts:
        hole = contact["layer"]
        contact_rows.append(
            {
                "contact_id": hole,
                "path": f"masks/contact_{hole}_tr_cut.png",
                "hole_layer": hole,
                "lower_layer": contact["lower"],
                "upper_layer": contact["upper"],
                "applicable_particle_source_steps": ["SOURCE_AFTER_TOP_CONDUCTOR"],
            }
        )
        with Image.open(source / "cut_layers" / f"{hole}.png") as image:
            tiled = np.tile(np.asarray(image.convert("L")), (2, 2))
            Image.fromarray(tiled.astype(np.uint8), mode="L").save(
                output / f"masks/contact_{hole}_tr_cut.png"
            )

    pairs = []
    for i, first in enumerate(electrode_rows):
        for second in electrode_rows[i + 1 :]:
            if first["net_id"] == second["net_id"]:
                continue
            pair_id = f"PAIR_{len(pairs) + 1:06d}"
            same_layer = first["layer_name"] == second["layer_name"]
            pairs.append(
                {
                    "pair_id": pair_id,
                    "electrode_a": first["electrode_id"],
                    "electrode_b": second["electrode_id"],
                    "failure_mode": "lateral_short" if same_layer else "vertical_short",
                }
            )

    steps = [
        {
            "step_id": "SOURCE_AFTER_TOP_CONDUCTOR",
            "lands_after_layer": source_layer,
            "surface_model": "flat",
            "fab_distribution_layer": "ASSUMED_SYNTHETIC_SOURCE",
        }
    ]
    manifest = {
        "schema_version": "2.0",
        "product_id": "SYN_LAYOUT_2X2",
        "product_family": "SYNTHETIC_LAYOUT",
        "design_version": "ASSUMED_01",
        "design_lineage_id": "SYNTHETIC_FIXTURE",
        "fab_id": "ASSUMED_NO_FAB_DATA",
        "is_synthetic": True,
        "coordinate_system": {
            "origin": "upper_left",
            "x_direction": "right",
            "y_direction": "down",
            "pixel_size_x_um": meta["pixel_size_um"],
            "pixel_size_y_um": meta["pixel_size_um"],
            "roi_width_um": meta["output_size_um"][0],
            "roi_height_um": meta["output_size_um"][1],
        },
        "stack": product_layers,
        "layer_masks": layer_mask_rows,
        "electrodes": electrode_rows,
        "particle_source_steps": steps,
        "electrode_pairs": pairs,
        "excluded_electrode_pairs": [],
        "open_paths": [],
        "contacts": contact_rows,
        "open_applicable_steps_by_layer": {
            name: [] for contact in contacts for name in (contact["lower"], contact["upper"])
        },
        "particle_sizes_um": [1.0],
        "embedding_depth_um": 0.0,
        "contact_margin_um": 0.0,
        "legacy_kernel": {"size": 5, "shape": "square", "iterations": "round"},
        "post_step_policy": {"mode": "exclude"},
    }
    (output / "product.yaml").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "manifest": str(output / "product.yaml"),
        "electrodes": len(electrode_rows),
        "nets": len({row["net_id"] for row in electrode_rows}),
        "contacts": len(contact_rows),
        "classified_pairs": len(pairs),
        "pair_policy": "all unordered different-net electrode pairs; no silent exclusions",
        "shape_px": meta["output_shape_px"],
    }
    (output / "adapter-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    provenance = {
        "source_extraction": str(source),
        "contact_masks": "cut_layers/<CNT-or-VIA>.png; TR union removed from every layer",
        "synthetic_physics": "assumed; not a calibrated process stack",
        "pair_selection": report["pair_policy"],
        "roi_terminal_policy": (
            "no ROI-boundary terminals declared; edge cuts remain open-boundary limited"
        ),
        "particle_sim_periodicity": "not supported; output is a 2x2 finite image",
        "particle_source_lands_after_layer": source_layer,
        "unsupported_contact_topologies": [
            issue
            for issue in meta.get("issues", [])
            if issue.get("type")
            in {
                "periodic_contact_network",
                "multi_endpoint_contact",
                "missing_endpoint_contact",
                "orphan_contact",
            }
        ],
        "contact_topology_policy": (
            "only a finite contact component touching exactly one lower and one upper extracted "
            "electrode of the same net is supported; other cases are preserved here and expected "
            "to fail particle-sim validate-input"
        ),
    }
    (output / "adapter-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return report
