"""Export extraction masks using the current particle-sim ProductManifest contract."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


def export_particle_sim(extraction_dir: str | Path, output_dir: str | Path) -> dict:
    """Write a schema-2.0 JSON/YAML-compatible product manifest and masks."""
    source = Path(extraction_dir).resolve(strict=True)
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    meta = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    layers = {row["id"]: row for row in meta["layers"]}
    conductors = [name for name in meta["stack"]]
    contacts = [row for row in meta["contact_rules"]]
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

    product_layers = []
    for name in conductors:
        role = layers[name]["role"]
        product_layers.append(
            {
                "layer_name": name,
                "process_order": len(product_layers),
                "material_type": "conductor",
                "thickness_um": 0.05 if role == "GAT" else 0.1,
                "patterned": True,
            }
        )
        if name == "ACTIVE":
            product_layers.append(
                {
                    "layer_name": "ILD_ACTIVE_OACTIVE",
                    "process_order": len(product_layers),
                    "material_type": "inorganic",
                    "thickness_um": 0.2,
                    "planarization_factor": 0.5,
                    "patterned": False,
                }
            )
        if name == "OACTIVE":
            product_layers.append(
                {
                    "layer_name": "ILD_OACTIVE_METAL1",
                    "process_order": len(product_layers),
                    "material_type": "inorganic",
                    "thickness_um": 0.2,
                    "planarization_factor": 0.5,
                    "patterned": False,
                }
            )
    for contact in contacts:
        # Explicit endpoints make the invented stack's skipped layers unambiguous.
        hole = contact["layer"]
        product_layers.append(
            {
                "layer_name": hole,
                "process_order": len(product_layers),
                "material_type": "inorganic",
                "thickness_um": 0.02,
                "patterned": False,
            }
        )
    # All non-patterned contact layers must sort between their declared endpoints.
    # Place contact markers immediately before METAL1 and retain explicit endpoint refs.
    metal_order = next(i for i, row in enumerate(product_layers) if row["layer_name"] == "METAL1")
    before = [row for row in product_layers if row["layer_name"] in {c["layer"] for c in contacts}]
    conduct = [row for row in product_layers if row not in before]
    product_layers = conduct[:metal_order] + before + conduct[metal_order:]
    for index, row in enumerate(product_layers):
        row["process_order"] = index

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
                "applicable_particle_source_steps": ["SOURCE_AFTER_METAL1"],
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
            "step_id": "SOURCE_AFTER_METAL1",
            "lands_after_layer": "METAL1",
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
        "unsupported_contact_topologies": [
            issue
            for issue in meta.get("issues", [])
            if issue.get("type") in {
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
