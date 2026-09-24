"""Circuit declarations and diagnostics kept separate from extracted geometry."""

from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .export_config import _fields, _identifier
from .schema import ManifestError


def _mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 0


def _pair_id(first: str, second: str) -> str:
    digest = hashlib.sha256(f"{first}\0{second}".encode()).hexdigest()[:16].upper()
    return f"PAIR_{digest}"


def circuit_declarations(
    source: Path, meta: dict, electrodes: list[dict], holes: list[dict], settings: dict | None
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Validate all declared circuit facts before any manifest is published."""
    extracted = {row["id"] for row in meta["electrodes"]}
    mapped = settings is not None and "net_map" in settings
    net_map = settings.get("net_map") if mapped else None
    if mapped:
        if not isinstance(net_map, dict) or set(net_map) != extracted:
            raise ManifestError("net_map must cover every extracted electrode ID exactly")
        for key, value in net_map.items():
            _identifier(key, "net_map extracted electrode ID")
            _identifier(value, f"net_map[{key}]")
    elif settings and (settings.get("open_paths") or settings.get("cno_open_relations")):
        raise ManifestError("explicit open paths and CNO relations require a complete net_map")

    by_id = {row["electrode_id"]: row for row in electrodes}
    for row in electrodes:
        extracted_id = row["electrode_id"].removesuffix(f"_{row['layer_name']}")
        row["net_id"] = net_map[extracted_id] if mapped else extracted_id
        row["electrode_role"] = "CIRCUIT_MAPPED" if mapped else "SYNTHETIC_EXTRACTED"

    excluded_requested = {}
    for index, value in enumerate(settings.get("excluded_pairs", []) if settings else []):
        row = _fields(
            value, {"electrode_a", "electrode_b", "reason"}, set(), f"excluded_pairs[{index}]"
        )
        a, b = row["electrode_a"], row["electrode_b"]
        _identifier(a, "excluded_pairs.electrode_a")
        _identifier(b, "excluded_pairs.electrode_b")
        if a not in by_id or b not in by_id or a == b:
            raise ManifestError("excluded_pairs references unknown or identical electrode IDs")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ManifestError("excluded_pairs requires a nonblank reason")
        key = tuple(sorted((a, b)))
        if key in excluded_requested:
            raise ManifestError("duplicate excluded_pairs entry")
        if by_id[a]["net_id"] == by_id[b]["net_id"]:
            raise ManifestError("excluded_pairs cannot name same-net electrodes")
        excluded_requested[key] = row["reason"].strip()

    included, excluded, inventory = [], [], []
    for first, second in combinations(electrodes, 2):
        a, b = first["electrode_id"], second["electrode_id"]
        key = tuple(sorted((a, b)))
        inventory_id = _pair_id(*key)
        pair_id = inventory_id if mapped or excluded_requested else f"PAIR_{len(included) + 1:06d}"
        if first["net_id"] == second["net_id"]:
            status, reason = "excluded", "same_declared_net" if mapped else "same_provisional_net"
        elif key in excluded_requested:
            status, reason = "excluded", excluded_requested[key]
            excluded.append({"electrode_a": a, "electrode_b": b, "reason": reason})
        else:
            status, reason = "included", None
            included.append(
                {
                    "pair_id": pair_id,
                    "electrode_a": a,
                    "electrode_b": b,
                    "failure_mode": (
                        "lateral_short"
                        if first["layer_name"] == second["layer_name"]
                        else "vertical_short"
                    ),
                }
            )
        inventory.append(
            {
                "pair_id": inventory_id,
                "manifest_pair_id": pair_id if status == "included" else None,
                "electrode_a": a,
                "electrode_b": b,
                "status": status,
                "reason": reason,
            }
        )

    step_ids = {stage["step_id"] for stage in settings["source_stages"]} if settings else set()
    opens, open_details = [], []
    for index, value in enumerate(settings.get("open_paths", []) if settings else []):
        row = _fields(
            value,
            {
                "path_id",
                "electrode",
                "terminal_a_yx_px",
                "terminal_b_yx_px",
                "applicable_particle_source_steps",
                "circuit_connection_id",
                "circuit_net_id",
            },
            set(),
            f"open_paths[{index}]",
        )
        path_id = _identifier(row["path_id"], "open path ID")
        connection = _identifier(row["circuit_connection_id"], "circuit connection ID")
        net = _identifier(row["circuit_net_id"], "open path circuit net ID")
        _identifier(row["electrode"], "open path electrode")
        electrode = by_id.get(row["electrode"])
        if electrode is None or not mapped or electrode["net_id"] != net:
            raise ManifestError(f"open path {path_id}: electrode and declared circuit net disagree")
        if any(item["path_id"] == path_id for item in opens):
            raise ManifestError(f"duplicate open path {path_id}")
        steps = row["applicable_particle_source_steps"]
        if (
            not isinstance(steps, list)
            or not steps
            or any(not isinstance(step, str) for step in steps)
            or len(set(steps)) != len(steps)
            or set(steps) - step_ids
        ):
            raise ManifestError(f"open path {path_id}: invalid source steps")
        extracted_id = electrode["electrode_id"].removesuffix(f"_{electrode['layer_name']}")
        source_electrode = next(item for item in meta["electrodes"] if item["id"] == extracted_id)
        mask = _mask(source / source_electrode["layers"][electrode["layer_name"]]["path"])
        if mask.shape != tuple(meta["output_shape_px"]):
            raise ManifestError(f"open path {path_id}: electrode mask shape mismatch")
        points = []
        for name in ("terminal_a_yx_px", "terminal_b_yx_px"):
            point = row[name]
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(type(v) is not int for v in point)
                or not (0 <= point[0] < mask.shape[0] and 0 <= point[1] < mask.shape[1])
                or not mask[point[0], point[1]]
            ):
                raise ManifestError(f"open path {path_id}: {name} must land on its electrode mask")
            points.append(point)
        if points[0] == points[1]:
            raise ManifestError(f"open path {path_id}: terminals must be distinct")
        labels, _ = ndimage.label(mask)
        if labels[tuple(points[0])] != labels[tuple(points[1])]:
            raise ManifestError(f"open path {path_id}: terminals are disconnected in finite mask")
        opens.append(
            {
                "path_id": path_id,
                "electrode": electrode["electrode_id"],
                "terminal_a_yx_px": points[0],
                "terminal_b_yx_px": points[1],
                "applicable_particle_source_steps": steps,
                "fallback": "error",
            }
        )
        open_details.append(
            {"path_id": path_id, "circuit_connection_id": connection, "circuit_net_id": net}
        )

    link_connections = {}
    link_steps = {}
    for hole in holes:
        link = f"cno:{hole['contact_id']}:{hole['lower_electrode']}__{hole['upper_electrode']}"
        hole["cno_link_id"] = link
        link_connections.setdefault(link, set()).add(
            hole["lower_electrode"].removesuffix(f"_{hole['lower_layer']}")
        )
        if settings:
            link_steps.setdefault(link, set()).update(
                settings["contact_applicable_stages"][hole["hole_layer"]]
            )
    details_by_path = {row["path_id"]: row for row in open_details}
    relations = []
    seen_relations = set()
    for index, value in enumerate(settings.get("cno_open_relations", []) if settings else []):
        row = _fields(
            value,
            {"cno_link_id", "open_path_id", "circuit_connection_id"},
            set(),
            f"cno_open_relations[{index}]",
        )
        link, path = row["cno_link_id"], row["open_path_id"]
        if not isinstance(link, str) or not isinstance(path, str):
            raise ManifestError("CNO/open relation IDs must be strings")
        detail = details_by_path.get(path)
        if link not in link_connections or detail is None:
            raise ManifestError("CNO/open relation references unknown link or open path")
        if detail["circuit_connection_id"] != row["circuit_connection_id"]:
            raise ManifestError("CNO/open relation circuit connection ID disagrees")
        linked_nets = {net_map[extracted_id] for extracted_id in link_connections[link]}
        if linked_nets != {detail["circuit_net_id"]}:
            raise ManifestError("CNO/open relation link and open path circuit nets disagree")
        open_steps = next(
            item["applicable_particle_source_steps"] for item in opens if item["path_id"] == path
        )
        if not link_steps[link].intersection(open_steps):
            raise ManifestError("CNO/open relation has no shared applicable source step")
        if (link, path) in seen_relations:
            raise ManifestError("duplicate CNO/open relation")
        seen_relations.add((link, path))
        relations.append(dict(row))

    sidecar = {
        "net_status": "declared" if mapped else "provisional_extracted_ids_unconfigured",
        "extracted_electrode_to_circuit_net": net_map if mapped else {},
        "pair_inventory": inventory,
        "open_path_status": "configured"
        if opens
        else "unsupported_unconfigured_no_explicit_terminals",
        "open_path_circuit_metadata": open_details,
        "cno_open_relations": relations,
        "auto_open": "disabled",
    }
    return included, excluded, opens, sidecar


def mask_diagnostics(source: Path, meta: dict, settings: dict | None) -> dict:
    """Record TR conservation and raw overlap as geometry observations only."""
    layers = {row["id"]: row for row in meta["layers"]}
    physical = meta.get("physical_stack", list(layers))
    shape = tuple(meta["unit_shape_px"])
    tr = _mask(source / meta["tr_union_path"])[: shape[0], : shape[1]]
    raw, cut, summaries = {}, {}, []
    for layer in physical:
        raw[layer] = _mask(source / layers[layer]["raw_path"])
        cut[layer] = _mask(source / layers[layer]["cut_path"])
        consistent = np.array_equal(cut[layer], raw[layer] & ~tr)
        if not consistent:
            raise ManifestError(f"{layer}: all-layer TR cut diagnostic failed")
        summaries.append(
            {
                "layer": layer,
                "raw_pixels_per_unit": int(raw[layer].sum()),
                "cut_pixels_per_unit": int(cut[layer].sum()),
                "tr_removed_pixels_per_unit": int((raw[layer] & tr).sum()),
            }
        )
    conductors = meta["stack"]
    overlaps = [
        {
            "layer_a": a,
            "layer_b": b,
            "raw_overlap_pixels_per_unit": int((raw[a] & raw[b]).sum()),
            "interpretation": "geometry_observation_only_not_a_process_short",
        }
        for a, b in combinations(conductors, 2)
        if np.any(raw[a] & raw[b])
    ]
    metal_over_tr = []
    for layer in conductors:
        if layers[layer].get("role") != "METAL":
            continue
        labels, count = ndimage.label(raw[layer])
        for component in range(1, count + 1):
            pixels = labels == component
            overlap = pixels & tr
            if not np.any(overlap):
                continue
            y, x = np.argwhere(overlap)[0]
            metal_over_tr.append(
                {
                    "code": "metal_over_tr",
                    "layer": layer,
                    "raw_component": component,
                    "overlap_seed_xy": [int(x), int(y)],
                    "raw_pixels": int(pixels.sum()),
                    "tr_overlap_pixels": int(overlap.sum()),
                    "policy": "allow_geometry_observation_only",
                }
            )
    stages = []
    stack_order = (
        {row["id"]: index for index, row in enumerate(settings["process_stack"])}
        if settings
        else {}
    )
    for stage in settings["source_stages"] if settings else []:
        layer = stage["after_layer"]
        prior_overlap = [
            {
                "conductor_layer": conductor,
                "raw_overlap_pixels_per_unit": int((raw[layer] & raw[conductor]).sum()),
            }
            for conductor in conductors
            if stack_order[conductor] < stack_order[layer] and np.any(raw[layer] & raw[conductor])
        ]
        stages.append(
            {
                "step_id": stage["step_id"],
                "after_layer": layer,
                "raw_mask_pixels_per_unit": int(raw[layer].sum()),
                "cut_mask_pixels_per_unit": int(cut[layer].sum()),
                "semantics": stage["semantics"],
                "prior_conductor_raw_overlaps": prior_overlap,
            }
        )
    return {
        "all_layer_tr_cut": summaries,
        "raw_conductor_overlaps": overlaps,
        "metal_over_tr": metal_over_tr,
        "source_stage_mask_diagnostics": stages,
        "raw_overlap_interpretation": "observation_only; no process short inferred",
    }
