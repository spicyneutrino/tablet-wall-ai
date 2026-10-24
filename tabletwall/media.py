"""Managed image store, upload admission, and object publication (R1).

Curated files stay in ``tabletwall.assets``: operator-placed, scanned, and
read-only. Managed uploads live here instead: an exclusive staging area, an
immutable content-addressed object tree, and indexed database rows. The two
stores share the ``sha256:`` ID shape, so the v2 still descriptor and the wall
scene document need no change.

Durability order is deliberate and is the reason this module exists rather
than a few route-local writes: object bytes are fsynced, published atomically
without replacing an existing immutable object, their directory is fsynced,
and only then are the ready relationships committed. A crash before the
commit leaves objects that no row lists; a crash after it leaves a valid
upload. Neither state can serve unverified bytes under a new ID.

The store is not a security sandbox around the decoder. The worker is a
separate, resource-bounded process, but it runs with the server's filesystem
permissions; the report says so instead of implying otherwise.
"""

import asyncio
import contextlib
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from tabletwall import persist
from tabletwall.media_limits import (
    FREE_RESERVE_BYTES,
    MAX_OBJECT_BYTES,
    MAX_SOURCE_BYTES,
    MAX_WAITING_UPLOADS,
    PIPELINE_VERSION,
    QUOTA_BYTES,
    RECEIVE_TIMEOUT_S,
    WORKER_TIMEOUT_S,
)
from tabletwall.protocol import ASSET_ID_PREFIX, _asset_url, _is_asset_id

DEFAULT_MEDIA_DIR = "./media"
STORE_LOCK_NAME = ".store.lock"
STAGING_DIR = "staging"
OBJECTS_DIR = "objects"

UPLOAD_MODE_ENV = "TABLET_WALL_UPLOAD_MODE"
OPERATOR_CREDENTIAL_ENV = "TABLET_WALL_OPERATOR_CREDENTIAL"
OPERATOR_ORIGIN_ENV = "TABLET_WALL_OPERATOR_ORIGIN"
CREDENTIAL_HEADER = "x-tablet-wall-operator"
UPLOAD_MODES = ("disabled", "loopback", "proxy")

TRUE_ROLES = ("master", "display", "fallback", "thumbnail")


