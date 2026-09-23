import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from layout_electrode_extractor import ManifestError, extract
from layout_electrode_extractor.periodic import Lattice, PeriodicGraph
from layout_electrode_extractor.review import ReviewProject


def fixture(tmp_path: Path, masks, *, connectivity=4, contacts=(), pairs=None):
    if pairs is None:
        pairs = [{"gat": "GAT", "channel": "ACTIVE"}]
    layers = []
    for name, (role, values) in masks.items():
        Image.fromarray(values.astype(np.uint8), mode="L").save(tmp_path / f"{name}.png")
        layers.append({"id": name, "path": f"{name}.png", "role": role})
    stack = [
        row["id"]
        for row in layers
        if row["role"] in {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}
    ]
    manifest = {
        "schema_version": 1,
        "pixel_size_um": 0.1,
        "origin_um": [2.5, -1.0],
        "connectivity": connectivity,
        "layers": layers,
        "stack": stack,
        "tr_pairs": pairs,
        "contacts": list(contacts),
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def base_masks(shape=(5, 5)):
    gat = np.zeros(shape, dtype=np.uint8)
    active = np.zeros(shape, dtype=np.uint8)
    gat[1, 1] = active[1, 1] = 255
    return {"GAT": ("GAT", gat), "ACTIVE": ("ACTIVE", active)}


def test_physical_stack_provenance_and_legacy_behavior(tmp_path):
    masks = base_masks()
    for name, role in (("METAL", "METAL"), ("CNT", "CNT"), ("VIA", "VIA"), ("OTHER", "OTHER")):
        masks[name] = role, np.zeros((5, 5), dtype=np.uint8)
    contacts = [{"layer": hole, "lower": "ACTIVE", "upper": "METAL"} for hole in ("CNT", "VIA")]
    path, source = fixture(tmp_path, masks, contacts=contacts)
    order = ["GAT", "ACTIVE", "CNT", "VIA", "METAL"]
    source["physical_stack"] = order
    path.write_text(json.dumps(source))
    output = tmp_path / "with-order"
    result = extract(path, output)
    assert result["stack"] == ["GAT", "ACTIVE", "METAL"]
    assert result["physical_stack"] == order
    assert json.loads((output / "manifest.json").read_text())["physical_stack"] == order
    reviewed = ReviewProject(output).export(tmp_path / "reviewed")
    assert json.loads((reviewed / "manifest.json").read_text())["physical_stack"] == order

    source.pop("physical_stack")
    path.write_text(json.dumps(source))
    legacy = extract(path, tmp_path / "legacy")
    assert "physical_stack" not in legacy
    assert legacy["stack"] == result["stack"]
    assert legacy["contact_rules"] == result["contact_rules"]
    legacy_reviewed = ReviewProject(tmp_path / "legacy").export(tmp_path / "legacy-reviewed")
    assert "physical_stack" not in json.loads((legacy_reviewed / "manifest.json").read_text())


@pytest.mark.parametrize(
    ("order", "message"),
    [
        (["GAT", "ACTIVE", "METAL"], "physical_stack"),
        (["GAT", "ACTIVE", "CNT", "CNT", "METAL"], "physical_stack"),
        (["GAT", "ACTIVE", "CNT", "MISSING", "METAL"], "physical_stack"),
        (["ACTIVE", "GAT", "CNT", "VIA", "METAL"], "conductor order"),
        (["GAT", "CNT", "ACTIVE", "VIA", "METAL"], "physical_stack order"),
        (["GAT", "ACTIVE", "METAL", "CNT", "VIA"], "physical_stack order"),
        (["GAT", "ACTIVE", "CNT", "VIA", "OTHER"], "physical_stack"),
        (None, "physical_stack"),
    ],
)
def test_invalid_physical_stack_fails_before_output(tmp_path, order, message):
    masks = base_masks()
    for name, role in (("METAL", "METAL"), ("CNT", "CNT"), ("VIA", "VIA"), ("OTHER", "OTHER")):
        masks[name] = role, np.zeros((5, 5), dtype=np.uint8)
    path, source = fixture(
        tmp_path,
        masks,
        contacts=[{"layer": hole, "lower": "ACTIVE", "upper": "METAL"} for hole in ("CNT", "VIA")],
    )
    source["physical_stack"] = order
    path.write_text(json.dumps(source))
    output = tmp_path / "out"
    with pytest.raises(ManifestError, match=message):
        extract(path, output)
    assert not output.exists()


def read(path):
    return np.asarray(Image.open(path)) != 0


def masks_for(meta, output, layer):
    return [
        read(output / item["layers"][layer]["path"])
        for item in meta["electrodes"]
        if layer in item["layers"]
    ]


def assert_partition(meta, output, layer):
    cut = np.tile(read(output / "cut_layers" / f"{layer}.png"), (2, 2))
    masks = masks_for(meta, output, layer)
    count = np.sum(masks, axis=0) if masks else np.zeros(cut.shape, dtype=int)
    np.testing.assert_array_equal(count, cut.astype(int))


def test_all_layer_cut_and_partition(tmp_path):
    masks = base_masks()
    for name, role in [("METAL", "METAL"), ("CNT", "CNT"), ("OTHER", "OTHER")]:
        image = np.zeros((5, 5), dtype=np.uint8)
        image[1, 1] = 255
        if name == "METAL":
            image[3, 3] = 255
        masks[name] = role, image
    path, _ = fixture(
        tmp_path, masks, contacts=[{"layer": "CNT", "lower": "ACTIVE", "upper": "METAL"}]
    )
    output = tmp_path / "out"
    meta = extract(path, output)
    assert meta["output_shape_px"] == [10, 10]
    assert meta["output_size_um"] == [1.0, 1.0]
    assert meta["origin_um"] == [2.5, -1.0]
    assert meta["tr_union_pixels_unit"] == 1
    for layer in masks:
        assert read(output / "raw_layers" / f"{layer}.png")[1, 1]
        assert not read(output / "cut_layers" / f"{layer}.png")[1, 1]
    for layer in ("GAT", "ACTIVE", "METAL", "CNT"):
        assert_partition(meta, output, layer)
    assert len(meta["tr"]) == 4
    assert len(masks_for(meta, output, "METAL")) == 4
    assert meta == extract(path, tmp_path / "out-again")


def test_independent_repeated_instances_and_infinite_bus(tmp_path):
    masks = base_masks()
    metal = np.zeros((5, 5), dtype=np.uint8)
    metal[3, 3] = 255
    masks["METAL"] = "METAL", metal
    path, _ = fixture(tmp_path, masks)
    meta = extract(path, tmp_path / "island")
    assert len(masks_for(meta, tmp_path / "island", "METAL")) == 4
    assert_partition(meta, tmp_path / "island", "METAL")
    metal[:] = 0
    metal[3, :] = 255
    path, _ = fixture(tmp_path, masks)
    meta = extract(path, tmp_path / "bus")
    bus_masks = masks_for(meta, tmp_path / "bus", "METAL")
    assert len(bus_masks) == 2
    assert sorted(int(mask.sum()) for mask in bus_masks) == [10, 10]
    assert_partition(meta, tmp_path / "bus", "METAL")


def test_boundary_contact_and_tr(tmp_path):
    masks = base_masks()
    for name in ("GAT", "ACTIVE"):
        masks[name][1][2, 0] = masks[name][1][2, 4] = 255
    metal = np.zeros((5, 5), dtype=np.uint8)
    contact = np.zeros((5, 5), dtype=np.uint8)
    for image in (metal, contact):
        image[3, 0] = image[3, 4] = 255
    masks["ACTIVE"][1][3, 0] = masks["ACTIVE"][1][3, 4] = 255
    masks["METAL"] = "METAL", metal
    masks["CNT"] = "CNT", contact
    path, _ = fixture(
        tmp_path, masks, contacts=[{"layer": "CNT", "lower": "ACTIVE", "upper": "METAL"}]
    )
    meta = extract(path, tmp_path / "out")
    assert any(
        read(tmp_path / "out" / item["path"])[2, 4] and read(tmp_path / "out" / item["path"])[2, 5]
        for item in meta["tr"]
    )
    contact_masks = masks_for(meta, tmp_path / "out", "CNT")
    assert any(mask[3, 4] and mask[3, 5] for mask in contact_masks)
    assert not any(
        item["type"] in {"missing_endpoint_contact", "multi_endpoint_contact"}
        for item in meta["issues"]
    )
    assert_partition(meta, tmp_path / "out", "ACTIVE")
    assert_partition(meta, tmp_path / "out", "CNT")


def test_diagonal_policy(tmp_path):
    masks = base_masks()
    metal = np.zeros((5, 5), dtype=np.uint8)
    metal[2, 2] = metal[3, 3] = 255
    masks["METAL"] = "METAL", metal
    path, _ = fixture(tmp_path, masks)
    four = extract(path, tmp_path / "four")
    path, _ = fixture(tmp_path, masks, connectivity=8)
    eight = extract(path, tmp_path / "eight")
    assert len(masks_for(four, tmp_path / "four", "METAL")) == 8
    assert len(masks_for(eight, tmp_path / "eight", "METAL")) == 4


def test_corner_boundary_diagonal_policy(tmp_path):
    masks = base_masks()
    metal = np.zeros((5, 5), dtype=np.uint8)
    metal[0, 0] = metal[4, 4] = 255
    masks["METAL"] = "METAL", metal
    path, _ = fixture(tmp_path, masks)
    four = extract(path, tmp_path / "four")
    path, _ = fixture(tmp_path, masks, connectivity=8)
    eight = extract(path, tmp_path / "eight")
    four_masks = masks_for(four, tmp_path / "four", "METAL")
    eight_masks = masks_for(eight, tmp_path / "eight", "METAL")
    assert not any(mask[4, 4] and mask[5, 5] for mask in four_masks)
    assert any(mask[4, 4] and mask[5, 5] for mask in eight_masks)


def test_diagonal_contact_policy(tmp_path):
    masks = base_masks()
    masks["ACTIVE"][1][2, 2] = 255
    metal = np.zeros((5, 5), dtype=np.uint8)
    metal[3, 3] = 255
    contact = np.zeros((5, 5), dtype=np.uint8)
    contact[2, 2] = contact[3, 3] = 255
    masks["METAL"] = "METAL", metal
    masks["CNT"] = "CNT", contact
    rule = [{"layer": "CNT", "lower": "ACTIVE", "upper": "METAL"}]
    path, _ = fixture(tmp_path, masks, contacts=rule)
    four = extract(path, tmp_path / "four")
    assert any(issue["type"] == "missing_endpoint_contact" for issue in four["issues"])
    path, _ = fixture(tmp_path, masks, connectivity=8, contacts=rule)
    eight = extract(path, tmp_path / "eight")
    assert not any(issue["type"] == "missing_endpoint_contact" for issue in eight["issues"])
    assert any(
        "ACTIVE" in item["layers"] and "METAL" in item["layers"] for item in eight["electrodes"]
    )


def test_tr_terminal_adjacency_keeps_split_gate_evidence(tmp_path):
    masks = base_masks()
    masks["GAT"][1][1, 0] = masks["GAT"][1][1, 2] = 255
    masks["ACTIVE"][1][0, 1] = masks["ACTIVE"][1][2, 1] = 255
    path, _ = fixture(tmp_path, masks)
    meta = extract(path, tmp_path / "out")
    central = next(item for item in meta["tr"] if read(tmp_path / "out" / item["path"])[1, 1])
    gate = [item for item in central["terminal_adjacency"] if item["layer"] == "GAT"]
    active = [item for item in central["terminal_adjacency"] if item["layer"] == "ACTIVE"]
    assert len(gate) == len(active) == 2
    assert all(item["electrode_id"] for item in gate + active)
    assert len({item["electrode_id"] for item in gate}) == 2


def test_multi_component_contact_is_diagnosed(tmp_path):
    masks = base_masks((7, 7))
    masks["ACTIVE"][1][3, 2] = masks["ACTIVE"][1][3, 4] = 255
    metal = np.zeros((7, 7), dtype=np.uint8)
    metal[3, 3] = 255
    contact = np.zeros((7, 7), dtype=np.uint8)
    contact[3, 2:5] = 255
    masks["METAL"] = "METAL", metal
    masks["CNT"] = "CNT", contact
    path, _ = fixture(
        tmp_path, masks, contacts=[{"layer": "CNT", "lower": "ACTIVE", "upper": "METAL"}]
    )
    meta = extract(path, tmp_path / "out")
    assert any(
        issue["type"] == "multi_endpoint_contact" and issue["endpoint_counts"]["ACTIVE"] == 2
        for issue in meta["issues"]
    )
    assert_partition(meta, tmp_path / "out", "ACTIVE")


def test_invalid_manifest_and_masks(tmp_path):
    masks = base_masks()
    path, manifest = fixture(tmp_path, masks)
    manifest["stack"] = ["GAT"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ManifestError, match="stack"):
        extract(path, tmp_path / "bad1")
    manifest["stack"] = ["GAT", "ACTIVE"]
    manifest["layers"][0]["path"] = "../escape.png"
    path.write_text(json.dumps(manifest))
    with pytest.raises((ManifestError, FileNotFoundError)):
        extract(path, tmp_path / "bad2")
    manifest["layers"][0]["path"] = "GAT.png"
    path.write_text(json.dumps(manifest))
    values = masks["GAT"][1].copy()
    values[2, 2] = 128
    Image.fromarray(values).save(tmp_path / "GAT.png")
    with pytest.raises(ManifestError, match="0 or 255"):
        extract(path, tmp_path / "bad3")
    assert not (tmp_path / "bad3").exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["tr_pairs"][0].update(gat=[]), "endpoints"),
        (lambda data: data["layers"][0].update(role=[]), "role"),
        (lambda data: data.update(connectivity=16), "connectivity"),
        (lambda data: data.update(schema_version=1.0), "schema_version"),
        (lambda data: data["layers"][0].update(id="../GAT"), "ASCII ID"),
    ],
)
def test_malformed_manifest_types_fail_cleanly(tmp_path, mutate, message):
    path, data = fixture(tmp_path, base_masks())
    mutate(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ManifestError, match=message):
        extract(path, tmp_path / "out")


def test_lattice_cosets_and_winding_graph():
    lattice = Lattice()
    for vector in ((4, 2), (2, 4), (6, 0)):
        lattice.add(vector)
    for a in range(-3, 4):
        for b in range(-3, 4):
            vector = (4 * a + 2 * b, 2 * a + 4 * b)
            assert lattice.key(vector) == lattice.key((0, 0))
    assert lattice.key((1, 0)) != lattice.key((0, 0))
    graph = PeriodicGraph()
    graph.add_nodes("M", 3)
    a, b, c = (graph.lookup["M", i] for i in (1, 2, 3))
    graph.add_edge(a, b, 1, 0)
    graph.add_edge(b, c, 0, 1)
    graph.add_edge(c, a, -1, 0)
    graph.solve()
    assert graph.key(a, 0, 0) == graph.key(c, 1, 1)
    assert graph.key(a, 0, 0) != graph.key(a, 1, 0)
    assert graph.lattices[0].rank == 1
