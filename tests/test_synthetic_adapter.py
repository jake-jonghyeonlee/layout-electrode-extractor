from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage

from layout_electrode_extractor import particle_sim_adapter
from layout_electrode_extractor.cli import main as cli_main
from layout_electrode_extractor.contact_export import (
    _check_four_partition,
    diagnose_physical_holes,
    prepare_contacts,
)
from layout_electrode_extractor.engine import extract
from layout_electrode_extractor.particle_sim_adapter import export_particle_sim
from layout_electrode_extractor.review import ReviewProject
from layout_electrode_extractor.schema import ManifestError
from layout_electrode_extractor.synthetic import (
    ACTIVE_GAT_METAL_BRIDGES,
    ACTIVE_METAL_LANDINGS,
    BRIDGE_ACTIVE_LANDINGS,
    BRIDGE_GAT_LANDINGS,
    GAT_METAL_LANDINGS,
    make_synthetic,
)


def _legacy_adapter_input(root: Path) -> Path:
    """Keep one-pair-per-physical-layer adapter regression coverage."""
    path = Path(make_synthetic(root)["manifest"])
    cnt_path = root / "masks" / "CNT1.png"
    cnt = np.asarray(Image.open(cnt_path)).copy()
    for x, y in BRIDGE_ACTIVE_LANDINGS + BRIDGE_GAT_LANDINGS + GAT_METAL_LANDINGS:
        cnt[y - 7 : y + 8, x - 7 : x + 8] = 0
    Image.fromarray(cnt).save(cnt_path)
    manifest = json.loads(path.read_text())
    manifest["contacts"] = [
        {"layer": "CNT1", "lower": "ACTIVE", "upper": "METAL1"},
        {"layer": "CNT2", "lower": "OACTIVE", "upper": "METAL1"},
    ]
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def test_legacy_contact_fixture_extract_and_particle_sim_export(tmp_path: Path) -> None:
    generated = _legacy_adapter_input(tmp_path / "input")
    source = generated.parent
    manifest = json.loads(generated.read_text())
    assert manifest["pixel_size_um"] == 0.1
    assert manifest["stack"] == ["ACTIVE", "GAT1", "GAT2", "OACTIVE", "GAT3", "METAL1"]
    assert manifest["physical_stack"] == [
        "ACTIVE",
        "GAT1",
        "GAT2",
        "OACTIVE",
        "GAT3",
        "CNT1",
        "CNT2",
        "METAL1",
    ]
    assert manifest["tr_pairs"] == [
        {"gat": "GAT1", "channel": "ACTIVE"},
        {"gat": "GAT2", "channel": "OACTIVE"},
        {"gat": "GAT3", "channel": "OACTIVE"},
    ]
    assert {row["id"] for row in manifest["layers"]} == {
        "GAT1",
        "GAT2",
        "GAT3",
        "ACTIVE",
        "OACTIVE",
        "CNT1",
        "CNT2",
        "METAL1",
    }
    with Image.open(source / "masks" / "GAT1.png") as image:
        assert image.size == (600, 600)

    extracted = tmp_path / "extracted"
    result = extract(generated, extracted)
    assert result["output_shape_px"] == [1200, 1200]
    assert result["pixel_size_um"] == 0.1
    assert len(result["tr"]) == 40
    assert result["issues"] == []
    assert result["physical_stack"] == manifest["physical_stack"]
    assert result["electrodes"]
    assert result["tr"]

    project = ReviewProject(extracted)
    annotations = project.state()["annotations"]
    first_electrode = result["electrodes"][0]["id"]
    first_tr = result["tr"][0]["id"]
    annotations["electrodes"][first_electrode] = {"name": "ANCHOR_E", "net": "NET_A"}
    annotations["tr"][first_tr] = {"name": "ANCHOR_TR", "device_id": ""}
    project.save_annotations(annotations, project.revision)
    reviewed = project.export(tmp_path / "reviewed")
    assert (
        json.loads((reviewed / "manifest.json").read_text())["physical_stack"]
        == manifest["physical_stack"]
    )

    adapted = tmp_path / "particle-sim"
    report = export_particle_sim(reviewed, adapted)
    product = json.loads((adapted / "product.yaml").read_text())
    assert product["schema_version"] == "2.0"
    assert product["coordinate_system"]["roi_width_um"] == 120.0
    assert report["shape_px"] == [1200, 1200]
    by_net: dict[str, list[dict]] = {}
    for electrode in product["electrodes"]:
        by_net.setdefault(electrode["net_id"], []).append(electrode)
    assert all(len(rows) >= 1 for rows in by_net.values())
    for electrode in product["electrodes"]:
        source_id = electrode["electrode_id"].split("_", maxsplit=1)[0]
        assert electrode["net_id"] == source_id
    assert len(product["electrode_pairs"]) == report["classified_pairs"]
    assert len(product["electrode_pairs"]) == sum(
        1
        for i, first in enumerate(product["electrodes"])
        for second in product["electrodes"][i + 1 :]
        if first["net_id"] != second["net_id"]
    )
    for contact in product["contacts"]:
        assert "tr_cut" in contact["path"]
        with Image.open(adapted / contact["path"]) as image:
            assert image.size == (1200, 1200)
    assert (adapted / "adapter-provenance.json").is_file()


def test_legacy_cross_layer_contact_rule_index_rejected_before_output(tmp_path: Path) -> None:
    manifest = _legacy_adapter_input(tmp_path / "input")
    source = tmp_path / "extracted"
    extract(manifest, source)
    original = json.loads((source / "manifest.json").read_text())
    assert original["contact_rules"][1]["layer"] == "CNT2"
    for kinds in (("raw_components",), ("components",), ("raw_components", "components")):
        meta = deepcopy(original)
        for kind in kinds:
            rows = [row for row in meta["contact_holes"][kind] if row["layer"] == "CNT1"]
            assert rows and all(row["seed"] is None for row in rows)
            for row in rows:
                row["contact_rule_index"] = 1
        for strict in (False, True):
            with pytest.raises(ManifestError, match="contact_rule_index.*layer"):
                diagnose_physical_holes(source, meta, meta["contact_rules"], strict=strict)
        with pytest.raises(ManifestError, match="contact_rule_index.*layer"):
            prepare_contacts(source, meta, meta["contact_rules"], mixed=True)
        if len(kinds) == 2:
            (source / "manifest.json").write_text(json.dumps(meta))
            output = tmp_path / "absent" / "product"
            with pytest.raises(ManifestError, match="contact_rule_index.*layer"):
                export_particle_sim(source, output)
            assert not output.parent.exists()


def test_legacy_export_rejects_diagonal_only_cnt_with_location(tmp_path: Path) -> None:
    manifest_path = _legacy_adapter_input(tmp_path / "input")
    source = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    manifest["connectivity"] = 8
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    cnt_path = source / "masks" / "CNT1.png"
    with Image.open(cnt_path) as image:
        cnt = np.asarray(image.convert("L")).copy()
    assert not cnt[10, 10] and not cnt[11, 11] and not cnt[10, 11] and not cnt[11, 10]
    cnt[10, 10] = cnt[11, 11] = 255
    Image.fromarray(cnt).save(cnt_path)

    extracted = tmp_path / "extracted"
    extract(manifest_path, extracted)
    output = tmp_path / "particle-sim"
    with pytest.raises(ManifestError, match="CNT1: diagonal-only 8-connected hole") as error:
        export_particle_sim(extracted, output)

    message = str(error.value)
    assert "pixel_yx=(10, 10)" in message
    assert "diagonal_neighbor_yx=(11, 11)" in message
    assert "raw_component=" in message and "8_component=" in message
    assert not output.exists()


