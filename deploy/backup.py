"""Verified backup, verify and restore for the tablet-wall data (Phase 3b).

Two files carry the wall's durable state: the SQLite database (``wall_state``
plus the named snapshots) and the curated JPEG/PNG assets that the active and
saved scenes reference by content ID (``sha256:<hex>``). This tool snapshots
both into one versioned directory, checks that snapshot independently, and
restores it. Standard library only, so it runs anywhere the server runs.

What a snapshot is:

* the database is copied with SQLite's **online backup API**
  (``Connection.backup``), never a raw file copy of a database a writer may be
  mid-transaction on. There is deliberately no deadline on that copy: it waits
  for locks to clear instead of ever reporting a half-taken snapshot.
* references are read **from the snapshot**, not from the live file: the
  active scene (``wall_state.scene``) and every ``saved_scenes.content``
  document, and the stored playlist, are walked for ``asset`` content IDs, and only those files are
  copied out of the asset directory (top-level, regular, non-symlink; no
  upload, no scanning of sub-directories). Unreferenced files are not part of
  the wall and are not claimed. The copied bytes are hashed against the ID
  they were fetched for, and a reference that is missing, unreadable or
  mismatched fails the whole backup.
* ``manifest.json`` records a version, relative artifact paths, byte lengths
  and SHA-256 digests for the database and every asset, plus the revision and
  the reference list. No machine path is ever recorded in it.

Everything is assembled in a private sibling staging directory (mode 0700,
``.<dest>.incomplete-<random>``) and published to ``--dest`` only by one
rename, after the staging directory passes the same full check the ``verify``
command runs: SQLite ``integrity_check``, the expected tables, reference
closure (database <-> manifest <-> files), manifest path safety and digests,
and a tree scan that tolerates no symlink, no traversal and no stray file. A
backup that fails, is interrupted, or dies leaves no destination at all —
only a staging directory whose name is never mistaken for one.

What this tool deliberately will not do: overwrite or force anything (restore
accepts only brand-new targets), migrate the schema, follow symlinks, or
claim an atomic cutover. The restore targets are **two** paths — a database
file and an asset directory — written one after the other, so recovery from
an interrupted restore is "delete the targets that run created and run it
again"; rollback here removes only targets this run created itself. Restoring
also assumes the wall service is stopped: the tool refuses targets that
``TABLET_WALL_DB`` or ``TABLET_WALL_ASSET_DIR`` still name, but it cannot
otherwise see whether the process is running, so stop it yourself.

Integrity caveats: verification proves byte-for-byte agreement with the
manifest plus SQLite's own page-level integrity, not that the images decode
(the bytes are never handed to Pillow — byte identity to a content ID that
the inventory minted is the guarantee), and not that a snapshot taken from an
already-corrupt database is any less corrupt than its source.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import posixpath
import re
import secrets
import shutil
import sqlite3
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, NoReturn, Sequence

# The artifact layout, all relative and fixed: the manifest may not point at
# anything outside these two prefixes, so a hostile or stale manifest cannot
# steer verification (or restore) at an arbitrary path.
MANIFEST_VERSION = 2
SUPPORTED_MANIFEST_VERSIONS = (1, 2)
MANIFEST_NAME = "manifest.json"
DATABASE_DIR = "database"
ASSETS_DIR = "assets"
MEDIA_DIR = "media"
MEDIA_OBJECTS_DIR = "media/objects"
DATABASE_REL = DATABASE_DIR + "/wall.db"
ASSETS_PREFIX = ASSETS_DIR + "/"
MEDIA_OBJECTS_PREFIX = MEDIA_DIR + "/objects/"
STORE_LOCK_NAME = ".store.lock"
MEDIA_PIPELINE_VERSION = 1

# The schema this tool expects to find in a source database. It is read, never
# written: there is no CREATE or ALTER anywhere below, so a backup can never
# migrate the operator's file. Extra tables are tolerated (they ride along in
# the copied bytes and are covered by the database digest); missing ones are
# not, because a file without them is not this application's database.
EXPECTED_TABLES = ("wall_state", "saved_layouts", "saved_scenes")

ASSET_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
HEX64_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

# Mirrors the curated-inventory limit in tabletwall.assets: a file larger than
# this could never have been inventoried, hence never referenced. Capping the
# read also bounds the work if a path is swapped for something enormous.
MAX_ASSET_BYTES = 10 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
READ_CHUNK = 1 << 20

# O_NOFOLLOW (where the platform has it) plus an fstat re-check on the opened
# descriptor: a path swapped for a symlink or a directory between listing and
# opening is refused instead of followed. The create side is O_EXCL for the
# same reason — targets only ever appear, never get replaced.
OPEN_READ = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
OPEN_CREATE = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
)

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAGIC_BY_FORMAT = {"jpeg": JPEG_MAGIC, "png": PNG_MAGIC}
EXTENSIONS_BY_FORMAT = {"jpeg": (".jpg", ".jpeg"), "png": (".png",)}

MANIFEST_KEYS_V1 = {
    "manifest_version",
    "created_utc",
    "database",
    "assets",
    "references",
    "revision",
}
MANIFEST_KEYS_V2 = MANIFEST_KEYS_V1 | {
    "schema_version",
    "pipeline_version",
    "scope",
    "media_objects",
    "media_assets",
    "omitted_media",
}
DIGEST_ENTRY_KEYS = {"path", "bytes", "sha256"}
ASSET_ENTRY_KEYS = {"id", "path", "bytes", "sha256"}
MEDIA_OBJECT_KEYS = {"object_id", "path", "bytes", "sha256", "width", "height", "mime"}
MEDIA_ASSET_KEYS = {"asset_id", "display_object", "master_object", "renditions"}
MEDIA_RENDITION_KEYS = {"role", "object_id", "width", "height"}
UUID4_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\Z"
)

_PROG = "backup.py"


class BackupError(Exception):
    """A refusal or failure worth showing an operator verbatim on stderr.

    Control flow: every message is written to be printed as-is, and reaching
    one means no claim of completeness was made anywhere.
    """


def _fail(message: str) -> NoReturn:
    raise BackupError(message)


# ---------------------------------------------------------------------------
# hashing and copying (both ends of every digest check)
# ---------------------------------------------------------------------------


def _hash_fd(fd: int, limit: int | None) -> tuple[str, int, bytes, bool]:
    """Hash at most ``limit`` bytes from an open descriptor.

    Returns ``(hex digest, bytes read, first eight bytes, truncated)``. The
    eight-byte head is what lets a caller recognise JPEG/PNG content without a
    second pass; ``truncated`` means the cap stopped the read, so the digest
    describes a prefix and must not be compared against a whole-file ID.
    """
    hasher = hashlib.sha256()
    head = bytearray()
    count = 0
    while limit is None or count < limit:
        want = READ_CHUNK if limit is None else min(READ_CHUNK, limit - count)
        chunk = os.read(fd, want)
        if not chunk:
            return hasher.hexdigest(), count, bytes(head), False
        if len(head) < 8:
            head.extend(chunk[: 8 - len(head)])
        hasher.update(chunk)
        count += len(chunk)
    return hasher.hexdigest(), count, bytes(head), True


def _open_read(path: str) -> int:
    """Open a file for reading without following a symlink, or fail loudly."""
    try:
        return os.open(path, OPEN_READ)
    except OSError as exc:
        raise BackupError(f"cannot read {path}: {exc.strerror or exc}") from exc


def _hash_file(path: str, limit: int | None = None) -> tuple[str, int, bytes, bool]:
    """``_hash_fd`` over a verified regular file; the descriptor always closes."""
    fd = _open_read(path)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _fail(f"not a regular file: {path}")
        return _hash_fd(fd, limit)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    """``os.write`` until the whole chunk is out — short writes are legal."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _pump(src_fd: int, dst_fd: int, expected_bytes: int | None) -> tuple[int, str]:
    """Copy from ``src_fd`` to ``dst_fd``, hashing exactly what was written.

    ``expected_bytes + 1`` bounds the read: a file one byte longer than it
    should be stops at the cap and comes back as a count that cannot equal the
    expectation, so an ever-growing swap cannot turn into an unbounded copy.
    The destination is fsynced before returning, because a digest over bytes
    that only live in the page cache is not a durable claim.
    """
    hasher = hashlib.sha256()
    count = 0
    limit = None if expected_bytes is None else expected_bytes + 1
    while limit is None or count < limit:
        want = READ_CHUNK if limit is None else min(READ_CHUNK, limit - count)
        chunk = os.read(src_fd, want)
        if not chunk:
            break
        _write_all(dst_fd, chunk)
        hasher.update(chunk)
        count += len(chunk)
    os.fsync(dst_fd)
    return count, hasher.hexdigest()


