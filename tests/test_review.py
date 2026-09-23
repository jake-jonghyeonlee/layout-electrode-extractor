import copy
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest
from PIL import Image

from layout_electrode_extractor import extract
from layout_electrode_extractor.circuit import CircuitError, load_circuit, suggest_matches
from layout_electrode_extractor.review import (
    ReviewError,
    ReviewProject,
    StaleAnnotationsError,
)
from layout_electrode_extractor.server import ReviewServer


def make_extraction(tmp_path: Path) -> Path:
    unit = tmp_path / "unit"
    unit.mkdir()
    masks = {name: np.zeros((7, 7), dtype=np.uint8) for name in ("GAT", "ACTIVE", "METAL")}
    masks["GAT"][3, 2:5] = 255
    masks["ACTIVE"][2:5, 3] = 255
    masks["METAL"][5, 5] = 255
    for name, values in masks.items():
        Image.fromarray(values).save(unit / f"{name}.png")
    manifest = {
        "schema_version": 1,
        "pixel_size_um": 0.1,
        "origin_um": [0, 0],
        "layers": [{"id": name, "path": f"{name}.png", "role": name} for name in masks],
        "stack": list(masks),
        "tr_pairs": [{"gat": "GAT", "channel": "ACTIVE"}],
        "contacts": [],
    }
    path = unit / "input.json"
    path.write_text(json.dumps(manifest))
    output = tmp_path / "extraction"
    extract(path, output)
    return output


def make_circuit(tmp_path: Path) -> Path:
    path = tmp_path / "circuit.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "devices": [
                    {
                        "id": "M1",
                        "channel_role": "ACTIVE",
                        "terminals": {"G": "NG", "S": "NS", "D": "ND", "B": "NB"},
                    },
                    {
                        "id": "M2",
                        "channel_role": "ACTIVE",
                        "terminals": {"G": "NG", "S": "NX", "D": "NY", "B": "NB"},
                    },
                ],
            }
        )
    )
    return path


def test_annotations_reload_named_export_and_provenance(tmp_path):
    root = make_extraction(tmp_path)
    circuit = make_circuit(tmp_path)
    schematic = tmp_path / "schematic.png"
    Image.new("RGB", (12, 8), "white").save(schematic)
    project = ReviewProject(root, circuit, schematic)
    data = copy.deepcopy(project.annotations)
    first, second = [item["id"] for item in project.metadata["electrodes"][:2]]
    tid = project.metadata["tr"][0]["id"]
    data["electrodes"][first] = {"name": "전원", "net": "NG"}
    data["electrodes"][second] = {"name": "Node B", "net": ""}
    data["tr"][tid] = {"name": "T1", "device_id": "M1"}
    data["terminal_links"][tid] = {
        "G": {"net": "NG", "electrodes": [first, second]},
        "S": {"net": "NS", "electrodes": []},
    }
    revision = project.save_annotations(data, project.revision)
    assert revision
    reloaded = ReviewProject(root, circuit, schematic)
    assert reloaded.annotations == data
    assert reloaded.revision == revision
    output = reloaded.export(tmp_path / "named")
    exported = json.loads((output / "manifest.json").read_text())
    assert exported["review_provenance"]["extraction_fingerprint"] == project.extraction_fingerprint
    assert (output / exported["review_provenance"]["circuit_path"]).is_file()
    assert (output / exported["review_provenance"]["schematic_path"]).is_file()
    assert exported["electrodes"][0]["name"] == "전원"
    assert "__전원/" in exported["electrodes"][0]["layers"]["GAT"]["path"]
    assert (output / exported["electrodes"][0]["layers"]["GAT"]["path"]).is_file()
    assert (output / "raw_layers/GAT.png").read_bytes() == (
        root / "raw_layers/GAT.png"
    ).read_bytes()
    assert json.loads((output / "annotations.json").read_text()) == data
    assert exported["naming_complete"] is False


