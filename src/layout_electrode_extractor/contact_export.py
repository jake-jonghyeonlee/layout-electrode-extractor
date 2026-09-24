"""Preflight physical holes and prepare endpoint-pair contact masks."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .schema import ManifestError

_FOUR = ndimage.generate_binary_structure(2, 1)
_EIGHT = ndimage.generate_binary_structure(2, 2)
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+\Z")


def _mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        mask = np.asarray(image.convert("L")) > 0
    if mask.shape != shape:
        raise ManifestError(f"mask shape mismatch: {path}")
    return mask


def _check_four_partition(mask: np.ndarray, layer: str, connectivity: int) -> None:
    """An extracted 8-connected hole cannot contain multiple physical 4-holes."""
    if connectivity != 8:
        return
    four, _ = ndimage.label(mask, _FOUR)
    eight, count = ndimage.label(mask, _EIGHT)
    for component in range(1, count + 1):
        if len(set(four[eight == component].tolist())) != 1:
            raise ManifestError(f"{layer}: 8-connectivity merges distinct 4-connected holes")


def prepare_contacts(
    source: Path, meta: dict, contacts: list[dict], *, mixed: bool
) -> tuple[list[dict], dict[str, np.ndarray], list[dict]]:
    """Return contact rows/masks/provenance only after complete geometry validation."""
    unit_shape = tuple(meta["unit_shape_px"])
    output_shape = tuple(meta["output_shape_px"])
    if output_shape != tuple(2 * value for value in unit_shape):
        raise ManifestError("contact export requires a 2x2 extraction")
    tr = _mask(source / meta["tr_union_path"], output_shape)
    unit_tr = tr[: unit_shape[0], : unit_shape[1]]
    if not np.array_equal(tr, np.tile(unit_tr, (2, 2))):
        raise ManifestError("TR union is not a 2x2 tile")
    layers = {row["id"]: row for row in meta["layers"]}
    physical_layers = meta.get("physical_stack", list(layers))
    raw = {}
    cut = {}
    for layer in physical_layers:
        raw[layer] = _mask(source / layers[layer]["raw_path"], unit_shape)
        cut[layer] = _mask(source / layers[layer]["cut_path"], unit_shape)
    for hole in {row["layer"] for row in contacts}:
        if np.any(raw[hole] & unit_tr):
            raise ManifestError(f"{hole}: partial or complete TR cut of a physical hole")
        if (
            np.any(raw[hole][0])
            or np.any(raw[hole][-1])
            or np.any(raw[hole][:, 0])
            or np.any(raw[hole][:, -1])
        ):
            raise ManifestError(f"{hole}: physical hole touches unit edge")
    for layer in physical_layers:
        if not np.array_equal(cut[layer], raw[layer] & ~unit_tr):
            raise ManifestError(f"{layer}: cut mask does not equal raw minus TR")

    endpoint_layers = {name for row in contacts for name in (row["lower"], row["upper"])}
    electrode_index = {}
    electrode_ids = {}
    for layer in endpoint_layers:
        index = np.zeros(output_shape, dtype=np.int32)
        ids = [row["id"] for row in meta["electrodes"] if layer in row["layers"]]
        for row in meta["electrodes"]:
            if layer not in row["layers"]:
                continue
            pixels = _mask(source / row["layers"][layer]["path"], output_shape)
            if np.any(pixels & (index != 0)) or np.any(pixels & ~np.tile(cut[layer], (2, 2))):
                raise ManifestError(f"{layer}: electrode masks overlap or exceed cut layer")
            index[pixels] = ids.index(row["id"]) + 1
        if not np.array_equal(index > 0, np.tile(cut[layer], (2, 2))):
            raise ManifestError(f"{layer}: electrode partition does not cover cut layer")
        electrode_index[layer] = index
        electrode_ids[layer] = ids

    raw_rows = defaultdict(dict)
    cut_rows = defaultdict(dict)
    for row in meta["contact_holes"]["raw_components"]:
        key = row["raw_component"]
        if key in raw_rows[row["layer"]]:
            raise ManifestError(f"{row['layer']}: duplicate raw hole provenance")
        raw_rows[row["layer"]][key] = row
    for row in meta["contact_holes"]["components"]:
        key = row["cut_component"]
        if key in cut_rows[row["layer"]]:
            raise ManifestError(f"{row['layer']}: duplicate cut hole provenance")
        cut_rows[row["layer"]][key] = row
    rules = {layer: set() for layer in {row["layer"] for row in contacts}}
    for row in contacts:
        rules[row["layer"]].add((row["lower"], row["upper"]))
    if set(raw_rows) != set(rules) or set(cut_rows) != set(rules):
        raise ManifestError("contact provenance has missing or unknown hole layers")
    graph_edges = {
        frozenset((tuple(edge["from"]), tuple(edge["to"])))
        for edge in json.loads((source / "connectivity.json").read_text())["edges"]
        if edge["displacement"] == [0, 0]
    }
    grouped_masks = {}
    provenance = []
    for hole in sorted(rules):
        _check_four_partition(raw[hole], hole, meta["connectivity"])
        _check_four_partition(cut[hole], hole, meta["connectivity"])
        labels, count = ndimage.label(raw[hole], _FOUR)
        cut_labels, cut_count = ndimage.label(cut[hole], _FOUR)
        if count == 0:
            raise ManifestError(f"{hole}: empty physical hole layer")
        if set(raw_rows[hole]) != set(range(1, count + 1)):
            raise ManifestError(
                f"{hole}: missing/extra raw hole provenance or 4-connectivity differs"
            )
        if set(cut_rows[hole]) != set(range(1, cut_count + 1)):
            raise ManifestError(
                f"{hole}: missing/extra cut hole provenance or 4-connectivity differs"
            )
        if count != cut_count:
            raise ManifestError(f"{hole}: raw hole vanished or split by TR")
        if not np.array_equal(raw[hole], cut[hole]):
            raise ManifestError(f"{hole}: raw/cut physical holes differ")
        for component in range(1, count + 1):
            raw_row = raw_rows[hole][component]
            cut_row = cut_rows[hole][component]
            pair = (raw_row["lower"], raw_row["upper"])
            if (
                pair not in rules[hole]
                or cut_row["raw_component"] != component
                or (cut_row["lower"], cut_row["upper"]) != pair
            ):
                raise ManifestError(f"{hole}: wrong or inconsistent hole endpoints")
            if raw_row["contact_rule_index"] != cut_row["contact_rule_index"]:
                raise ManifestError(f"{hole}: raw/cut rule mismatch")
            rule_index = raw_row["contact_rule_index"]
            if (
                type(rule_index) is not int
                or not 0 <= rule_index < len(contacts)
                or (
                    contacts[rule_index]["layer"],
                    contacts[rule_index]["lower"],
                    contacts[rule_index]["upper"],
                )
                != (hole, *pair)
            ):
                raise ManifestError(f"{hole}: hole provenance does not match its declared rule")
            for endpoint in pair:
                if frozenset(((hole, component), (endpoint, component))) in graph_edges:
                    continue  # Component IDs across layers need not coincide; checked below.
                if not any(
                    (hole, component) in edge and any(node[0] == endpoint for node in edge)
                    for edge in graph_edges
                ):
                    raise ManifestError(
                        f"{hole} component {component}: missing graph edge to {endpoint}"
                    )
            ys, xs = np.nonzero(labels == component)
            for ty in range(2):
                for tx in range(2):
                    yy = ys + ty * unit_shape[0]
                    xx = xs + tx * unit_shape[1]
                    lower, upper = pair
                    lower_hits = set(electrode_index[lower][yy, xx].tolist()) - {0}
                    upper_hits = set(electrode_index[upper][yy, xx].tolist()) - {0}
                    if len(lower_hits) != 1 or len(upper_hits) != 1:
                        raise ManifestError(
                            f"{hole} component {component}: wrong endpoint electrode count"
                        )
                    lower_id = electrode_ids[lower][next(iter(lower_hits)) - 1]
                    upper_id = electrode_ids[upper][next(iter(upper_hits)) - 1]
                    if lower_id != upper_id:
                        raise ManifestError(
                            f"{hole} component {component}: endpoints have different extracted nets"
                        )
                    effective = (electrode_index[lower][yy, xx] > 0) & (
                        electrode_index[upper][yy, xx] > 0
                    )
                    if not np.any(effective):
                        raise ManifestError(
                            f"{hole} component {component}: empty effective contact"
                        )
                    contact_id = hole if not mixed else f"{hole}_{lower}_{upper}"
                    if (
                        not _SAFE_ID.fullmatch(contact_id)
                        or "__" in contact_id
                        or ":" in contact_id
                    ):
                        raise ManifestError(f"unsafe generated contact_id {contact_id}")
                    key = (hole, lower, upper)
                    grouped_masks.setdefault(key, np.zeros(output_shape, dtype=bool))[yy, xx] = True
                    provenance.append(
                        {
                            "hole_layer": hole,
                            "raw_component": component,
                            "cut_component": component,
                            "contact_rule_index": raw_row["contact_rule_index"],
                            "seed": raw_row["seed"],
                            "tile_xy": [tx, ty],
                            "contact_id": contact_id,
                            "lower_layer": lower,
                            "upper_layer": upper,
                            "lower_electrode": f"{lower_id}_{lower}",
                            "upper_electrode": f"{upper_id}_{upper}",
                            "raw_pixels": int(np.count_nonzero(labels == component)),
                            "cut_pixels": int(np.count_nonzero(cut_labels == component)),
                            "effective_pixels": int(np.count_nonzero(effective)),
                        }
                    )
    rows = []
    masks = {}
    for (hole, lower, upper), pixels in grouped_masks.items():
        contact_id = hole if not mixed else f"{hole}_{lower}_{upper}"
        path = f"masks/contact_{contact_id}_tr_cut.png"
        rows.append(
            {
                "contact_id": contact_id,
                "path": path,
                "hole_layer": hole,
                "lower_layer": lower,
                "upper_layer": upper,
            }
        )
        masks[path] = pixels
    for hole in rules:
        union = np.zeros(output_shape, dtype=bool)
        for row in rows:
            if row["hole_layer"] != hole:
                continue
            pixels = masks[row["path"]]
            if np.any(union & pixels):
                raise ManifestError(f"{hole}: overlapping endpoint-pair masks")
            union |= pixels
        if not np.array_equal(union, np.tile(cut[hole], (2, 2))):
            raise ManifestError(f"{hole}: endpoint-pair masks do not partition physical hole layer")
    return rows, masks, provenance