def _remove_file_if_unchanged(path: str, ino: int) -> bool:
    """Delete ``path`` only if it is still the same inode this run created.

    A file swapped underneath us is somebody else's now, and rollback must
    never delete somebody else's file. True when the path is already gone.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return True
    if not stat.S_ISREG(info.st_mode) or info.st_ino != ino:
        return False
    try:
        os.unlink(path)
    except OSError:
        return False
    return True


def _copy_verified(
    source: str,
    target: str,
    *,
    expected_sha256: str,
    expected_bytes: int,
) -> tuple[int, int]:
    """Copy one file into a brand-new path, hashing the bytes that land there.

    The target is created with ``O_EXCL`` (absent-only, no overwrite), the
    source is read through ``O_NOFOLLOW`` + ``fstat``, and the digest of what
    was actually written must equal the expected one. Returns
    ``(inode, byte count)`` — the inode so the caller can record it for
    rollback, the count so a manifest never records a length it did not
    verify; on any failure the partial file is removed again before the error
    propagates.
    """
    src_fd = _open_read(source)
    created_ino: int | None = None
    try:
        if not stat.S_ISREG(os.fstat(src_fd).st_mode):
            _fail(f"not a regular file: {source}")
        dst_fd: int | None = None
        try:
            try:
                dst_fd = os.open(target, OPEN_CREATE, 0o666)
            except OSError as exc:
                _fail(f"cannot create {target}: {exc.strerror or exc}")
            created_ino = os.fstat(dst_fd).st_ino
            count, digest = _pump(src_fd, dst_fd, expected_bytes)
        finally:
            if dst_fd is not None:
                os.close(dst_fd)
        if count != expected_bytes or digest != expected_sha256:
            _fail(
                f"copied bytes of {source} are {count} bytes with sha256:{digest}, "
                f"expected {expected_bytes} bytes with sha256:{expected_sha256}"
            )
        return created_ino, count
    except BaseException:
        if created_ino is not None:
            _remove_file_if_unchanged(target, created_ino)
        raise
    finally:
        os.close(src_fd)


def _fsync_dir(path: str) -> None:
    """Make a rename durable where the platform allows it (best effort)."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# the online snapshot and the references read from it
# ---------------------------------------------------------------------------


def _connect_ro(path: str) -> sqlite3.Connection:
    """Open an existing database strictly read-only (URI ``mode=ro``).

    Read-only on purpose: a backup must never create a missing file, touch a
    journal, or otherwise write into the operator's source or an artifact.
    """
    uri = Path(os.path.abspath(path)).as_uri() + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"cannot open {path} read-only: {exc}") from exc


