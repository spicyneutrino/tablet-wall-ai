"""Operator readiness projection for the trusted HTTP hotspot profile.

Everything here is derived from what the running instance already knows: the
configured origins and storage paths, the in-memory wall, and the backup
directory the operator chose. Nothing is probed with a shell command per read
and nothing invents a value it cannot see. An unknown Wi-Fi name, overlooked
backup directory or unrecorded restore rehearsal stays explicitly unknown.

The HTTP trial prints its tablet address in the launcher. This module gives the
controller the same address plus the context an operator needs around it: the
security mode the profile actually runs (unauthenticated, uploads disabled),
which content is selected and whether its bytes are present, where data and
logs live, and how old the newest verified-looking snapshot is. It never
claims a tablet can be woken, and it never treats the join QR as pairing.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from tabletwall import assets, media, persist
from tabletwall.state import _is_online, devices, wall

TABLET_ORIGIN_ENV = "TABLET_WALL_TABLET_ORIGIN"
OPERATOR_ORIGIN_ENV = "TABLET_WALL_OPERATOR_ORIGIN"
UPLOAD_MODE_ENV = "TABLET_WALL_UPLOAD_MODE"
AUTH_TOKEN_ENV = "TABLET_WALL_AUTH_TOKEN"
WIFI_NAME_ENV = "TABLET_WALL_WIFI_NAME"
BACKUP_DIR_ENV = "TABLET_WALL_BACKUP_DIR"

RESTORE_REHEARSAL_NAME = "restore-rehearsal.json"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_REHEARSAL_BYTES = 64 * 1024

BACKUP_SCOPE = (
    "A snapshot contains the database plus only the referenced curated assets "
    "and uploads; unused files in the asset directory and unused uploads are "
    "excluded."
)


@dataclass(frozen=True)
class WallSnapshot:
    """The small, already-computed slice of live state a readiness read needs."""

    generation: str
    revision: int
    devices_total: int
    devices_online: int
    content_type: str
    content_asset: str | None
    layout_kind: str
    schema_version: int | None
    storage_readable: bool


@dataclass(frozen=True)
class Config:
    """Operator-visible configuration read from the environment."""

    tablet_origin: str | None
    operator_origin: str | None
    uploads: str
    authentication: str
    wifi_name: str | None
    backup_dir: str | None
    errors: tuple[str, ...]

    @property
    def secure_context(self) -> bool:
        return bool(self.tablet_origin and urlsplit(self.tablet_origin).scheme == "https")

    @property
    def schema_expected(self) -> int:
        return persist.SCHEMA_VERSION


def _validated_origin(name: str) -> tuple[str | None, str | None]:
    """``scheme://host[:port]`` exactly, or ``(None, why)``.

    The launcher and the proxy put these strings in front of a browser, so a
    value that is not an origin is a configuration error rather than something
    to repair or guess.
    """
    raw = os.environ.get(name) or ""
    if not raw:
        return None, None
    if not raw.isascii() or any(
        ch.isspace() or not 0x21 <= ord(ch) <= 0x7E for ch in raw
    ):
        return None, f"{name} is not a printable ASCII origin"
    if any(ch in raw for ch in "*@\\"):
        return None, f"{name} must not contain wildcards, credentials, or backslashes"
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return None, f"{name} is not a valid origin"
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None, f"{name} must be an http or https origin"
    if parts.path or parts.query or parts.fragment:
        return None, f"{name} must be exactly scheme://host[:port], with no path"
    if parts.username is not None or parts.password is not None:
        return None, f"{name} must not contain credentials"
    if port is not None and not 1 <= port <= 65535:
        return None, f"{name} has an invalid port"
    if f"{parts.scheme}://{parts.netloc}" != raw:
        return None, f"{name} is not in canonical scheme://host[:port] form"
    return raw, None


def _wifi_name() -> str | None:
    raw = os.environ.get(WIFI_NAME_ENV)
    if raw is None:
        return None
    name = raw.strip()
    if not name or len(name) > 64 or not name.isprintable():
        return None
    return name


def read_config() -> Config:
    """Read the deployment values this process was started with.

    Origins are read per call so a restart or a test can change them. No
    NetworkManager query happens here; the hotspot launcher discovers the SSID
    once at startup and hands it over as ``TABLET_WALL_WIFI_NAME``.
    """
    tablet, tablet_error = _validated_origin(TABLET_ORIGIN_ENV)
    operator, operator_error = _validated_origin(OPERATOR_ORIGIN_ENV)
    uploads = (os.environ.get(UPLOAD_MODE_ENV) or "disabled").strip().lower()
    errors: list[str] = []
    for error in (tablet_error, operator_error):
        if error:
            errors.append(error)
    if tablet is None:
        errors.append(
            f"{TABLET_ORIGIN_ENV} is not configured; set it to the origin tablets "
            "open (make hotspot sets http://<hotspot-ip>:<tablet-port>)"
        )
    if uploads not in ("disabled", "loopback", "proxy"):
        errors.append(
            f"{UPLOAD_MODE_ENV} is {uploads!r}, not one of disabled, loopback, proxy"
        )
    return Config(
        tablet_origin=tablet,
        operator_origin=operator,
        uploads=uploads,
        authentication="shared-secret" if os.environ.get(AUTH_TOKEN_ENV) else "disabled",
        wifi_name=_wifi_name(),
        backup_dir=os.environ.get(BACKUP_DIR_ENV) or None,
        errors=tuple(errors),
    )


def _probe_storage() -> tuple[int | None, bool]:
    """Read-only schema and readability probe; never creates or migrates."""
    try:
        connection = sqlite3.connect(
            f"file:{quote(os.path.abspath(persist.db_path()))}?mode=ro",
            uri=True, timeout=1,
        )
        try:
            row = connection.execute("PRAGMA user_version").fetchone()
            schema = int(row[0]) if row else None
            connection.execute(
                "SELECT generation, revision FROM wall_state WHERE id = 1"
            ).fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return None, False
    return schema, True


def live_snapshot() -> WallSnapshot:
    """Build the readiness slice from the process's own state and store."""
    schema, readable = _probe_storage()
    content = wall["scene"]["content"]
    asset = content.get("asset")
    return WallSnapshot(
        generation=str(wall["generation"]),
        revision=int(wall["revision"]),
        devices_total=len(devices),
        devices_online=sum(1 for device_id in devices if _is_online(device_id)),
        content_type=str(content.get("type") or "color"),
        content_asset=asset if isinstance(asset, str) else None,
        layout_kind=str(wall["layout"].get("kind") or "logical"),
        schema_version=schema,
        storage_readable=readable,
    )


