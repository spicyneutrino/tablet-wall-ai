"""Managed image and video store, upload admission, and object publication (R1, R4).

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

A video asset (``tabletwall.video``) uses the same store: its remuxed MP4 and
its poster are two objects under roles ``video`` and ``thumbnail``, its facts
are one ``media_video`` row, and everything commits in the same transaction.
Stills never see a video through ``find_object``; ``find_servable`` and
``open_video`` are the serving-side lookups.

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
import stat
import sys
import threading
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
    MAX_VIDEO_BYTES,
    PIPELINE_VERSION,
    QUOTA_BYTES,
    RECEIVE_TIMEOUT_S,
    VIDEO_PIPELINE_VERSION,
    VIDEO_WORKER_TIMEOUT_S,
    WORKER_TIMEOUT_S,
)
from tabletwall.protocol import ASSET_ID_PREFIX, _asset_url, _is_asset_id
from tabletwall.media_video import VIDEO_MIME, validate_facts

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
# Per-kind rendition contract: role -> (mime, byte limit). A video asset is
# the faststart MP4 plus its poster, which is an ordinary thumbnail object.
IMAGE_SPEC = {role: ("image/jpeg", MAX_OBJECT_BYTES) for role in TRUE_ROLES}
VIDEO_SPEC = {"video": (VIDEO_MIME, MAX_VIDEO_BYTES), "thumbnail": ("image/jpeg", MAX_OBJECT_BYTES)}
_EXTENSIONS = {"image/jpeg": ".jpg", VIDEO_MIME: ".mp4"}


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


async def receive_body(
    job: Job,
    chunks: AsyncIterator[bytes],
    declared: int | None,
    *,
    limit: int | None = None,
    deadline_s: float | None = None,
    noun: str = "image",
) -> int:
    """Stream a request body to ``job.source``, enforcing the source cap.

    A wrong or absent ``Content-Length`` never widens the limit: every chunk
    is counted, and the write stops one byte over the cap. The file is fsynced
    before the worker can see it. An exception or disconnect removes the whole
    job directory, so an interrupted upload cannot leave a candidate object.
    The defaults are the still-image limits; a video upload passes its own.
    """
    cap = MAX_SOURCE_BYTES if limit is None else limit
    window = RECEIVE_TIMEOUT_S if deadline_s is None else deadline_s
    fd = os.open(job.source, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    total = 0
    try:
        async def bounded() -> AsyncIterator[bytes]:
            nonlocal total
            deadline = time.monotonic() + window
            async for chunk in chunks:
                if time.monotonic() > deadline:
                    raise StoreError(408, "upload receive deadline exceeded")
                total += len(chunk)
                if total > cap:
                    raise StoreError(413, f"{noun} is larger than the {cap // (1024 * 1024)} MiB source limit")
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


async def _run_worker(job: Job, module: str, timeout_s: int, noun: str) -> dict[str, Any]:
    """Run one decoder module in a subprocess under a wall-clock deadline.

    The child sets its own address-space and CPU limits. If it hangs, is
    killed, writes no result, or reports failure, the job directory is
    removed and the caller gets an actionable refusal.
    """
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", module,
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
        await asyncio.wait_for(process.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, 15)
        except ProcessLookupError:
            pass
        await process.wait()
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, f"{noun} processing exceeded {timeout_s} seconds")
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, 15)
        await process.wait()
        shutil.rmtree(job.directory, ignore_errors=True)
        raise
    if process.returncode != 0:
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, f"{noun} processing failed")
    try:
        result = json.loads(open(job.result, encoding="utf-8").read(4 * 1024 * 1024))
    except (OSError, ValueError):
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, f"{noun} processing wrote no usable result")
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else None
        shutil.rmtree(job.directory, ignore_errors=True)
        raise StoreError(422, str(error or f"{noun} was rejected"))
    return result


async def run_worker(job: Job) -> dict[str, Any]:
    """Normalize a still image in the bounded image worker."""
    return await _run_worker(job, "tabletwall.media_worker", WORKER_TIMEOUT_S, "image")


async def run_video_worker(job: Job) -> dict[str, Any]:
    """Inspect and remux a video in the bounded video worker."""
    return await _run_worker(job, "tabletwall.video", VIDEO_WORKER_TIMEOUT_S, "video")


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
                raise StoreError(422, f"normalized object exceeds the {limit // (1024 * 1024)} MiB limit")
            digest.update(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest(), total


def _validated_objects(
    job: Job, result: dict[str, Any], spec: dict[str, tuple[str, int]] = IMAGE_SPEC
) -> list[dict[str, Any]]:
    """Check the worker's claim against the bytes it actually wrote."""
    objects = result.get("objects")
    if not isinstance(objects, list) or len(objects) != len(spec):
        raise StoreError(422, f"worker result did not describe all {len(spec)} renditions")
    seen_roles: set[str] = set()
    checked: list[dict[str, Any]] = []
    for entry in objects:
        if not isinstance(entry, dict):
            raise StoreError(422, "worker result contains a malformed object")
        role = entry.get("role")
        filename = entry.get("filename")
        claimed = entry.get("sha256")
        if role not in spec or role in seen_roles:
            raise StoreError(422, "worker result has an unknown or duplicate role")
        if not isinstance(filename, str) or "/" in filename or filename in ("", ".", ".."):
            raise StoreError(422, "worker result names an unsafe object file")
        path = os.path.join(job.directory, filename)
        if os.path.islink(path) or not os.path.isfile(path):
            raise StoreError(422, "worker result names a missing object")
        mime, limit = spec[role]
        digest, size = _hash_file(path, limit)
        if not isinstance(claimed, str) or claimed != digest:
            raise StoreError(422, "worker object hash does not match its bytes")
        width, height = entry.get("width"), entry.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise StoreError(422, "worker object has invalid dimensions")
        if entry.get("mime") != mime:
            raise StoreError(422, f"worker object is not {mime}")
        seen_roles.add(role)
        checked.append({
            "role": role, "path": path, "sha256": digest, "id": ASSET_ID_PREFIX + digest,
            "bytes": size, "width": width, "height": height, "mime": mime,
        })
    if seen_roles != set(spec):
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
    limit = MAX_VIDEO_BYTES if entry["mime"] == VIDEO_MIME else MAX_OBJECT_BYTES
    relative = os.path.join(entry["sha256"][:2], entry["sha256"] + _EXTENSIONS[entry["mime"]])
    target = os.path.join(root, relative)
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    if os.path.exists(target):
        digest, size = _hash_file(target, limit)
        if digest != entry["sha256"] or size != entry["bytes"]:
            raise StoreError(500, "an existing store object does not match its ID")
    else:
        try:
            os.link(entry["path"], target)
        except FileExistsError:
            digest, size = _hash_file(target, limit)
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


