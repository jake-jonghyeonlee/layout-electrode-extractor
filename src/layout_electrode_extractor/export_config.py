"""Strict version-one process settings for particle-sim exports."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .schema import ManifestError

PARTICLE_SIZES = [*range(1, 31), 40, 50]
_ID = re.compile(r"[A-Za-z0-9_-]+\Z")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or "__" in value:
        raise ManifestError(f"{field} must be a safe ASCII ID without '__' or ':'")
    return value


def _fields(value: object, required: set[str], optional: set[str], field: str) -> dict:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ManifestError(f"{field} missing {sorted(missing)} or unknown {sorted(extra)}")
    return value


def _number(value: object, field: str, *, positive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ManifestError(f"{field} must be finite and positive")
    return result


def upper_mask_row(rows: list[dict], after: str, contacts: list[dict]) -> str | None:
    """The mask row directly above `after`, as particle-sim counts it, or None.

    Conductor rows and contact-bearing hole rows have masks in the particle-sim manifest;
    unmasked dielectrics and hole rows without contacts are skipped.
    """
    holes = {row["layer"] for row in contacts}
    ids = [row["id"] for row in rows]
    for row in rows[ids.index(after) + 1:]:
        if row["kind"] == "conductor" or (row["kind"] == "hole" and row["id"] in holes):
            return row["id"]
    return None


def _fab_layer(stage: dict, rows: list[dict], contacts: list[dict], field: str) -> str:
    """Fab density comes from the mask layer directly above the landing layer (2026-09-30)."""
    upper = upper_mask_row(rows, stage["after_layer"], contacts)
    given = stage.get("fab_distribution_layer")
    if given is not None:
        given = _identifier(given, f"{field}.fab_distribution_layer")
    if upper is None:
        if given is None:
            raise ManifestError(
                f"{field}: no mask layer above {stage['after_layer']}; "
                "set fab_distribution_layer explicitly"
            )
        return given
    if given is not None and given != upper:
        raise ManifestError(
            f"{field}.fab_distribution_layer must be {upper}, "
            f"the mask layer directly above {stage['after_layer']}"
        )
    return upper


def load_export_config(path: str | Path, meta: dict, contacts: list[dict]) -> dict:
    """Validate input completely before the adapter creates an output directory."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"invalid export config: {exc}") from exc
    _fields(
        config,
        {
            "schema_version",
            "profile",
            "process_stack",
            "source_stages",
            "contact_applicable_stages",
        },
        {"particle_sizes_um", "net_map", "excluded_pairs", "open_paths", "cno_open_relations"},
        "config",
    )
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ManifestError("config schema_version must be 1")
    profile = config["profile"]
    if not isinstance(profile, str) or profile not in {"synthetic", "measured"}:
        raise ManifestError("config profile must be synthetic or measured")
    for field in ("excluded_pairs", "open_paths", "cno_open_relations"):
        if field in config and not isinstance(config[field], list):
            raise ManifestError(f"{field} must be a list")
    if "net_map" in config and not isinstance(config["net_map"], dict):
        raise ManifestError("net_map must be an object")
    if not isinstance(config["process_stack"], list) or not config["process_stack"]:
        raise ManifestError("process_stack must be a nonempty list")
    if "physical_stack" not in meta:
        raise ManifestError("--config requires extraction physical_stack")
    rows = []
    ids = set()
    for index, value in enumerate(config["process_stack"]):
        field = f"process_stack[{index}]"
        row = _fields(
            value,
            {"id", "kind", "mask_layer", "material_type", "thickness_um", "patterned"},
            {"planarization_factor"},
            field,
        )
        row_id = _identifier(row["id"], f"{field}.id")
        if row_id in ids:
            raise ManifestError(f"duplicate process_stack id {row_id}")
        ids.add(row_id)
        kind = row["kind"]
        if not isinstance(kind, str) or kind not in {"conductor", "hole", "dielectric"}:
            raise ManifestError(f"{field}.kind is unsupported")
        material = row["material_type"]
        mask = row["mask_layer"]
        patterned = row["patterned"]
        if type(patterned) is not bool:
            raise ManifestError(f"{field}.patterned must be boolean")
        if kind in {"conductor", "hole"}:
            if mask != row_id or not patterned:
                raise ManifestError(
                    f"{field}: {kind} requires its own mask_layer and patterned=true"
                )
            if material != ("conductor" if kind == "conductor" else "inorganic"):
                raise ManifestError(f"{field}: material_type conflicts with {kind}")
        elif mask is not None or patterned or material not in {"inorganic", "organic"}:
            raise ManifestError(f"{field}: dielectric must be unmasked, unpatterned, insulating")
        _number(row["thickness_um"], f"{field}.thickness_um")
        if "planarization_factor" in row:
            factor = _number(
                row["planarization_factor"], f"{field}.planarization_factor", positive=False
            )
            if not 0 <= factor <= 1:
                raise ManifestError(f"{field}.planarization_factor must be in [0,1]")
        rows.append(row)
    masked = [row["id"] for row in rows if row["mask_layer"] is not None]
    conductors = [row["id"] for row in rows if row["kind"] == "conductor"]
    if masked != meta["physical_stack"] or conductors != meta["stack"]:
        raise ManifestError(
            "process_stack projection must match physical_stack and conductor stack"
        )
    kinds = {row["id"]: row["kind"] for row in rows}
    stack_order = {row["id"]: index for index, row in enumerate(rows)}
    for contact in contacts:
        hole, lower, upper = contact["layer"], contact["lower"], contact["upper"]
        if (
            kinds.get(hole) != "hole"
            or kinds.get(lower) != "conductor"
            or kinds.get(upper) != "conductor"
            or not stack_order[lower] < stack_order[hole] < stack_order[upper]
        ):
            raise ManifestError(f"unsupported contact topology for {hole}: wrong endpoints")
    if not isinstance(config["source_stages"], list):
        raise ManifestError("source_stages must be a list")
    stages = []
    stage_ids = set()
    previous_order = -1
    order = {row["id"]: index for index, row in enumerate(rows)}
    for index, value in enumerate(config["source_stages"]):
        field = f"source_stages[{index}]"
        stage = dict(_fields(
            value,
            {"step_id", "after_layer", "semantics", "surface_model"},
            {"fab_distribution_layer"},
            field,
        ))
        step_id = _identifier(stage["step_id"], f"{field}.step_id")
        after = _identifier(stage["after_layer"], f"{field}.after_layer")
        if step_id in stage_ids:
            raise ManifestError(f"duplicate source stage {step_id}")
        stage_ids.add(step_id)
        if after not in kinds or kinds[after] == "dielectric":
            raise ManifestError(f"{field}.after_layer must name a masked stack row")
        if order[after] <= previous_order:
            raise ManifestError(
                "source_stages must follow process_stack order without duplicate layers"
            )
        previous_order = order[after]
        if not isinstance(stage["semantics"], str) or stage["semantics"] not in {
            "after_pattern",
            "cnt_open_before_fill_approximation",
        }:
            raise ManifestError(f"{field}.semantics is unsupported")
        if stage["semantics"] == "after_pattern" and kinds[after] != "conductor":
            raise ManifestError(f"{field}: after_pattern must follow a conductor row")
        surface_model = stage["surface_model"]
        if not isinstance(surface_model, str) or surface_model not in {
            "flat", "conformal", "partial"
        }:
            raise ManifestError(f"{field}.surface_model must be flat, conformal or partial")
        if surface_model == "partial":
            # Match particle-sim's schema prerequisite, including unpatterned hole rows.
            for row in rows[: order[after] + 1]:
                if row["material_type"] != "conductor" and "planarization_factor" not in row:
                    raise ManifestError(
                        f"{field}: partial surface_model requires planarization_factor "
                        f"on process_stack row {row['id']} at or below {after}"
                    )
        if stage["semantics"] == "cnt_open_before_fill_approximation" and kinds[after] != "hole":
            raise ManifestError(f"{field}: CNT open approximation must follow a hole row")
        stage["fab_distribution_layer"] = _fab_layer(stage, rows, contacts, field)
        stages.append(stage)
    config["source_stages"] = stages  # carries each resolved fab_distribution_layer
    applicable = config["contact_applicable_stages"]
    if not isinstance(applicable, dict):
        raise ManifestError("contact_applicable_stages must be an object")
    holes = {row["layer"] for row in contacts}
    if set(applicable) != holes:
        raise ManifestError(
            "contact_applicable_stages must name exactly the contact-bearing hole layers"
        )
    for hole, selected in applicable.items():
        _identifier(hole, "contact_applicable_stages key")
        matching = [
            stage["step_id"]
            for stage in stages
            if stage["after_layer"] == hole
            and stage["semantics"] == "cnt_open_before_fill_approximation"
        ]
        if profile == "synthetic" and (len(matching) != 1 or selected != matching):
            raise ManifestError(f"{hole}: require exactly its CNT open approximation stage")
    if profile == "measured" and contacts:
        raise ManifestError("measured CNT open stage/contact physics is unsupported")
    if profile == "measured" and "net_map" not in config:
        raise ManifestError("measured profile requires an explicit net_map")
    sizes = config.get("particle_sizes_um", PARTICLE_SIZES if profile == "synthetic" else None)
    if not isinstance(sizes, list) or not sizes:
        raise ManifestError("particle_sizes_um must be a nonempty explicit list")
    converted = [_number(value, "particle_sizes_um entry") for value in sizes]
    if any(value not in PARTICLE_SIZES for value in converted) or any(
        b <= a for a, b in zip(converted, converted[1:], strict=False)
    ):
        raise ManifestError("particle_sizes_um must be a strictly increasing subset of 1..30,40,50")
    config["particle_sizes_um"] = converted
    return config


def product_stack(config: dict) -> list[dict]:
    rows = []
    for row in config["process_stack"]:
        product = {
            "layer_name": row["id"],
            "process_order": len(rows),
            "material_type": row["material_type"],
            "thickness_um": row["thickness_um"],
            "patterned": row["kind"] == "conductor",
        }
        if "planarization_factor" in row:
            product["planarization_factor"] = row["planarization_factor"]
        rows.append(product)
    return rows