def test_mixed_contact_fixture_rejected_before_adapter_output(tmp_path: Path) -> None:
    generated = Path(make_synthetic(tmp_path / "source")["manifest"])
    extracted = tmp_path / "extracted"
    result = extract(generated, extracted)
    assert len(result["tr"]) == 40
    assert result["issues"] == []
    reviewed = ReviewProject(extracted).export(tmp_path / "reviewed")
    reviewed_meta = json.loads((reviewed / "manifest.json").read_text())
    assert reviewed_meta["contact_holes"] == result["contact_holes"]
    output = tmp_path / "particle-sim"
    with pytest.raises(ManifestError, match="one endpoint pair per physical"):
        export_particle_sim(reviewed, output)
    assert not output.exists()


def test_synthetic_crossings_contacts_and_rgb_seams(tmp_path: Path) -> None:
    manifest = Path(make_synthetic(tmp_path / "source")["manifest"])
    source = manifest.parent
    raw = {
        name: np.asarray(Image.open(source / "masks" / f"{name}.png")) > 0
        for name in ("GAT1", "GAT2", "GAT3", "ACTIVE", "OACTIVE", "CNT1", "CNT2", "METAL1")
    }
    assert all(mask.shape == (600, 600) for mask in raw.values())
    assert np.count_nonzero(raw["GAT1"][:, 300]) == 40  # Two 20 px horizontal buses.
    assert np.count_nonzero(raw["GAT2"][:, 300]) == 20
    assert np.count_nonzero(raw["METAL1"][570, :]) == 40  # Two 20 px vertical trunks.
    expected = {"GAT1_ACTIVE": 4, "GAT2_OACTIVE": 2, "GAT3_OACTIVE": 4}
    overlaps = {}
    tr_union = np.zeros((600, 600), dtype=bool)
    source_manifest = json.loads(manifest.read_text())
    for pair in source_manifest["tr_pairs"]:
        gate, channel = pair["gat"], pair["channel"]
        selected = raw[gate] & raw[channel]
        key = f"{gate}_{channel}"
        overlaps[key] = ndimage.label(selected)[1]
        assert not np.any(tr_union & selected), key
        tr_union |= selected
    assert overlaps == expected
    assert not np.any(raw["GAT2"] & raw["ACTIVE"])
    assert not np.any(raw["CNT1"] & raw["CNT2"])
    assert ndimage.label(raw["GAT1"])[1] == 2  # R and B are separate wires.
    assert ndimage.label(raw["GAT2"])[1] == 1  # G is a third periodic bus.
    assert np.array_equal(raw["GAT1"][:, 0], raw["GAT1"][:, -1])
    assert np.array_equal(raw["GAT2"][:, 0], raw["GAT2"][:, -1])

    extracted = tmp_path / "extracted"
    result = extract(manifest, extracted)
    assert result["output_shape_px"] == [1200, 1200]
    assert result["pixel_size_um"] == 0.1
    assert result["output_size_um"] == [120.0, 120.0]
    assert len(result["tr"]) == 40
    assert not result["issues"]
    assert result["stack"] == ["ACTIVE", "GAT1", "GAT2", "OACTIVE", "GAT3", "METAL1"]
    assert result["physical_stack"] == [
        "ACTIVE",
        "GAT1",
        "GAT2",
        "OACTIVE",
        "GAT3",
        "CNT1",
        "CNT2",
        "METAL1",
    ]
    assert not np.any(raw["METAL1"] & tr_union)
    quadrant_pairs = {(x, y): Counter() for y in range(2) for x in range(2)}
    for item in result["tr"]:
        tr_mask = np.asarray(Image.open(extracted / item["path"])) > 0
        pair = f"{item['source_pair']['gat']}_{item['source_pair']['channel']}"
        touched = [
            (x, y)
            for y in range(2)
            for x in range(2)
            if np.any(tr_mask[y * 600 : (y + 1) * 600, x * 600 : (x + 1) * 600])
        ]
        assert len(touched) == 1
        quadrant_pairs[touched[0]][pair] += 1
    assert all(dict(pairs) == expected for pairs in quadrant_pairs.values())
    for name, value in raw.items():
        cut = np.asarray(Image.open(extracted / "cut_layers" / f"{name}.png")) > 0
        assert np.array_equal(cut, value & ~tr_union), name
    rows = result["contact_holes"]["raw_components"]
    rules = result["contact_rules"]
    for row in rows:
        rule = rules[row["contact_rule_index"]]
        assert (rule["layer"], rule["lower"], rule["upper"]) == (
            row["layer"],
            row["lower"],
            row["upper"],
        )
        if "holes" in rule:
            assert row["seed"] in rule["holes"]
        else:
            assert row["seed"] is None
    assert Counter((row["layer"], row["lower"], row["upper"]) for row in rows) == {
        ("CNT1", "ACTIVE", "METAL1"): 11,
        ("CNT1", "GAT2", "METAL1"): 3,
        ("CNT2", "OACTIVE", "METAL1"): 11,
    }
    assert {tuple(row["seed"]) for row in rows if row["layer"] == "CNT1"} == set(
        ACTIVE_METAL_LANDINGS + BRIDGE_ACTIVE_LANDINGS + BRIDGE_GAT_LANDINGS + GAT_METAL_LANDINGS
    )
    for hole, count in (("CNT1", 14), ("CNT2", 11)):
        raw_labels, raw_count = ndimage.label(raw[hole])
        cut_hole = np.asarray(Image.open(extracted / "cut_layers" / f"{hole}.png")) > 0
        cut_labels, cut_count = ndimage.label(cut_hole)
        assert raw_count == cut_count == count
        assert np.array_equal(raw_labels > 0, cut_labels > 0)
        assert not np.any(raw[hole] & tr_union)
        for index in range(1, count + 1):
            row = next(
                row for row in rows if row["layer"] == hole and row["raw_component"] == index
            )
            component = cut_labels == index
            endpoints = {row["lower"], row["upper"]}
            for endpoint in endpoints:
                cut_endpoint = (
                    np.asarray(Image.open(extracted / "cut_layers" / f"{endpoint}.png")) > 0
                )
                overlap = np.count_nonzero(component & cut_endpoint)
                raw_overlap = np.count_nonzero(component & raw[endpoint])
                if tuple(row["seed"] or ()) in BRIDGE_ACTIVE_LANDINGS + BRIDGE_GAT_LANDINGS:
                    assert overlap == raw_overlap == np.count_nonzero(component), (
                        hole,
                        index,
                        endpoint,
                    )
                else:
                    assert overlap > 0 and raw_overlap > 0, (hole, index, endpoint)
            undeclared = {"GAT1", "GAT2", "GAT3", "ACTIVE", "OACTIVE", "METAL1"} - endpoints
            assert all(not np.any(component & raw[name]) for name in undeclared)
    assert len(result["contact_holes"]["components"]) == 25
    assert sum(ndimage.label(raw[name])[1] for name in ("CNT1", "CNT2")) == 25
    graph = json.loads((extracted / "connectivity.json").read_text())
    direct_component = int(ndimage.label(raw["CNT1"])[0][200, 40])
    direct_node = ["CNT1", direct_component]
    direct_neighbors = {
        tuple(edge["to"] if edge["from"] == direct_node else edge["from"])
        for edge in graph["edges"]
        if edge["from"] == direct_node or edge["to"] == direct_node
    }
    assert {layer for layer, _ in direct_neighbors} == {"GAT2", "METAL1"}
    cut_labels = {
        layer: ndimage.label(np.asarray(Image.open(extracted / "cut_layers" / f"{layer}.png")) > 0)[
            0
        ]
        for layer in ("ACTIVE", "GAT2", "METAL1", "CNT1")
    }
    edges = {
        frozenset((tuple(edge["from"]), tuple(edge["to"])))
        for edge in graph["edges"]
        if edge["displacement"] == [0, 0]
    }

    bridge_rows = []
    for active_point, gat_point in ACTIVE_GAT_METAL_BRIDGES:
        ax, ay = active_point
        gx, gy = gat_point
        active_hole = next(row for row in rows if row["seed"] == [ax, ay])
        gat_hole = next(row for row in rows if row["seed"] == [gx, gy])
        assert active_hole["layer"] == gat_hole["layer"] == "CNT1"
        assert (active_hole["lower"], active_hole["upper"]) == ("ACTIVE", "METAL1")
        assert (gat_hole["lower"], gat_hole["upper"]) == ("GAT2", "METAL1")
        assert active_hole["raw_component"] != gat_hole["raw_component"]
        metal_component = int(cut_labels["METAL1"][ay, ax])
        assert metal_component and cut_labels["METAL1"][gy, gx] == metal_component
        # Every center pixel along the drawn L is retained in one cut metal component.
        assert np.all(cut_labels["METAL1"][ay, min(ax, gx) : max(ax, gx) + 1] == metal_component)
        assert np.all(cut_labels["METAL1"][min(ay, gy) : max(ay, gy) + 1, gx] == metal_component)
        route_nodes = [
            ("ACTIVE", int(cut_labels["ACTIVE"][ay, ax])),
            ("CNT1", active_hole["raw_component"]),
            ("METAL1", metal_component),
            ("CNT1", gat_hole["raw_component"]),
            ("GAT2", int(cut_labels["GAT2"][gy, gx])),
        ]
        assert all(component for _, component in route_nodes)
        assert all(frozenset((first, second)) in edges for first, second in pairwise(route_nodes))
        for hole_node, expected_neighbors in (
            (route_nodes[1], {route_nodes[0], route_nodes[2]}),
            (route_nodes[3], {route_nodes[2], route_nodes[4]}),
        ):
            actual_neighbors = {
                tuple(edge["to"] if edge["from"] == list(hole_node) else edge["from"])
                for edge in graph["edges"]
                if edge["from"] == list(hole_node) or edge["to"] == list(hole_node)
            }
            assert actual_neighbors == expected_neighbors
        bridge_rows.append(route_nodes)
    assert len(bridge_rows) == 2
    assert bridge_rows[0][2] != bridge_rows[1][2]

    def owner(layer: str, x: int, y: int) -> str:
        hits = [
            electrode["id"]
            for electrode in result["electrodes"]
            if layer in electrode["layers"]
            and np.asarray(Image.open(extracted / electrode["layers"][layer]["path"]))[y, x]
        ]
        assert len(hits) == 1, (layer, x, y, hits)
        return hits[0]

    cut_active = np.asarray(Image.open(extracted / "cut_layers" / "ACTIVE.png")) > 0
    active_components, _ = ndimage.label(cut_active)
    assert active_components[145, 100] != active_components[325, 180]
    assert active_components[145, 100] and active_components[325, 180]

    # Both two-hole bridges join distinct cut ACTIVE fragments to the GAT2 bus.
    routed = {
        owner(layer, x, y)
        for layer, x, y in (
            ("METAL1", 40, 145),
            ("CNT1", 100, 145),
            ("ACTIVE", 100, 145),
            ("CNT1", 100, 120),
            ("METAL1", 150, 160),
            ("CNT1", 150, 200),
            ("GAT2", 200, 200),
            ("CNT1", 215, 200),
            ("METAL1", 215, 260),
            ("CNT1", 180, 325),
            ("ACTIVE", 180, 325),
            ("METAL1", 40, 200),
            ("CNT1", 40, 200),
            ("GAT2", 40, 200),
        )
    }
    assert len(routed) == 1
    direct_active = owner("METAL1", 180, 55)
    assert direct_active == owner("CNT1", 180, 55) == owner("ACTIVE", 180, 55)
    direct_oactive = owner("METAL1", 460, 235)
    assert direct_oactive == owner("CNT2", 460, 235) == owner("OACTIVE", 460, 235)
    assert len({*routed, direct_active, direct_oactive}) == 3

    # METAL1 has two separate top-to-bottom trunks. Their selected branches join
    # CNT1 ACTIVE(100,145), direct GAT2(40,200), and CNT2 OACTIVE(460,235)/(460,540);
    # other landing pads have no direct trunk branch. Check extracted masks.
    raw_metal = raw["METAL1"]
    for x in (40, 560):
        assert np.all(raw_metal[10:590, x - 9 : x + 10])
        assert np.any(raw_metal[0, x - 9 : x + 10])
        assert np.any(raw_metal[599, x - 9 : x + 10])
    for tx in (0, 1):
        for name, unit_x in (("left", 40), ("right", 560)):
            x = tx * 600 + unit_x
            boundary_ids = {
                seam_y: [
                    row["id"]
                    for row in result["electrodes"]
                    if "METAL1" in row["layers"]
                    and np.asarray(Image.open(extracted / row["layers"]["METAL1"]["path"]))[
                        seam_y, x
                    ]
                ]
                for seam_y in (599, 600)
            }
            assert len(boundary_ids[599]) == len(boundary_ids[600]) == 1, (name, tx)
            assert boundary_ids[599] == boundary_ids[600], (name, tx)
            owner = next(row for row in result["electrodes"] if row["id"] == boundary_ids[599][0])
            extracted_metal = np.asarray(Image.open(extracted / owner["layers"]["METAL1"]["path"]))
            assert np.all(extracted_metal[10:1190, x]), (name, tx, owner["id"])
            assert extracted_metal[0, x] and extracted_metal[1199, x], (name, tx, owner["id"])
            selected_pads = (
                [(tx * 600 + 100, 145)]
                if name == "left"
                else [(tx * 600 + 460, 235), (tx * 600 + 460, 540)]
            )
            for pad_x, pad_y in selected_pads:
                assert extracted_metal[pad_y, pad_x], (name, tx, pad_x, pad_y, owner["id"])

    # The output keeps individual periodic bus identities while joining each seam.
    bus_ids = {}
    for name, layer, y in (("R", "GAT1", 100), ("G", "GAT2", 200), ("B", "GAT1", 300)):
        hits = [
            row["id"]
            for row in result["electrodes"]
            if layer in row["layers"]
            and np.asarray(Image.open(extracted / row["layers"][layer]["path"]))[y, 599]
        ]
        assert len(hits) == 1, name
        bus_ids[name] = hits[0]
        output_bus = (
            np.asarray(
                Image.open(
                    extracted
                    / next(
                        row["layers"][layer]["path"]
                        for row in result["electrodes"]
                        if row["id"] == hits[0]
                    )
                )
            )
            > 0
        )
        assert output_bus[y, 599] and output_bus[y, 600], name
    assert len(set(bus_ids.values())) == 3


