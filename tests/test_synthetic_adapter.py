from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from layout_electrode_extractor.engine import extract
from layout_electrode_extractor.particle_sim_adapter import export_particle_sim
from layout_electrode_extractor.review import ReviewProject
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