class StoreError(Exception):
    """A refusal or failure with an operator-facing reason."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# paths and the cross-process store lock
# ---------------------------------------------------------------------------


def media_dir() -> str:
    """Where managed objects live: ``TABLET_WALL_MEDIA_DIR``, else ``./media``."""
    return os.environ.get("TABLET_WALL_MEDIA_DIR") or DEFAULT_MEDIA_DIR


def objects_dir() -> str:
    return os.path.join(media_dir(), OBJECTS_DIR)


def staging_dir() -> str:
    return os.path.join(media_dir(), STAGING_DIR)


def lock_path() -> str:
    return os.path.join(media_dir(), STORE_LOCK_NAME)


def ensure_dirs() -> None:
    """Create the store layout (0700) and the lock file, idempotently."""
    root = os.path.abspath(media_dir())
    os.makedirs(root, mode=0o700, exist_ok=True)
    for path in (objects_dir(), staging_dir()):
        os.makedirs(path, mode=0o700, exist_ok=True)
    os.close(os.open(lock_path(), os.O_CREAT | os.O_RDONLY, 0o600))


@contextmanager
def store_lock(*, exclusive: bool = False) -> Iterator[None]:
    """The stable cross-process lock for the media store.

    Backup takes it shared from database capture through artifact
    verification; destructive maintenance takes it exclusive before touching
    the database or the object tree. Immutable publication does not need to
    hold it for a whole copy: a backup's captured database decides what is
    copied, and an object committed after that capture is simply not part of
    it. The inode is fixed (``.<root>/.store.lock``) so two tools cannot lock
    different files and both believe they are protected.
    """
    ensure_dirs()
    fd = os.open(lock_path(), os.O_RDWR | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------


def _tree_bytes(root: str) -> int:
    total = 0
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += _tree_bytes(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except FileNotFoundError:
        return 0
    return total


def check_capacity(incoming: int) -> None:
    """Refuse an upload that would exceed the store quota or the free reserve.

    Called before the body is read with the declared (or worst-case) size, and
    again after staging with the actual bytes. Staging, job outputs and
    retained objects are all counted because they all occupy this tree.
    """
    ensure_dirs()
    used = _tree_bytes(media_dir())
    usage = shutil.disk_usage(media_dir())
    if used + incoming > QUOTA_BYTES:
        raise StoreError(507, "media store quota is exhausted")
    if usage.free - incoming < FREE_RESERVE_BYTES:
        raise StoreError(507, "media store is below its free-space reserve")


# ---------------------------------------------------------------------------
# staging and the worker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    directory: str
    source: str
    result: str


def new_job() -> Job:
    """An exclusive staging directory for one upload."""
    ensure_dirs()
    directory = os.path.join(staging_dir(), uuid.uuid4().hex)
    os.mkdir(directory, 0o700)
    return Job(
        directory=directory,
        source=os.path.join(directory, "source"),
        result=os.path.join(directory, "result.json"),
    )


async def receive_body(job: Job, chunks: AsyncIterator[bytes], declared: int | None) -> int:
    """Stream a request body to ``job.source``, enforcing the source cap.

    A wrong or absent ``Content-Length`` never widens the limit: every chunk
    is counted, and the write stops one byte over the cap. The file is fsynced
    before the worker can see it. An exception or disconnect removes the whole
    job directory, so an interrupted upload cannot leave a candidate object.
    """
    fd = os.open(job.source, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    total = 0
    try:
        async def bounded() -> AsyncIterator[bytes]:
            nonlocal total
            deadline = time.monotonic() + RECEIVE_TIMEOUT_S
            async for chunk in chunks:
                if time.monotonic() > deadline:
                    raise StoreError(408, "upload receive deadline exceeded")
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise StoreError(413, "image is larger than the 32 MiB source limit")
                yield chunk

        async for chunk in bounded():
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view):]
        os.fsync(fd)
    except Exception:
        shutil.rmtree(job.directory, ignore_errors=True)
        raise
    finally:
        os.close(fd)
    if declared is not None and declared != total:
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(400, "Content-Length does not match the received body")
    if total == 0:
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(400, "empty request body")
    return total


async def run_worker(job: Job) -> dict[str, Any]:
    """Run the decoder in a subprocess under a wall-clock deadline.

    The child sets its own address-space and CPU limits. If it hangs, is
    killed, writes no result, or reports failure, the job directory is
    removed and the caller gets an actionable refusal.
    """
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tabletwall.media_worker",
        job.source, job.directory, job.result,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
        # The C locale keeps Python from mapping a large locale archive into
        # the address space, which otherwise consumes a third of the 512 MiB
        # worker budget before Pillow decodes a phone image.
        env={**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0"},
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=WORKER_TIMEOUT_S)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, 15)
        except ProcessLookupError:
            pass
        await process.wait()
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, "image processing exceeded 30 seconds")
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, 15)
        await process.wait()
        shutil.rmtree(job.directory, ignore_errors=True)
        raise
    if process.returncode != 0:
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, "image processing failed")
    try:
        result = json.loads(open(job.result, encoding="utf-8").read(4 * 1024 * 1024))
    except (OSError, ValueError):
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, "image processing wrote no usable result")
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else None
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, str(error or "image was rejected"))
    return result


# ---------------------------------------------------------------------------
# publication and lookup
# ---------------------------------------------------------------------------


def _hash_file(path: str, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise StoreError(422, "normalized object exceeds the 10 MiB limit")
            digest.update(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest(), total


def _validated_objects(job: Job, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Check the worker's claim against the bytes it actually wrote."""
    objects = result.get("objects")
    if not isinstance(objects, list) or len(objects) != len(TRUE_ROLES):
        raise StoreError(422, "worker result did not describe all four renditions")
    seen_roles: set[str] = set()
    checked: list[dict[str, Any]] = []
    for entry in objects:
        if not isinstance(entry, dict):
            raise StoreError(422, "worker result contains a malformed object")
        role = entry.get("role")
        filename = entry.get("filename")
        claimed = entry.get("sha256")
        if role not in TRUE_ROLES or role in seen_roles:
            raise StoreError(422, "worker result has an unknown or duplicate role")
        if not isinstance(filename, str) or "/" in filename or filename in ("", ".", ".."):
            raise StoreError(422, "worker result names an unsafe object file")
        path = os.path.join(job.directory, filename)
        if os.path.islink(path) or not os.path.isfile(path):
            raise StoreError(422, "worker result names a missing object")
        digest, size = _hash_file(path, MAX_OBJECT_BYTES)
        if not isinstance(claimed, str) or claimed != digest:
            raise StoreError(422, "worker object hash does not match its bytes")
        width, height = entry.get("width"), entry.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise StoreError(422, "worker object has invalid dimensions")
        if entry.get("mime") != "image/jpeg":
            raise StoreError(422, "worker object is not JPEG")
        seen_roles.add(role)
        checked.append({
            "role": role, "path": path, "sha256": digest, "id": ASSET_ID_PREFIX + digest,
            "bytes": size, "width": width, "height": height, "mime": "image/jpeg",
        })
    if seen_roles != set(TRUE_ROLES):
        raise StoreError(422, "worker result is missing a rendition role")
    return checked