def _renamed_manifest(path: Path, *, add_ambiguous_active: bool = False) -> Path:
    manifest_path = _legacy_adapter_input(path)
    manifest = json.loads(manifest_path.read_text())
    renames = {"ACTIVE": "ACT_A", "OACTIVE": "OACT_A", "METAL1": "MTL_TOP"}
    for layer in manifest["layers"]:
        layer["id"] = renames.get(layer["id"], layer["id"])
    manifest["stack"] = [renames.get(layer, layer) for layer in manifest["stack"]]
    manifest["physical_stack"] = [renames.get(layer, layer) for layer in manifest["physical_stack"]]
    manifest["tr_pairs"] = [
        {
            "gat": pair["gat"],
            "channel": renames.get(pair["channel"], pair["channel"]),
        }
        for pair in manifest["tr_pairs"]
    ]
    for contact in manifest["contacts"]:
        contact["lower"] = renames.get(contact["lower"], contact["lower"])
        contact["upper"] = renames.get(contact["upper"], contact["upper"])
        if contact["layer"] == "CNT1":
            contact["upper"] = "MTL_MID"
    manifest["stack"].insert(manifest["stack"].index("MTL_TOP"), "MTL_MID")
    manifest["physical_stack"].insert(manifest["physical_stack"].index("MTL_TOP"), "MTL_MID")
    manifest["layers"].append({"id": "MTL_MID", "path": "masks/MTL_MID.png", "role": "METAL"})
    Image.open(path / "masks" / "METAL1.png").save(path / "masks" / "MTL_MID.png")
    if add_ambiguous_active:
        manifest["layers"].append({"id": "ACT_B", "path": "masks/ACT_B.png", "role": "ACTIVE"})
        manifest["stack"].insert(manifest["stack"].index("OACT_A"), "ACT_B")
        manifest["physical_stack"].insert(manifest["physical_stack"].index("OACT_A"), "ACT_B")
        Image.open(path / "masks" / "ACTIVE.png").save(path / "masks" / "ACT_B.png")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def test_renamed_roles_and_non_top_metal_contact_endpoint(tmp_path: Path) -> None:
    input_manifest = _renamed_manifest(tmp_path / "renamed-input")
    extraction = tmp_path / "renamed-extraction"
    extract(input_manifest, extraction)

    output = tmp_path / "renamed-particle-sim"
    export_particle_sim(extraction, output)
    product = json.loads((output / "product.yaml").read_text())
    stack_order = {layer["layer_name"]: layer["process_order"] for layer in product["stack"]}
    assert {"ACT_A", "OACT_A", "MTL_MID", "MTL_TOP"} <= stack_order.keys()
    assert stack_order["ILD_ACTIVE_OACTIVE"] < stack_order["OACT_A"]
    assert stack_order["ILD_OACTIVE_METAL"] < stack_order["MTL_MID"]
    assert stack_order["ACT_A"] < stack_order["CNT1"] < stack_order["MTL_MID"]
    assert stack_order["OACT_A"] < stack_order["CNT2"] < stack_order["MTL_TOP"]
    assert product["contacts"][0]["upper_layer"] == "MTL_MID"
    assert product["particle_source_steps"][0]["lands_after_layer"] == "MTL_TOP"