def test_stale_extraction_and_circuit_rejected(tmp_path):
    root = make_extraction(tmp_path)
    circuit = make_circuit(tmp_path)
    project = ReviewProject(root, circuit)
    project.save_annotations(project.annotations, project.revision)
    circuit.write_text(circuit.read_text() + "\n")
    with pytest.raises(StaleAnnotationsError, match="circuit"):
        ReviewProject(root, circuit)
    circuit.write_text(circuit.read_text().rstrip())
    root.joinpath("cut_layers/GAT.png").write_bytes(b"changed")
    with pytest.raises(StaleAnnotationsError, match="extraction"):
        ReviewProject(root, circuit)


def test_name_collisions_paths_revision_and_unknown_ids(tmp_path):
    root = make_extraction(tmp_path)
    project = ReviewProject(root)
    first, second = [item["id"] for item in project.metadata["electrodes"][:2]]
    data = copy.deepcopy(project.annotations)
    data["electrodes"][first] = {"name": "Node A", "net": ""}
    data["electrodes"][second] = {"name": "Node_A", "net": ""}
    with pytest.raises(ReviewError, match="duplicate"):
        project.save_annotations(data, project.revision)
    data["electrodes"][second]["name"] = "../outside"
    with pytest.raises(ReviewError, match="unsafe"):
        project.save_annotations(data, project.revision)
    data["electrodes"][second]["name"] = "Node B"
    revision = project.save_annotations(data, project.revision)
    with pytest.raises(ReviewError, match="another session"):
        project.save_annotations(data, "wrong revision")
    assert revision == project.revision
    with pytest.raises(ReviewError, match="new directory outside"):
        project.export(root / "nested")
    project.annotations["electrodes"][first]["name"] = "Unsaved"
    with pytest.raises(ReviewError, match="save in-memory"):
        project.export(tmp_path / "unsaved")
    project.annotations["electrodes"][first]["name"] = "Node A"
    bad = copy.deepcopy(data)
    tid = project.metadata["tr"][0]["id"]
    bad["terminal_links"][tid] = {"G": {"net": "N", "electrodes": ["E99999"]}}
    with pytest.raises(ReviewError, match="unknown terminal"):
        project.save_annotations(bad, revision)
    metadata = json.loads((root / "manifest.json").read_text())
    metadata["electrodes"][0]["layers"]["GAT"]["path"] = "../../secret.png"
    (root / "manifest.json").write_text(json.dumps(metadata))
    with pytest.raises(ReviewError, match="unsafe electrode"):
        ReviewProject(root)


def test_circuit_json_csv_and_anchored_suggestions(tmp_path):
    path = make_circuit(tmp_path)
    circuit = load_circuit(path)
    csv_path = tmp_path / "circuit.csv"
    csv_path.write_text(
        "device,terminal,net,channel_role\n"
        "M1,G,NG,ACTIVE\nM1,S,NS,ACTIVE\nM1,D,ND,ACTIVE\nM1,B,NB,ACTIVE\n"
    )
    assert load_circuit(csv_path).devices["M1"].terminals["G"] == "NG"
    metadata = {
        "layers": [{"id": "GAT", "role": "GAT"}, {"id": "ACTIVE", "role": "ACTIVE"}],
        "tr": [
            {
                "id": "TR1",
                "source_pair": {"gat": "GAT", "channel": "ACTIVE"},
                "terminal_adjacency": [
                    {"layer": "GAT", "electrode_id": "E1"},
                    {"layer": "GAT", "electrode_id": "E2"},
                    {"layer": "ACTIVE", "electrode_id": "E3"},
                ],
            },
            {
                "id": "TR2",
                "source_pair": {"gat": "GAT", "channel": "ACTIVE"},
                "terminal_adjacency": [{"layer": "GAT", "electrode_id": "E2"}],
            },
        ],
    }
    annotations = {
        "electrodes": {},
        "tr": {"TR1": {"name": "Anchor", "device_id": "M1"}},
        "terminal_links": {},
    }
    result = suggest_matches(metadata, circuit, annotations)
    assert result["electrodes"]["E1"]["net_candidates"] == ["NG"]
    assert result["electrodes"]["E2"]["net_candidates"] == ["NG"]
    assert result["electrodes"]["E3"]["net_candidates"] == ["ND", "NS"]
    assert result["tr"]["TR2"]["device_candidates"] == ["M1", "M2"]
    assert result["tr"]["TR2"]["status"] == "ambiguous"
    circuit.devices["M1"].terminals["G"] = "OTHER"
    result = suggest_matches(metadata, circuit, annotations)
    assert result["tr"]["TR2"]["device_candidates"] == ["M1"]
    assert result["tr"]["TR2"]["status"] == "unique_candidate"
    assert annotations["tr"].get("TR2") is None
    path.write_text('{"schema_version":1,"devices":[{"id":"M1","terminals":{}}]}')
    with pytest.raises(CircuitError, match="G, S and D"):
        load_circuit(path)


