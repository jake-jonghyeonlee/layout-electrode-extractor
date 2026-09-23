"""Reproducible, explicitly assumed RGB-node 600 px unit layout fixture."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 20) -> None:
    draw.line(points, fill=255, width=width, joint="curve")


def _via(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rectangle((x - 7, y - 7, x + 7, y + 7), fill=255)


def make_synthetic(output_dir: str | Path) -> dict:
    """Write a 600x600, 0.1 um/px assumed RGB-node stack and manifest."""
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    masks = root / "masks"
    masks.mkdir()
    layers: dict[str, tuple[str, np.ndarray]] = {}
    for layer, role in (
        ("GAT1", "GAT"),
        ("GAT2", "GAT"),
        ("ACTIVE", "ACTIVE"),
        ("OACTIVE", "OACTIVE"),
        ("CNT1", "CNT"),
        ("CNT2", "CNT"),
        ("METAL1", "METAL"),
    ):
        image = Image.new("L", (600, 600), 0)
        draw = ImageDraw.Draw(image)
        if layer == "GAT1":
            # Two local gates cross the red and green ACTIVE node channels.
            _line(draw, [(70, 285), (70, 315)])
            _line(draw, [(130, 285), (130, 315)])
            _line(draw, [(270, 365), (270, 395)])
            _line(draw, [(330, 365), (330, 395)])
        elif layer == "GAT2":
            # Two local gates cross the blue OACTIVE node channel.
            _line(draw, [(470, 455), (470, 485)])
            _line(draw, [(530, 455), (530, 485)])
        elif layer == "ACTIVE":
            # RGB branches each join one corresponding periodic METAL bus.
            _line(draw, [(100, 70), (100, 300), (40, 300), (160, 300)])
            _line(draw, [(300, 120), (300, 380), (240, 380), (360, 380)])
            # Separate full-height edge wire makes vertical seam behavior visible.
            _line(draw, [(20, 0), (20, 599)])
            _line(draw, [(580, 0), (580, 599)])
        elif layer == "OACTIVE":
            _line(draw, [(500, 170), (500, 470), (430, 470), (560, 470)])
        elif layer == "METAL1":
            # Three distinct horizontal buses; clipped endpoint pixels match at
            # left/right edges so repeating tiles join without a seam gap.
            _line(draw, [(0, 70), (599, 70)])   # R
            _line(draw, [(0, 120), (599, 120)])  # G
            _line(draw, [(0, 170), (599, 170)])  # B
            # Isolated source/drain landing pads on the opposite ends of nodes.
            for x, y in ((40, 300), (160, 300), (240, 380), (360, 380), (430, 470), (560, 470)):
                draw.rectangle((x - 16, y - 16, x + 16, y + 16), fill=255)
        elif layer == "CNT1":
            # Exactly one red and one green RGB bus via per unit, plus S/D vias.
            for x, y in ((100, 70), (300, 120), (40, 300), (160, 300), (240, 380), (360, 380)):
                _via(draw, x, y)
        elif layer == "CNT2":
            # Exactly one blue RGB bus via per unit, plus S/D vias.
            for x, y in ((500, 170), (430, 470), (560, 470)):
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
        "stack": ["GAT1", "GAT2", "ACTIVE", "OACTIVE", "METAL1"],
        "tr_pairs": [
            {"gat": "GAT1", "channel": "ACTIVE"},
            {"gat": "GAT2", "channel": "OACTIVE"},
        ],
        "contacts": [
            {"layer": "CNT1", "lower": "ACTIVE", "upper": "METAL1"},
            {"layer": "CNT2", "lower": "OACTIVE", "upper": "METAL1"},
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"input": str(root), "manifest": str(root / "manifest.json"), "shape_px": [600, 600]}