def asset_available(asset_id: str) -> bool:
    """True when this content ID still resolves to readable published bytes."""
    try:
        if media.find_object(asset_id) is not None:
            return True
    except (OSError, sqlite3.Error):
        pass
    try:
        return assets.find(asset_id) is not None
    except (OSError, ValueError):
        return False


def _content(
    snapshot: WallSnapshot | None, resolve: Callable[[str], bool]
) -> dict[str, Any]:
    if snapshot is None:
        return {
            "type": "unknown",
            "available": False,
            "summary": "Live wall state could not be read.",
        }
    kind = snapshot.content_type
    if kind == "image":
        asset = snapshot.content_asset
        available = bool(asset and resolve(asset))
        return {
            "type": "image",
            "available": available,
            "summary": (
                "A still image is selected and its bytes are available."
                if available else
                "A still image is selected but its bytes are missing; tablets "
                "report an image failure instead of showing it."
            ),
        }
    if kind == "calibration":
        return {
            "type": "calibration",
            "available": True,
            "summary": "The selected content is the calibration pattern.",
        }
    return {
        "type": "color",
        "available": True,
        "summary": "A solid colour is selected; no image bytes are needed.",
    }


def _newest_manifest(backup_dir: str | None) -> str | None:
    """Newest ``created_utc`` in the chosen backup directory, if readable.

    This is the same read-only convention ``GET /diagnostics`` uses: the
    directory may hold one snapshot or snapshots one level down. An unset,
    unreadable or oversized manifest answers unknown (``None``); nothing here
    writes or verifies a backup.
    """
    if not backup_dir:
        return None
    paths = [os.path.join(backup_dir, "manifest.json")]
    try:
        with os.scandir(backup_dir) as entries:
            paths += [
                os.path.join(entry.path, "manifest.json")
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            ]
    except OSError:
        return None
    newest: str | None = None
    for path in paths:
        try:
            if os.lstat(path).st_size > MAX_MANIFEST_BYTES:
                continue
            with open(path, encoding="utf-8") as handle:
                created = json.load(handle).get("created_utc")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(created, str) and len(created) <= 40 and (
            newest is None or created > newest
        ):
            newest = created
    return newest


