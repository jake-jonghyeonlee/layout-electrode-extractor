"""Export extraction masks using the current particle-sim ProductManifest contract."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .contact_export import diagnose_physical_holes, prepare_contacts
from .export_config import load_export_config, product_stack
from .export_semantics import circuit_declarations, mask_diagnostics
from .schema import ManifestError

_CONDUCTOR_ROLES = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}
_CONTACT_ID = re.compile(r"[A-Za-z0-9_-]+\Z")


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


def _legacy_contacts(
    source: Path, contacts: list[dict]
) -> tuple[list[dict], dict[str, np.ndarray], list[dict], int]:
    """Keep the old one-pair-per-layer, TR-cut mask contract unchanged."""
    rows = []
    masks = {}
    holes = 0
    for contact in contacts:
        hole = contact["layer"]
        if not _CONTACT_ID.fullmatch(hole) or "__" in hole or ":" in hole:
            raise ManifestError(f"unsafe generated contact_id {hole}")
        path = f"masks/contact_{hole}_tr_cut.png"
        with Image.open(source / "cut_layers" / f"{hole}.png") as image:
            unit = np.asarray(image.convert("L")) > 0
        holes += 4 * ndimage.label(unit)[1]
        masks[path] = np.tile(unit, (2, 2))
        rows.append(
            {
                "contact_id": hole,
                "path": path,
                "hole_layer": hole,
                "lower_layer": contact["lower"],
                "upper_layer": contact["upper"],
            }
        )
    return rows, masks, [], holes


def export_particle_sim(
    extraction_dir: str | Path, output_dir: str | Path, config: str | Path | None = None
) -> dict:
    """Validate first, then atomically publish a schema-2.0 export."""
    source = Path(extraction_dir).resolve(strict=True)
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    meta = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    layers = {row["id"]: row for row in meta["layers"]}
    conductors = list(meta["stack"])
    contacts = [row for row in meta["contact_rules"]]
    settings = load_export_config(config, meta, contacts) if config is not None else None
    # Resolve unsupported or ambiguous topology before creating any output files.
    contact_layers = [row["layer"] for row in contacts]
    if settings is None and len(contact_layers) != len(set(contact_layers)):
        raise ManifestError(
            "unsupported contact topology: particle-sim export requires one endpoint pair "
            "per physical CNT/VIA layer; per-hole rules need separate validated masks"
        )
    product_layers = product_stack(settings) if settings else _stack_layers(meta, layers, contacts)
    if settings:
        contact_rows, contact_masks, hole_provenance = prepare_contacts(
            source, meta, contacts, mixed=True
        )
        hole_diagnostics = diagnose_physical_holes(source, meta, contacts, strict=True)
        hole_count = len(hole_provenance)
    else:
        contact_rows, contact_masks, hole_provenance, hole_count = _legacy_contacts(
            source, contacts
        )
        hole_diagnostics = diagnose_physical_holes(source, meta, contacts, strict=False)
    for row in contact_rows:
        contact_id = row["contact_id"]
        if not _CONTACT_ID.fullmatch(contact_id) or "__" in contact_id or ":" in contact_id:
            raise ManifestError(f"unsafe generated contact_id {contact_id}")
    if settings:
        for row in contact_rows:
            row["applicable_particle_source_steps"] = settings["contact_applicable_stages"][
                row["hole_layer"]
            ]
        steps = [
            {
                "step_id": stage["step_id"],
                "lands_after_layer": stage["after_layer"],
                "surface_model": stage["surface_model"],
                "fab_distribution_layer": stage["fab_distribution_layer"],
            }
            for stage in settings["source_stages"]
        ]
    else:
        for row in contact_rows:
            row["applicable_particle_source_steps"] = ["SOURCE_AFTER_TOP_CONDUCTOR"]
        steps = [
            {
                "step_id": "SOURCE_AFTER_TOP_CONDUCTOR",
                "lands_after_layer": conductors[-1],
                "surface_model": "flat",
                "fab_distribution_layer": "ASSUMED_SYNTHETIC_SOURCE",
            }
        ]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        report = _write_export(
            source,
            staging,
            output,
            meta,
            layers,
            conductors,
            contacts,
            product_layers,
            contact_rows,
            contact_masks,
            hole_provenance,
            hole_diagnostics,
            hole_count,
            steps,
            settings,
        )
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        os.rename(staging, output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _write_export(
    source: Path,
    output: Path,
    final_output: Path,
    meta: dict,
    layers: dict,
    conductors: list[str],
    contacts: list[dict],
    product_layers: list[dict],
    contact_rows: list[dict],
    contact_masks: dict[str, np.ndarray],
    hole_provenance: list[dict],
    hole_diagnostics: list[dict],
    hole_count: int,
    steps: list[dict],
    settings: dict | None,
) -> dict:
    """Write to an unpublished sibling directory after preflight succeeds."""
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

    pairs, excluded_pairs, open_paths, circuit_sidecar = circuit_declarations(
        source, meta, electrode_rows, hole_provenance, settings
    )
    diagnostics = mask_diagnostics(source, meta, settings)
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

    for relative, pixels in contact_masks.items():
        Image.fromarray((pixels * 255).astype(np.uint8), mode="L").save(output / relative)

    manifest = {
        "schema_version": "2.0",
        "product_id": "SYN_LAYOUT_2X2",
        "product_family": "SYNTHETIC_LAYOUT",
        "design_version": "ASSUMED_01",
        "design_lineage_id": "SYNTHETIC_FIXTURE",
        "fab_id": "ASSUMED_NO_FAB_DATA",
        "is_synthetic": settings is None or settings["profile"] == "synthetic",
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
        "excluded_electrode_pairs": excluded_pairs,
        "open_paths": open_paths,
        "contacts": contact_rows,
        "open_applicable_steps_by_layer": {
            name: [] for contact in contacts for name in (contact["lower"], contact["upper"])
        },
        "particle_sizes_um": settings["particle_sizes_um"] if settings else [1.0],
        "embedding_depth_um": 0.0,
        "contact_margin_um": 0.0,
        "legacy_kernel": {"size": 5, "shape": "square", "iterations": "round"},
        "post_step_policy": {"mode": "exclude"},
    }
    (output / "product.yaml").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "manifest": str(final_output / "product.yaml"),
        "electrodes": len(electrode_rows),
        "nets": len({row["net_id"] for row in electrode_rows}),
        "declared_circuit_nets": (
            len({row["net_id"] for row in electrode_rows})
            if circuit_sidecar["net_status"] == "declared"
            else 0
        ),
        "provisional_extracted_nets": (
            len({row["net_id"] for row in electrode_rows})
            if circuit_sidecar["net_status"] != "declared"
            else 0
        ),
        "contacts": len(contact_rows),
        "classified_pairs": len(pairs),
        "excluded_pairs": len(excluded_pairs),
        "total_pair_inventory": len(circuit_sidecar["pair_inventory"]),
        "net_status": circuit_sidecar["net_status"],
        "open_path_status": circuit_sidecar["open_path_status"],
        "open_paths": len(open_paths),
        "pair_policy": "every unordered electrode pair included or excluded with reason",
        "shape_px": meta["output_shape_px"],
        "holes": hole_count,
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
        "particle_source_lands_after_layer": source_layer if settings is None else None,
        "particle_source_lands_after_layers": [step["lands_after_layer"] for step in steps],
        "profile": settings["profile"] if settings else "legacy",
        "particle_sizes_um": settings["particle_sizes_um"] if settings else [1.0],
        "process_stack_source": "explicit_config" if settings else "assumed_legacy",
        "process_stack_conversion": (
            "hole rows are simulator non-patterned inorganic films; conductor raw layer_masks "
            "remain topography inputs"
        ),
        "source_stages": settings["source_stages"] if settings else [],
        "surface_semantics": (
            "flat_film_approximation_unsupported" if settings and contacts else "legacy_flat"
        ),
        "contact_holes": hole_provenance,
        "physical_hole_diagnostics": hole_diagnostics,
        "circuit": circuit_sidecar,
        "mask_diagnostics": diagnostics,
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
