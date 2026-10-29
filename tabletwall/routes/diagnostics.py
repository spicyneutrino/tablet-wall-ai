"""Operator storage and client health diagnostics."""

import json
import os
import shutil
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from tabletwall import media, persist
from tabletwall.media_limits import FREE_RESERVE_BYTES, QUOTA_BYTES
from tabletwall.state import _is_online, devices

WAKE_LOCK_STATES = frozenset({"held", "released", "unsupported", "insecure", "denied"})
router = APIRouter()


def _store_error(error: media.StoreError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content={"detail": error.message},
                        headers={"Cache-Control": "no-store"})


BACKUP_DIR_ENV = "TABLET_WALL_BACKUP_DIR"


def _last_backup_at() -> str | None:
    """Newest ``created_utc`` among manifests under ``TABLET_WALL_BACKUP_DIR``.

    Read-only and best effort: the directory may itself be a snapshot or hold
    snapshots one level down. Unset, unreadable and oversized all answer
    ``None``; this server never writes backups.
    """
    root = os.environ.get(BACKUP_DIR_ENV)
    if not root:
        return None
    paths = [os.path.join(root, "manifest.json")]
    try:
        with os.scandir(root) as entries:
            paths += [
                os.path.join(entry.path, "manifest.json")
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            ]
    except OSError:
        pass
    newest: str | None = None
    for path in paths:
        try:
            if os.lstat(path).st_size > 16 * 1024 * 1024:
                continue
            with open(path, encoding="utf-8") as handle:
                created = json.load(handle).get("created_utc")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(created, str) and len(created) <= 40 and (newest is None or created > newest):
            newest = created
    return newest


def _media_diagnostics() -> dict[str, Any]:
    """Quota and store counts; ``orphans`` are object files no row lists."""
    media.ensure_dirs()
    with persist._connection() as connection:
        listed = {str(row[0]) for row in connection.execute("SELECT path FROM media_objects")}
        assets_ready = connection.execute(
            "SELECT COUNT(*) FROM media_assets WHERE state = 'ready'"
        ).fetchone()[0]
    root = media.media_dir()
    orphans = 0
    for directory, _dirs, names in os.walk(media.objects_dir()):
        for name in names:
            relative = os.path.relpath(os.path.join(directory, name), root)
            if relative.replace(os.sep, "/") not in listed:
                orphans += 1
    return {
        "quota_bytes": QUOTA_BYTES,
        "used_bytes": media._tree_bytes(root),
        "free_bytes": shutil.disk_usage(root).free,
        "reserve_bytes": FREE_RESERVE_BYTES,
        "objects": len(listed),
        "assets": assets_ready,
        "orphans": orphans,
    }


@router.get("/diagnostics")
def get_diagnostics(request: Request, verify: bool = Query(default=False)):
    """Operator-only storage and health readout.

    Admitted exactly like the managed library (``media.admit_library``), so
    it is unreachable on the tablet listener and fails closed while uploads
    are disabled. Cheap by default; ``?verify=1`` additionally re-hashes every
    ready object (``media.verify_integrity``) and reports objects whose bytes
    are missing or no longer match their ID under ``media.integrity``.
    """
    try:
        media.admit_library(request)
    except media.StoreError as error:
        return _store_error(error)
    store = _media_diagnostics()
    if verify:
        problems = media.verify_integrity()
        store["integrity"] = {"ok": not problems, "problems": problems}
    try:
        db_bytes = os.path.getsize(persist.db_path())
    except OSError:
        db_bytes = None
    roster = list(devices)
    wake_lock = {state: 0 for state in sorted(WAKE_LOCK_STATES)}
    for device_id in roster:
        state = devices[device_id].get("wake_lock")
        if state in wake_lock:
            wake_lock[state] += 1
    return JSONResponse(
        content={
            "media": store,
            "db": {"schema": persist.schema_version(), "bytes": db_bytes},
            "backup": {"last_manifest_at": _last_backup_at()},
            "clients": {
                "online": sum(1 for device_id in roster if _is_online(device_id)),
                "total": len(roster),
                "wake_lock": wake_lock,
            },
        },
        headers={"Cache-Control": "no-store"},
    )