def _publish_object(entry: dict[str, Any]) -> tuple[str, str]:
    """Link one verified object into the immutable tree; return ``(id, relpath)``.

    ``os.link`` publishes without replacing: an existing identical object is
    reused after a re-hash, never overwritten. The source stays in staging
    until the whole job is committed, so a later failure cannot delete an
    object another asset already references.
    """
    root = objects_dir()
    relative = os.path.join(entry["sha256"][:2], entry["sha256"] + ".jpg")
    target = os.path.join(root, relative)
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    if os.path.exists(target):
        digest, size = _hash_file(target, MAX_OBJECT_BYTES)
        if digest != entry["sha256"] or size != entry["bytes"]:
            raise StoreError(500, "an existing store object does not match its ID")
    else:
        try:
            os.link(entry["path"], target)
        except FileExistsError:
            digest, size = _hash_file(target, MAX_OBJECT_BYTES)
            if digest != entry["sha256"] or size != entry["bytes"]:
                raise StoreError(500, "an existing store object does not match its ID")
        os.chmod(target, 0o600)
        _fsync_path(target)
    _fsync_dir(os.path.dirname(target))
    return entry["id"], os.path.join(OBJECTS_DIR, relative).replace(os.sep, "/")


def _fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: str) -> None:
    fd = os.open(path or ".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(job: Job, result: dict[str, Any], name: str) -> dict[str, Any]:
    """Publish one verified job and commit its ready rows atomically."""
    try:
        objects = _validated_objects(job, result)
        published: list[tuple[dict[str, Any], str]] = []
        for entry in objects:
            object_id, relative = _publish_object(entry)
            published.append(({**entry, "relative": relative}, object_id))
        asset_id = str(uuid.uuid4())
        now = _now()
        display = next(entry for entry in published if entry[0]["role"] == "display")
        master = next(entry for entry in published if entry[0]["role"] == "master")
        with persist._connection() as connection:
            for entry, object_id in published:
                connection.execute(
                    "INSERT OR IGNORE INTO media_objects "
                    "(object_id, mime, bytes, width, height, path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (object_id, entry["mime"], entry["bytes"], entry["width"],
                     entry["height"], entry["relative"], now),
                )
            connection.execute(
                "INSERT INTO media_assets "
                "(asset_id, name, kind, state, pipeline_version, width, height, "
                "display_object, master_object, error, created_at, updated_at) "
                "VALUES (?, ?, 'image', 'ready', ?, ?, ?, ?, ?, NULL, ?, ?)",
                (asset_id, name, PIPELINE_VERSION, display[0]["width"],
                 display[0]["height"], display[1], master[1], now, now),
            )
            for entry, object_id in published:
                connection.execute(
                    "INSERT INTO media_renditions "
                    "(asset_id, object_id, role, width, height) VALUES (?, ?, ?, ?, ?)",
                    (asset_id, object_id, entry["role"], entry["width"], entry["height"]),
                )
        return asset_descriptor(asset_id) or {}
    finally:
        shutil.rmtree(job.directory, ignore_errors=True)


