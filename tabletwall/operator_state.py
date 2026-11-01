"""Operator read projections. Durable hashes exclude all runtime observations."""
import hashlib
import json
import time
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from tabletwall import displays, layouts, persist, render_status, tablet_models
from tabletwall.state import (
    _is_online, current_mapping, devices, identify_commands, render_mapping, wall,
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]


def identify_status(device_id: str) -> dict[str, Any] | None:
    command = identify_commands.get(device_id)
    if command is None:
        return None
    remaining = max(0.0, (command["expires_mono"] - time.monotonic()) * 1000)
    return {key: value for key, value in command.items() if key != "expires_mono"} | {
        "remaining_ms": remaining, "active": remaining > 0 and command["state"] != "cleared",
    }


def device_status(device_id: str, *, presentation_active: bool = False) -> dict[str, Any]:
    record = devices.get(device_id, {})
    mapping, _, _ = current_mapping(device_id, record)
    identify = identify_status(device_id)
    evidence = render_status.project(
        device_id, online=_is_online(device_id), caps=record.get("caps") or [],
        mapping=render_mapping(mapping, record, experimental=presentation_active),
        generation=wall["generation"], revision=wall["revision"],
        identify_active=bool(identify and identify["active"]), presentation_active=presentation_active,
    )
    if record.get("protocol") != 3 and evidence.state == "unsupported":
        render = {**asdict(evidence), "state": "unknown"}
    else:
        render = asdict(evidence)
    return {"online": _is_online(device_id), "last_seen": record.get("last_seen"),
            "protocol": record.get("protocol"), "caps": list(record.get("caps") or []),
            "number": record.get("number"), "label": record.get("label"),
            "viewport": deepcopy(record.get("viewport")), "wake_lock": record.get("wake_lock"),
            "mapping": mapping, "render": render, "identify": identify,
            "model_suggestions": tablet_models.match(record)}


def runtime(*, presentation_active: bool = False, presentation_state: str = "static") -> dict[str, Any]:
    ids = set(devices) | set(layouts.entries(wall["layout"]))
    observations = [record["last_seen"] for record in devices.values() if record.get("last_seen")]
    return {"observed_at": max(observations, default=None),
            "devices": {key: device_status(key, presentation_active=presentation_active) for key in sorted(ids)},
            "presentation": {"owner": "playback" if presentation_active else "static", "state": presentation_state}}


def snapshots(valid_layout: Any, valid_scene: Any) -> dict[str, Any]:
    summaries = {}
    for kind, rows, valid in (("layout", persist.load_layouts(), valid_layout), ("scene", persist.load_scenes(), valid_scene)):
        digests = persist.snapshot_digests(kind)
        summaries[kind + "s"] = [{"name": name, "etag": digests[name],
            "kind": layouts.kind(value) if isinstance(value, dict) and kind == "layout" else kind,
            "valid": valid(value)} for name, value in rows]
    return summaries


def durable_etag(payload: dict[str, Any]) -> str:
    durable = deepcopy({key: value for key, value in payload.items() if key not in ("runtime", "etag")})
    for key in ("available", "name", "url"):
        durable["scene"]["content"].pop(key, None)
    durable["measurement_histories"] = displays.histories()
    durable["model_histories"] = persist.load_meta("tablet_model_calibrations") or {}
    return digest(durable)