def _commit_asset(
    objects: list[dict[str, Any]],
    *,
    name: str,
    kind: str,
    pipeline_version: int,
    display_role: str,
    master_role: str,
    facts: dict[str, Any] | None,
) -> str:
    """Publish verified objects, then commit the ready rows in one transaction.

    The object files are linked and fsynced first; only the database commit
    makes them reachable. A crash in between leaves unlisted objects that no
    lookup can serve.
    """
    published: list[tuple[dict[str, Any], str]] = []
    for entry in objects:
        object_id, relative = _publish_object(entry)
        published.append(({**entry, "relative": relative}, object_id))
    asset_id = str(uuid.uuid4())
    now = _now()
    display = next(item for item in published if item[0]["role"] == display_role)
    master = next(item for item in published if item[0]["role"] == master_role)
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
            "VALUES (?, ?, ?, 'ready', ?, ?, ?, ?, ?, NULL, ?, ?)",
            (asset_id, name, kind, pipeline_version, display[0]["width"],
             display[0]["height"], display[1], master[1], now, now),
        )
        for entry, object_id in published:
            connection.execute(
                "INSERT INTO media_renditions "
                "(asset_id, object_id, role, width, height) VALUES (?, ?, ?, ?, ?)",
                (asset_id, object_id, entry["role"], entry["width"], entry["height"]),
            )
        if facts is not None:
            connection.execute(
                "INSERT INTO media_video "
                "(asset_id, duration_ms, codec, profile, level, pixel_format, "
                "frame_rate, bitrate, faststart, has_audio) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (asset_id, facts["durationMs"], facts["codec"], facts["profile"],
                 facts["level"], facts["pixelFormat"], float(facts["frameRate"]),
                 facts["bitrate"], int(facts["faststart"]), int(facts["audio"])),
            )
    return asset_id


