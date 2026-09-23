"""Strict manifest contract; all names become safe output path components."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """Input manifest or mask violates the extraction contract."""


_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_ROLES = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR", "CNT", "VIA", "OTHER"}
_HOLES = {"CNT", "VIA"}
_CONDUCTORS = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}


def _keys(value: object, required: set[str], optional: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise ManifestError(f"{where} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ManifestError(f"{where}: missing {sorted(missing)}, unknown {sorted(extra)}")
    return value


def _id(value: object, where: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ManifestError(f"{where} must be an ASCII ID matching {_ID.pattern}")
    return value


@dataclass(frozen=True)
class Layer:
    id: str
    path: Path
    role: str


@dataclass(frozen=True)
class Contact:
    layer: str
    lower: str
    upper: str
    holes: tuple[tuple[int, int], ...] | None = None


@dataclass(frozen=True)
class Manifest:
    path: Path
    pixel_size_um: float
    origin_um: tuple[float, float]
    connectivity: int
    layers: tuple[Layer, ...]
    stack: tuple[str, ...]
    tr_pairs: tuple[tuple[str, str], ...]
    contacts: tuple[Contact, ...]
    physical_stack: tuple[str, ...] | None = None


def load_manifest(path: str | Path) -> Manifest:
    """Load a JSON manifest with explicit stack, TR pairs and hole endpoints.

    Layer paths are relative to the manifest directory and cannot escape it, even
    through symlinks. Masks must be single-channel PNGs with values 0 and 255.
    """
    path = Path(path).resolve(strict=True)
    try:
        if path.stat().st_size > 1_000_000:
            raise ManifestError("manifest exceeds 1 MB")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read JSON manifest: {exc}") from exc
    data = _keys(
        data,
        {"schema_version", "pixel_size_um", "origin_um", "layers", "stack", "tr_pairs", "contacts"},
        {"connectivity", "physical_stack"},
        "manifest",
    )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ManifestError("schema_version must be 1")
    from math import isfinite

    scale = data["pixel_size_um"]
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (int, float))
        or not isfinite(scale)
        or scale <= 0
    ):
        raise ManifestError("pixel_size_um must be finite and positive")
    origin = data["origin_um"]
    if (
        not isinstance(origin, list)
        or len(origin) != 2
        or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
            for v in origin
        )
    ):
        raise ManifestError("origin_um must contain two finite numbers")
    connectivity = data.get("connectivity", 4)
    if type(connectivity) is not int or connectivity not in (4, 8):
        raise ManifestError("connectivity must be 4 or 8")
    rows = data["layers"]
    if not isinstance(rows, list) or not rows or len(rows) > 32:
        raise ManifestError("layers must contain 1..32 entries")
    layers = []
    seen = set()
    root = path.parent
    for index, row in enumerate(rows):
        row = _keys(row, {"id", "path", "role"}, set(), f"layers[{index}]")
        lid = _id(row["id"], f"layers[{index}].id")
        if lid in seen:
            raise ManifestError(f"duplicate layer ID {lid}")
        seen.add(lid)
        if not isinstance(row["role"], str) or row["role"] not in _ROLES:
            raise ManifestError(f"unknown role for {lid}")
        raw_path = row["path"]
        if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
            raise ManifestError(f"{lid}: path must be relative to manifest")
        layer_path = (root / raw_path).resolve(strict=True)
        if not layer_path.is_relative_to(root):
            raise ManifestError(f"{lid}: path escapes manifest directory")
        if layer_path.suffix.lower() != ".png" or not layer_path.is_file():
            raise ManifestError(f"{lid}: mask must be a PNG file")
        layers.append(Layer(lid, layer_path, row["role"]))
    roles = {layer.id: layer.role for layer in layers}
    stack = data["stack"]
    if not isinstance(stack, list) or not stack or any(not isinstance(v, str) for v in stack):
        raise ManifestError("stack must list conductor layer IDs in height order")
    if len(stack) != len(set(stack)) or set(stack) != {
        i for i, role in roles.items() if role in _CONDUCTORS
    }:
        raise ManifestError("stack must contain every conductor layer exactly once")
    physical_stack = None
    if "physical_stack" in data:
        physical_stack = data["physical_stack"]
        relevant = {i for i, role in roles.items() if role in _CONDUCTORS | _HOLES}
        if (
            not isinstance(physical_stack, list)
            or any(not isinstance(v, str) for v in physical_stack)
            or len(physical_stack) != len(relevant)
            or len(set(physical_stack)) != len(physical_stack)
            or set(physical_stack) != relevant
        ):
            raise ManifestError(
                "physical_stack must list every conductor and CNT/VIA layer exactly once"
            )
        if [lid for lid in physical_stack if roles[lid] in _CONDUCTORS] != stack:
            raise ManifestError("physical_stack conductor order must equal stack")
    pairs = data["tr_pairs"]
    if not isinstance(pairs, list) or not pairs or len(pairs) > 64:
        raise ManifestError("tr_pairs must contain 1..64 entries")
    tr_pairs = []
    for index, row in enumerate(pairs):
        row = _keys(row, {"gat", "channel"}, set(), f"tr_pairs[{index}]")
        gat, channel = row["gat"], row["channel"]
        if not isinstance(gat, str) or not isinstance(channel, str):
            raise ManifestError(f"tr_pairs[{index}] endpoints must be layer IDs")
        if roles.get(gat) != "GAT" or roles.get(channel) not in {"ACTIVE", "OACTIVE"}:
            raise ManifestError(f"tr_pairs[{index}] must name a GAT and ACTIVE/OACTIVE")
        if (gat, channel) in tr_pairs:
            raise ManifestError("duplicate TR source pair")
        tr_pairs.append((gat, channel))
    rows = data["contacts"]
    if not isinstance(rows, list):
        raise ManifestError("contacts must be a list")
    contacts = []
    for index, row in enumerate(rows):
        row = _keys(row, {"layer", "lower", "upper"}, {"holes"}, f"contacts[{index}]")
        layer, lower, upper = row["layer"], row["lower"], row["upper"]
        if any(not isinstance(value, str) for value in (layer, lower, upper)):
            raise ManifestError(f"contacts[{index}] endpoints must be layer IDs")
        if roles.get(layer) not in _HOLES or lower not in stack or upper not in stack:
            raise ManifestError(f"contacts[{index}] has invalid layer/endpoints")
        if stack.index(lower) >= stack.index(upper):
            raise ManifestError(f"contacts[{index}] endpoints violate stack order")
        if physical_stack is not None and not (
            physical_stack.index(lower) < physical_stack.index(layer) < physical_stack.index(upper)
        ):
            raise ManifestError(f"contacts[{index}] endpoints violate physical_stack order")
        seeds = row.get("holes")
        if "holes" in row:
            if not isinstance(seeds, list) or not seeds:
                raise ManifestError(f"contacts[{index}].holes must be a non-empty list")
            for seed in seeds:
                if (
                    not isinstance(seed, list)
                    or len(seed) != 2
                    or any(type(value) is not int or value < 0 for value in seed)
                ):
                    raise ManifestError(f"contacts[{index}].holes must contain pixel [x,y] seeds")
            seeds = tuple((x, y) for x, y in seeds)
        if any(c.layer == layer for c in contacts) and (
            seeds is None or any(c.layer == layer and c.holes is None for c in contacts)
        ):
            raise ManifestError(f"duplicate legacy contact rule for {layer}")
        contacts.append(Contact(layer, lower, upper, seeds))
    if {i for i, role in roles.items() if role in _HOLES} != {c.layer for c in contacts}:
        raise ManifestError("every CNT/VIA layer needs exactly one contact rule")
    return Manifest(
        path,
        float(scale),
        (float(origin[0]), float(origin[1])),
        connectivity,
        tuple(layers),
        tuple(stack),
        tuple(tr_pairs),
        tuple(contacts),
        tuple(physical_stack) if physical_stack is not None else None,
    )
