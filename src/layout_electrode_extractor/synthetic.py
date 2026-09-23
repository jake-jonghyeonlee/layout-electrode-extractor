"""Reproducible, explicitly assumed 600 px unit layout fixture."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 20) -> None:
    draw.line(points, fill=255, width=width, joint="curve")


def make_synthetic(output_dir: str | Path) -> dict:
    """Write a 600x600, 0.1 um/px synthetic stack input and extractor manifest."""
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
            _line(draw, [(150, 0), (150, 100), (190, 150), (190, 290), (150, 340), (150, 599)])
            _line(draw, [(410, 0), (410, 599)])
            _line(draw, [(0, 80), (80, 80), (100, 60)])
        elif layer == "GAT2":
            _line(draw, [(300, 0), (300, 599)])
            _line(draw, [(520, 0), (520, 599)])
        elif layer == "ACTIVE":
            _line(
                draw,
                [
                    (0, 210),
                    (70, 210),
                    (120, 190),
                    (210, 190),
                    (260, 230),
                    (350, 230),
                    (400, 200),
                    (530, 200),
                    (599, 220),
                ],
            )
            _line(draw, [(120, 190), (120, 130), (170, 100)])
            _line(draw, [(350, 230), (350, 290), (300, 320), (220, 320), (190, 290)])
            _line(draw, [(500, 200), (540, 160), (580, 160)])
            draw.ellipse((30, 400, 70, 440), fill=255)  # independent island
        elif layer == "OACTIVE":
            _line(
                draw,
                [
                    (0, 410),
                    (90, 410),
                    (140, 450),
                    (260, 450),
                    (300, 420),
                    (390, 420),
                    (450, 390),
                    (599, 390),
                ],
            )
            _line(draw, [(260, 450), (260, 510), (220, 540), (160, 540), (130, 510), (130, 450)])
            _line(draw, [(450, 390), (500, 340), (570, 340)])
            draw.ellipse((500, 500, 540, 540), fill=255)
        elif layer == "METAL1":
            _line(draw, [(60, 210), (540, 210)])
            _line(draw, [(80, 410), (520, 410)])
            _line(draw, [(180, 450), (220, 450)])
            # Independent conductor island and a cross-boundary winding trace.
            draw.rectangle((250, 70, 310, 85), fill=255)
            _line(draw, [(570, 520), (599, 520), (0, 520), (30, 500), (50, 480)])
        elif layer == "CNT1":
            for x, y in ((120, 210), (480, 210)):
                draw.rectangle((x - 7, y - 7, x + 7, y + 7), fill=255)
        elif layer == "CNT2":
            for x, y in ((200, 450), (400, 410)):
                draw.rectangle((x - 7, y - 7, x + 7, y + 7), fill=255)
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