def asset_descriptor(asset_id: str) -> dict[str, Any] | None:
    """The v2 still descriptor for a ready asset, plus additive library fields."""
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT a.asset_id, a.name, a.width, a.height, a.state, a.created_at, "
            "o.object_id, o.mime, o.bytes "
            "FROM media_assets a JOIN media_objects o ON o.object_id = a.display_object "
            "WHERE a.asset_id = ?",
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        thumb = connection.execute(
            "SELECT o.object_id, o.width, o.height FROM media_renditions r "
            "JOIN media_objects o ON o.object_id = r.object_id "
            "WHERE r.asset_id = ? AND r.role = 'thumbnail'",
            (asset_id,),
        ).fetchone()
    return {
        "id": row[6],
        "asset_id": row[0],
        "name": row[1],
        "mime": row[7],
        "intrinsicWidth": row[2],
        "intrinsicHeight": row[3],
        "bytes": row[8],
        "url": _asset_url(row[6]),
        "state": row[4],
        "created_at": row[5],
        "thumbnail": (
            {"id": thumb[0], "url": _asset_url(thumb[0]), "width": thumb[1], "height": thumb[2]}
            if thumb else None
        ),
    }


def list_assets() -> list[dict[str, Any]]:
    """Ready library entries, newest first, in the controller's wire shape."""
    with persist._connection() as connection:
        ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT asset_id FROM media_assets WHERE state = 'ready' "
                "ORDER BY created_at DESC"
            ).fetchall()
        ]
    return [entry for entry in (asset_descriptor(asset_id) for asset_id in ids) if entry]


def find_object(object_id: str) -> dict[str, Any] | None:
    """Metadata for a ready published object, without reading its bytes."""
    if not _is_asset_id(object_id):
        return None
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT o.object_id, o.mime, o.bytes, o.path, o.width, o.height "
            "FROM media_objects o JOIN media_renditions r ON r.object_id = o.object_id "
            "JOIN media_assets a ON a.asset_id = r.asset_id "
            "WHERE o.object_id = ? AND a.state = 'ready' LIMIT 1",
            (object_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "mime": row[1], "bytes": row[2], "path": row[3],
            "width": row[4], "height": row[5]}


def fetch_object(object_id: str) -> tuple[bytes, str] | None:
    """Read and re-hash one published object; None refuses to serve it.

    The ID is the hash of the bytes, so a response whose bytes still hash to
    the requested ID is provably that object. A missing row, a vanished file,
    a symlink, a path outside the object tree, or a hash mismatch all mean
    "serve nothing" rather than "serve something close".
    """
    entry = find_object(object_id)
    if entry is None:
        return None
    root = os.path.realpath(objects_dir())
    path = os.path.realpath(os.path.join(media_dir(), entry["path"]))
    if not path.startswith(root + os.sep):
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        chunks: list[bytes] = []
        remaining = MAX_OBJECT_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    if len(data) > MAX_OBJECT_BYTES:
        return None
    if ASSET_ID_PREFIX + hashlib.sha256(data).hexdigest() != object_id:
        return None
    return data, entry["mime"]


def verify_integrity() -> list[dict[str, Any]]:
    """Re-hash every ready object; return the entries that do not match.

    This is the explicit check an operator can run after a restore or a disk
    event. It never mutates rows or files.
    """
    problems: list[dict[str, Any]] = []
    with persist._connection() as connection:
        rows = connection.execute(
            "SELECT o.object_id, o.path FROM media_objects o "
            "JOIN media_renditions r ON r.object_id = o.object_id "
            "JOIN media_assets a ON a.asset_id = r.asset_id "
            "WHERE a.state = 'ready'"
        ).fetchall()
    for object_id, relative in rows:
        data = fetch_object(str(object_id))
        if data is None:
            problems.append({"object_id": object_id, "path": relative,
                             "problem": "missing or does not match its ID"})
    return problems


