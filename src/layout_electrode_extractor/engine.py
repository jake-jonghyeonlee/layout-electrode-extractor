"""Manifest-driven, pixel-exact extraction and 2×2 export."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .periodic import PeriodicGraph, ResourceError, label_mask
from .schema import Manifest, ManifestError, load_manifest

MAX_UNIT_PIXELS = 2_000_000
MAX_INPUT_PIXELS = 20_000_000
MAX_OUTPUT_BYTES = 1_000_000_000


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save_mask(path: Path, mask: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.where(mask, 255, 0).astype(np.uint8)
    Image.fromarray(values, mode="L").save(path)
    return _digest(values.tobytes())


def _load_masks(manifest: Manifest) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    masks: dict[str, np.ndarray] = {}
    hashes = {}
    shape = None
    for layer in manifest.layers:
        with Image.open(layer.path) as img:
            if img.format != "PNG" or img.mode not in {"L", "1"}:
                raise ManifestError(f"{layer.id}: mask must be single-channel grayscale/binary PNG")
            width, height = img.size
            if width < 2 or height < 2 or width * height > MAX_UNIT_PIXELS:
                raise ResourceError(
                    f"unit dimensions must be >=2 and at most {MAX_UNIT_PIXELS} pixels"
                )
            values = np.asarray(img.convert("L"))
        if values.ndim != 2 or not np.all((values == 0) | (values == 255)):
            raise ManifestError(f"{layer.id}: pixels must be exactly 0 or 255")
        if shape is None:
            shape = values.shape
            h, w = shape
            if h * w * len(manifest.layers) > MAX_INPUT_PIXELS:
                raise ResourceError(f"input exceeds {MAX_INPUT_PIXELS} layer-pixels")
        elif values.shape != shape:
            raise ManifestError(f"{layer.id}: shape {values.shape} does not match {shape}")
        masks[layer.id] = values != 0
        hashes[layer.id] = _digest(values.tobytes())
    return masks, hashes


def _make_graph(
    labels: dict[str, np.ndarray],
    counts: dict[str, int],
    connectivity: int,
    contacts: tuple = (),
    resolved: dict[str, dict[int, int]] | None = None,
) -> PeriodicGraph:
    graph = PeriodicGraph()
    for layer, count in counts.items():
        graph.add_nodes(layer, count)
        graph.add_periodic_boundaries(layer, labels[layer], connectivity)
    for rule_index, contact in enumerate(contacts):
        hole = labels[contact.layer]
        for endpoint in (contact.lower, contact.upper):
            pairs = np.stack((hole.ravel(), labels[endpoint].ravel()), axis=1)
            pairs = np.unique(pairs[(pairs[:, 0] > 0) & (pairs[:, 1] > 0)], axis=0)
            for hole_id, endpoint_id in pairs:
                if resolved is not None and resolved[contact.layer][int(hole_id)] != rule_index:
                    continue
                graph.add_edge(
                    graph.lookup[contact.layer, int(hole_id)],
                    graph.lookup[endpoint, int(endpoint_id)],
                )
    graph.solve()
    return graph


def _resolve_contacts(
    manifest: Manifest,
    raw: dict[str, np.ndarray],
    cut_labels: dict[str, np.ndarray],
) -> tuple[dict[str, dict[int, int]], list[dict], list[dict]]:
    """Bind each cut hole component to the unique seed of its raw component."""
    resolved: dict[str, dict[int, int]] = {}
    provenance = []
    raw_provenance = []
    for layer in sorted({rule.layer for rule in manifest.contacts}):
        raw_labels, raw_count = label_mask(raw[layer], manifest.connectivity)
        raw_graph = _make_graph({layer: raw_labels}, {layer: raw_count}, manifest.connectivity)
        rules = [(i, rule) for i, rule in enumerate(manifest.contacts) if rule.layer == layer]
        assigned: dict[int, tuple[int, tuple[int, int] | None]] = {}
        if len(rules) == 1 and rules[0][1].holes is None:
            assigned = {component: (rules[0][0], None) for component in range(1, raw_count + 1)}
        else:
            height, width = raw_labels.shape
            for index, rule in rules:
                if rule.holes is None:
                    raise ManifestError(f"{layer}: mixed legacy and seeded contact rules")
                for x, y in rule.holes:
                    if x >= width or y >= height or not raw_labels[y, x]:
                        raise ManifestError(f"{layer}: hole seed [{x},{y}] is outside a raw hole")
                    component = int(raw_labels[y, x])
                    if component in assigned:
                        raise ManifestError(
                            f"{layer}: duplicate or ambiguous hole assignment for raw component "
                            f"{component}"
                        )
                    assigned[component] = (index, (x, y))
            missing = set(range(1, raw_count + 1)) - assigned.keys()
            if missing:
                raise ManifestError(f"{layer}: unassigned raw hole components {sorted(missing)}")
        # A seam can join distinct local raw components; it cannot change their endpoints.
        periodic_pair: dict[int, tuple[str, str]] = {}
        for component, (index, seed) in assigned.items():
            graph_component = raw_graph.component[raw_graph.lookup[layer, component]]
            rule = manifest.contacts[index]
            pair = (rule.lower, rule.upper)
            if graph_component in periodic_pair and periodic_pair[graph_component] != pair:
                raise ManifestError(
                    f"{layer}: conflicting endpoint pairs in one periodic hole component"
                )
            periodic_pair[graph_component] = pair
            raw_provenance.append({
                "layer": layer,
                "raw_component": component,
                "contact_rule_index": index,
                "seed": list(seed) if seed is not None else None,
                "lower": rule.lower,
                "upper": rule.upper,
            })
        per_cut = {}
        cut_representatives = {}
        for y, x in np.argwhere(cut_labels[layer] > 0):
            cut_representatives.setdefault(int(cut_labels[layer][y, x]), (y, x))
        for cut_id, (y, x) in cut_representatives.items():
            raw_component = int(raw_labels[y, x])
            index, seed = assigned[raw_component]
            per_cut[cut_id] = index
            rule = manifest.contacts[index]
            provenance.append({
                "layer": layer,
                "cut_component": cut_id,
                "raw_component": raw_component,
                "contact_rule_index": index,
                "seed": list(seed) if seed is not None else None,
                "lower": rule.lower,
                "upper": rule.upper,
            })
        resolved[layer] = per_cut
    return (
        resolved,
        sorted(provenance, key=lambda row: (row["layer"], row["cut_component"])),
        sorted(raw_provenance, key=lambda row: (row["layer"], row["raw_component"])),
    )


def _states(graph: PeriodicGraph) -> dict[tuple, list[tuple[str, int, int, int]]]:
    groups: dict[tuple, list[tuple[str, int, int, int]]] = defaultdict(list)
    for node, (layer, local) in enumerate(graph.names):
        for ty in range(2):
            for tx in range(2):
                groups[graph.key(node, tx, ty)].append((layer, local, tx, ty))
    return groups


def _render(
    members: list[tuple[str, int, int, int]], labels: dict[str, np.ndarray], shape: tuple[int, int]
) -> dict[str, np.ndarray]:
    h, w = shape
    output = {}
    for layer, local, tx, ty in members:
        if layer not in output:
            output[layer] = np.zeros((2 * h, 2 * w), dtype=bool)
        region = output[layer][ty * h : (ty + 1) * h, tx * w : (tx + 1) * w]
        region |= labels[layer] == local
    return {layer: mask for layer, mask in output.items() if np.any(mask)}


def _contact_issues(
    manifest: Manifest,
    labels: dict[str, np.ndarray],
    hole_graph: PeriodicGraph,
    conductor_graph: PeriodicGraph,
    resolved: dict[str, dict[int, int]],
) -> tuple[list[dict], list[dict]]:
    """Diagnose each 2×2 hole instance using unbridged conductor identities.

    Infinite hole buses are reported as unsupported adapter topology. Finite hole
    components are followed beyond the output window before counting endpoints.
    """
    issues = []
    instances = []
    groups = _states(hole_graph)
    seen = set()
    component_rules: dict[int, set[int]] = defaultdict(set)
    for node, (layer, local) in enumerate(hole_graph.names):
        component_rules[hole_graph.component[node]].add(resolved[layer][local])
    for key, visible in groups.items():
        layer = visible[0][0]
        rule_indices = component_rules[key[0]]
        pairs = {
            (manifest.contacts[index].lower, manifest.contacts[index].upper)
            for index in rule_indices
        }
        if len(pairs) != 1:
            raise ManifestError(f"{layer}: conflicting endpoint pairs in one periodic cut hole")
        rule_index = min(rule_indices)
        contact = manifest.contacts[rule_index]
        provenance = {
            "layer": layer,
            "instance": repr(key),
            "contact_rule_indices": sorted(rule_indices),
            "lower": contact.lower,
            "upper": contact.upper,
            "members": [
                {
                    "cut_component": local,
                    "tile": [tx, ty],
                    "contact_rule_index": resolved[layer][local],
                }
                for _, local, tx, ty in visible
            ],
        }
        instances.append(provenance)
        lattice = hole_graph.lattices[key[0]]
        signature = (layer, key)
        if signature in seen:
            continue
        seen.add(signature)
        if lattice.rank:
            issues.append(
                {
                    "type": "periodic_contact_network",
                    "layer": layer,
                    "instance": repr(key),
                    "rank": lattice.rank,
                    "contact_rule_indices": sorted(rule_indices),
                    "lower": contact.lower,
                    "upper": contact.upper,
                }
            )
            continue
        anchor_layer, anchor_local, anchor_tx, anchor_ty = visible[0]
        anchor_node = hole_graph.lookup[anchor_layer, anchor_local]
        px, py = hole_graph.potential[anchor_node]
        root_x, root_y = anchor_tx - px, anchor_ty - py
        endpoint_sets = {contact.lower: set(), contact.upper: set()}
        for node, (other_layer, local) in enumerate(hole_graph.names):
            if other_layer != layer or hole_graph.component[node] != key[0]:
                continue
            ox, oy = hole_graph.potential[node]
            tx, ty = root_x + ox, root_y + oy
            hole_mask = labels[layer] == local
            for endpoint in endpoint_sets:
                touched = np.unique(labels[endpoint][hole_mask])
                for endpoint_id in touched:
                    if endpoint_id:
                        enode = conductor_graph.lookup[endpoint, int(endpoint_id)]
                        endpoint_sets[endpoint].add(conductor_graph.key(enode, tx, ty))
        counts = {endpoint: len(identities) for endpoint, identities in endpoint_sets.items()}
        if any(count != 1 for count in counts.values()):
            issue_type = (
                "multi_endpoint_contact"
                if any(count > 1 for count in counts.values())
                else "missing_endpoint_contact"
            )
            issues.append(
                {
                    "type": issue_type,
                    "layer": layer,
                    "instance": repr(key),
                    "endpoint_counts": counts,
                    "contact_rule_indices": sorted(rule_indices),
                    "lower": contact.lower,
                    "upper": contact.upper,
                }
            )
    return issues, instances


def _write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tr_terminals(
    members: list[tuple[str, int, int, int]],
    pair_labels: np.ndarray,
    source_layers: tuple[str, str],
    cut_labels: dict[str, np.ndarray],
    graph: PeriodicGraph,
    electrode_ids: dict[tuple, str],
    connectivity: int,
    objects: list[tuple[slice, slice] | None],
) -> list[dict]:
    """Keep direct, pre-cut source-pair evidence beside each TR candidate."""
    h, w = pair_labels.shape
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if connectivity == 8:
        directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    touched: dict[tuple[str, tuple], int] = defaultdict(int)
    for _, local, tx, ty in members:
        box = objects[local - 1]
        if box is None:
            continue
        for local_y, local_x in np.argwhere(pair_labels[box] == local):
            y, x = int(local_y) + box[0].start, int(local_x) + box[1].start
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                ntx, nty = tx + nx // w, ty + ny // h
                for layer in source_layers:
                    component = int(cut_labels[layer][ny % h, nx % w])
                    if component:
                        node = graph.lookup[layer, component]
                        touched[layer, graph.key(node, ntx, nty)] += 1
    return [
        {
            "layer": layer,
            "electrode_id": electrode_ids.get(key),
            "graph_component": key[0],
            "coset": list(key[1]),
            "adjacent_pixel_edges": count,
        }
        for (layer, key), count in sorted(touched.items())
    ]


def extract(manifest_path: str | Path, output_dir: str | Path) -> dict:
    """Validate inputs and write a deterministic 2×2 extraction directory.

    Fails before replacing an existing output. Returned metadata is also saved as
    ``manifest.json``. IDs are extraction IDs, never user-facing names.
    """
    manifest = load_manifest(manifest_path)
    raw, raw_hashes = _load_masks(manifest)
    h, w = next(iter(raw.values())).shape
    output = Path(output_dir).resolve()
    if output.exists():
        raise ManifestError(f"output already exists: {output}")
    if output.is_relative_to(manifest.path.parent) and any(
        output == layer.path or output in layer.path.parents for layer in manifest.layers
    ):
        raise ManifestError("output would contain an input mask")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        metadata = _extract_into(manifest, raw, raw_hashes, temp, (h, w))
        os.replace(temp, output)
        return metadata
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _extract_into(
    manifest: Manifest,
    raw: dict[str, np.ndarray],
    raw_hashes: dict[str, str],
    output: Path,
    shape: tuple[int, int],
) -> dict:
    h, w = shape
    tr_union = np.zeros(shape, dtype=bool)
    tr_items = []
    tr_graphs = []
    for pair_index, (gat, channel) in enumerate(manifest.tr_pairs):
        overlap = raw[gat] & raw[channel]
        if np.any(overlap & tr_union):
            raise ManifestError("TR source pairs overlap at the same pixel")
        tr_union |= overlap
        name = f"PAIR{pair_index + 1:03d}"
        labels, count = label_mask(overlap, manifest.connectivity)
        graph = _make_graph({name: labels}, {name: count}, manifest.connectivity)
        tr_graphs.append((name, gat, channel, labels, graph, ndimage.find_objects(labels)))
    cut = {layer.id: raw[layer.id] & ~tr_union for layer in manifest.layers}
    conductors = {
        layer.id
        for layer in manifest.layers
        if layer.role in {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}
    }
    holes = {layer.id for layer in manifest.layers if layer.role in {"CNT", "VIA"}}
    graph_layers = {
        layer.id: cut[layer.id] for layer in manifest.layers if layer.id in conductors | holes
    }
    labels = {}
    counts = {}
    for layer, mask in graph_layers.items():
        labels[layer], counts[layer] = label_mask(mask, manifest.connectivity)
    resolved, hole_components, raw_holes = _resolve_contacts(manifest, raw, labels)
    graph = _make_graph(labels, counts, manifest.connectivity, manifest.contacts, resolved)
    conductor_graph = _make_graph(
        {k: v for k, v in labels.items() if k in conductors},
        {k: v for k, v in counts.items() if k in conductors},
        manifest.connectivity,
    )
    hole_graph = _make_graph(
        {k: v for k, v in labels.items() if k in holes},
        {k: v for k, v in counts.items() if k in holes},
        manifest.connectivity,
    )
    issues, hole_instances = _contact_issues(
        manifest, labels, hole_graph, conductor_graph, resolved
    )
    for layer in manifest.layers:
        _save_mask(output / "raw_layers" / f"{layer.id}.png", raw[layer.id])
        _save_mask(output / "cut_layers" / f"{layer.id}.png", cut[layer.id])
    _save_mask(output / "tr_union.png", np.tile(tr_union, (2, 2)))
    groups = _states(graph)
    electrode_items = []
    electrode_ids = {key: f"E{index:05d}" for index, key in enumerate(sorted(groups), start=1)}
    projected_bytes = 0
    for key in sorted(groups):
        members = groups[key]
        image_layers = _render(members, labels, shape)
        if not any(layer in conductors for layer in image_layers):
            issues.append({"type": "orphan_contact", "instance": repr(key)})
        electrode_id = electrode_ids[key]
        image_info = {}
        for layer, mask in image_layers.items():
            projected_bytes += mask.size
            if projected_bytes > MAX_OUTPUT_BYTES:
                raise ResourceError(f"output masks exceed {MAX_OUTPUT_BYTES} decoded bytes")
            image_info[layer] = {
                "path": f"electrodes/{electrode_id}/{layer}.png",
                "pixels": int(np.count_nonzero(mask)),
                "sha256_pixels": _save_mask(
                    output / "electrodes" / electrode_id / f"{layer}.png", mask
                ),
            }
        electrode_items.append(
            {
                "id": electrode_id,
                "layers": image_info,
                "graph_component": key[0],
                "coset": list(key[1]),
            }
        )
    tr_index = 0
    for name, gat, channel, pair_labels, tr_graph, objects in tr_graphs:
        for key, members in sorted(_states(tr_graph).items()):
            masks = _render(members, {name: pair_labels}, shape)
            if not masks:
                continue
            tr_index += 1
            tr_id = f"TR{tr_index:05d}"
            mask = masks[name]
            projected_bytes += mask.size
            if projected_bytes > MAX_OUTPUT_BYTES:
                raise ResourceError(f"output masks exceed {MAX_OUTPUT_BYTES} decoded bytes")
            path = f"tr/{tr_id}/mask.png"
            sha = _save_mask(output / path, mask)
            item = {
                "id": tr_id,
                "source_pair": {"gat": gat, "channel": channel},
                "path": path,
                "pixels": int(np.count_nonzero(mask)),
                "sha256_pixels": sha,
                "graph_component": key[0],
                "coset": list(key[1]),
                "terminal_adjacency": _tr_terminals(
                    members,
                    pair_labels,
                    (gat, channel),
                    labels,
                    graph,
                    electrode_ids,
                    manifest.connectivity,
                    objects,
                ),
            }
            _write_json(output / "tr" / tr_id / "metadata.json", item)
            tr_items.append(item)
    metadata = {
        "schema_version": 1,
        "algorithm": "exact_z2_lift",
        "source_manifest_sha256": _digest(manifest.path.read_bytes()),
        "unit_shape_px": [h, w],
        "output_shape_px": [2 * h, 2 * w],
        "pixel_size_um": manifest.pixel_size_um,
        "origin_um": list(manifest.origin_um),
        "unit_size_um": [w * manifest.pixel_size_um, h * manifest.pixel_size_um],
        "output_size_um": [2 * w * manifest.pixel_size_um, 2 * h * manifest.pixel_size_um],
        "connectivity": manifest.connectivity,
        "layers": [
            {
                "id": layer.id,
                "role": layer.role,
                "source_path": str(layer.path.relative_to(manifest.path.parent)),
                "raw_path": f"raw_layers/{layer.id}.png",
                "cut_path": f"cut_layers/{layer.id}.png",
                "raw_sha256_pixels": raw_hashes[layer.id],
                "raw_pixels": int(raw[layer.id].sum()),
                "cut_pixels": int(cut[layer.id].sum()),
            }
            for layer in manifest.layers
        ],
        "stack": list(manifest.stack),
        "contact_rules": [
            {"layer": c.layer, "lower": c.lower, "upper": c.upper, **(
                {"holes": [list(seed) for seed in c.holes]} if c.holes is not None else {}
            )}
            for c in manifest.contacts
        ],
        "contact_holes": {
            "raw_components": raw_holes,
            "components": hole_components,
            "instances": hole_instances,
        },
        "tr_pairs": [{"gat": gat, "channel": channel} for gat, channel in manifest.tr_pairs],
        "tr_union_path": "tr_union.png",
        "tr_union_pixels_unit": int(tr_union.sum()),
        "electrodes": electrode_items,
        "tr": tr_items,
        "issues": issues,
        "naming_complete": False,
    }
    _write_json(output / "manifest.json", metadata)
    _write_json(output / "connectivity.json", graph.describe())
    _write_json(output / "review" / "issues.json", issues)
    return metadata