def test_conductor_role_above_oactive_gets_assumed_ild(tmp_path: Path) -> None:
    manifest_path = _legacy_adapter_input(tmp_path / "conductor-role-input")
    manifest = json.loads(manifest_path.read_text())
    for layer in manifest["layers"]:
        if layer["id"] == "METAL1":
            layer["role"] = "CONDUCTOR"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    extraction = tmp_path / "conductor-role-extraction"
    extract(manifest_path, extraction)

    output = tmp_path / "conductor-role-particle-sim"
    export_particle_sim(extraction, output)
    product = json.loads((output / "product.yaml").read_text())
    stack_order = {layer["layer_name"]: layer["process_order"] for layer in product["stack"]}
    assert stack_order["OACTIVE"] < stack_order["ILD_OACTIVE_METAL"] < stack_order["METAL1"]
    assert product["particle_source_steps"][0]["lands_after_layer"] == "METAL1"


def test_ambiguous_role_stack_fails_before_creating_output(tmp_path: Path) -> None:
    input_manifest = _renamed_manifest(tmp_path / "ambiguous-input", add_ambiguous_active=True)
    extraction = tmp_path / "ambiguous-extraction"
    extract(input_manifest, extraction)
    output = tmp_path / "unsupported-particle-sim"

    with pytest.raises(ManifestError, match="multiple ACTIVE-role layers"):
        export_particle_sim(extraction, output)

    assert not output.exists()


def test_unsupported_contact_endpoint_fails_before_creating_output(tmp_path: Path) -> None:
    input_manifest = _renamed_manifest(tmp_path / "invalid-contact-input")
    extraction = tmp_path / "invalid-contact-extraction"
    extract(input_manifest, extraction)
    extraction_manifest = extraction / "manifest.json"
    metadata = json.loads(extraction_manifest.read_text())
    metadata["contact_rules"][0]["upper"] = "UNKNOWN_LAYER"
    extraction_manifest.write_text(json.dumps(metadata) + "\n")
    output = tmp_path / "invalid-contact-particle-sim"

    with pytest.raises(ManifestError, match="unsupported contact topology"):
        export_particle_sim(extraction, output)

    assert not output.exists()


