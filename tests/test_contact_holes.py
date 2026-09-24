import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from layout_electrode_extractor import ManifestError, extract
from layout_electrode_extractor.particle_sim_adapter import export_particle_sim
from layout_electrode_extractor.review import ReviewProject


def _fixture(root: Path) -> tuple[Path, dict]:
    root.mkdir()
    masks = {name: np.zeros((7, 7), dtype=np.uint8) for name in (
        "GAT", "ACTIVE", "OACTIVE", "METAL", "CNT"
    )}
    # The first raw hole is cut in two; its seed is itself removed by the TR.
    masks["CNT"][3, 2:5] = 255
    masks["GAT"][3, 3] = masks["ACTIVE"][3, 3] = 255
    masks["ACTIVE"][3, 2] = masks["ACTIVE"][3, 4] = 255
    masks["METAL"][3, 2] = masks["METAL"][3, 4] = 255
    masks["CNT"][5, 5] = masks["OACTIVE"][5, 5] = masks["METAL"][5, 5] = 255
    for name, mask in masks.items():
        Image.fromarray(mask).save(root / f"{name}.png")
    data = {
        "schema_version": 1,
        "pixel_size_um": 0.1,
        "origin_um": [0, 0],
        "layers": [
            {"id": name, "path": f"{name}.png", "role": name}
            for name in masks
        ],
        "stack": ["GAT", "ACTIVE", "OACTIVE", "METAL"],
        "tr_pairs": [{"gat": "GAT", "channel": "ACTIVE"}],
        "contacts": [
            {"layer": "CNT", "lower": "ACTIVE", "upper": "METAL", "holes": [[3, 3]]},
            {"layer": "CNT", "lower": "OACTIVE", "upper": "METAL", "holes": [[5, 5]]},
        ],
    }
    path = root / "input.json"
    path.write_text(json.dumps(data))
    return path, data


def _extract(root: Path, data: dict, output: Path) -> dict:
    (root / "input.json").write_text(json.dumps(data))
    return extract(root / "input.json", output)