def _backup_with_retries(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    """Run ``Connection.backup`` until it succeeds, waiting out any lock.

    There is deliberately no deadline: the memo for this tool refuses to
    promise a backup completes within some fixed time, so a writer holding the
    database only delays the copy instead of corrupting it. Ctrl-C still works
    (the sleeps are interruptible), and the caller discards the staging file
    if that happens. Anything that is not a lock problem is a real failure and
    propagates.
    """
    delay = 0.05
    while True:
        try:
            source.backup(target)
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" not in message and "busy" not in message:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)


def _snapshot_database(source_path: str, target_path: str) -> None:
    """Copy ``source_path`` into ``target_path`` with SQLite's backup API.

    This is the whole point of the tool's first step: the source may be live,
    mid-transaction, and the copy still lands as one committed state. The
    result is normalised to a plain rollback journal so a source configured
    for WAL does not leave the artifact depending on sidecar ``-wal``/``-shm``
    files that the tree scan would (rightly) refuse as strays.
    """
    source = _connect_ro(source_path)
    try:
        try:
            target = sqlite3.connect(target_path)
        except sqlite3.Error as exc:
            raise BackupError(f"cannot create the snapshot {target_path}: {exc}") from exc
        try:
            try:
                _backup_with_retries(source, target)
                target.commit()
                target.execute("PRAGMA journal_mode=DELETE").fetchone()
                target.commit()
            except sqlite3.Error as exc:
                raise BackupError(
                    f"cannot take an online snapshot of {source_path}: {exc}"
                ) from exc
        finally:
            target.close()
    finally:
        source.close()


def _parse_document(text: Any, where: str) -> Any:
    """Parse one stored JSON document, failing when it cannot be read.

    Fail-closed on purpose: a scene whose JSON is unreadable has unknown
    image references, and a backup that silently skipped them would claim a
    closure it never checked. The listing API tolerates damaged snapshots;
    the backup refuses until the operator deletes or replaces the row.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        _fail(
            f"{where} is not readable JSON, so its image references cannot be "
            f"determined ({exc})"
        )


def _collect_references(document: Any, where: str, out: set[str]) -> None:
    """Gather every ``asset`` content ID inside one JSON document.

    Only values stored under the key ``asset`` count: that is where both the
    active scene and a saved scene keep their image reference, and scanning
    arbitrary strings for anything shaped like an ID would drag in content
    the wall never addresses that way. A value under ``asset`` that is neither
    null nor a well-formed content ID cannot be resolved, copied or verified,
    so it fails the backup rather than being skipped.
    """
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "asset":
                if value is None:
                    continue
                if not isinstance(value, str) or ASSET_ID_PATTERN.match(value) is None:
                    _fail(
                        f"{where} carries an invalid asset reference "
                        f"({value!r}), which cannot be backed up"
                    )
                out.add(value)
            else:
                _collect_references(value, where, out)
    elif isinstance(document, list):
        for item in document:
            _collect_references(item, where, out)


def _read_snapshot(database_path: str) -> tuple[set[str], int | None]:
    """Verify a database file and read its references — from that file alone.

    Returns ``(reference set, revision)``. The order matters: integrity check
    first (a file that fails it proves nothing else), then the expected tables
    (a file without them is not this application's database), then the JSON
    documents. Everything is read through the read-only connection, so this
    function cannot repair, migrate or otherwise touch its input.
    """
    connection = _connect_ro(database_path)
    try:
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.Error as exc:
            _fail(f"{database_path} is not a readable SQLite database: {exc}")
        if rows != [("ok",)]:
            problems = "; ".join(str(row[0]) for row in rows[:5])
            _fail(f"SQLite integrity check failed for {database_path}: {problems}")
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = [name for name in EXPECTED_TABLES if name not in tables]
            if missing:
                _fail(
                    f"{database_path} is missing expected table(s): "
                    f"{', '.join(missing)}"
                )
            references: set[str] = set()
            revision: int | None = None
            row = connection.execute(
                "SELECT scene, revision FROM wall_state WHERE id = 1"
            ).fetchone()
            if row is not None:
                scene, revision_value = row
                try:
                    revision = int(revision_value)
                except (TypeError, ValueError):
                    _fail(
                        f"{database_path} holds a wall revision that is not an "
                        f"integer: {revision_value!r}"
                    )
                _collect_references(
                    _parse_document(scene, "the active scene"),
                    "the active scene",
                    references,
                )
            saved = connection.execute(
                "SELECT name, content FROM saved_scenes ORDER BY name"
            ).fetchall()
            playlist = None
            if "schema_meta" in tables:
                found = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'playlist'"
                ).fetchone()
                playlist = found[0] if found else None
        except sqlite3.Error as exc:
            _fail(f"cannot read the database {database_path}: {exc}")
        if playlist is not None:
            # The playlist names assets no scene may reference; without this
            # a playlist-only upload is omitted and restored as unavailable.
            _collect_references(_parse_document(playlist, "the playlist"), "the playlist", references)
        for name, content in saved:
            document = _parse_document(content, f"saved scene {name!r}")
            if document is None:
                # JSON null carries nothing to reference; the app's own listing
                # treats such a snapshot as absent content as well.
                continue
            _collect_references(document, f"saved scene {name!r}", references)
        return references, revision
    finally:
        connection.close()


def _schema_version(database_path: str) -> int:
    connection = _connect_ro(database_path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        _fail(f"cannot read the schema version from {database_path}: {exc}")
    finally:
        connection.close()


def _read_media_closure(
    database_path: str, references: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Read the managed-media closure from the captured database.

    A scene root is a published object ID. The asset that owns it contributes
    its master, display, fallback and thumbnail objects, so the manifest can
    describe transitive closure without pretending those extra objects are
    scene references. Ready assets no scene references are returned as
    ``omitted``: their rows are marked unavailable in the captured copy rather
    than being claimed as backed up.
    """
    connection = _connect_ro(database_path)
    try:
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {"media_assets", "media_objects", "media_renditions"}
            if not required <= tables:
                return [], [], []
            object_rows = connection.execute(
                "SELECT object_id, mime, bytes, width, height, path FROM media_objects"
            ).fetchall()
            asset_rows = connection.execute(
                "SELECT asset_id, display_object, master_object, state FROM media_assets"
            ).fetchall()
            rendition_rows = connection.execute(
                "SELECT asset_id, object_id, role, width, height FROM media_renditions"
            ).fetchall()
        except sqlite3.Error as exc:
            _fail(f"cannot read managed media from {database_path}: {exc}")
    finally:
        connection.close()

    objects = {
        str(row[0]): {
            "object_id": str(row[0]), "mime": str(row[1]), "bytes": int(row[2]),
            "width": int(row[3]), "height": int(row[4]), "path": str(row[5]),
        }
        for row in object_rows
    }
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for asset_id, object_id, role, width, height in rendition_rows:
        by_asset.setdefault(str(asset_id), []).append(
            {"role": str(role), "object_id": str(object_id),
             "width": int(width), "height": int(height)}
        )
    referenced_assets: set[str] = set()
    for asset_id, renditions in by_asset.items():
        if any(rendition["object_id"] in references for rendition in renditions):
            referenced_assets.add(asset_id)

    media_assets: list[dict[str, Any]] = []
    used: set[str] = set()
    for asset_id, display_object, master_object, state in asset_rows:
        asset_id = str(asset_id)
        if asset_id not in referenced_assets:
            continue
        renditions = sorted(
            by_asset.get(asset_id, []), key=lambda entry: entry["role"]
        )
        if not renditions:
            _fail(f"managed asset {asset_id} has no renditions")
        for object_id in {str(display_object), str(master_object)} | {
            rendition["object_id"] for rendition in renditions
        }:
            if object_id not in objects:
                _fail(f"managed asset {asset_id} names a missing object {object_id}")
            used.add(object_id)
        media_assets.append({
            "asset_id": asset_id,
            "display_object": str(display_object),
            "master_object": str(master_object),
            "renditions": renditions,
        })

    media_objects = []
    for object_id in sorted(used):
        entry = dict(objects[object_id])
        entry["path"] = MEDIA_DIR + "/" + entry["path"]
        entry["sha256"] = object_id.split(":", 1)[1]
        media_objects.append(entry)

    omitted = sorted(
        str(asset_id)
        for asset_id, _display, _master, _state in asset_rows
        if str(asset_id) not in referenced_assets
    )
    return media_objects, media_assets, omitted


def _mark_omitted_media(database_path: str, omitted: list[str]) -> None:
    """Mark unreferenced ready assets unavailable inside the captured copy.

    This runs only on the snapshot, never on the live database, and before the
    snapshot's final digest. The restored application therefore never lists
    or serves a ready asset whose bytes were deliberately left out of the
    backup.
    """
    if not omitted:
        return
    connection = sqlite3.connect(database_path)
    try:
        connection.executemany(
            "UPDATE media_assets SET state = 'unavailable' WHERE asset_id = ?",
            [(asset_id,) for asset_id in omitted],
        )
        connection.commit()
    except sqlite3.Error as exc:
        _fail(f"cannot mark omitted media in the captured database: {exc}")
    finally:
        connection.close()


@contextlib.contextmanager
def _store_lock(media_source: str) -> Iterator[None]:
    """Hold the app's shared store lock from capture through verification.

    The lock file is the same stable inode ``tabletwall.media`` uses. A
    missing media directory is allowed only when the captured database has no
    media closure; the caller decides that after reading it, so this context
    is entered only when a media directory exists.
    """
    os.makedirs(media_source, exist_ok=True)
    lock = os.path.join(media_source, STORE_LOCK_NAME)
    fd = os.open(lock, os.O_CREAT | os.O_RDONLY | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# locating and copying referenced assets
# ---------------------------------------------------------------------------


def _candidates(directory: str) -> list[tuple[str, str]]:
    """Top-level, regular, non-symlink entries as ``(name, path)``, sorted.

    The same shape the curated inventory scans, and for the same reason: only
    the file itself is an asset. Symlinks are skipped rather than followed (a
    link out of the directory must not become a copy of something the wall
    cannot serve either), sub-directories are not descended into, and a
    directory that does not exist yet reads as empty. Anything else that goes
    wrong scanning — a path that is a plain file, a permissions failure — is
    an error, because guessing "no assets" there would hide a mistyped flag.
    """
    try:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except FileNotFoundError:
        return []
    except NotADirectoryError as exc:
        raise BackupError(f"asset path is not a directory: {directory}") from exc
    except OSError as exc:
        raise BackupError(f"cannot scan asset directory {directory}: {exc}") from exc
    result: list[tuple[str, str]] = []
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError:
            continue  # vanished between listing and statting: not a candidate
        result.append((entry.name, entry.path))
    return result


def _candidate_digest(path: str) -> tuple[str, int, bytes] | None:
    """Hash one candidate under the size cap; None when it cannot qualify.

    Unreadable, not a regular file, or over the curated byte limit all mean
    the same thing here: this path cannot be carrying the referenced bytes.
    """
    try:
        fd = os.open(path, OPEN_READ)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        digest, count, head, truncated = _hash_fd(fd, MAX_ASSET_BYTES + 1)
        if truncated or count > MAX_ASSET_BYTES:
            return None
        return digest, count, head
    finally:
        os.close(fd)


def _curated_format(name: str, head: bytes) -> str | None:
    """``jpeg``/``png`` when the name and the magic agree, else None.

    The inventory only ever lists a JPEG whose extension says JPEG and a PNG
    whose extension says PNG (and only those two formats), so a reference
    resolved to anything else is a reference the running wall cannot serve —
    the backup fails it instead of copying bytes under an asset ID that would
    404 after a restore.
    """
    extension = posixpath.splitext(name)[1].lower()
    for image_format, extensions in EXTENSIONS_BY_FORMAT.items():
        if extension in extensions and head.startswith(MAGIC_BY_FORMAT[image_format]):
            return image_format
    return None


def _locate_asset(
    directory: str,
    asset_id: str,
    cache: dict[str, tuple[str, int, bytes] | None],
) -> tuple[str, str, int]:
    """Find the curated file carrying ``asset_id``'s bytes.

    Returns ``(path, name, byte count)``. Each candidate is hashed at most
    once per run (identical bytes under two names are one logical asset, so
    the first match in sort order wins — the same tie-break the inventory
    uses). The three failure messages distinguish "gone", "not a curated
    JPEG/PNG" and "bytes do not match", because those need three different
    operator responses.
    """
    expected = asset_id.split(":", 1)[1]
    candidates = _candidates(directory)
    if not candidates:
        _fail(f"referenced asset {asset_id} is missing: {directory} holds no regular files")
    policy_violations = False
    for name, path in candidates:
        if path not in cache:
            cache[path] = _candidate_digest(path)
        cached = cache[path]
        if cached is None:
            continue
        digest, count, head = cached
        if digest != expected:
            continue
        if _curated_format(name, head) is None:
            policy_violations = True
            continue
        return path, name, count
    if policy_violations:
        _fail(
            f"referenced asset {asset_id} matches only files that are not a "
            f"curated JPEG/PNG in {directory}"
        )
    _fail(
        f"referenced asset {asset_id} is missing or unreadable in {directory} "
        f"(no top-level regular file carries its bytes)"
    )


def _asset_filename(asset_id: str, source_name: str) -> str:
    """The artifact's name for a copied asset: ``<hex><lowercase extension>``.

    Content-addressed and filesystem-safe by construction: no operator
    filename (which could be anything) is ever carried into the artifact, and
    the digest in the name is checked against the digest in the manifest.
    """
    digest = asset_id.split(":", 1)[1]
    extension = posixpath.splitext(source_name)[1].lower()
    return digest + extension


# ---------------------------------------------------------------------------
# manifest loading and path safety
# ---------------------------------------------------------------------------


def _require_safe_relative(value: Any, label: str) -> None:
    """Refuse anything that could leave the artifact directory when joined.

    Absolute paths, drive letters, backslashes, empty segments, ``.`` and
    ``..`` segments, NUL bytes and non-normalised forms are all rejected, so
    ``os.path.join(root, *value.split("/"))`` provably stays under ``root``.
    The message is identical for every reason: callers (and tests) need to
    know a manifest path was unsafe, not which flavour of unsafe it was.
    """
    if not isinstance(value, str) or not value:
        _fail(f"manifest {label} path is not a safe relative path: {value!r}")
    if "\x00" in value or "\\" in value:
        _fail(f"manifest {label} path is not a safe relative path: {value!r}")
    if posixpath.isabs(value) or re.match(r"[A-Za-z]:", value):
        _fail(f"manifest {label} path is not a safe relative path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _fail(f"manifest {label} path is not a safe relative path: {value!r}")
    if posixpath.normpath(value) != value:
        _fail(f"manifest {label} path is not a safe relative path: {value!r}")


def _require_digest_entry(entry: dict[str, Any], label: str) -> None:
    """Type-check one ``{path, bytes, sha256}`` record before any use of it.

    ``type(...) is int`` rather than ``isinstance`` so a JSON ``true`` cannot
    pass as a byte count, and the digest must be lowercase hex: comparing
    against a differently-cased digest would be a silent mismatch forever.
    """
    byte_count = entry["bytes"]
    if type(byte_count) is not int or byte_count < 0:
        _fail(f"manifest {label} bytes must be a non-negative integer, not {byte_count!r}")
    digest = entry["sha256"]
    if not isinstance(digest, str) or HEX64_PATTERN.match(digest) is None:
        _fail(f"manifest {label} sha256 must be 64 lowercase hex digits, not {digest!r}")


def _validate_manifest(manifest: Any) -> None:
    """Check a version 1 or version 2 manifest's shape and closure.

    Version 1 artifacts remain readable exactly as they were: their
    ``assets`` list is the scene-root reference list. Version 2 separates
    scene roots (``references``) from curated bytes (``assets``), managed
    objects (``media_objects``) and the asset-to-rendition relationships
    (``media_assets``), because one managed upload contributes several objects
    that are not themselves scene roots.
    """
    if not isinstance(manifest, dict):
        _fail(f"{MANIFEST_NAME} must contain a JSON object")
    version = manifest.get("manifest_version")
    if type(version) is not int:
        _fail(f"{MANIFEST_NAME} manifest_version must be an integer, not {version!r}")
    if version == 1:
        _validate_manifest_v1(manifest)
        return
    if version == 2:
        _validate_manifest_v2(manifest)
        return
    _fail(
        f"unsupported manifest version {version}: this tool reads versions "
        f"{', '.join(str(v) for v in SUPPORTED_MANIFEST_VERSIONS)}"
    )


def _validate_manifest_v1(manifest: dict[str, Any]) -> None:
    """The original manifest: assets list equals the scene-root references."""
    missing = sorted(MANIFEST_KEYS_V1 - set(manifest))
    unexpected = sorted(set(manifest) - MANIFEST_KEYS_V1)
    if missing or unexpected:
        _fail(
            f"{MANIFEST_NAME} must carry exactly {sorted(MANIFEST_KEYS_V1)} "
            f"(missing: {missing}, unexpected: {unexpected})"
        )
    if not isinstance(manifest["created_utc"], str):
        _fail(f"{MANIFEST_NAME} created_utc must be a string")
    revision = manifest["revision"]
    if revision is not None and type(revision) is not int:
        _fail(f"{MANIFEST_NAME} revision must be an integer or null, not {revision!r}")

    database = manifest["database"]
    if not isinstance(database, dict) or set(database) != DIGEST_ENTRY_KEYS:
        _fail(f"{MANIFEST_NAME} database must be an object with exactly path, bytes, sha256")
    _require_digest_entry(database, "database")
    _require_safe_relative(database["path"], "database")
    if database["path"] != DATABASE_REL:
        _fail(
            f"manifest database path must be {DATABASE_REL!r}, not {database['path']!r}"
        )

    seen_references = _validate_reference_list(manifest["references"])
    seen_ids = _validate_curated_assets(manifest["assets"])
    if seen_ids != seen_references:
        _fail(
            "manifest references and assets disagree: only in references "
            f"{sorted(seen_references - seen_ids)}, only in assets "
            f"{sorted(seen_ids - seen_references)}"
        )


def _validate_reference_list(references: Any) -> set[str]:
    if not isinstance(references, list):
        _fail(f"{MANIFEST_NAME} references must be a list")
    seen: set[str] = set()
    for reference in references:
        if not isinstance(reference, str) or ASSET_ID_PATTERN.match(reference) is None:
            _fail(f"manifest reference is not a content id: {reference!r}")
        if reference in seen:
            _fail(f"manifest lists reference {reference} twice")
        seen.add(reference)
    return seen


def _validate_curated_assets(assets: Any) -> set[str]:
    if not isinstance(assets, list):
        _fail(f"{MANIFEST_NAME} assets must be a list")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict) or set(entry) != ASSET_ENTRY_KEYS:
            _fail(
                f"{MANIFEST_NAME} asset entries must be objects with exactly "
                f"id, path, bytes, sha256"
            )
        asset_id = entry["id"]
        if not isinstance(asset_id, str) or ASSET_ID_PATTERN.match(asset_id) is None:
            _fail(f"manifest asset id is not a content id: {asset_id!r}")
        if asset_id in seen_ids:
            _fail(f"manifest lists asset {asset_id} twice")
        seen_ids.add(asset_id)
        _require_digest_entry(entry, f"asset {asset_id}")
        _require_safe_relative(entry["path"], f"asset {asset_id}")
        if not entry["path"].startswith(ASSETS_PREFIX):
            _fail(
                f"manifest asset path must start with {ASSETS_PREFIX!r}, "
                f"not {entry['path']!r}"
            )
        filename = entry["path"][len(ASSETS_PREFIX) :]
        digest = asset_id.split(":", 1)[1]
        extension = posixpath.splitext(filename)[1]
        if (
            extension != extension.lower()
            or extension not in (".jpg", ".jpeg", ".png")
            or filename != digest + extension
        ):
            _fail(
                f"manifest asset path must be {ASSETS_PREFIX}<sha256 hex>"
                f"<.jpg|.jpeg|.png>, not {entry['path']!r}"
            )
        if entry["sha256"] != digest:
            _fail(f"manifest digest for {asset_id} does not match its own id")
        if entry["path"] in seen_paths:
            _fail(f"manifest lists the same asset path twice: {entry['path']!r}")
        seen_paths.add(entry["path"])
    return seen_ids


def _validate_manifest_v2(manifest: dict[str, Any]) -> None:
    missing = sorted(MANIFEST_KEYS_V2 - set(manifest))
    unexpected = sorted(set(manifest) - MANIFEST_KEYS_V2)
    if missing or unexpected:
        _fail(
            f"{MANIFEST_NAME} must carry exactly {sorted(MANIFEST_KEYS_V2)} "
            f"(missing: {missing}, unexpected: {unexpected})"
        )
    if not isinstance(manifest["created_utc"], str):
        _fail(f"{MANIFEST_NAME} created_utc must be a string")
    revision = manifest["revision"]
    if revision is not None and type(revision) is not int:
        _fail(f"{MANIFEST_NAME} revision must be an integer or null, not {revision!r}")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] < 0:
        _fail(f"{MANIFEST_NAME} schema_version must be a non-negative integer")
    if type(manifest["pipeline_version"]) is not int or manifest["pipeline_version"] < 1:
        _fail(f"{MANIFEST_NAME} pipeline_version must be a positive integer")
    if manifest["scope"] != "referenced":
        _fail(f"{MANIFEST_NAME} scope must be 'referenced', not {manifest['scope']!r}")

    database = manifest["database"]
    if not isinstance(database, dict) or set(database) != DIGEST_ENTRY_KEYS:
        _fail(f"{MANIFEST_NAME} database must be an object with exactly path, bytes, sha256")
    _require_digest_entry(database, "database")
    _require_safe_relative(database["path"], "database")
    if database["path"] != DATABASE_REL:
        _fail(
            f"manifest database path must be {DATABASE_REL!r}, not {database['path']!r}"
        )

    references = _validate_reference_list(manifest["references"])
    curated_ids = _validate_curated_assets(manifest["assets"])

    objects = manifest["media_objects"]
    if not isinstance(objects, list):
        _fail(f"{MANIFEST_NAME} media_objects must be a list")
    object_ids: set[str] = set()
    object_paths: set[str] = set()
    for entry in objects:
        if not isinstance(entry, dict) or set(entry) != MEDIA_OBJECT_KEYS:
            _fail(
                f"{MANIFEST_NAME} media objects must carry exactly "
                f"{sorted(MEDIA_OBJECT_KEYS)}"
            )
        object_id = entry["object_id"]
        if not isinstance(object_id, str) or ASSET_ID_PATTERN.match(object_id) is None:
            _fail(f"manifest media object id is not a content id: {object_id!r}")
        if object_id in object_ids:
            _fail(f"manifest lists media object {object_id} twice")
        object_ids.add(object_id)
        path = entry["path"]
        _require_safe_relative(path, f"media object {object_id}")
        if not path.startswith(MEDIA_OBJECTS_PREFIX):
            _fail(
                f"manifest media path must start with {MEDIA_OBJECTS_PREFIX!r}, "
                f"not {path!r}"
            )
        relative = path[len(MEDIA_OBJECTS_PREFIX) :]
        parts = relative.split("/")
        digest = object_id.split(":", 1)[1]
        if len(parts) != 2 or parts[0] != digest[:2] or parts[1] != digest + ".jpg":
            _fail(
                f"manifest media path must be {MEDIA_OBJECTS_PREFIX}<aa>/<hex>.jpg, "
                f"not {path!r}"
            )
        if path in object_paths:
            _fail(f"manifest lists the same media path twice: {path!r}")
        object_paths.add(path)
        if entry["sha256"] != digest:
            _fail(f"manifest digest for {object_id} does not match its own id")
        for field in ("bytes", "width", "height"):
            if type(entry[field]) is not int or entry[field] <= 0:
                _fail(f"manifest media object {object_id} has an invalid {field}")
        if entry["bytes"] > MAX_ASSET_BYTES:
            _fail(f"manifest media object {object_id} exceeds the byte ceiling")
        if entry["mime"] != "image/jpeg":
            _fail(f"manifest media object {object_id} is not image/jpeg")

    assets = manifest["media_assets"]
    if not isinstance(assets, list):
        _fail(f"{MANIFEST_NAME} media_assets must be a list")
    asset_ids: set[str] = set()
    covered: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict) or set(entry) != MEDIA_ASSET_KEYS:
            _fail(
                f"{MANIFEST_NAME} media assets must carry exactly "
                f"{sorted(MEDIA_ASSET_KEYS)}"
            )
        asset_id = entry["asset_id"]
        if not isinstance(asset_id, str) or UUID4_PATTERN.match(asset_id) is None:
            _fail(f"manifest media asset id is not a UUID4: {asset_id!r}")
        if asset_id in asset_ids:
            _fail(f"manifest lists media asset {asset_id} twice")
        asset_ids.add(asset_id)
        for field in ("display_object", "master_object"):
            if entry[field] not in object_ids:
                _fail(f"media asset {asset_id} names an unknown {field}")
        renditions = entry["renditions"]
        if not isinstance(renditions, list):
            _fail(f"media asset {asset_id} renditions must be a list")
        roles: dict[str, str] = {}
        for rendition in renditions:
            if not isinstance(rendition, dict) or set(rendition) != MEDIA_RENDITION_KEYS:
                _fail(
                    f"media asset {asset_id} renditions must carry exactly "
                    f"role, object_id"
                )
            role = rendition["role"]
            if role not in {"master", "display", "fallback", "thumbnail"}:
                _fail(f"media asset {asset_id} has an unknown role {role!r}")
            if role in roles:
                _fail(f"media asset {asset_id} lists role {role} twice")
            if rendition["object_id"] not in object_ids:
                _fail(f"media asset {asset_id} names an unknown object")
            for field in ("width", "height"):
                if type(rendition[field]) is not int or rendition[field] <= 0:
                    _fail(f"media asset {asset_id} has an invalid rendition {field}")
            roles[role] = rendition["object_id"]
            covered.add(rendition["object_id"])
        if set(roles) != {"master", "display", "fallback", "thumbnail"}:
            _fail(f"media asset {asset_id} is missing a rendition role")
        if roles["display"] != entry["display_object"]:
            _fail(f"media asset {asset_id} display object disagrees with its role")
        if roles["master"] != entry["master_object"]:
            _fail(f"media asset {asset_id} master object disagrees with its role")
        if not (set(roles.values()) & references):
            _fail(f"media asset {asset_id} is not referenced by any scene")

    omitted = manifest["omitted_media"]
    if not isinstance(omitted, list):
        _fail(f"{MANIFEST_NAME} omitted_media must be a list")
    seen_omitted: set[str] = set()
    for asset_id in omitted:
        if not isinstance(asset_id, str) or UUID4_PATTERN.match(asset_id) is None:
            _fail(f"omitted media id is not a UUID4: {asset_id!r}")
        if asset_id in seen_omitted:
            _fail(f"manifest lists omitted media {asset_id} twice")
        seen_omitted.add(asset_id)
    overlap = seen_omitted & asset_ids
    if overlap:
        _fail(f"manifest includes and omits the same media asset: {sorted(overlap)}")
    if covered != object_ids:
        _fail(
            "manifest media objects and renditions disagree: unreferenced objects "
            f"{sorted(object_ids - covered)}"
        )
    managed_references = references & object_ids
    if managed_references - covered:
        _fail(
            "manifest references name unmanaged objects: "
            f"{sorted(managed_references - covered)}"
        )
    if curated_ids != references - object_ids:
        _fail(
            "manifest references and curated assets disagree: only in references "
            f"{sorted(references - object_ids - curated_ids)}, only in assets "
            f"{sorted(curated_ids - (references - object_ids))}"
        )


def _load_manifest(path: str) -> dict[str, Any]:
    """Read and fully validate ``manifest.json``; a missing one is incomplete.

    The missing-file message is deliberately about completeness rather than
    error: an interrupted backup never writes its manifest, so a directory
    without one is precisely a half-finished staging area that must never be
    recognised as a backup.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"{MANIFEST_NAME} is missing: {path} is not a complete artifact")
    if stat.S_ISLNK(info.st_mode):
        _fail(f"{MANIFEST_NAME} is a symlink: {path}")
    if not stat.S_ISREG(info.st_mode):
        _fail(f"{MANIFEST_NAME} is not a regular file: {path}")
    fd = _open_read(path)
    chunks: list[bytes] = []
    count = 0
    try:
        while True:
            chunk = os.read(fd, READ_CHUNK)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_MANIFEST_BYTES:
                _fail(f"{MANIFEST_NAME} is larger than {MAX_MANIFEST_BYTES} bytes")
            chunks.append(chunk)
    finally:
        os.close(fd)
    try:
        manifest = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{MANIFEST_NAME} is not valid JSON: {exc}")
    _validate_manifest(manifest)
    return manifest


def _write_manifest(path: str, manifest: dict[str, Any]) -> None:
    """Write the manifest last, durably, as one new file (never a rewrite)."""
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(path, OPEN_CREATE, 0o666)
    except OSError as exc:
        _fail(f"cannot create {path}: {exc.strerror or exc}")
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# artifact structure and content verification
# ---------------------------------------------------------------------------


def _require_artifact_directory(path: str) -> str:
    """The ``--src``/``--dest`` directory itself: present, a directory, not a link."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"artifact directory does not exist: {path}")
    if stat.S_ISLNK(info.st_mode):
        _fail(f"artifact path is a symlink: {path}")
    if not stat.S_ISDIR(info.st_mode):
        _fail(f"artifact path is not a directory: {path}")
    return path


def _artifact_file(root: str, relative: str) -> str:
    """Join a manifest path that has already passed the safety check."""
    return os.path.join(root, *relative.split("/"))


def _is_inside(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or lives under it (resolved, so a
    symlinked parent cannot smuggle a target in beside the snapshot)."""
    resolved_path = os.path.realpath(path)
    resolved_root = os.path.realpath(root)
    return resolved_path == resolved_root or resolved_path.startswith(
        resolved_root + os.sep
    )


def _check_tree(root: str, manifest: dict[str, Any]) -> None:
    """Walk the artifact: exact contents, no symlinks, no specials, no strays.

    This is also where "unreferenced files are not claimed" is enforced in the
    other direction: a file in the artifact that the manifest does not list is
    a failure, so nothing inside a snapshot can be secretly carried along.
    Symlinked directories are flagged without being descended into
    (``followlinks=False``), and a manifest file missing from the tree is
    reported as incompleteness rather than as corruption.
    """
    expected = {MANIFEST_NAME, manifest["database"]["path"]}
    expected.update(entry["path"] for entry in manifest["assets"])
    allowed_directories = {"", DATABASE_DIR, ASSETS_DIR}
    if manifest["manifest_version"] == 2:
        expected.update(entry["path"] for entry in manifest["media_objects"])
        allowed_directories |= {MEDIA_DIR, MEDIA_OBJECTS_DIR}
        for entry in manifest["media_objects"]:
            allowed_directories.add(posixpath.dirname(entry["path"]))
    seen: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        relative_directory = os.path.relpath(directory, root)
        if relative_directory == ".":
            relative_directory = ""
        relative_directory = relative_directory.replace(os.sep, "/")
        for name in dirnames:
            relative = f"{relative_directory}/{name}" if relative_directory else name
            info = os.lstat(os.path.join(directory, name))
            if stat.S_ISLNK(info.st_mode):
                _fail(f"artifact contains a symlinked directory: {relative}")
            if relative not in allowed_directories:
                _fail(f"artifact contains an unexpected directory: {relative}")
        for name in filenames:
            relative = f"{relative_directory}/{name}" if relative_directory else name
            info = os.lstat(os.path.join(directory, name))
            if stat.S_ISLNK(info.st_mode):
                _fail(f"artifact contains a symlink: {relative}")
            if not stat.S_ISREG(info.st_mode):
                _fail(f"artifact contains a special file: {relative}")
            if relative not in expected:
                _fail(f"artifact contains an unexpected file: {relative}")
            seen.add(relative)
    if seen != expected:
        absent = sorted(expected - seen)
        _fail(f"artifact is incomplete; missing: {', '.join(absent)}")


def _check_digest_file(path: str, entry: dict[str, Any], label: str) -> None:
    """One file must exist as a regular file with exactly the recorded bytes."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"{label} is missing: {path}")
    if stat.S_ISLNK(info.st_mode):
        _fail(f"{label} is a symlink: {path}")
    if not stat.S_ISREG(info.st_mode):
        _fail(f"{label} is not a regular file: {path}")
    if info.st_size != entry["bytes"]:
        _fail(f"{label} is {info.st_size} bytes, the manifest says {entry['bytes']}")
    digest, count, _head, truncated = _hash_file(path, limit=entry["bytes"] + 1)
    if truncated or count != entry["bytes"] or digest != entry["sha256"]:
        _fail(
            f"{label} does not match the manifest digest "
            f"(sha256:{digest}, {count} bytes)"
        )


def _check_reference_closure(references: set[str], manifest: dict[str, Any]) -> None:
    """Database ⇄ manifest agreement: every reference has an asset and back."""
    expected = set(manifest["references"])
    if references != expected:
        _fail(
            "reference closure failed: only in the database "
            f"{sorted(references - expected)}, only in the manifest "
            f"{sorted(expected - references)}"
        )


def _check_manifest_closure(
    database_path: str, references: set[str], manifest: dict[str, Any]
) -> None:
    """Database and manifest must describe the same closure, version-specifically."""
    if manifest["manifest_version"] == 1:
        _check_reference_closure(references, manifest)
        return
    if references != set(manifest["references"]):
        _fail(
            "reference closure failed: only in the database "
            f"{sorted(references - set(manifest['references']))}, only in the "
            f"manifest {sorted(set(manifest['references']) - references)}"
        )
    objects, assets, omitted = _read_media_closure(database_path, references)
    wanted_objects = {entry["object_id"]: entry for entry in manifest["media_objects"]}
    actual_objects = {entry["object_id"]: entry for entry in objects}
    if set(wanted_objects) != set(actual_objects):
        _fail(
            "managed object closure failed: only in the database "
            f"{sorted(set(actual_objects) - set(wanted_objects))}, only in the "
            f"manifest {sorted(set(wanted_objects) - set(actual_objects))}"
        )
    for object_id, wanted in wanted_objects.items():
        actual = actual_objects[object_id]
        for field in ("path", "bytes", "sha256", "width", "height", "mime"):
            if wanted[field] != actual[field]:
                _fail(
                    f"managed object {object_id} {field} disagrees between the "
                    f"database and the manifest"
                )
    wanted_assets = {entry["asset_id"]: entry for entry in manifest["media_assets"]}
    actual_assets = {entry["asset_id"]: entry for entry in assets}
    if set(wanted_assets) != set(actual_assets):
        _fail(
            "managed asset closure failed: only in the database "
            f"{sorted(set(actual_assets) - set(wanted_assets))}, only in the "
            f"manifest {sorted(set(wanted_assets) - set(actual_assets))}"
        )
    for asset_id, wanted in wanted_assets.items():
        actual = actual_assets[asset_id]
        if (
            wanted["display_object"] != actual["display_object"]
            or wanted["master_object"] != actual["master_object"]
            or sorted(wanted["renditions"], key=lambda entry: entry["role"])
            != sorted(actual["renditions"], key=lambda entry: entry["role"])
        ):
            _fail(f"managed asset {asset_id} disagrees between the database and the manifest")
    if sorted(omitted) != sorted(manifest["omitted_media"]):
        _fail(
            "omitted media closure failed: only in the database "
            f"{sorted(set(omitted) - set(manifest['omitted_media']))}, only in "
            f"the manifest {sorted(set(manifest['omitted_media']) - set(omitted))}"
        )


def verify_artifact(src: str) -> dict[str, Any]:
    """Fully check a snapshot directory; return its manifest or raise.

    The single verification path: ``backup`` runs this on its staging
    directory before the rename that makes the snapshot exist at all, and the
    ``verify`` and ``restore`` commands run it on whatever directory they are
    given. Order is structural first (manifest, then the tree, then per-file
    digests) so no content is ever read through a path the structure has not
    blessed, and the database is last because it is what ties the manifest's
    claim about references back to the data itself.
    """
    root = _require_artifact_directory(src)
    manifest = _load_manifest(os.path.join(root, MANIFEST_NAME))
    _check_tree(root, manifest)
    database_path = _artifact_file(root, manifest["database"]["path"])
    _check_digest_file(database_path, manifest["database"], "database")
    for entry in manifest["assets"]:
        _check_digest_file(
            _artifact_file(root, entry["path"]), entry, f"asset {entry['id']}"
        )
    for entry in manifest.get("media_objects", []):
        _check_digest_file(
            _artifact_file(root, entry["path"]), entry,
            f"media object {entry['object_id']}",
        )
    references, revision = _read_snapshot(database_path)
    _check_manifest_closure(database_path, references, manifest)
    if revision != manifest["revision"]:
        _fail(
            f"manifest revision {manifest['revision']!r} does not match the "
            f"database revision {revision!r}"
        )
    return manifest


# ---------------------------------------------------------------------------
# restore-side guards and rollback
# ---------------------------------------------------------------------------


def _assert_service_stopped(
    db_target: str, assets_target: str, media_target: str | None = None
) -> None:
    """Refuse targets the current environment still names for the service.

    A best-effort check and nothing more: the tool cannot see whether the
    wall process is running, but a service configured with ``TABLET_WALL_DB``
    or ``TABLET_WALL_ASSET_DIR`` pointing at these exact paths is the dangerous
    case — writing here would hand a future start a database it believes is
    its own. Everything else (a service configured elsewhere, or stopped but
    remembered in another shell) is the operator's to handle; the restore help
    says so, because a guard that pretended otherwise would be worse than
    none.
    """
    configured_targets = [
        ("TABLET_WALL_DB", db_target),
        ("TABLET_WALL_ASSET_DIR", assets_target),
    ]
    if media_target is not None:
        configured_targets.append(("TABLET_WALL_MEDIA_DIR", media_target))
    for variable, target in configured_targets:
        configured = os.environ.get(variable)
        if not configured:
            continue
        resolved = os.path.abspath(os.path.expanduser(configured))
        if resolved == target:
            _fail(
                f"{variable} still names this restore target ({target}); stop "
                f"the wall service and restore to a path it is not configured with"
            )


def _rollback(created: Sequence[tuple[str, str, int]]) -> None:
    """Remove exactly what this run created, newest first, inode-guarded.

    Paths this run did not create are never in the list (every target is
    refused before any write if it exists), so "rollback" here cannot reach
    the operator's previous database or asset directory — those are the
    rollback, and they stay. A path that was swapped out from under us is
    reported instead of deleted.
    """
    for path, kind, ino in reversed(list(created)):
        if kind == "dir":
            try:
                info = os.lstat(path)
            except FileNotFoundError:
                continue
            if (
                not stat.S_ISDIR(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_ino != ino
            ):
                print(
                    f"warning: not removing {path}: it is no longer the "
                    f"directory this run created",
                    file=sys.stderr,
                )
                continue
            shutil.rmtree(path, ignore_errors=True)
        elif not _remove_file_if_unchanged(path, ino):
            print(
                f"warning: not removing {path}: it is no longer the file this "
                f"run created",
                file=sys.stderr,
            )


def _remove_staging(path: str, ino: int) -> None:
    """Discard a failed run's staging directory — and nothing else.

    Inode-guarded because a path that got replaced between creation and
    cleanup is not ours to delete; a path that is already gone is the normal
    case after a successful promotion.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and info.st_ino == ino:
        shutil.rmtree(path, ignore_errors=True)


def _print_summary(heading: str, root: str, manifest: dict[str, Any]) -> None:
    """A short, operator-facing account of what was proven (paths included:
    they go to the terminal, never into the artifact)."""
    asset_bytes = sum(entry["bytes"] for entry in manifest["assets"])
    print(f"{heading} {root}")
    print(
        f"  database: {manifest['database']['path']} "
        f"({manifest['database']['bytes']} bytes, "
        f"sha256:{manifest['database']['sha256']})"
    )
    print(f"  assets: {len(manifest['assets'])} referenced file(s), {asset_bytes} bytes")
    if manifest["manifest_version"] == 2:
        media_bytes = sum(entry["bytes"] for entry in manifest["media_objects"])
        print(
            f"  media: {len(manifest['media_assets'])} managed asset(s), "
            f"{len(manifest['media_objects'])} object(s), {media_bytes} bytes"
        )
        print(f"  omitted media: {len(manifest['omitted_media'])} unused upload(s)")
        print(
            f"  schema {manifest['schema_version']}, pipeline "
            f"{manifest['pipeline_version']}, scope {manifest['scope']}"
        )
    print(f"  revision: {manifest['revision']}")
    print(f"  references: {len(manifest['references'])}")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_backup(args: argparse.Namespace) -> int:
    """``backup --db PATH --assets DIR --dest DIR`` — snapshot into a new directory."""
    db_source = os.path.abspath(args.db)
    assets_source = os.path.abspath(args.assets)
    media_source = os.path.abspath(args.media)
    dest = os.path.abspath(args.dest)

    # Every refusal that can be decided from the paths alone happens before
    # the first byte is written, so a rejected backup leaves no trace — not a
    # staging directory, not an emptied destination, not a created parent.
    if not os.path.exists(db_source):
        _fail(f"source database does not exist: {db_source}")
    if os.path.isdir(db_source):
        _fail(f"source database is a directory: {db_source}")
    if os.path.exists(assets_source) and not os.path.isdir(assets_source):
        _fail(f"asset path is not a directory: {assets_source}")
    if os.path.exists(media_source) and not os.path.isdir(media_source):
        _fail(f"media path is not a directory: {media_source}")
    if dest == db_source or dest == assets_source:
        _fail(f"destination must not be one of the source paths: {dest}")
    if os.path.lexists(dest):
        _fail(f"destination already exists; refusing to overwrite: {dest}")
    parent = os.path.dirname(dest)
    if not os.path.isdir(parent):
        _fail(f"destination parent directory does not exist: {parent}")

    # Private staging: a random sibling of the destination, mode 0700, whose
    # name is never mistaken for a finished backup. Only the final rename
    # below puts anything at the destination path, and it happens after the
    # whole artifact has passed verification.
    staging = os.path.join(
        parent, f".{os.path.basename(dest)}.incomplete-{secrets.token_hex(6)}"
    )
    try:
        os.mkdir(staging, 0o700)
    except OSError as exc:
        _fail(f"cannot create staging directory {staging}: {exc.strerror or exc}")
    staging_ino = os.lstat(staging).st_ino

    try:
        lock = _store_lock(media_source) if os.path.isdir(media_source) else contextlib.nullcontext()
        with lock:
            os.mkdir(os.path.join(staging, DATABASE_DIR), 0o777)
            snapshot_path = _artifact_file(staging, DATABASE_REL)
            _snapshot_database(db_source, snapshot_path)
            # References and managed closure come from the snapshot, never
            # from the live file: they describe exactly the state copied.
            references, revision = _read_snapshot(snapshot_path)
            media_objects, media_assets, omitted = _read_media_closure(
                snapshot_path, references
            )
            if media_objects and not os.path.isdir(media_source):
                _fail(
                    f"the captured database references managed media, but "
                    f"{media_source} does not exist"
                )
            _mark_omitted_media(snapshot_path, omitted)

            os.mkdir(os.path.join(staging, ASSETS_DIR), 0o777)
            digests: dict[str, tuple[str, int, bytes] | None] = {}
            asset_entries: list[dict[str, Any]] = []
            managed_ids = {entry["object_id"] for entry in media_objects}
            for asset_id in sorted(references):
                if asset_id in managed_ids:
                    continue
                source_path, source_name, source_bytes = _locate_asset(
                    assets_source, asset_id, digests
                )
                filename = _asset_filename(asset_id, source_name)
                _asset_ino, written = _copy_verified(
                    source_path,
                    os.path.join(staging, ASSETS_DIR, filename),
                    expected_sha256=asset_id.split(":", 1)[1],
                    expected_bytes=source_bytes,
                )
                asset_entries.append(
                    {
                        "id": asset_id,
                        "path": ASSETS_PREFIX + filename,
                        "bytes": written,
                        "sha256": asset_id.split(":", 1)[1],
                    }
                )

            for entry in media_objects:
                relative = entry["path"][len(MEDIA_DIR) + 1 :]
                parts = relative.split("/")
                digest = entry["sha256"]
                if (
                    not relative.startswith("objects/")
                    or len(parts) != 3
                    or parts[1] != digest[:2]
                    or parts[2] != digest + ".jpg"
                ):
                    _fail(
                        f"managed object {entry['object_id']} has an unsafe store path"
                    )
                target = os.path.join(staging, *entry["path"].split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                _copy_verified(
                    os.path.join(media_source, *parts),
                    target,
                    expected_sha256=digest,
                    expected_bytes=entry["bytes"],
                )

            database_digest, database_bytes, _head, _truncated = _hash_file(snapshot_path)
            manifest = {
                "manifest_version": MANIFEST_VERSION,
                "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "schema_version": _schema_version(snapshot_path),
                "pipeline_version": MEDIA_PIPELINE_VERSION,
                "scope": "referenced",
                "database": {
                    "path": DATABASE_REL,
                    "bytes": database_bytes,
                    "sha256": database_digest,
                },
                "assets": asset_entries,
                "media_objects": media_objects,
                "media_assets": media_assets,
                "omitted_media": omitted,
                "references": sorted(references),
                "revision": revision,
            }
            # The manifest goes in last: until it exists, a directory cannot be
            # mistaken for a backup even by someone who finds it mid-run.
            _write_manifest(os.path.join(staging, MANIFEST_NAME), manifest)
            # Verify the staging directory with the same code path the verify
            # command uses, and only then publish it in one rename. An artifact
            # that is not fully checked never reaches the destination path.
            verify_artifact(staging)
            if os.path.lexists(dest):
                _fail(
                    f"destination appeared while the backup was running; refusing "
                    f"to overwrite: {dest}"
                )
            try:
                os.rename(staging, dest)
            except OSError as exc:
                _fail(f"cannot publish the snapshot to {dest}: {exc.strerror or exc}")
            _fsync_dir(parent)
    except BaseException:
        _remove_staging(staging, staging_ino)
        raise

    _print_summary("backup complete:", dest, manifest)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """``verify --src DIR`` — fully check an existing snapshot directory."""
    manifest = verify_artifact(os.path.abspath(args.src))
    _print_summary("verified:", os.path.abspath(args.src), manifest)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """``restore --src DIR --db NEW_PATH --assets NEW_DIR [--media NEW_DIR]``."""
    src = os.path.abspath(args.src)
    db_target = os.path.abspath(args.db)
    assets_target = os.path.abspath(args.assets)
    media_target = os.path.abspath(args.media) if args.media else None

    # Nothing is written until the snapshot itself has proven sound, and
    # every target check happens before any write, so a refusal anywhere
    # leaves the machine exactly as it was.
    manifest = verify_artifact(src)
    if (
        manifest["manifest_version"] == 2
        and manifest["media_objects"]
        and media_target is None
    ):
        _fail(
            "this snapshot carries managed media, so restore also needs "
            "--media NEW_DIR"
        )
    targets = [("database", db_target), ("asset directory", assets_target)]
    if media_target is not None:
        targets.append(("media directory", media_target))
    for index, (label, target) in enumerate(targets):
        for other_label, other in targets[index + 1:]:
            if target == other:
                _fail(f"{label} and {other_label} targets must be two different paths")
        if os.path.lexists(target):
            _fail(f"{label} target already exists; refusing to overwrite: {target}")
        target_parent = os.path.dirname(target)
        if not os.path.isdir(target_parent):
            _fail(f"{label} target parent directory does not exist: {target_parent}")
        if _is_inside(target, src):
            _fail(f"{label} target would be written inside the snapshot: {target}")
    _assert_service_stopped(db_target, assets_target, media_target)

    created: list[tuple[str, str, int]] = []
    try:
        database_ino, _database_bytes = _copy_verified(
            _artifact_file(src, manifest["database"]["path"]),
            db_target,
            expected_sha256=manifest["database"]["sha256"],
            expected_bytes=manifest["database"]["bytes"],
        )
        created.append((db_target, "file", database_ino))
        try:
            os.mkdir(assets_target, 0o777)
        except OSError as exc:
            _fail(f"cannot create {assets_target}: {exc.strerror or exc}")
        created.append((assets_target, "dir", os.lstat(assets_target).st_ino))
        for entry in manifest["assets"]:
            _copy_verified(
                _artifact_file(src, entry["path"]),
                os.path.join(assets_target, posixpath.basename(entry["path"])),
                expected_sha256=entry["sha256"],
                expected_bytes=entry["bytes"],
            )
        if manifest["manifest_version"] == 2 and manifest["media_objects"]:
            try:
                os.mkdir(media_target, 0o777)
            except OSError as exc:
                _fail(f"cannot create {media_target}: {exc.strerror or exc}")
            created.append((media_target, "dir", os.lstat(media_target).st_ino))
            for entry in manifest["media_objects"]:
                relative = entry["path"][len(MEDIA_DIR) + 1 :]
                target = os.path.join(media_target, *relative.split("/"))
                os.makedirs(os.path.dirname(target), mode=0o777, exist_ok=True)
                _copy_verified(
                    _artifact_file(src, entry["path"]),
                    target,
                    expected_sha256=entry["sha256"],
                    expected_bytes=entry["bytes"],
                )
        # Last look, at the targets themselves: the bytes really landed, the
        # restored database still passes integrity, and every reference in it
        # resolves to bytes in the restored directories that hash to that ID.
        _check_restored(db_target, assets_target, media_target, manifest)
    except BaseException:
        _rollback(created)
        raise

    _print_summary(
        "restore complete (targets, no cutover — repoint the service yourself):",
        db_target,
        manifest,
    )
    print(f"  assets: {assets_target}")
    if media_target is not None:
        print(f"  media:  {media_target}")
    return 0


def _check_restored(
    db_target: str,
    assets_target: str,
    media_target: str | None,
    manifest: dict[str, Any],
) -> None:
    """Prove the restored targets stand on their own before reporting."""
    _check_digest_file(db_target, manifest["database"], "restored database")
    references, revision = _read_snapshot(db_target)
    _check_manifest_closure(db_target, references, manifest)
    if revision != manifest["revision"]:
        _fail(
            f"restored database revision {revision!r} does not match the "
            f"manifest revision {manifest['revision']!r}"
        )
    expected_names = {
        posixpath.basename(entry["path"]) for entry in manifest["assets"]
    }
    try:
        actual_names = set(os.listdir(assets_target))
    except OSError as exc:
        _fail(f"cannot read the restored asset directory {assets_target}: {exc}")
    if actual_names != expected_names:
        _fail(
            f"restored asset directory holds {sorted(actual_names)}, expected "
            f"{sorted(expected_names)}"
        )
    for entry in manifest["assets"]:
        _check_digest_file(
            os.path.join(assets_target, posixpath.basename(entry["path"])),
            entry,
            f"restored asset {entry['id']}",
        )

    if manifest["manifest_version"] != 2 or not manifest["media_objects"]:
        return
    if media_target is None:
        _fail("a version 2 snapshot cannot be checked without a media target")
    expected_media = {
        entry["path"][len(MEDIA_DIR) + 1 :]: entry
        for entry in manifest["media_objects"]
    }
    seen: set[str] = set()
    for directory, dirnames, filenames in os.walk(media_target, followlinks=False):
        relative_directory = os.path.relpath(directory, media_target)
        if relative_directory == ".":
            relative_directory = ""
        relative_directory = relative_directory.replace(os.sep, "/")
        for name in dirnames:
            relative = f"{relative_directory}/{name}" if relative_directory else name
            info = os.lstat(os.path.join(directory, name))
            if stat.S_ISLNK(info.st_mode):
                _fail(f"restored media contains a symlinked directory: {relative}")
            allowed = relative == "objects" or (
                relative.startswith("objects/") and len(relative.split("/")) == 2
                and len(relative.split("/")[1]) == 2
            )
            if not allowed:
                _fail(f"restored media contains an unexpected directory: {relative}")
        for name in filenames:
            relative = f"{relative_directory}/{name}" if relative_directory else name
            info = os.lstat(os.path.join(directory, name))
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                _fail(f"restored media contains a non-regular file: {relative}")
            if relative not in expected_media:
                _fail(f"restored media contains an unexpected file: {relative}")
            seen.add(relative)
    if seen != set(expected_media):
        _fail(
            f"restored media is incomplete; missing: "
            f"{', '.join(sorted(set(expected_media) - seen))}"
        )
    for relative, entry in expected_media.items():
        _check_digest_file(
            os.path.join(media_target, *relative.split("/")),
            entry,
            f"restored media object {entry['object_id']}",
        )
    # Omitted ready assets must never look usable after a referenced backup.
    connection = _connect_ro(db_target)
    try:
        states = dict(
            connection.execute("SELECT asset_id, state FROM media_assets").fetchall()
        )
    finally:
        connection.close()
    for asset_id in manifest["omitted_media"]:
        if states.get(asset_id) != "unavailable":
            _fail(f"omitted media asset {asset_id} is not marked unavailable")


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """The whole interface: three subcommands, no force flag, help that tells
    the two truths this tool cannot enforce for you — the restore is two
    separate paths rather than an atomic cutover, and the service must be
    stopped first."""
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description=(
            "Back up, verify and restore the tablet-wall database together "
            "with only the curated assets its scenes reference."
        ),
        epilog=(
            "A snapshot is one versioned directory: manifest.json (relative "
            "paths, byte lengths, SHA-256 digests, revision, references), "
            "database/wall.db and assets/ holding only the referenced files. "
            "Restore writes two separate targets, a database file and an "
            "asset directory, one after the other: there is no single atomic "
            "cutover and none is claimed, so an interrupted restore is "
            "recovered by deleting the targets that run created and running "
            "it again. Nothing that exists is ever overwritten and there is "
            "no --force. Stop the wall service before restoring."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser(
        "backup",
        help="snapshot the live database and its referenced assets into a new directory",
        description=(
            "Copy the database with SQLite's online backup API — the source "
            "may be in service, and the tool waits for locks to clear rather "
            "than working to a deadline — then copy only the assets the "
            "snapshot's own scenes reference, write the manifest, verify the "
            "staging directory in full, and only then rename it to --dest. "
            "Any failure removes the staging directory, so no destination "
            "ever appears half-built."
        ),
    )
    backup_parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="source SQLite database file (must exist; may be in use)",
    )
    backup_parser.add_argument(
        "--assets",
        required=True,
        metavar="DIR",
        help="curated asset directory to copy referenced files from",
    )
    backup_parser.add_argument(
        "--media",
        default="./media",
        metavar="DIR",
        help="managed media directory (default ./media); absent is allowed "
             "only when the captured database references no managed media",
    )
    backup_parser.add_argument(
        "--dest",
        required=True,
        metavar="DIR",
        help="new directory for the snapshot (must not exist; parent must)",
    )
    backup_parser.set_defaults(handler=cmd_backup)

    verify_parser = commands.add_parser(
        "verify",
        help="check every byte, digest and reference of a snapshot directory",
        description=(
            "Re-derive the whole claim: manifest shape and safe relative "
            "paths, no symlinks or strays anywhere in the directory, byte "
            "lengths and SHA-256 digests for the database and each asset, "
            "SQLite integrity_check, the expected tables, and reference "
            "closure between database, manifest and files. An unverified "
            "snapshot is not a backup."
        ),
    )
    verify_parser.add_argument(
        "--src", required=True, metavar="DIR", help="snapshot directory to check"
    )
    verify_parser.set_defaults(handler=cmd_verify)

    restore_parser = commands.add_parser(
        "restore",
        help="restore a verified snapshot into brand-new paths (service stopped)",
        description=(
            "Verify the snapshot, then write two new targets: the database "
            "file at --db and the asset directory at --assets. Both must be "
            "absent — restore never overwrites, offers no force flag, and "
            "rolls back only targets this run created if something fails "
            "halfway. Stop the wall service first; the tool refuses targets "
            "TABLET_WALL_DB or TABLET_WALL_ASSET_DIR still name, but cannot "
            "otherwise see whether the process is running."
        ),
        epilog=(
            "There is no atomic cutover: the database file and the asset "
            "directory are two paths written one after the other, and the "
            "tool records no destination anywhere — after a successful "
            "restore you point TABLET_WALL_DB and TABLET_WALL_ASSET_DIR at "
            "the new paths and start the service yourself. If a restore is "
            "interrupted, delete the targets that run created and run it "
            "again; anything that existed before is untouched and remains "
            "your rollback."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    restore_parser.add_argument(
        "--src", required=True, metavar="DIR", help="verified snapshot directory"
    )
    restore_parser.add_argument(
        "--db",
        required=True,
        metavar="NEW_PATH",
        help="new database file to create (must not exist)",
    )
    restore_parser.add_argument(
        "--assets",
        required=True,
        metavar="NEW_DIR",
        help="new asset directory to create (must not exist)",
    )
    restore_parser.add_argument(
        "--media",
        metavar="NEW_DIR",
        help="new managed media directory to create (required for manifest 2)",
    )
    restore_parser.set_defaults(handler=cmd_restore)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse, run one command, and turn every expected failure into exit 1.

    Usage errors exit 2 (argparse's own convention), interruption exits 130,
    and every refusal or verification failure becomes one line on stderr —
    never a traceback, because a traceback in an operations tool invites
    scroll-past reading where a sentence cannot be ignored.
    """
    args = _build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except BackupError as exc:
        print(f"{_PROG}: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"{_PROG}: error: interrupted; no destination was created", file=sys.stderr)
        return 130
    except (OSError, sqlite3.Error) as exc:
        print(f"{_PROG}: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