def cleanup_staging(max_age_s: int = 3600) -> int:
    """Remove stale job directories older than ``max_age_s``; return the count.

    Only directories directly under ``staging/`` are considered, never a
    caller-supplied path. Destructive object GC is deliberately not here.
    """
    removed = 0
    cutoff = time.time() - max_age_s
    try:
        with os.scandir(staging_dir()) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                        continue
                    shutil.rmtree(entry.path, ignore_errors=True)
                    removed += 1
                except OSError:
                    continue
    except FileNotFoundError:
        return 0
    return removed


# ---------------------------------------------------------------------------
# operator admission
# ---------------------------------------------------------------------------


def upload_mode() -> str:
    """The configured admission mode; an unknown value is never enabled."""
    return (os.environ.get(UPLOAD_MODE_ENV) or "disabled").strip().lower()


def _operator_origin() -> str | None:
    value = os.environ.get(OPERATOR_ORIGIN_ENV)
    value = value.strip() if value else ""
    return value or None


def _single_origin(request: Any) -> str | None:
    values = request.headers.getlist("origin")
    if len(values) != 1:
        return None
    value = values[0]
    return None if value in ("", "null") else value


def _forwarded(headers: Any) -> bool:
    for key in headers.keys():
        lowered = key.lower()
        if lowered == "forwarded" or lowered.startswith("x-forwarded-"):
            return True
    return False


def _loopback_peer(request: Any) -> bool:
    host = request.client.host if request.client else None
    try:
        return ipaddress.ip_address(host).is_loopback
    except (TypeError, ValueError):
        return False


def _check_proxy_credential(request: Any) -> None:
    expected = os.environ.get(OPERATOR_CREDENTIAL_ENV) or ""
    if len(expected) < 16:
        raise StoreError(503, "operator credential is not configured")
    values = request.headers.getlist(CREDENTIAL_HEADER)
    if len(values) != 1 or not hmac.compare_digest(values[0], expected):
        raise StoreError(403, "operator credential is invalid")


def _check_mode() -> str:
    mode = upload_mode()
    if mode == "disabled":
        raise StoreError(403, "uploads are disabled")
    if mode not in UPLOAD_MODES:
        raise StoreError(503, "upload mode is not a supported value")
    if _operator_origin() is None:
        raise StoreError(503, "operator origin is not configured")
    return mode


def admit_upload(request: Any) -> None:
    """Refuse an upload unless this exact request proves operator admission.

    Both enabled modes require exactly one Origin equal to the configured
    operator origin. ``proxy`` additionally requires exactly one internal
    credential, which Caddy overwrites after operator authentication.
    ``loopback`` additionally requires a loopback transport peer and refuses
    forwarded headers, so a generic proxy cannot turn itself into an operator.
    The origin guard's "unset means allow" result is never used here.
    """
    mode = _check_mode()
    if _single_origin(request) != _operator_origin():
        raise StoreError(403, "operator origin mismatch")
    if mode == "proxy":
        _check_proxy_credential(request)
    else:
        if not _loopback_peer(request):
            raise StoreError(403, "loopback mode requires a local transport peer")
        if _forwarded(request.headers):
            raise StoreError(403, "forwarded headers are not accepted in loopback mode")


def admit_library(request: Any) -> None:
    """Refuse a library read unless it comes from the operator path.

    A same-origin browser GET commonly omits Origin, so the proxy credential
    is the proof on the authenticated operator listener. Direct local mode
    accepts a loopback transport peer and refuses forwarded headers; neither
    path is reachable on the tablet listener.
    """
    mode = _check_mode()
    if mode == "proxy":
        _check_proxy_credential(request)
        return
    if not _loopback_peer(request):
        raise StoreError(403, "loopback mode requires a local transport peer")
    if _forwarded(request.headers):
        raise StoreError(403, "forwarded headers are not accepted in loopback mode")