@pytest.fixture(scope="module")
def mixed_extraction(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("mixed-export")
    generated = Path(make_synthetic(root / "source")["manifest"])
    extraction = root / "extraction"
    extract(generated, extraction)
    return extraction


def _synthetic_config() -> dict:
    path = Path(__file__).resolve().parents[1] / "examples" / "synthetic-particle-config.json"
    return json.loads(path.read_text())


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


@pytest.fixture(scope="module")
def circuit_case(mixed_extraction: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("circuit-case")
    baseline = root / "baseline"
    config_path = root / "config.json"
    config_path.write_text(json.dumps(_synthetic_config()))
    export_particle_sim(mixed_extraction, baseline, config_path)
    meta = json.loads((mixed_extraction / "manifest.json").read_text())
    product = json.loads((baseline / "product.yaml").read_text())
    provenance = json.loads((baseline / "adapter-provenance.json").read_text())
    net_map = {row["id"]: f"NET_{row['id']}" for row in meta["electrodes"]}
    first, second = list(net_map)[:2]
    net_map[second] = net_map[first]
    hole = provenance["contact_holes"][0]
    electrode = next(
        row for row in product["electrodes"] if row["electrode_id"] == hole["lower_electrode"]
    )
    mask = np.asarray(Image.open(baseline / electrode["path"])) > 0
    points = np.argwhere(mask)[:2].tolist()
    config = _synthetic_config()
    config["net_map"] = net_map
    config["open_paths"] = [
        {
            "path_id": "OPEN_1",
            "electrode": electrode["electrode_id"],
            "terminal_a_yx_px": points[0],
            "terminal_b_yx_px": points[1],
            "applicable_particle_source_steps": [f"SOURCE_{hole['hole_layer']}_OPEN"],
            "circuit_connection_id": "CONNECTION_1",
            "circuit_net_id": net_map[
                electrode["electrode_id"].removesuffix(f"_{electrode['layer_name']}")
            ],
        }
    ]
    config["cno_open_relations"] = [
        {
            "cno_link_id": hole["cno_link_id"],
            "open_path_id": "OPEN_1",
            "circuit_connection_id": "CONNECTION_1",
        }
    ]
    return {"config": config, "meta": meta, "baseline": baseline}


def test_declared_circuit_map_pair_partition_and_explicit_open(
    tmp_path: Path, mixed_extraction: Path, circuit_case: dict
) -> None:
    config = deepcopy(circuit_case["config"])
    product = json.loads((circuit_case["baseline"] / "product.yaml").read_text())
    candidates = [row["electrode_id"] for row in product["electrodes"]]
    a, b = next(
        (a, b)
        for a in candidates
        for b in candidates
        if config["net_map"][a.rsplit("_", 1)[0]] != config["net_map"][b.rsplit("_", 1)[0]]
    )
    config["excluded_pairs"] = [
        {"electrode_a": a, "electrode_b": b, "reason": "manual_bounded_probe"}
    ]
    output = tmp_path / "mapped"
    report = export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    manifest = json.loads((output / "product.yaml").read_text())
    sidecar = json.loads((output / "adapter-provenance.json").read_text())
    circuit = sidecar["circuit"]
    assert report["declared_circuit_nets"] == len(set(config["net_map"].values()))
    assert report["provisional_extracted_nets"] == 0
    assert len(circuit["pair_inventory"]) == 155 * 154 // 2
    assert len({row["pair_id"] for row in circuit["pair_inventory"]}) == len(
        circuit["pair_inventory"]
    )
    assert sum(row["status"] == "included" for row in circuit["pair_inventory"]) == len(
        manifest["electrode_pairs"]
    )
    assert all(row["reason"] for row in circuit["pair_inventory"] if row["status"] == "excluded")
    assert len(manifest["excluded_electrode_pairs"]) == 1
    assert manifest["open_paths"][0]["fallback"] == "error"
    assert all(not steps for steps in manifest["open_applicable_steps_by_layer"].values())
    assert circuit["cno_open_relations"] == config["cno_open_relations"]
    assert circuit["auto_open"] == "disabled"
    assert {row["raw_pixels"] for row in sidecar["contact_holes"]} == {225}
    assert {row["cut_pixels"] for row in sidecar["contact_holes"]} == {225}
    assert len(sidecar["mask_diagnostics"]["all_layer_tr_cut"]) == 8
    assert len(sidecar["mask_diagnostics"]["source_stage_mask_diagnostics"]) == 3
    assert sidecar["mask_diagnostics"]["raw_conductor_overlaps"]
    assert "no process short inferred" in sidecar["mask_diagnostics"]["raw_overlap_interpretation"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: c["net_map"].pop(next(iter(c["net_map"]))), "cover every"),
        (lambda c: c["net_map"].update(UNKNOWN="NET_X"), "cover every"),
        (lambda c: c["net_map"].update({next(iter(c["net_map"])): "BAD:NET"}), "safe ASCII"),
        (
            lambda c: c.update(
                excluded_pairs=[
                    {
                        "electrode_a": "UNKNOWN",
                        "electrode_b": c["open_paths"][0]["electrode"],
                        "reason": "x",
                    }
                ]
            ),
            "unknown or identical",
        ),
        (
            lambda c: c.update(
                excluded_pairs=[
                    {
                        "electrode_a": c["open_paths"][0]["electrode"],
                        "electrode_b": c["open_paths"][0]["electrode"],
                        "reason": "x",
                    }
                ]
            ),
            "unknown or identical",
        ),
        (lambda c: c["open_paths"][0].update(terminal_a_yx_px=[0, 0]), "land on"),
        (lambda c: c["open_paths"][0].update(circuit_net_id="WRONG"), "disagree"),
        (lambda c: c["open_paths"][0].update(fallback="roi_boundary"), "unknown"),
        (lambda c: c["open_paths"].append(c["open_paths"][0].copy()), "duplicate open path"),
        (
            lambda c: c["open_paths"][0].update(applicable_particle_source_steps=["BAD"]),
            "source steps",
        ),
        (lambda c: c["cno_open_relations"][0].update(cno_link_id="cno:UNKNOWN"), "unknown"),
        (lambda c: c["cno_open_relations"][0].update(open_path_id="UNKNOWN"), "unknown"),
        (lambda c: c["cno_open_relations"][0].update(circuit_connection_id="OTHER"), "disagrees"),
        (lambda c: c["cno_open_relations"].append(c["cno_open_relations"][0].copy()), "duplicate"),
        (
            lambda c: c["open_paths"][0].update(
                applicable_particle_source_steps=["SOURCE_AFTER_METAL1"]
            ),
            "shared applicable",
        ),
    ],
)
def test_circuit_declarations_rejected_before_output(
    tmp_path: Path, mixed_extraction: Path, circuit_case: dict, change, message: str
) -> None:
    config = deepcopy(circuit_case["config"])
    change(config)
    output = tmp_path / "invalid"
    with pytest.raises(ManifestError, match=message):
        export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    assert not output.exists()


