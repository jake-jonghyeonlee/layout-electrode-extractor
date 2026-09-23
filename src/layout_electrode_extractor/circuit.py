"""Explicit circuit tables and conservative anchored layout suggestions."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


class CircuitError(ValueError):
    """The circuit table does not meet its documented contract."""


_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_NET = re.compile(r"[A-Za-z0-9_.:+-]{1,128}\Z")
_REQUIRED_TERMINALS = {"G", "S", "D"}
_TERMINALS = _REQUIRED_TERMINALS | {"B"}


@dataclass(frozen=True)
class Device:
    id: str
    terminals: dict[str, str]
    channel_role: str | None


@dataclass(frozen=True)
class Circuit:
    devices: dict[str, Device]
    nets: frozenset[str]
    source_sha256: str

    def to_json(self) -> dict:
        return {
            "schema_version": 1,
            "devices": [
                {
                    "id": device.id,
                    "terminals": device.terminals,
                    "channel_role": device.channel_role,
                }
                for device in self.devices.values()
            ],
            "nets": sorted(self.nets),
            "source_sha256": self.source_sha256,
        }


def _device(row: object, index: int) -> Device:
    if not isinstance(row, dict) or set(row) - {"id", "terminals", "channel_role"}:
        raise CircuitError(f"devices[{index}] has invalid fields")
    device_id = row.get("id")
    if not isinstance(device_id, str) or not _ID.fullmatch(device_id):
        raise CircuitError(f"devices[{index}].id is invalid")
    terminals = row.get("terminals")
    if not isinstance(terminals, dict) or set(terminals) not in (
        _REQUIRED_TERMINALS,
        _TERMINALS,
    ):
        raise CircuitError(f"devices[{index}] needs G, S and D nets, with optional B")
    for terminal, net in terminals.items():
        if not isinstance(net, str) or not _NET.fullmatch(net):
            raise CircuitError(f"devices[{index}].{terminal} net is invalid")
    role = row.get("channel_role")
    if role is not None and (not isinstance(role, str) or role not in {"ACTIVE", "OACTIVE"}):
        raise CircuitError(f"devices[{index}].channel_role is invalid")
    return Device(device_id, dict(terminals), role)


def load_circuit(path: str | Path) -> Circuit:
    """Read JSON devices or CSV device,terminal,net[,channel_role] rows."""
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 1_000_000:
        raise CircuitError("circuit table exceeds 1 MB")
    raw = path.read_bytes()
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {"schema_version", "devices"}:
                raise CircuitError("JSON circuit requires schema_version and devices")
            if type(value["schema_version"]) is not int or value["schema_version"] != 1:
                raise CircuitError("unsupported circuit schema_version")
            rows = value["devices"]
            if not isinstance(rows, list):
                raise CircuitError("devices must be a list")
        elif path.suffix.lower() == ".csv":
            reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
            if len(reader.fieldnames or ()) != len(set(reader.fieldnames or ())) or set(
                reader.fieldnames or ()
            ) not in (
                {"device", "terminal", "net"},
                {"device", "terminal", "net", "channel_role"},
            ):
                raise CircuitError("CSV needs device,terminal,net[,channel_role] header")
            grouped: dict[str, dict] = {}
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise CircuitError("malformed CSV row")
                device_id = row["device"]
                terminal = row["terminal"]
                if not isinstance(device_id, str) or not _ID.fullmatch(device_id):
                    raise CircuitError("invalid CSV device ID")
                if terminal not in _TERMINALS:
                    raise CircuitError("invalid CSV terminal")
                device = grouped.setdefault(
                    device_id,
                    {"id": device_id, "terminals": {}, "channel_role": None},
                )
                if terminal in device["terminals"]:
                    raise CircuitError("duplicate device terminal row")
                device["terminals"][terminal] = row["net"]
                role = row.get("channel_role") or None
                if role:
                    if device["channel_role"] not in {None, role}:
                        raise CircuitError("inconsistent channel_role for device")
                    device["channel_role"] = role
            rows = list(grouped.values())
        else:
            raise CircuitError("circuit table must be JSON or CSV")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise CircuitError(f"cannot parse circuit table: {exc}") from exc
    if not rows or len(rows) > 500:
        raise CircuitError("circuit must have 1..500 devices")
    devices = {}
    for index, row in enumerate(rows):
        device = _device(row, index)
        if device.id in devices:
            raise CircuitError(f"duplicate device ID {device.id}")
        devices[device.id] = device
    nets = frozenset(net for device in devices.values() for net in device.terminals.values())
    return Circuit(devices, nets, hashlib.sha256(raw).hexdigest())


def suggest_matches(metadata: dict, circuit: Circuit | None, annotations: dict) -> dict:
    """Propagate confirmed nets through shared electrode IDs without guessing symmetry.

    Gate branches from an anchored TR inherit its G net even when the TR cut
    made several electrodes. Channel branches retain the S/D net set unless a
    human resolved their orientation. All suggestions require confirmation.
    """
    possible: dict[str, set[str]] = {}
    conflicts = []

    def constrain(eid: str, nets: set[str]) -> None:
        if eid in possible:
            possible[eid] &= nets
        else:
            possible[eid] = set(nets)
        if not possible[eid] and eid not in conflicts:
            conflicts.append(eid)

    for eid, row in annotations.get("electrodes", {}).items():
        if row.get("net"):
            constrain(eid, {row["net"]})
    for tid, links in annotations.get("terminal_links", {}).items():
        assigned_device = annotations.get("tr", {}).get(tid, {}).get("device_id")
        device = circuit.devices.get(assigned_device) if circuit and assigned_device else None
        for terminal, row in links.items():
            net = row.get("net") or (device.terminals[terminal] if device else "")
            if net:
                for eid in row.get("electrodes", []):
                    constrain(eid, {net})
    tr_items = {item["id"]: item for item in metadata.get("tr", [])}
    if circuit:
        for tid, row in annotations.get("tr", {}).items():
            device = circuit.devices.get(row.get("device_id"))
            if device is None or tid not in tr_items:
                continue
            item = tr_items[tid]
            gat = item["source_pair"]["gat"]
            channel = item["source_pair"]["channel"]
            for adjacent in item.get("terminal_adjacency", []):
                eid = adjacent.get("electrode_id")
                if not eid:
                    continue
                if adjacent["layer"] == gat:
                    constrain(eid, {device.terminals["G"]})
                elif adjacent["layer"] == channel:
                    constrain(eid, {device.terminals["S"], device.terminals["D"]})
    proposals = {}
    for tid, item in tr_items.items():
        anchored = annotations.get("tr", {}).get(tid, {}).get("device_id")
        if not circuit:
            candidates = []
        elif anchored:
            candidates = [anchored]
        else:
            role = next(
                (
                    layer["role"]
                    for layer in metadata.get("layers", [])
                    if layer["id"] == item["source_pair"]["channel"]
                ),
                None,
            )
            candidates = []
            for device in circuit.devices.values():
                if device.channel_role and device.channel_role != role:
                    continue
                valid = True
                for adjacent in item.get("terminal_adjacency", []):
                    eid = adjacent.get("electrode_id")
                    if not eid:
                        continue
                    constrained = possible.get(eid)
                    if constrained is None:
                        continue
                    if adjacent["layer"] == item["source_pair"]["gat"]:
                        permitted = {device.terminals["G"]}
                    else:
                        permitted = {device.terminals["S"], device.terminals["D"]}
                    if not constrained & permitted:
                        valid = False
                        break
                if valid:
                    candidates.append(device.id)
        proposals[tid] = {
            "device_candidates": sorted(candidates),
            "status": (
                "no_circuit"
                if not circuit
                else "confirmed"
                if anchored
                else "unique_candidate"
                if len(candidates) == 1
                else "ambiguous"
                if candidates
                else "no_match"
            ),
        }
    electrode_proposals = {
        eid: {
            "net_candidates": sorted(nets),
            "status": (
                "conflict" if not nets else "unique_candidate" if len(nets) == 1 else "ambiguous"
            ),
        }
        for eid, nets in possible.items()
    }
    return {"tr": proposals, "electrodes": electrode_proposals, "conflicts": sorted(conflicts)}
