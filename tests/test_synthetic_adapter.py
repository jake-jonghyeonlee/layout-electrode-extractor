from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

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
    assert len(manifest["tr_pairs"]) == 2
    assert {row["id"] for row in manifest["layers"]} == {
        "GAT1",
        "GAT2",
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