def test_configured_mixed_export_partitions_all_holes(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    output = tmp_path / "product"
    report = export_particle_sim(
        mixed_extraction, output, _write_config(tmp_path, _synthetic_config())
    )
    product = json.loads((output / "product.yaml").read_text())
    provenance = json.loads((output / "adapter-provenance.json").read_text())
    assert provenance["product_yaml_sha256"] == hashlib.sha256(
        (output / "product.yaml").read_bytes()
    ).hexdigest()
    assert (
        report["electrodes"],
        report["nets"],
        report["contacts"],
        report["holes"],
        report["classified_pairs"],
    ) == (155, 101, 3, 100, 11879)
    assert len(product["layer_masks"]) == 6
    assert product["particle_sizes_um"] == [*range(1, 31), 40, 50]
    assert [row["hole_layer"] for row in product["contacts"]] == ["CNT1", "CNT1", "CNT2"]
    assert len(provenance["contact_holes"]) == 100
    diagnostics = provenance["physical_hole_diagnostics"]
    assert len(diagnostics) == 100
    assert (
        len(
            {
                (row["hole_layer"], row["raw_component"], tuple(row["tile_xy"]))
                for row in diagnostics
            }
        )
        == 100
    )
    assert {row["effective_pixels"] for row in diagnostics} == {120, 195, 225}
    assert all(row["raw_pixels"] == row["cut_pixels"] == 225 for row in diagnostics)
    assert all(row["tr_removed_pixels"] == 0 for row in diagnostics)
    assert all(
        {item["layer"] for item in row["other_conductor_intersections"]}
        == {item["layer_name"] for item in product["layer_masks"]}
        - {row["lower_layer"], row["upper_layer"]}
        for row in diagnostics
    )
    assert all(
        row["lower_enclosure"]["cut_pixels"] >= row["effective_pixels"]
        and row["upper_enclosure"]["cut_pixels"] >= row["effective_pixels"]
        and row["lower_enclosure"]["cut_fraction"] == row["lower_enclosure"]["cut_pixels"] / 225
        and row["upper_enclosure"]["cut_fraction"] == row["upper_enclosure"]["cut_pixels"] / 225
        for row in diagnostics
    )
    assert all(
        item["raw_intersection_pixels"] == 0
        for row in diagnostics
        for item in row["other_conductor_intersections"]
        if item["relation"] == "intermediate"
    )
    assert {row["raw_pixels"] for row in provenance["contact_holes"]} == {225}
    assert {row["cut_pixels"] for row in provenance["contact_holes"]} == {225}
    assert all(0 < row["effective_pixels"] <= 225 for row in provenance["contact_holes"])
    electrode_paths = {row["electrode_id"]: row["path"] for row in product["electrodes"]}
    cached_masks = {}
    unit_labels = {
        hole: ndimage.label(
            np.asarray(Image.open(mixed_extraction / "raw_layers" / f"{hole}.png")) > 0
        )[0]
        for hole in ("CNT1", "CNT2")
    }
    for row in provenance["contact_holes"]:
        hole = row["hole_layer"]
        ys, xs = np.nonzero(unit_labels[hole] == row["raw_component"])
        tx, ty = row["tile_xy"]
        yy, xx = ys + ty * 600, xs + tx * 600
        for electrode in (row["lower_electrode"], row["upper_electrode"]):
            if electrode not in cached_masks:
                cached_masks[electrode] = (
                    np.asarray(Image.open(output / electrode_paths[electrode])) > 0
                )
        effective = (
            cached_masks[row["lower_electrode"]][yy, xx]
            & cached_masks[row["upper_electrode"]][yy, xx]
        )
        assert row["effective_pixels"] == int(np.count_nonzero(effective))
    for hole in ("CNT1", "CNT2"):
        union = np.zeros((1200, 1200), dtype=bool)
        for row in product["contacts"]:
            if row["hole_layer"] == hole:
                mask = np.asarray(Image.open(output / row["path"])) > 0
                assert not np.any(union & mask)
                union |= mask
        cut = np.asarray(Image.open(mixed_extraction / "cut_layers" / f"{hole}.png")) > 0
        assert np.array_equal(union, np.tile(cut, (2, 2)))


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("hole_in_tr", "hole_in_tr"),
        ("hole_in_tr_full", "hole_in_tr"),
        ("metal_over_tr", "metal_over_tr"),
        ("hole_through_gat2", "hole_through_intermediate_conductor"),
    ],
)
def test_per_hole_adversarial_geometry_has_distinct_policy(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    input_manifest = Path(make_synthetic(tmp_path / "input")["manifest"])
    layer = {
        "hole_in_tr": "GAT1",
        "hole_in_tr_full": "GAT1",
        "metal_over_tr": "METAL1",
        "hole_through_gat2": "GAT2",
    }[mutation]
    x, y = (100, 100) if mutation == "metal_over_tr" else (100, 55)
    path = input_manifest.parent / "masks" / f"{layer}.png"
    mask = np.asarray(Image.open(path)).copy()
    assert mask[y, x] == 0
    if mutation == "hole_in_tr_full":
        mask[y - 7 : y + 8, x - 7 : x + 8] = 255
    else:
        mask[y, x] = 255
    Image.fromarray(mask).save(path)
    extraction = tmp_path / "extraction"
    extract(input_manifest, extraction)
    output = tmp_path / "product"
    config = _write_config(tmp_path, _synthetic_config())
    if mutation == "metal_over_tr":
        export_particle_sim(extraction, output, config)
        sidecar = json.loads((output / "adapter-provenance.json").read_text())
        hits = sidecar["mask_diagnostics"]["metal_over_tr"]
        assert any(row["code"] == expected and row["tr_overlap_pixels"] >= 1 for row in hits)
        assert len(sidecar["physical_hole_diagnostics"]) == 100
    else:
        with pytest.raises(ManifestError, match=expected) as error:
            export_particle_sim(extraction, output, config)
        assert "CNT1 raw_component=" in str(error.value)
        assert "seed=[100, 55]" in str(error.value)
        if mutation == "hole_in_tr_full":
            assert "cut=0" in str(error.value)
        if mutation == "hole_through_gat2":
            assert "intermediate_layer=GAT2" in str(error.value)
        assert not output.exists()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: c.update(schema_version=2), "schema_version"),
        (lambda c: c.update(unexpected=1), "unknown"),
        (lambda c: c.pop("process_stack"), "missing"),
        (lambda c: c.update(particle_sizes_um=[]), "particle_sizes_um"),
        (lambda c: c.update(particle_sizes_um=[1, 1]), "strictly increasing"),
        (lambda c: c.update(particle_sizes_um=[2, 1]), "strictly increasing"),
        (lambda c: c.update(particle_sizes_um=[31]), "strictly increasing"),
        (lambda c: c["process_stack"][0].update(thickness_um=float("nan")), "finite"),
        (lambda c: c["process_stack"][0].update(patterned=False), "patterned"),
        (lambda c: c["source_stages"][0].update(surface_model="unknown"), "surface_model"),
        (lambda c: c["source_stages"][1].update(step_id="SOURCE_CNT1_OPEN"), "duplicate"),
        (lambda c: c["contact_applicable_stages"].update(CNT1=["SOURCE_CNT2_OPEN"]), "CNT1"),
    ],
)
def test_config_rejected_before_output(
    tmp_path: Path, mixed_extraction: Path, change, message: str
) -> None:
    config = _synthetic_config()
    change(config)
    output = tmp_path / "product"
    with pytest.raises(ManifestError, match=message):
        export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    assert not output.exists()


@pytest.mark.parametrize("surface_model", ["flat", "conformal", "partial"])
def test_source_surface_model_passed_through(
    tmp_path: Path, mixed_extraction: Path, surface_model: str
) -> None:
    config = _synthetic_config()
    config["source_stages"][-1]["surface_model"] = surface_model
    if surface_model == "partial":
        for row in config["process_stack"]:
            if row["material_type"] != "conductor":
                row["planarization_factor"] = 0.25
    output = tmp_path / "product"
    export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    product = json.loads((output / "product.yaml").read_text())
    assert [stage["surface_model"] for stage in product["particle_source_steps"]] == [
        "flat", "flat", surface_model
    ]
    if surface_model == "partial":
        assert all(
            row["planarization_factor"] == 0.25
            for row in product["stack"] if row["material_type"] != "conductor"
        )


@pytest.mark.parametrize("missing", ["ILD_ACTIVE_OACTIVE", "CNT1", "CNT2"])
def test_partial_surface_requires_nonconductor_factors_before_output(
    tmp_path: Path, mixed_extraction: Path, missing: str
) -> None:
    config = _synthetic_config()
    config["source_stages"][-1]["surface_model"] = "partial"
    for row in config["process_stack"]:
        if row["material_type"] != "conductor":
            row["planarization_factor"] = 0.5
        if row["id"] == missing:
            row.pop("planarization_factor", None)
    output = tmp_path / "product"
    with pytest.raises(ManifestError, match=f"partial.*planarization_factor.*{missing}"):
        export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    assert not output.exists()


def test_partial_surface_does_not_require_factors_above_landing(tmp_path: Path) -> None:
    from layout_electrode_extractor.export_config import load_export_config

    config = _synthetic_config()
    config["source_stages"] = [{
        "step_id": "EARLY", "after_layer": "GAT2", "semantics": "after_pattern",
        "surface_model": "partial"
    }]
    config["contact_applicable_stages"] = {}
    for row in config["process_stack"]:
        row.pop("planarization_factor", None)
    meta = {
        "physical_stack": [r["id"] for r in config["process_stack"] if r["mask_layer"]],
        "stack": [r["id"] for r in config["process_stack"] if r["kind"] == "conductor"],
    }
    validated = load_export_config(_write_config(tmp_path, config), meta, [])
    assert validated["source_stages"] == [
        {**config["source_stages"][0], "fab_distribution_layer": "OACTIVE"}
    ]


def test_fab_layer_is_the_mask_layer_directly_above_the_landing_layer(tmp_path: Path) -> None:
    from layout_electrode_extractor.export_config import load_export_config

    config = _synthetic_config()
    config["contact_applicable_stages"] = {}
    meta = {
        "physical_stack": [r["id"] for r in config["process_stack"] if r["mask_layer"]],
        "stack": [r["id"] for r in config["process_stack"] if r["kind"] == "conductor"],
    }

    def load(**stage: str) -> list[dict]:
        config["source_stages"] = [{"step_id": "S", "semantics": "after_pattern",
                                    "surface_model": "conformal", **stage}]
        return load_export_config(_write_config(tmp_path, config), meta, [])["source_stages"]

    # The unmasked ILD between GAT2 and OACTIVE is skipped.
    assert load(after_layer="GAT2")[0]["fab_distribution_layer"] == "OACTIVE"
    assert load(after_layer="GAT2", fab_distribution_layer="OACTIVE")[0][
        "fab_distribution_layer"] == "OACTIVE"
    with pytest.raises(ManifestError, match="must be OACTIVE"):
        load(after_layer="GAT2", fab_distribution_layer="GATE_PHOTO")
    # Hole rows without contacts have no mask in particle-sim, so GAT3 -> METAL1.
    assert load(after_layer="GAT3")[0]["fab_distribution_layer"] == "METAL1"
    with pytest.raises(ManifestError, match="no mask layer above METAL1"):
        load(after_layer="METAL1")
    assert load(after_layer="METAL1", fab_distribution_layer="TOP")[0][
        "fab_distribution_layer"] == "TOP"


