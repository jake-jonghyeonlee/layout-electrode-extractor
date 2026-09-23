"""Reproducible, explicitly assumed orthogonal RGB crossing fixture."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]]) -> None:
    draw.line(points, fill=255, width=20, joint="curve")


def _via(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rectangle((x - 7, y - 7, x + 7, y + 7), fill=255)


# Every landing lies within one channel segment and away from all TR intersections.
ACTIVE_LANDINGS = tuple((x, y) for x in (100, 180) for y in (55, 145, 255, 350)) + ((140, 260),)
OACTIVE_LANDINGS = tuple((x, y) for x in (380, 460) for y in (165, 235, 390, 460, 540)) + (
    (420, 460),
)


def make_synthetic(output_dir: str | Path) -> dict:
    """Write a 600x600 unit at 0.1 um/px with ten orthogonal TR crossings."""
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    masks = root / "masks"
    masks.mkdir()
    layers: dict[str, tuple[str, np.ndarray]] = {}
    for layer, role in (
        ("GAT1", "GAT"),
        ("GAT2", "GAT"),
        ("GAT3", "GAT"),
        ("ACTIVE", "ACTIVE"),
        ("OACTIVE", "OACTIVE"),
        ("CNT1", "CNT"),
        ("CNT2", "CNT"),
        ("METAL1", "METAL"),
    ):
        image = Image.new("L", (600, 600), 0)
        draw = ImageDraw.Draw(image)
        if layer == "GAT1":
            # R and B are distinct periodic gate nets, even though they share a layer.
            for y in (100, 300):
                _line(draw, [(0, y), (599, y)])
        elif layer == "GAT2":
            _line(draw, [(0, 200), (599, 200)])  # periodic G bus
        elif layer == "GAT3":
            # Local gate branches cross OACTIVE twice each.
            for y in (420, 500):
                _line(draw, [(340, y), (500, y)])
        elif layer == "ACTIVE":
            for x in (100, 180):
                _line(draw, [(x, 40), (x, 150)])
                _line(draw, [(x, 250), (x, 360)])
            _line(draw, [(100, 260), (180, 260)])
        elif layer == "OACTIVE":
            for x in (380, 460):
                _line(draw, [(x, 160), (x, 240)])
                _line(draw, [(x, 390), (x, 560)])
            _line(draw, [(380, 460), (460, 460)])
        elif layer == "METAL1":
            # Existing isolated landing pads create only declared channel-to-metal paths.
            for x, y in ACTIVE_LANDINGS + OACTIVE_LANDINGS:
                draw.rectangle((x - 16, y - 16, x + 16, y + 16), fill=255)
            # Two independent vertical trunks repeat through both horizontal seams.
            # Keep them outside every GAT/channel overlap (TR) footprint.
            _line(draw, [(40, 0), (40, 599)])
            _line(draw, [(560, 0), (560, 599)])
            # The left trunk joins one CNT1 pad; the right trunk joins two CNT2 pads.
            # Other pads have no direct metal branch. GAT crossings are not contacts.
            _line(draw, [(40, 145), (100, 145)])
            _line(draw, [(560, 235), (460, 235)])
            _line(draw, [(560, 540), (460, 540)])
        elif layer == "CNT1":
            for x, y in ACTIVE_LANDINGS:
                _via(draw, x, y)
        elif layer == "CNT2":
            for x, y in OACTIVE_LANDINGS:
                _via(draw, x, y)
        layers[layer] = (role, np.asarray(image, dtype=np.uint8))

    for layer, (_, pixels) in layers.items():
        Image.fromarray(pixels, mode="L").save(masks / f"{layer}.png")

    manifest = {
        "schema_version": 1,
        "pixel_size_um": 0.1,
        "origin_um": [0.0, 0.0],
        "connectivity": 4,
        "layers": [
            {"id": layer, "path": f"masks/{layer}.png", "role": role}
            for layer, (role, _) in layers.items()
        ],
        "stack": ["GAT1", "GAT2", "GAT3", "ACTIVE", "OACTIVE", "METAL1"],
        "tr_pairs": [
            {"gat": "GAT1", "channel": "ACTIVE"},
            {"gat": "GAT2", "channel": "OACTIVE"},
            {"gat": "GAT3", "channel": "OACTIVE"},
        ],
        "contacts": [
            {"layer": "CNT1", "lower": "ACTIVE", "upper": "METAL1"},
            {"layer": "CNT2", "lower": "OACTIVE", "upper": "METAL1"},
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"input": str(root), "manifest": str(root / "manifest.json"), "shape_px": [600, 600]}