def test_mixed_pairs_cut_split_provenance_review_and_adapter_rejection(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    out = tmp_path / "out"
    meta = extract(path, out)
    assert not np.asarray(Image.open(out / "cut_layers/CNT.png"))[3, 3]
    components = meta["contact_holes"]["components"]
    assert len(components) == 3
    assert len({row["raw_component"] for row in components if row["seed"] == [3, 3]}) == 1
    assert len([row for row in components if row["seed"] == [3, 3]]) == 2
    assert {row["lower"] for row in components} == {"ACTIVE", "OACTIVE"}
    assert all(row["contact_rule_index"] in (0, 1) for row in components)
    assert all(row["lower"] in {"ACTIVE", "OACTIVE"} for row in meta["contact_holes"]["instances"])
    assert not any(
        "ACTIVE" in electrode["layers"] and "OACTIVE" in electrode["layers"]
        for electrode in meta["electrodes"]
    )
    assert not any(issue["type"] == "missing_endpoint_contact" for issue in meta["issues"])
    project = ReviewProject(out)
    reviewed = project.export(tmp_path / "reviewed")
    assert json.loads((reviewed / "manifest.json").read_text())["contact_holes"] == meta[
        "contact_holes"
    ]
    with pytest.raises(ManifestError, match="one endpoint pair per physical"):
        export_particle_sim(out, tmp_path / "sim")
    assert not (tmp_path / "sim").exists()


def test_single_seeded_pair_can_export(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    cnt = np.asarray(Image.open(path.parent / "CNT.png")).copy()
    cnt[5, 5] = 0
    Image.fromarray(cnt).save(path.parent / "CNT.png")
    data["contacts"] = [data["contacts"][0]]
    meta = _extract(path.parent, data, tmp_path / "single")
    assert meta["contact_rules"][0]["holes"] == [[3, 3]]
    export_particle_sim(tmp_path / "single", tmp_path / "sim")
    product = json.loads((tmp_path / "sim" / "product.yaml").read_text())
    assert len(product["contacts"]) == 1
    assert product["contacts"][0]["lower_layer"] == "ACTIVE"
    diagnostics = json.loads((tmp_path / "sim" / "adapter-provenance.json").read_text())[
        "physical_hole_diagnostics"
    ]
    assert len(diagnostics) == 4
    assert all(row["raw_pixels"] == 3 and row["cut_pixels"] == 2 for row in diagnostics)
    assert all("hole_in_tr" in row["diagnostic_codes"] for row in diagnostics)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["contacts"][1].update(holes=[]), "non-empty"),
        (lambda data: data["contacts"][1].update(holes=None), "non-empty"),
        (lambda data: data["contacts"][1].update(holes=[[0, 0]]), "outside a raw hole"),
        (lambda data: data["contacts"][1].update(holes=[[7, 0]]), "outside a raw hole"),
        (lambda data: data["contacts"][1].update(holes=[[True, 5]]), "pixel"),
        (lambda data: data["contacts"][1].update(holes=[[3, 3]]), "duplicate or ambiguous"),
        (lambda data: data["contacts"][0].update(holes=[[3, 3], [3, 3]]), "duplicate or ambiguous"),
        (lambda data: data["contacts"].pop(), "unassigned"),
        (lambda data: data["contacts"][1].pop("holes"), "duplicate legacy"),
        (lambda data: data["contacts"][1].update(lower="METAL", upper="OACTIVE"), "stack order"),
    ],
)
def test_invalid_seed_assignments(tmp_path: Path, mutate, message: str) -> None:
    path, data = _fixture(tmp_path / "unit")
    mutate(data)
    with pytest.raises(ManifestError, match=message):
        _extract(path.parent, data, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_missing_endpoint_diagnostic_uses_each_hole_pair(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    mask = np.asarray(Image.open(path.parent / "OACTIVE.png")).copy()
    mask[5, 5] = 0
    Image.fromarray(mask).save(path.parent / "OACTIVE.png")
    meta = extract(path, tmp_path / "out")
    missing = [issue for issue in meta["issues"] if issue["type"] == "missing_endpoint_contact"]
    assert missing
    assert {issue["lower"] for issue in missing} == {"OACTIVE"}
    assert all(issue["endpoint_counts"]["OACTIVE"] == 0 for issue in missing)


def test_fully_tr_removed_hole_has_no_conductive_instance(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    for name in ("GAT", "ACTIVE"):
        mask = np.asarray(Image.open(path.parent / f"{name}.png")).copy()
        mask[5, 5] = 255
        Image.fromarray(mask).save(path.parent / f"{name}.png")
    meta = extract(path, tmp_path / "out")
    assert len(meta["contact_holes"]["raw_components"]) == 2
    assert len(meta["contact_holes"]["components"]) == 2
    assert all(row["seed"] == [3, 3] for row in meta["contact_holes"]["components"])
    assert not np.asarray(Image.open(tmp_path / "out" / "cut_layers/CNT.png"))[5, 5]
    assert all(row["lower"] == "ACTIVE" for row in meta["contact_holes"]["instances"])


def test_periodic_boundary_hole_pair_conflict_and_identity(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    for name in ("CNT", "ACTIVE", "METAL"):
        mask = np.asarray(Image.open(path.parent / f"{name}.png")).copy()
        mask[1, 0] = mask[1, 6] = 255
        Image.fromarray(mask).save(path.parent / f"{name}.png")
    data["contacts"][0]["holes"].extend([[0, 1], [6, 1]])
    meta = _extract(path.parent, data, tmp_path / "same")
    assert any(
        np.asarray(Image.open(tmp_path / "same" / item["layers"]["CNT"]["path"]))[1, 6]
        and np.asarray(Image.open(tmp_path / "same" / item["layers"]["CNT"]["path"]))[1, 7]
        for item in meta["electrodes"] if "CNT" in item["layers"]
    )
    data["contacts"][0]["holes"].remove([6, 1])
    data["contacts"][1]["holes"].append([6, 1])
    with pytest.raises(ManifestError, match="conflicting endpoint pairs"):
        _extract(path.parent, data, tmp_path / "conflict")
    data["contacts"][1]["lower"] = "ACTIVE"
    same_pair = _extract(path.parent, data, tmp_path / "same-pair-rules")
    assert any(
        row["contact_rule_indices"] == [0, 1]
        for row in same_pair["contact_holes"]["instances"]
    )


def test_legacy_contact_rule_keeps_output_semantics(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path / "unit")
    data["contacts"] = [{"layer": "CNT", "lower": "ACTIVE", "upper": "METAL"}]
    meta = _extract(path.parent, data, tmp_path / "legacy")
    assert meta["contact_rules"] == data["contacts"]
    assert all(row["lower"] == "ACTIVE" for row in meta["contact_holes"]["components"])
    assert any(
        issue["endpoint_counts"].get("ACTIVE") == 0
        for issue in meta["issues"]
        if "endpoint_counts" in issue
    )