def test_synthetic_size_subset_and_measured_contact_rejection(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    config = _synthetic_config()
    config["particle_sizes_um"] = [1, 30, 40, 50]
    output = tmp_path / "subset"
    export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    product = json.loads((output / "product.yaml").read_text())
    provenance = json.loads((output / "adapter-provenance.json").read_text())
    assert product["particle_sizes_um"] == provenance["particle_sizes_um"] == [1, 30, 40, 50]
    config["profile"] = "measured"
    rejected = tmp_path / "measured"
    with pytest.raises(
        ManifestError, match="measured CNT open stage/contact physics is unsupported"
    ):
        export_particle_sim(mixed_extraction, rejected, _write_config(tmp_path, config))
    assert not rejected.exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("drop", "raw hole provenance"),
        ("drop_hole", "raw hole provenance"),
        ("duplicate", "duplicate raw hole provenance"),
        ("endpoint", "wrong or inconsistent hole endpoints"),
        ("rule_endpoint", "unsupported contact topology"),
        ("rule_index", "contact_rule_index.*layer"),
        ("invalid_rule_index", "invalid raw_components contact_rule_index"),
        ("missing_seed", "malformed raw_components hole provenance"),
        ("missing_cut_seed", "malformed components hole provenance"),
        ("null_seed", "missing raw hole seed"),
        ("extra", "contact_rule_index.*layer"),
        ("partial_tr", "partial or complete TR cut"),
        ("edge", "edge"),
        ("overlap", "overlap"),
    ],
)
def test_corrupt_hole_or_electrode_rejected_before_output(
    tmp_path: Path, mixed_extraction: Path, mutation: str, message: str
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    metadata = json.loads(metadata_path.read_text())
    if mutation == "drop":
        metadata["contact_holes"]["raw_components"].pop()
    elif mutation == "drop_hole":
        raw_path = source / "raw_layers" / "CNT1.png"
        labels, _ = ndimage.label(np.asarray(Image.open(raw_path)) > 0)
        for directory in ("raw_layers", "cut_layers"):
            path = source / directory / "CNT1.png"
            mask = np.asarray(Image.open(path)).copy()
            mask[labels == 1] = 0
            Image.fromarray(mask).save(path)
    elif mutation == "duplicate":
        metadata["contact_holes"]["raw_components"].append(
            metadata["contact_holes"]["raw_components"][0].copy()
        )
    elif mutation == "endpoint":
        metadata["contact_holes"]["raw_components"][0]["lower"] = "GAT1"
    elif mutation == "rule_endpoint":
        metadata["contact_rules"][0]["lower"] = "UNKNOWN_LAYER"
    elif mutation == "rule_index":
        metadata["contact_holes"]["raw_components"][0]["contact_rule_index"] = 2
        metadata["contact_holes"]["components"][0]["contact_rule_index"] = 2
    elif mutation == "invalid_rule_index":
        metadata["contact_holes"]["raw_components"][0]["contact_rule_index"] = 99
    elif mutation == "missing_seed":
        metadata["contact_holes"]["raw_components"][0].pop("seed")
    elif mutation == "missing_cut_seed":
        metadata["contact_holes"]["components"][0].pop("seed")
    elif mutation == "null_seed":
        metadata["contact_holes"]["raw_components"][0]["seed"] = None
    elif mutation == "extra":
        extra = metadata["contact_holes"]["raw_components"][0].copy()
        extra["layer"] = "UNKNOWN_LAYER"
        metadata["contact_holes"]["raw_components"].append(extra)
    elif mutation == "partial_tr":
        raw = np.asarray(Image.open(source / "raw_layers" / "CNT1.png")) > 0
        y, x = np.argwhere(raw)[0]
        tr = np.asarray(Image.open(source / "tr_union.png")).copy()
        cut_path = source / "cut_layers" / "CNT1.png"
        cut = np.asarray(Image.open(cut_path)).copy()
        cut[y, x] = 0
        Image.fromarray(cut).save(cut_path)
        for ty in range(2):
            for tx in range(2):
                tr[y + ty * 600, x + tx * 600] = 255
        Image.fromarray(tr).save(source / "tr_union.png")
    elif mutation == "edge":
        for directory in ("raw_layers", "cut_layers"):
            path = source / directory / "CNT1.png"
            mask = np.asarray(Image.open(path)).copy()
            mask[55, :180] = 255
            Image.fromarray(mask).save(path)
    elif mutation == "overlap":
        active_rows = [row for row in metadata["electrodes"] if "ACTIVE" in row["layers"]]
        first = np.asarray(Image.open(source / active_rows[0]["layers"]["ACTIVE"]["path"]))
        second_path = source / active_rows[1]["layers"]["ACTIVE"]["path"]
        second = np.asarray(Image.open(second_path)).copy()
        y, x = np.argwhere(first > 0)[0]
        second[y, x] = 255
        Image.fromarray(second).save(second_path)
    metadata_path.write_text(json.dumps(metadata))
    output = tmp_path / "product"
    with pytest.raises(ManifestError, match=message):
        export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.exists()


def test_diagonal_eight_connected_holes_rejected() -> None:
    diagonal = np.array([[1, 0], [0, 1]], dtype=bool)
    with pytest.raises(ManifestError, match="CNT1: diagonal-only 8-connected hole") as error:
        _check_four_partition(diagonal, "CNT1", 8)
    assert "pixel_yx=(0, 0)" in str(error.value)
    assert "diagonal_neighbor_yx=(1, 1)" in str(error.value)
    assert "raw_component=1" in str(error.value)
    assert "diagonal_raw_component=2" in str(error.value)
    assert "8_component=1" in str(error.value)


def test_swapped_same_rule_seeds_rejected_by_both_preflights(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    rows = meta["contact_holes"]["raw_components"]
    first, second = next(
        (a, b)
        for a in rows
        for b in rows
        if a is not b
        and a["layer"] == b["layer"]
        and a["contact_rule_index"] == b["contact_rule_index"]
    )
    first["seed"], second["seed"] = second["seed"], first["seed"]
    metadata_path.write_text(json.dumps(meta))
    for preflight in (
        lambda: prepare_contacts(source, meta, meta["contact_rules"], mixed=True),
        lambda: diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True),
    ):
        with pytest.raises(ManifestError, match="seed .* does not match raw_component"):
            preflight()
    output = tmp_path / "absent" / "product"
    with pytest.raises(ManifestError, match="seed .* does not match raw_component"):
        export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.parent.exists()


def test_multi_rule_null_seed_rejected_even_without_rule_holes(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    layer = "CNT1"
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    for rule in meta["contact_rules"]:
        if rule["layer"] == layer:
            rule.pop("holes", None)
    for kind in ("raw_components", "components"):
        for row in meta["contact_holes"][kind]:
            if row["layer"] == layer:
                row["seed"] = None
    metadata_path.write_text(json.dumps(meta))
    for preflight in (
        lambda: prepare_contacts(source, meta, meta["contact_rules"], mixed=True),
        lambda: diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True),
    ):
        with pytest.raises(ManifestError, match=f"{layer}: missing raw hole seed"):
            preflight()
    with pytest.raises(ManifestError, match="CNT1: missing raw hole seed"):
        diagnose_physical_holes(source, meta, meta["contact_rules"], strict=False)
    output = tmp_path / "absent" / "product"
    with pytest.raises(ManifestError, match=f"{layer}: missing raw hole seed"):
        export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.parent.exists()


def test_configured_single_rule_without_holes_allows_null_seed(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    rule = next(rule for rule in meta["contact_rules"] if rule["layer"] == "CNT2")
    assert "holes" not in rule
    for kind in ("raw_components", "components"):
        for row in meta["contact_holes"][kind]:
            if row["layer"] == "CNT2":
                row["seed"] = None
    metadata_path.write_text(json.dumps(meta))
    prepare_contacts(source, meta, meta["contact_rules"], mixed=True)
    diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True)
    output = tmp_path / "product"
    export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert (output / "product.yaml").is_file()


def test_explicit_rule_holes_reject_null_seed_on_single_rule_layer(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    rule = next(rule for rule in meta["contact_rules"] if rule["layer"] == "CNT2")
    rule["holes"] = [
        row["seed"]
        for row in meta["contact_holes"]["raw_components"]
        if row["layer"] == "CNT2"
    ]
    for kind in ("raw_components", "components"):
        next(row for row in meta["contact_holes"][kind] if row["layer"] == "CNT2")[
            "seed"
        ] = None
    metadata_path.write_text(json.dumps(meta))
    for preflight in (
        lambda: prepare_contacts(source, meta, meta["contact_rules"], mixed=True),
        lambda: diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True),
    ):
        with pytest.raises(ManifestError, match="CNT2: missing raw hole seed"):
            preflight()
    output = tmp_path / "absent" / "product"
    with pytest.raises(ManifestError, match="CNT2: missing raw hole seed"):
        export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.parent.exists()


def test_explicit_seed_requires_declared_rule_holes(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    assert "holes" not in next(
        rule for rule in meta["contact_rules"] if rule["layer"] == "CNT2"
    )
    labels, _ = ndimage.label(np.asarray(Image.open(source / "raw_layers" / "CNT2.png")) > 0)
    for kind in ("raw_components", "components"):
        row = next(row for row in meta["contact_holes"][kind] if row["layer"] == "CNT2")
        y, x = np.argwhere(labels == row["raw_component"])[0]
        row["seed"] = [int(x), int(y)]
    metadata_path.write_text(json.dumps(meta))
    for preflight in (
        lambda: prepare_contacts(source, meta, meta["contact_rules"], mixed=True),
        lambda: diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True),
    ):
        with pytest.raises(ManifestError, match="seed .* is not in declared rule holes"):
            preflight()


def test_swapped_rule_assignment_rejected_by_seed_rule_membership(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(mixed_extraction, source)
    metadata_path = source / "manifest.json"
    meta = json.loads(metadata_path.read_text())
    first, second = next(
        (a, b)
        for a in meta["contact_holes"]["raw_components"]
        for b in meta["contact_holes"]["raw_components"]
        if a["layer"] == b["layer"] == "CNT1"
        and a["contact_rule_index"] != b["contact_rule_index"]
    )
    for kind in ("raw_components", "components"):
        rows = meta["contact_holes"][kind]
        for component, other in (
            (first["raw_component"], second),
            (second["raw_component"], first),
        ):
            row = next(
                row
                for row in rows
                if row["layer"] == "CNT1" and row["raw_component"] == component
            )
            for key in ("contact_rule_index", "lower", "upper"):
                row[key] = other[key]
    metadata_path.write_text(json.dumps(meta))
    for preflight in (
        lambda: prepare_contacts(source, meta, meta["contact_rules"], mixed=True),
        lambda: diagnose_physical_holes(source, meta, meta["contact_rules"], strict=True),
    ):
        with pytest.raises(ManifestError, match="seed .* is not in declared rule holes"):
            preflight()
    output = tmp_path / "absent" / "product"
    with pytest.raises(ManifestError, match="seed .* is not in declared rule holes"):
        export_particle_sim(source, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.parent.exists()


@pytest.mark.parametrize("occupied", [False, True])
def test_atomic_publish_rejects_concurrent_directory_even_if_empty(
    tmp_path: Path, mixed_extraction: Path, monkeypatch, occupied: bool
) -> None:
    output = tmp_path / "parent" / "product"
    original_publish = particle_sim_adapter._publish_noreplace

    def claim_then_publish(staging: Path, destination: Path) -> None:
        destination.mkdir()
        if occupied:
            (destination / "owner.txt").write_text("other process")
        original_publish(staging, destination)

    monkeypatch.setattr(particle_sim_adapter, "_publish_noreplace", claim_then_publish)
    with pytest.raises(FileExistsError, match="output already exists"):
        export_particle_sim(
            mixed_extraction, output, _write_config(tmp_path, _synthetic_config())
        )
    assert output.is_dir()
    assert sorted(path.name for path in output.iterdir()) == (["owner.txt"] if occupied else [])
    assert not list(output.parent.glob(".product.*"))


def test_circuit_preflight_does_not_create_output_parent(
    tmp_path: Path, mixed_extraction: Path
) -> None:
    config = _synthetic_config()
    config["net_map"] = {"UNKNOWN": "NET"}
    output = tmp_path / "uncreated" / "product"
    with pytest.raises(ManifestError, match="net_map must cover every"):
        export_particle_sim(mixed_extraction, output, _write_config(tmp_path, config))
    assert not output.parent.exists()


def test_export_cli_modes(tmp_path: Path, mixed_extraction: Path, capsys) -> None:
    legacy_rejected = tmp_path / "legacy-rejected"
    assert cli_main(["export-particle-sim", str(mixed_extraction), str(legacy_rejected)]) == 2
    assert not legacy_rejected.exists()
    synthetic = tmp_path / "synthetic"
    config = _write_config(tmp_path, _synthetic_config())
    assert (
        cli_main(
            ["export-particle-sim", str(mixed_extraction), str(synthetic), "--config", str(config)]
        )
        == 0
    )
    assert json.loads((synthetic / "product.yaml").read_text())["particle_sizes_um"] == [
        *range(1, 31),
        40,
        50,
    ]
    measured_config = _synthetic_config()
    measured_config["profile"] = "measured"
    measured = tmp_path / "measured"
    assert (
        cli_main(
            [
                "export-particle-sim",
                str(mixed_extraction),
                str(measured),
                "--config",
                str(_write_config(tmp_path, measured_config)),
            ]
        )
        == 2
    )
    assert not measured.exists()
    assert "unsupported" in capsys.readouterr().err


def test_export_write_failure_leaves_no_output_or_sibling(
    tmp_path: Path, mixed_extraction: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_copy(*_args, **_kwargs) -> None:
        raise OSError("injected copy failure")

    monkeypatch.setattr(particle_sim_adapter.shutil, "copyfile", fail_copy)
    output = tmp_path / "product"
    with pytest.raises(OSError, match="injected copy failure"):
        export_particle_sim(mixed_extraction, output, _write_config(tmp_path, _synthetic_config()))
    assert not output.exists()
    assert not list(tmp_path.glob(".product.*"))


def test_unsafe_generated_legacy_contact_id_rejected_before_output(tmp_path: Path) -> None:
    generated = _legacy_adapter_input(tmp_path / "input")
    extraction = tmp_path / "extraction"
    extract(generated, extraction)
    metadata_path = extraction / "manifest.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["contact_rules"][0]["layer"] = "CNT__UNSAFE"
    metadata_path.write_text(json.dumps(metadata))
    output = tmp_path / "product"
    with pytest.raises(ManifestError, match="unsafe generated contact_id"):
        export_particle_sim(extraction, output)
    assert not output.exists()