def publish(job: Job, result: dict[str, Any], name: str) -> dict[str, Any]:
    """Publish one verified still job and commit its ready rows atomically."""
    try:
        objects = _validated_objects(job, result)
        asset_id = _commit_asset(
            objects, name=name, kind="image", pipeline_version=PIPELINE_VERSION,
            display_role="display", master_role="master", facts=None,
        )
        return asset_descriptor(asset_id) or {}
    finally:
        shutil.rmtree(job.directory, ignore_errors=True)


def publish_video(job: Job, result: dict[str, Any], name: str) -> dict[str, Any]:
    """Publish one verified video job: the MP4 object plus its poster thumbnail."""
    try:
        objects = _validated_objects(job, result, VIDEO_SPEC)
        try:
            facts = validate_facts(result.get("video"))
        except ValueError as error:
            raise StoreError(422, f"worker video facts were refused ({error})") from error
        video = next(entry for entry in objects if entry["role"] == "video")
        if (facts["intrinsicWidth"], facts["intrinsicHeight"]) != (video["width"], video["height"]):
            raise StoreError(422, "worker video dimensions disagree with its facts")
        asset_id = _commit_asset(
            objects, name=name, kind="video", pipeline_version=VIDEO_PIPELINE_VERSION,
            display_role="video", master_role="video", facts=facts,
        )
        return asset_descriptor(asset_id) or {}
    finally:
        shutil.rmtree(job.directory, ignore_errors=True)


def asset_descriptor(asset_id: str) -> dict[str, Any] | None:
    """The v2 still descriptor for a ready asset, plus additive library fields.

    A video asset adds the R4 fields (``kind``, ``durationMs``, codec facts and
    ``poster``); a still carries none of them, so existing readers see exactly
    what they saw before.
    """
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT a.asset_id, a.name, a.width, a.height, a.state, a.created_at, "
            "o.object_id, o.mime, o.bytes, a.kind "
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
        video = None
        if row[9] == "video":
            video = connection.execute(
                "SELECT duration_ms, codec, profile, level, pixel_format, frame_rate, "
                "bitrate, faststart, has_audio FROM media_video WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if video is None:
                return None
    thumbnail = (
        {"id": thumb[0], "url": _asset_url(thumb[0]), "width": thumb[1], "height": thumb[2]}
        if thumb else None
    )
    descriptor = {
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
        "thumbnail": thumbnail,
    }
    if video is not None:
        descriptor.update({
            "kind": "video",
            "durationMs": video[0],
            "codec": video[1],
            "profile": video[2],
            "level": video[3],
            "pixelFormat": video[4],
            "frameRate": video[5],
            "bitrate": video[6],
            "faststart": bool(video[7]),
            "audio": bool(video[8]),
            "poster": thumbnail,
        })
    return descriptor


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


def video_descriptor(object_id: str) -> dict[str, Any] | None:
    """The full video descriptor for a ready video's ``sha256:`` content id.

    Playlist items name the content id, not the library's UUID, so this is the
    lookup the playlist validator and the ``prepare`` frame builder use.
    ``None`` means the id is not a ready video (a still, a poster, unknown).
    """
    if not _is_asset_id(object_id):
        return None
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT a.asset_id FROM media_assets a "
            "JOIN media_renditions r ON r.asset_id = a.asset_id "
            "WHERE r.object_id = ? AND r.role = 'video' AND a.kind = 'video' "
            "AND a.state = 'ready' LIMIT 1",
            (object_id,),
        ).fetchone()
    return asset_descriptor(str(row[0])) if row else None


def video_duration_ms(object_id: str) -> int | None:
    """``durationMs`` of a ready video content id; the playlist dwell for it."""
    descriptor = video_descriptor(object_id)
    return int(descriptor["durationMs"]) if descriptor else None


def _lookup(object_id: str, kind: str | None) -> dict[str, Any] | None:
    if not _is_asset_id(object_id):
        return None
    query = (
        "SELECT o.object_id, o.mime, o.bytes, o.path, o.width, o.height, a.kind "
        "FROM media_objects o JOIN media_renditions r ON r.object_id = o.object_id "
        "JOIN media_assets a ON a.asset_id = r.asset_id "
        "WHERE o.object_id = ? AND a.state = 'ready'"
    )
    arguments: tuple[str, ...] = (object_id,)
    if kind is not None:
        query += " AND a.kind = ?"
        arguments += (kind,)
    with persist._connection() as connection:
        row = connection.execute(query + " LIMIT 1", arguments).fetchone()
    if row is None:
        return None
    return {"id": row[0], "mime": row[1], "bytes": row[2], "path": row[3],
            "width": row[4], "height": row[5], "kind": row[6]}