def _restore_rehearsal(backup_dir: str | None) -> str | None:
    """``completed_utc`` from an operator-written rehearsal record, if present."""
    if not backup_dir:
        return None
    path = Path(backup_dir) / RESTORE_REHEARSAL_NAME
    try:
        if path.stat().st_size > MAX_REHEARSAL_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    completed = document.get("completed_utc") if isinstance(document, dict) else None
    if isinstance(completed, str) and 0 < len(completed) <= 40:
        return completed
    return None


def _advice(config: Config) -> list[str]:
    advice = [
        "Screen sleep, auto-lock, and remote wake are tablet-OS decisions. This "
        "server cannot wake a sleeping tablet, power one on, or force fullscreen.",
        "The page's Full screen button needs a tap and does not survive a reload "
        "or a browser restart.",
    ]
    if config.secure_context:
        advice.append(
            "The Screen Wake Lock is best effort in this secure context and does "
            "not replace the tablet's own display timeout or Guided Access."
        )
    else:
        advice.append(
            "The Screen Wake Lock API is unavailable on this plain-HTTP origin; "
            "keep tablets awake with their own auto-lock and stay-awake settings."
        )
    return advice


def health(snapshot: WallSnapshot) -> dict[str, Any]:
    """The minimal ``/healthz`` body: no paths, no secrets, no asset lookup."""
    ready = bool(
        snapshot.storage_readable
        and snapshot.schema_version is not None
        and snapshot.schema_version == persist.SCHEMA_VERSION
    )
    return {
        "ready": ready,
        "schema": snapshot.schema_version,
        "schema_expected": persist.SCHEMA_VERSION,
        "generation": snapshot.generation,
        "revision": snapshot.revision,
        "counts": {
            "devices_online": snapshot.devices_online,
            "devices_total": snapshot.devices_total,
        },
        "storage_readable": snapshot.storage_readable,
    }


def readiness(
    snapshot: WallSnapshot | None,
    config: Config,
    resolve: Callable[[str], bool] = asset_available,
    error: str | None = None,
) -> dict[str, Any]:
    """The operator projection behind ``GET /api/v3/readiness``.

    ``snapshot=None`` is the degraded answer when live state could not be
    read: every field is still present, content and wall values are unknown,
    and ``error`` says why.
    """
    tablet_url = f"{config.tablet_origin}/client/" if config.tablet_origin else None
    backup_at = _newest_manifest(config.backup_dir)
    rehearsal_at = _restore_rehearsal(config.backup_dir)
    errors = [*config.errors, *([error] if error else [])]
    return {
        "tablet_url": tablet_url,
        "join_qr_url": "/api/v3/join-qr" if tablet_url else None,
        "wifi": {"name": config.wifi_name, "known": config.wifi_name is not None},
        "security": {
            "transport": "https" if config.secure_context else (
                "http" if config.tablet_origin else "unknown"
            ),
            "authentication": config.authentication,
            "uploads": config.uploads,
            "trust": (
                "Trusted local hotspot. Registration and device sockets are open "
                "to its clients; do not use it on shared or venue Wi-Fi."
                if config.authentication == "disabled" else
                "Shared-secret session, not a per-device identity; keep the "
                "operator listener on loopback."
            ),
        },
        "content": _content(snapshot, resolve),
        "wall": {
            "schema": snapshot.schema_version if snapshot else None,
            "generation": snapshot.generation if snapshot else None,
            "revision": snapshot.revision if snapshot else None,
            "layout": snapshot.layout_kind if snapshot else None,
        },
        "devices": {
            "online": snapshot.devices_online if snapshot else 0,
            "total": snapshot.devices_total if snapshot else 0,
        },
        "storage": {
            "readable": bool(snapshot and snapshot.storage_readable),
            "database": persist.db_path(),
            "assets": assets.asset_dir(),
            "media": media.media_dir(),
            "backup_dir": config.backup_dir,
        },
        "backup": {
            "last_manifest_at": backup_at,
            "recorded": backup_at is not None,
            "scope": BACKUP_SCOPE,
        },
        "restore_rehearsal": {
            "completed_utc": rehearsal_at,
            "recorded": rehearsal_at is not None,
        },
        "advice": _advice(config),
        "errors": errors,
    }
