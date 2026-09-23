"""Review state, safe annotations, provenance and renamed export."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image

from .circuit import Circuit, load_circuit, suggest_matches


class ReviewError(ValueError):
    """Invalid review data or unsafe file operation."""


class StaleAnnotationsError(ReviewError):
    """Saved annotations belong to another extraction or circuit revision."""


_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_NET = re.compile(r"[A-Za-z0-9_.:+-]{1,128}\Z")
_TERMINALS = {"G", "S", "D", "B"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _require_dict(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        raise ReviewError(f"{where} must be an object")
    return value


def _valid_name(value: object, where: str) -> str:
    if not isinstance(value, str) or len(value) > 128 or value != value.strip():
        raise ReviewError(f"{where} must be a trimmed string of at most 128 characters")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} or c in "/\\" for c in value) or value in {
        ".",
        "..",
    }:
        raise ReviewError(f"{where} contains an unsafe path character")
    return value


def safe_slug(value: str) -> str:
    """Portable path component; display spelling stays in annotations."""
    normalized = unicodedata.normalize("NFKC", value)
    slug = "".join(c if c.isalnum() else "_" for c in normalized).strip("_")
    return slug[:80] or "unnamed"


def _valid_net(value: object, where: str) -> str:
    if not isinstance(value, str) or (value and not _NET.fullmatch(value)):
        raise ReviewError(f"{where} must be a simple net ID")
    return value


class ReviewProject:
    """One extraction directory with one bound annotation document."""

    def __init__(
        self,
        root: str | Path,
        circuit_path: str | Path | None = None,
        schematic_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ReviewError("extraction path must be a directory")
        self.metadata = self._read_metadata()
        self.allowed_assets = self._validate_assets()
        self.extraction_fingerprint = self._fingerprint()
        self.circuit_path = Path(circuit_path).resolve(strict=True) if circuit_path else None
        self.circuit: Circuit | None = (
            load_circuit(self.circuit_path) if self.circuit_path else None
        )
        self.circuit_fingerprint = self.circuit.source_sha256 if self.circuit else None
        self.schematic_path = self._check_schematic(schematic_path) if schematic_path else None
        self.schematic_fingerprint = (
            _sha(self.schematic_path.read_bytes()) if self.schematic_path else None
        )
        self.annotation_path = self.root / "annotations.json"
        self.annotations, self.revision = self._load_annotations()

    def _read_metadata(self) -> dict:
        path = self.root / "manifest.json"
        if path.stat().st_size > 10_000_000:
            raise ReviewError("extraction manifest exceeds 10 MB")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewError(f"cannot read extraction manifest: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ReviewError("unsupported extraction manifest schema")
        if not isinstance(data.get("electrodes"), list) or not isinstance(data.get("tr"), list):
            raise ReviewError("extraction manifest is missing objects")
        return data

    def _path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ReviewError("invalid artifact path")
        path = Path(relative)
        if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
            raise ReviewError("artifact path traversal")
        absolute = (self.root / path).resolve(strict=True)
        if not absolute.is_relative_to(self.root) or not absolute.is_file():
            raise ReviewError("artifact path escapes extraction")
        return absolute

    def _validate_assets(self) -> frozenset[str]:
        meta = self.metadata
        paths = {"manifest.json", "connectivity.json", "tr_union.png", "review/issues.json"}
        seen_e, seen_tr, layer_ids = set(), set(), set()
        for layer in meta.get("layers", []):
            if not isinstance(layer, dict):
                raise ReviewError("invalid extraction layer")
            lid = layer.get("id")
            if not isinstance(lid, str) or not _ID.fullmatch(lid) or lid in layer_ids:
                raise ReviewError("invalid or duplicate layer ID")
            layer_ids.add(lid)
            for field, expected in (
                ("raw_path", f"raw_layers/{lid}.png"),
                ("cut_path", f"cut_layers/{lid}.png"),
            ):
                if layer.get(field) != expected:
                    raise ReviewError(f"unsafe {field} for {lid}")
                paths.add(expected)
        for electrode in meta["electrodes"]:
            if not isinstance(electrode, dict):
                raise ReviewError("invalid electrode")
            eid = electrode.get("id")
            if not isinstance(eid, str) or not _ID.fullmatch(eid) or eid in seen_e:
                raise ReviewError("invalid or duplicate electrode ID")
            seen_e.add(eid)
            layers = _require_dict(electrode.get("layers"), f"electrode {eid} layers")
            for lid, item in layers.items():
                if lid not in layer_ids or not isinstance(item, dict):
                    raise ReviewError("invalid electrode layer")
                expected = f"electrodes/{eid}/{lid}.png"
                if item.get("path") != expected:
                    raise ReviewError("unsafe electrode mask path")
                paths.add(expected)
        for tr in meta["tr"]:
            if not isinstance(tr, dict):
                raise ReviewError("invalid TR")
            tid = tr.get("id")
            if not isinstance(tid, str) or not _ID.fullmatch(tid) or tid in seen_tr:
                raise ReviewError("invalid or duplicate TR ID")
            seen_tr.add(tid)
            expected = f"tr/{tid}/mask.png"
            if tr.get("path") != expected:
                raise ReviewError("unsafe TR mask path")
            paths.update((expected, f"tr/{tid}/metadata.json"))
        for relative in paths:
            self._path(relative)
        self.electrode_ids = frozenset(seen_e)
        self.tr_ids = frozenset(seen_tr)
        return frozenset(paths)

    def _fingerprint(self) -> str:
        digest = hashlib.sha256()
        for relative in sorted(self.allowed_assets):
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            with self._path(relative).open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        return digest.hexdigest()

    def _check_schematic(self, path: str | Path) -> Path:
        path = Path(path).resolve(strict=True)
        if path.stat().st_size > 20_000_000:
            raise ReviewError("schematic image exceeds 20 MB")
        with Image.open(path) as img:
            suffix_matches = (img.format == "PNG" and path.suffix.lower() == ".png") or (
                img.format == "JPEG" and path.suffix.lower() in {".jpg", ".jpeg"}
            )
            if not suffix_matches or max(img.size) > 8192 or img.width * img.height > 20_000_000:
                raise ReviewError("schematic must be PNG/JPEG and at most 20 million pixels")
            img.verify()
        return path

    def _blank_annotations(self) -> dict:
        return {
            "schema_version": 1,
            "extraction_fingerprint": self.extraction_fingerprint,
            "circuit_fingerprint": self.circuit_fingerprint,
            "schematic_fingerprint": self.schematic_fingerprint,
            "electrodes": {},
            "tr": {},
            "terminal_links": {},
        }

    def _load_annotations(self) -> tuple[dict, str]:
        if not self.annotation_path.exists():
            return self._blank_annotations(), ""
        if self.annotation_path.is_symlink() or self.annotation_path.stat().st_size > 1_000_000:
            raise ReviewError("unsafe annotations file")
        raw = self.annotation_path.read_bytes()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"invalid annotations JSON: {exc}") from exc
        self.validate_annotations(data)
        return data, _sha(raw)

    def validate_annotations(self, data: object) -> dict:
        data = _require_dict(data, "annotations")
        expected = set(self._blank_annotations())
        if (
            set(data) != expected
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
        ):
            raise ReviewError("unsupported annotations schema")
        for key, value in (
            ("extraction_fingerprint", self.extraction_fingerprint),
            ("circuit_fingerprint", self.circuit_fingerprint),
            ("schematic_fingerprint", self.schematic_fingerprint),
        ):
            if data[key] != value:
                raise StaleAnnotationsError(f"{key} changed; saved names require review")
        for kind, ids, fields in (
            ("electrodes", self.electrode_ids, {"name", "net"}),
            ("tr", self.tr_ids, {"name", "device_id"}),
        ):
            rows = _require_dict(data[kind], kind)
            names, slugs = set(), set()
            for item_id, row in rows.items():
                if item_id not in ids:
                    raise ReviewError(f"unknown {kind} ID {item_id}")
                row = _require_dict(row, f"{kind}.{item_id}")
                if set(row) != fields:
                    raise ReviewError(f"{kind}.{item_id} requires {sorted(fields)}")
                name = _valid_name(row["name"], f"{kind}.{item_id}.name")
                if name:
                    normalized = unicodedata.normalize("NFKC", name).casefold()
                    slug = safe_slug(name).casefold()
                    if normalized in names or slug in slugs:
                        raise ReviewError(f"duplicate {kind} name or folder slug: {name}")
                    names.add(normalized)
                    slugs.add(slug)
                if kind == "electrodes":
                    _valid_net(row["net"], f"{kind}.{item_id}.net")
                else:
                    device = row["device_id"]
                    if not isinstance(device, str) or (
                        device and (not self.circuit or device not in self.circuit.devices)
                    ):
                        raise ReviewError(f"unknown circuit device {device}")
        links = _require_dict(data["terminal_links"], "terminal_links")
        for tid, terminals in links.items():
            if tid not in self.tr_ids:
                raise ReviewError(f"unknown TR ID {tid}")
            terminals = _require_dict(terminals, f"terminal_links.{tid}")
            if set(terminals) - _TERMINALS:
                raise ReviewError("terminal must be G, S, D or B")
            assigned_device = data["tr"].get(tid, {}).get("device_id")
            if (
                assigned_device
                and self.circuit
                and "B" not in self.circuit.devices[assigned_device].terminals
                and "B" in terminals
            ):
                raise ReviewError("three-terminal device cannot have a body link")
            for terminal, row in terminals.items():
                row = _require_dict(row, f"terminal_links.{tid}.{terminal}")
                if set(row) != {"net", "electrodes"}:
                    raise ReviewError("terminal link requires net and electrodes")
                _valid_net(row["net"], "terminal net")
                ids = row["electrodes"]
                if not isinstance(ids, list) or len(ids) > len(self.electrode_ids):
                    raise ReviewError("terminal electrodes must be a bounded list")
                if any(not isinstance(eid, str) or eid not in self.electrode_ids for eid in ids):
                    raise ReviewError("unknown terminal electrode ID")
                if len(ids) != len(set(ids)):
                    raise ReviewError("duplicate terminal electrode ID")
        return data

    def save_annotations(self, data: dict, revision: str) -> str:
        self.validate_annotations(data)
        self._assert_fresh()
        if self.annotation_path.is_symlink():
            raise ReviewError("unsafe annotations file")
        current = _sha(self.annotation_path.read_bytes()) if self.annotation_path.exists() else ""
        if current != revision:
            raise ReviewError("annotations changed in another session; reload before saving")
        raw = _json_bytes(data)
        if len(raw) > 1_000_000:
            raise ReviewError("annotations exceed 1 MB")
        fd, temp_name = tempfile.mkstemp(prefix=".annotations-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.annotation_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        self.annotations = copy.deepcopy(data)
        self.revision = _sha(raw)
        return self.revision

    def _assert_fresh(self) -> None:
        if self._fingerprint() != self.extraction_fingerprint:
            raise StaleAnnotationsError("extraction changed while review was open")
        if self.circuit_path and _sha(self.circuit_path.read_bytes()) != self.circuit_fingerprint:
            raise StaleAnnotationsError("circuit table changed while review was open")
        if (
            self.schematic_path
            and _sha(self.schematic_path.read_bytes()) != self.schematic_fingerprint
        ):
            raise StaleAnnotationsError("schematic image changed while review was open")

    def state(self) -> dict:
        return {
            "metadata": self.metadata,
            "annotations": self.annotations,
            "revision": self.revision,
            "circuit": self.circuit.to_json() if self.circuit else None,
            "suggestions": suggest_matches(self.metadata, self.circuit, self.annotations),
            "schematic_available": self.schematic_path is not None,
        }

    def export(self, output_dir: str | Path) -> Path:
        """Copy a reviewed extraction with safe named folders and provenance."""
        self.validate_annotations(self.annotations)
        self._assert_fresh()
        if self.annotation_path.is_symlink():
            raise ReviewError("unsafe annotations file")
        current = _sha(self.annotation_path.read_bytes()) if self.annotation_path.exists() else ""
        if current != self.revision:
            raise ReviewError("annotations changed in another session; reload before export")
        saved = (
            json.loads(self.annotation_path.read_bytes())
            if self.annotation_path.exists()
            else self._blank_annotations()
        )
        if saved != self.annotations:
            raise ReviewError("save in-memory annotations before export")
        output = Path(output_dir).resolve()
        if output.exists() or output.is_relative_to(self.root) or self.root.is_relative_to(output):
            raise ReviewError("export output must be a new directory outside the extraction")
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
        try:
            metadata = copy.deepcopy(self.metadata)
            for relative in self.allowed_assets:
                if relative == "manifest.json" or relative.startswith(("electrodes/", "tr/")):
                    continue
                target = temp / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._path(relative), target)
            for electrode in metadata["electrodes"]:
                eid = electrode["id"]
                name = self.annotations["electrodes"].get(eid, {}).get("name", "")
                folder = f"electrodes/{eid}__{safe_slug(name or eid)}"
                electrode["name"] = name
                electrode["net"] = self.annotations["electrodes"].get(eid, {}).get("net", "")
                for item in electrode["layers"].values():
                    source = item["path"]
                    new_path = f"{folder}/{Path(source).name}"
                    (temp / folder).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self._path(source), temp / new_path)
                    item["path"] = new_path
            for tr in metadata["tr"]:
                tid = tr["id"]
                row = self.annotations["tr"].get(tid, {})
                name = row.get("name", "")
                folder = f"tr/{tid}__{safe_slug(name or tid)}"
                source = tr["path"]
                tr["path"] = f"{folder}/mask.png"
                tr["name"] = name
                tr["circuit_device_id"] = row.get("device_id", "")
                (temp / folder).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._path(source), temp / tr["path"])
                (temp / folder / "metadata.json").write_bytes(_json_bytes(tr))
            metadata["naming_complete"] = all(
                self.annotations[kind].get(item["id"], {}).get("name")
                for kind, key in (("electrodes", "electrodes"), ("tr", "tr"))
                for item in metadata[key]
            )
            metadata["review_provenance"] = {
                "extraction_fingerprint": self.extraction_fingerprint,
                "circuit_fingerprint": self.circuit_fingerprint,
                "schematic_fingerprint": self.schematic_fingerprint,
                "annotation_sha256": _sha(_json_bytes(self.annotations)),
            }
            if self.circuit_path:
                circuit_file = f"review/circuit{self.circuit_path.suffix.lower()}"
                shutil.copyfile(self.circuit_path, temp / circuit_file)
                metadata["review_provenance"]["circuit_path"] = circuit_file
            if self.schematic_path:
                image_file = f"review/schematic{self.schematic_path.suffix.lower()}"
                shutil.copyfile(self.schematic_path, temp / image_file)
                metadata["review_provenance"]["schematic_path"] = image_file
            (temp / "manifest.json").write_bytes(_json_bytes(metadata))
            (temp / "annotations.json").write_bytes(_json_bytes(self.annotations))
            os.replace(temp, output)
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        return output