def find_object(object_id: str) -> dict[str, Any] | None:
    """Metadata for a ready published still object, without reading its bytes.

    Video assets are excluded on purpose: this lookup feeds the still scene
    and playlist code, which must not accept an MP4 or a poster as an image.
    Use ``find_servable`` to serve bytes and ``video_descriptor`` for video.
    """
    return _lookup(object_id, "image")


def find_servable(object_id: str) -> dict[str, Any] | None:
    """Metadata for any ready published object: a still, a video, or a poster."""
    return _lookup(object_id, None)


def _object_path(entry: dict[str, Any]) -> str | None:
    """The object's file path, only when it resolves inside the object tree."""
    root = os.path.realpath(objects_dir())
    path = os.path.realpath(os.path.join(media_dir(), entry["path"]))
    return path if path.startswith(root + os.sep) else None


def fetch_object(object_id: str) -> tuple[bytes, str] | None:
    """Read and re-hash one published image object; None refuses to serve it.

    The ID is the hash of the bytes, so a response whose bytes still hash to
    the requested ID is provably that object. A missing row, a vanished file,
    a symlink, a path outside the object tree, or a hash mismatch all mean
    "serve nothing" rather than "serve something close". Videos are served by
    ``open_video`` instead, which does not buffer the file.
    """
    entry = find_servable(object_id)
    if entry is None or entry["mime"] == VIDEO_MIME:
        return None
    path = _object_path(entry)
    if path is None:
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


@dataclass(frozen=True)
class VideoFile:
    path: str
    stat: os.stat_result
    etag: str
    mime: str


# Objects whose full hash has been checked against their ID, keyed by file
# identity. A range request must not re-hash 250 MiB, but the first serve
# after a start or a restore still proves the bytes are the ID's bytes; a
# replaced or resized file changes the key and is re-verified.
_VERIFIED_VIDEOS: dict[str, tuple[int, int, int]] = {}
_VERIFY_LOCK = threading.Lock()
_VERIFIED_LIMIT = 256


def open_video(object_id: str) -> VideoFile | None:
    """A verified video file ready to stream, or None to serve nothing.

    The object must belong to a ready asset, live inside the object tree as a
    regular non-symlink file of exactly the recorded size, and hash to its own
    ID. The hash is checked once per file identity and cached.
    """
    entry = find_servable(object_id)
    if entry is None or entry["mime"] != VIDEO_MIME:
        return None
    path = _object_path(entry)
    if path is None:
        return None
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size != entry["bytes"]:
        return None
    key = (info.st_ino, info.st_size, info.st_mtime_ns)
    if _VERIFIED_VIDEOS.get(object_id) != key:
        with _VERIFY_LOCK:
            if _VERIFIED_VIDEOS.get(object_id) != key:
                try:
                    digest, size = _hash_file(path, MAX_VIDEO_BYTES)
                    after = os.lstat(path)
                except (OSError, StoreError):
                    return None
                if (
                    ASSET_ID_PREFIX + digest != object_id
                    or size != entry["bytes"]
                    or (after.st_ino, after.st_size, after.st_mtime_ns) != key
                ):
                    return None
                if len(_VERIFIED_VIDEOS) >= _VERIFIED_LIMIT:
                    _VERIFIED_VIDEOS.clear()
                _VERIFIED_VIDEOS[object_id] = key
    return VideoFile(path=path, stat=info, etag=f'"{object_id[len(ASSET_ID_PREFIX):]}"', mime=entry["mime"])


def verify_integrity() -> list[dict[str, Any]]:
    """Re-hash every ready object; return the entries that do not match.

    This is the explicit check an operator can run after a restore or a disk
    event. It never mutates rows or files.
    """
    problems: list[dict[str, Any]] = []
    with persist._connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT o.object_id, o.path, o.mime FROM media_objects o "
            "JOIN media_renditions r ON r.object_id = o.object_id "
            "JOIN media_assets a ON a.asset_id = r.asset_id "
            "WHERE a.state = 'ready'"
        ).fetchall()
    for object_id, relative, mime in rows:
        if mime == VIDEO_MIME:
            _VERIFIED_VIDEOS.pop(str(object_id), None)
            good = open_video(str(object_id)) is not None
        else:
            good = fetch_object(str(object_id)) is not None
        if not good:
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
    if host is None:
        return False
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

