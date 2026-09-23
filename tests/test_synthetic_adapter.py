from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage

from layout_electrode_extractor.engine import extract
from layout_electrode_extractor.particle_sim_adapter import export_particle_sim
from layout_electrode_extractor.review import ReviewProject
from layout_electrode_extractor.schema import ManifestError
from layout_electrode_extractor.synthetic import make_synthetic


def test_synthetic_extract_and_particle_sim_export(tmp_path: Path) -> None:
    generated = Path(make_synthetic(tmp_path / "input")["manifest"])
    source = generated.parent
    manifest = json.loads(generated.read_text())
    assert manifest["pixel_size_um"] == 0.1
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


def test_synthetic_crossings_contacts_and_rgb_seams(tmp_path: Path) -> None:
    manifest = Path(make_synthetic(tmp_path / "source")["manifest"])
    source = manifest.parent
    raw = {
        name: np.asarray(Image.open(source / "masks" / f"{name}.png")) > 0
        for name in ("GAT1", "GAT2", "GAT3", "ACTIVE", "OACTIVE", "CNT1", "CNT2", "METAL1")
    }
    expected = {"GAT1_ACTIVE": 4, "GAT2_OACTIVE": 2, "GAT3_OACTIVE": 4}
    overlaps = {}
    tr_union = np.zeros((600, 600), dtype=bool)
    for gate in ("GAT1", "GAT2", "GAT3"):
        for channel in ("ACTIVE", "OACTIVE"):
            selected = raw[gate] & raw[channel]
            key = f"{gate}_{channel}"
            overlaps[key] = ndimage.label(selected)[1]
            assert not np.any(tr_union & selected), key
            tr_union |= selected
    assert {key: count for key, count in overlaps.items() if count} == expected
    assert ndimage.label(raw["GAT1"])[1] == 2  # R and B are separate wires.
    assert ndimage.label(raw["GAT2"])[1] == 1  # G is a third periodic bus.
    assert np.array_equal(raw["GAT1"][:, 0], raw["GAT1"][:, -1])
    assert np.array_equal(raw["GAT2"][:, 0], raw["GAT2"][:, -1])

    extracted = tmp_path / "extracted"
    result = extract(manifest, extracted)
    assert len(result["tr"]) == 40
    assert not result["issues"]
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
    for hole, lower, count in (("CNT1", "ACTIVE", 9), ("CNT2", "OACTIVE", 11)):
        raw_labels, raw_count = ndimage.label(raw[hole])
        cut_hole = np.asarray(Image.open(extracted / "cut_layers" / f"{hole}.png")) > 0
        cut_labels, cut_count = ndimage.label(cut_hole)
        cut_lower = np.asarray(Image.open(extracted / "cut_layers" / f"{lower}.png")) > 0
        cut_upper = np.asarray(Image.open(extracted / "cut_layers" / "METAL1.png")) > 0
        undeclared = {"GAT1", "GAT2", "GAT3", "ACTIVE", "OACTIVE"} - {lower}
        assert raw_count == cut_count == count
        assert np.array_equal(raw_labels > 0, cut_labels > 0)
        for index in range(1, count + 1):
            component = cut_labels == index
            assert np.any(component & cut_lower)
            assert np.any(component & cut_upper)
            assert np.any(component & raw[lower])
            assert np.any(component & raw["METAL1"])
            assert all(not np.any(component & raw[name]) for name in undeclared)
    assert sum(ndimage.label(raw[name])[1] for name in ("CNT1", "CNT2")) == 20

    # METAL1 has two separate top-to-bottom trunks. Their selected branches join
    # CNT1 pad ACTIVE(100,145) and CNT2 pads OACTIVE(460,235)/(460,540); all
    # other landing pads receive direct branches. Check the actual extracted masks.
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
                    and np.asarray(
                        Image.open(extracted / row["layers"]["METAL1"]["path"])
                    )[seam_y, x]
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
    manifest_path = Path(make_synthetic(path)["manifest"])
    manifest = json.loads(manifest_path.read_text())
    renames = {"ACTIVE": "ACT_A", "OACTIVE": "OACT_A", "METAL1": "MTL_TOP"}
    for layer in manifest["layers"]:
        layer["id"] = renames.get(layer["id"], layer["id"])
    manifest["stack"] = [renames.get(layer, layer) for layer in manifest["stack"]]
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
    manifest["layers"].append({"id": "MTL_MID", "path": "masks/MTL_MID.png", "role": "METAL"})
    Image.open(path / "masks" / "METAL1.png").save(path / "masks" / "MTL_MID.png")
    if add_ambiguous_active:
        manifest["layers"].append({"id": "ACT_B", "path": "masks/ACT_B.png", "role": "ACTIVE"})
        manifest["stack"].insert(manifest["stack"].index("OACT_A"), "ACT_B")
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
    manifest_path = Path(make_synthetic(tmp_path / "conductor-role-input")["manifest"])
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