def test_three_terminal_tft_preserves_optional_body_boundary(tmp_path):
    root = make_extraction(tmp_path)
    path = tmp_path / "tft.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "devices": [{"id": "TFT1", "terminals": {"G": "VG", "S": "VS", "D": "VD"}}],
            }
        )
    )
    circuit = load_circuit(path)
    assert set(circuit.devices["TFT1"].terminals) == {"G", "S", "D"}
    assert set(circuit.to_json()["devices"][0]["terminals"]) == {"G", "S", "D"}
    csv_path = tmp_path / "tft.csv"
    csv_path.write_text("device,terminal,net\nTFT1,G,VG\nTFT1,S,VS\nTFT1,D,VD\n")
    assert set(load_circuit(csv_path).devices["TFT1"].terminals) == {"G", "S", "D"}
    project = ReviewProject(root, path)
    tid = project.metadata["tr"][0]["id"]
    data = copy.deepcopy(project.annotations)
    data["tr"][tid] = {"name": "Display TFT", "device_id": "TFT1"}
    data["terminal_links"][tid] = {
        "G": {"net": "VG", "electrodes": []},
        "S": {"net": "VS", "electrodes": []},
        "D": {"net": "VD", "electrodes": []},
    }
    project.save_annotations(data, project.revision)
    assert "B" not in project.annotations["terminal_links"][tid]
    bad = copy.deepcopy(data)
    bad["terminal_links"][tid]["B"] = {"net": "VB", "electrodes": []}
    with pytest.raises(ReviewError, match="cannot have a body"):
        project.validate_annotations(bad)


def test_http_review_smoke_and_security(tmp_path):
    root = make_extraction(tmp_path)
    schematic = tmp_path / "schematic.png"
    Image.new("RGB", (12, 8), "white").save(schematic)
    project = ReviewProject(root, schematic_path=schematic)
    server = ReviewServer(("127.0.0.1", 0), project)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/") as response:
            assert b"Layout electrode review" in response.read()
        with urlopen(base + "/static/app.js") as response:
            assert b"terminal_adjacency" in response.read()
        with urlopen(base + "/api/state") as response:
            state = json.load(response)
        assert state["metadata"]["output_shape_px"] == [14, 14]
        assert state["schematic_available"] is True
        with urlopen(base + "/api/schematic") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"
        mask = state["metadata"]["electrodes"][0]["layers"]["GAT"]["path"]
        with urlopen(base + "/api/asset/" + mask.replace("/", "%2F")) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"
        body = json.dumps(
            {"annotations": state["annotations"], "revision": state["revision"]}
        ).encode()
        request = Request(
            base + "/api/save",
            body,
            {"Content-Type": "application/json", "X-Review-Token": state["csrf"]},
        )
        with urlopen(request) as response:
            assert json.load(response)["revision"]
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/save", body, {"Content-Type": "application/json"}))
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/asset/..%2Fsecret.png")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
