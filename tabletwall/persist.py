"""SQLite persistence for the wall state (PROTOCOL.md "Persistence").

One table, one row: the active layout, the active scene, the revision, and
the generation. Two further tables hold the *saved* layouts and scenes behind
named save/recall: they are keyed by name and written by their own CRUD calls,
which never touch the wall row — saving or deleting a snapshot therefore
cannot bump the revision or move the active wall. Sockets, presence, heartbeat
timestamps, and the device roster stay in memory. Standard library ``sqlite3``
only — no new dependencies.

The database file comes from ``TABLET_WALL_DB`` (read at call time, so tests
can point it at a temporary file) and defaults to ``tablet-wall.db`` in the
working directory, which ``*.db`` already keeps out of git.
"""

import fcntl
import json
import os
import secrets
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_FILENAME = "tablet-wall.db"

# The database schema version, kept separately from the web protocol major and
# from the wall document shape. Version 0 is the pre-media database that older
# builds wrote implicitly; version 1 adds the managed-media index and pins the
# version in ``PRAGMA user_version``. Anything newer is refused before a write,
# because an older binary cannot know what it would be rewriting.
SCHEMA_VERSION = 2

# The whole persisted wall state lives in a single row (the CHECK pins id to
# 1). ``layout`` and ``scene`` are JSON documents, so the schema does not need
# to know about placements, bezels, or content types.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS wall_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    layout     TEXT NOT NULL,
    scene      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    generation TEXT NOT NULL
)
"""

# Named save/recall: one row per saved name, the payload as JSON exactly as
# the wall row stores its layout and scene.
_SAVED_LAYOUTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_layouts (
    name   TEXT PRIMARY KEY,
    layout TEXT NOT NULL
)
"""

_SAVED_SCENES_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_scenes (
    name    TEXT PRIMARY KEY,
    content TEXT NOT NULL
)
"""

# Schema 2: immutable physical measurements and calibrations. Both are keyed
# by device and revision; an update appends a revision rather than mutating
# the one a saved layout already references.
_DISPLAY_PROFILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS display_profiles (
    device_id        TEXT NOT NULL,
    revision         INTEGER NOT NULL,
    active_width_mm  REAL NOT NULL,
    active_height_mm REAL NOT NULL,
    bezel_left_mm    REAL NOT NULL,
    bezel_top_mm     REAL NOT NULL,
    bezel_right_mm   REAL NOT NULL,
    bezel_bottom_mm  REAL NOT NULL,
    panel_pixels_width  INTEGER,
    panel_pixels_height INTEGER,
    label            TEXT NOT NULL,
    provenance       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (device_id, revision)
)
"""

_CALIBRATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS calibrations (
    device_id           TEXT NOT NULL,
    revision            INTEGER NOT NULL,
    profile_revision    INTEGER NOT NULL,
    viewport_width      REAL NOT NULL,
    viewport_height     REAL NOT NULL,
    dpr                 REAL NOT NULL,
    orientation         INTEGER NOT NULL,
    mode                TEXT NOT NULL,
    quarter_turn        INTEGER NOT NULL,
    panel_offset_x_mm   REAL NOT NULL,
    panel_offset_y_mm   REAL NOT NULL,
    mm_per_css_x        REAL NOT NULL,
    mm_per_css_y        REAL NOT NULL,
    anchor_edge         TEXT NOT NULL,
    uncertainty_mm      REAL NOT NULL,
    method              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    PRIMARY KEY (device_id, revision)
)
"""

# Schema 1: the managed media index. Object bytes live on disk under the media
# directory; these rows are the authority for what may be served and listed.
# ``media_assets`` is the upload identity, ``media_objects`` the exact-byte
# content, and ``media_renditions`` the roles an asset publishes. Roles are
# scoped to one asset, so two assets may share an object without sharing a
# row.
_MEDIA_ASSETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_assets (
    asset_id         TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    state            TEXT NOT NULL CHECK (state IN ('ready', 'failed', 'unavailable')),
    pipeline_version INTEGER NOT NULL,
    width            INTEGER NOT NULL,
    height           INTEGER NOT NULL,
    display_object   TEXT NOT NULL REFERENCES media_objects(object_id),
    master_object    TEXT NOT NULL REFERENCES media_objects(object_id),
    error            TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
)
"""

_MEDIA_OBJECTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_objects (
    object_id  TEXT PRIMARY KEY,
    mime       TEXT NOT NULL,
    bytes      INTEGER NOT NULL,
    width      INTEGER NOT NULL,
    height     INTEGER NOT NULL,
    path       TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_MEDIA_RENDITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_renditions (
    asset_id  TEXT NOT NULL REFERENCES media_assets(asset_id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES media_objects(object_id),
    role      TEXT NOT NULL,
    width     INTEGER NOT NULL,
    height    INTEGER NOT NULL,
    PRIMARY KEY (asset_id, role)
)
"""

_SCHEMA_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

# Applied in order, one statement per ``execute`` call. ``IF NOT EXISTS`` makes
# a re-run harmless, but it is not the migration mechanism: the version gate in
# ``ensure_schema`` decides whether DDL may run at all.
_MIGRATION = (
    _SCHEMA,
    _SAVED_LAYOUTS_SCHEMA,
    _SAVED_SCENES_SCHEMA,
    _MEDIA_OBJECTS_SCHEMA,
    _MEDIA_ASSETS_SCHEMA,
    _MEDIA_RENDITIONS_SCHEMA,
    _SCHEMA_META_SCHEMA,
    _DISPLAY_PROFILES_SCHEMA,
    _CALIBRATIONS_SCHEMA,
)

# A schema-0 file is this application's database when it carries ``wall_state``.
# The saved-snapshot tables arrived later and a pre-snapshot file legitimately
# lacks them, so they are added by the migration rather than demanded first.
_REQUIRED_TABLES = frozenset({"wall_state"})
_SCHEMA_1_TABLES = frozenset({
    "wall_state", "saved_layouts", "saved_scenes",
    "media_assets", "media_objects", "media_renditions", "schema_meta",
})
_SCHEMA_2_TABLES = _SCHEMA_1_TABLES | {"display_profiles", "calibrations"}


class SchemaError(RuntimeError):
    """The database cannot be opened safely; startup must refuse it.

    Raised for a future schema, a file that is not this application's
    database, a missing required table, a failed pre-migration backup, or a
    wall row that cannot be validated. The message is operator-facing.
    """


def _user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(path: str) -> None:
    fd = os.open(path or ".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_migration_backup(connection: sqlite3.Connection) -> str:
    """Copy the schema-0 database beside itself, durably, before any DDL.

    SQLite's online backup API is used rather than a raw copy, so a writer in
    another process cannot leave a torn page in the backup. The copy is
    integrity-checked and fsynced before its path is returned; any failure
    raises and the caller must not migrate. The name is unique per attempt so
    a retry cannot overwrite the only usable rollback copy.
    """
    source = db_path()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target_path = (
        f"{source}.pre-schema-{SCHEMA_VERSION}.{stamp}."
        f"{os.getpid()}.{secrets.token_hex(4)}.bak"
    )
    target = sqlite3.connect(target_path)
    try:
        connection.backup(target)
        target.commit()
        check = target.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise SchemaError(
                f"pre-migration backup failed integrity_check: {check!r}"
            )
    except SchemaError:
        raise
    except Exception as error:
        raise SchemaError(
            f"pre-migration backup failed ({type(error).__name__}: {error}); "
            "the database was not migrated"
        ) from error
    finally:
        target.close()
    os.chmod(target_path, 0o600)
    _fsync_path(target_path)
    _fsync_directory(os.path.dirname(os.path.abspath(target_path)))
    return target_path


@contextmanager
def _migration_lock() -> Iterator[None]:
    """Serialize schema-0 migration across processes with one stable inode.

    The lock file is a sibling of the database, not the database itself: a
    SQLite connection holding a write transaction cannot also run its own
    backup API. The lock is released by the OS if the process dies, so an
    interrupted migration cannot wedge the next start.
    """
    path = os.path.abspath(db_path()) + ".schema.lock"
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _require_tables(connection: sqlite3.Connection, version: int) -> None:
    required = {1: _SCHEMA_1_TABLES, 2: _SCHEMA_2_TABLES}[version]
    missing = required - _tables(connection)
    if missing:
        raise SchemaError(
            f"database schema {version} is missing required tables: "
            f"{', '.join(sorted(missing))}"
        )


def ensure_schema() -> int:
    """Bring the database to ``SCHEMA_VERSION``, or refuse it.

    Called by every persistence entry point, not only the lifespan, so a test
    or a direct caller cannot bypass the gate. A new empty file is migrated
    without a backup. An existing older file is backed up before any DDL; a
    file that is neither new nor this application's database is refused. The
    DDL and the version bump commit together, so an interrupted attempt
    reopens at the previous version and can be retried with a fresh backup.

    Schema 1 to 2 is additive: it creates the display/calibration tables and
    bumps the version. It deliberately does not rewrite the active or saved
    documents. Legacy logical documents are adapted at read time, which keeps
    damaged saved rows byte-for-byte visible and deletable as they were.
    """
    path = db_path()
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        try:
            version = _user_version(connection)
        except sqlite3.DatabaseError as error:
            raise SchemaError(f"{path} is not a usable SQLite database: {error}") from error
        if version > SCHEMA_VERSION:
            raise SchemaError(
                f"database schema {version} is newer than this build supports "
                f"({SCHEMA_VERSION}); refusing to modify {path}"
            )
        if version == SCHEMA_VERSION:
            _require_tables(connection, version)
            connection.execute("PRAGMA foreign_keys = ON")
            return version
        if version not in (0, 1):
            raise SchemaError(f"unsupported database schema {version} in {path}")

        with _migration_lock():
            # Another process may have migrated while this one waited.
            connection.close()
            connection = sqlite3.connect(path)
            version = _user_version(connection)
            if version > SCHEMA_VERSION:
                raise SchemaError(
                    f"database schema {version} is newer than this build supports "
                    f"({SCHEMA_VERSION}); refusing to modify {path}"
                )
            if version == SCHEMA_VERSION:
                _require_tables(connection, version)
                return version
            if version == 1:
                _require_tables(connection, 1)
            else:
                existing = _tables(connection)
                size = os.path.getsize(path) if os.path.exists(path) else 0
                if existing:
                    missing = _REQUIRED_TABLES - existing
                    if missing:
                        raise SchemaError(
                            f"{path} exists but is not this application's database: "
                            f"missing {', '.join(sorted(missing))}"
                        )
                elif size > 0:
                    raise SchemaError(
                        f"{path} is an existing non-empty file with no tables; "
                        "refusing to overwrite it"
                    )

            if _tables(connection):
                # A durable rollback copy before the first DDL. A failed
                # backup aborts the migration.
                _write_migration_backup(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in _MIGRATION:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            connection.execute("PRAGMA foreign_keys = ON")
            return SCHEMA_VERSION
    finally:
        connection.close()


def schema_version() -> int:
    """The current version, read through the same gate as every other call."""
    return ensure_schema()



def db_path() -> str:
    """Where the wall state lives: ``TABLET_WALL_DB``, else ``tablet-wall.db``."""
    return os.environ.get("TABLET_WALL_DB") or DEFAULT_DB_FILENAME


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """A connection to a migrated database; commits on success, always closes.

    ``ensure_schema`` runs first so a brand-new file, an old file and a file
    that another process just migrated all reach the body with every table
    present. It refuses a future schema or a damaged database before this
    connection can read or write it. A failed write skips the commit and the
    connection closes with its open transaction rolled back, so a failed
    mutation never half-persists.
    """
    ensure_schema()
    connection = sqlite3.connect(db_path())
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    finally:
        connection.close()


def _runtime_layout(document: Any) -> Any:
    """Adapt a stored layout envelope to the runtime shape.

    Legacy logical documents are returned unchanged; a physical envelope is
    exposed with its bounds and slots; a logical envelope is unwrapped. This
    is the read-time migration the advisor required: no saved row is
    rewritten, and a damaged row keeps its bytes and its existing listing
    behaviour.
    """
    if not isinstance(document, dict):
        return document
    if document.get("kind") == "physical":
        bounds = document.get("bounds")
        slots = document.get("slots")
        if not isinstance(bounds, dict) or not isinstance(slots, dict):
            return document
        return {
            "kind": "physical",
            "bounds": {
                "x": bounds.get("x", 0), "y": bounds.get("y", 0),
                "width": bounds.get("width"), "height": bounds.get("height"),
            },
            "slots": slots,
        }
    if document.get("schema") == 2 and document.get("kind") == "logical":
        data = document.get("data")
        return data if isinstance(data, dict) else document
    return document


def _runtime_scene(document: Any) -> Any:
    """Unwrap a schema-2 static scene envelope; legacy scenes pass through."""
    if (
        isinstance(document, dict)
        and document.get("kind") == "static"
        and isinstance(document.get("content"), dict)
    ):
        return {"content": document["content"], "layout": document.get("layout", "active")}
    return document


def _validate_wall_state(wall: Any, where: str) -> dict[str, Any]:
    """The persisted wall row must be a complete, usable document.

    Returning defaults for a damaged row would make the next save overwrite
    the operator's only copy. Every required piece is therefore checked here,
    before the lifespan can adopt it or rewrite the generation.
    """
    if not isinstance(wall, dict):
        raise SchemaError(f"{where} is not a mapping")
    layout = wall.get("layout")
    scene = wall.get("scene")
    if not isinstance(layout, dict) or not isinstance(scene, dict):
        raise SchemaError(f"{where} is missing its layout or scene document")
    if layout.get("kind") == "physical":
        bounds = layout.get("bounds")
        if (
            not isinstance(bounds, dict)
            or not isinstance(bounds.get("x"), (int, float))
            or not isinstance(bounds.get("y"), (int, float))
            or not isinstance(bounds.get("width"), (int, float))
            or not isinstance(bounds.get("height"), (int, float))
            or bounds["width"] <= 0
            or bounds["height"] <= 0
            or not isinstance(layout.get("slots"), dict)
        ):
            raise SchemaError(f"{where} has an invalid physical layout document")
        for device_id, slot in layout["slots"].items():
            if not isinstance(device_id, str) or not isinstance(slot, dict):
                raise SchemaError(f"{where} has an invalid physical slot")
            if not all(
                isinstance(slot.get(field), (int, float))
                and not isinstance(slot.get(field), bool)
                for field in ("center_x_mm", "center_y_mm", "mount_angle",
                              "nudge_x_mm", "nudge_y_mm")
            ):
                raise SchemaError(f"{where} has a slot without a pose")
            if not isinstance(slot.get("profile_revision"), int) or not isinstance(
                slot.get("calibration_revision"), int
            ):
                raise SchemaError(f"{where} has a slot without a revision")
            if not isinstance(slot.get("participating", True), bool):
                raise SchemaError(f"{where} has an invalid participating flag")
    elif (
        not isinstance(layout.get("width"), int)
        or isinstance(layout["width"], bool)
        or layout["width"] <= 0
        or not isinstance(layout.get("height"), int)
        or isinstance(layout["height"], bool)
        or layout["height"] <= 0
        or not isinstance(layout.get("placements"), dict)
    ):
        raise SchemaError(f"{where} has an invalid layout document")
    if (
        not isinstance(scene.get("content"), dict)
        or not isinstance(scene.get("layout"), str)
    ):
        raise SchemaError(f"{where} has an invalid scene document")
    revision = wall.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise SchemaError(f"{where} has an invalid revision")
    if not isinstance(wall.get("generation"), str) or not wall["generation"]:
        raise SchemaError(f"{where} has an invalid generation")
    return wall


def load_state() -> dict[str, Any] | None:
    """The persisted wall state, or None when the database has no row yet.

    Called from the lifespan before the app accepts a socket. A row that
    cannot be read or does not validate raises instead of being papered over
    with defaults: serving defaults would then silently overwrite real state
    on the next save.
    """
    with _connection() as connection:
        row = connection.execute(
            "SELECT layout, scene, revision, generation FROM wall_state WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    try:
        layout = json.loads(row[0])
        scene = json.loads(row[1])
        revision = int(row[2])
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SchemaError(f"wall_state row is not valid: {error}") from error
    return _validate_wall_state(
        {
            "layout": _runtime_layout(layout),
            "scene": _runtime_scene(scene),
            "revision": revision,
            "generation": str(row[3]),
        },
        "wall_state",
    )


def save_state(wall: Mapping[str, Any]) -> None:
    """Persist the wall state in one committed transaction.

    Mutating routes call this on a *proposed* state (see ``main._commit_wall``)
    and apply it to the live wall only after this returns, so the commit always
    precedes both the in-memory mutation and the broadcast: a controller is
    never told about state that would not survive a restart, and a failed save
    leaves memory untouched (PROTOCOL.md "Persistence").
    """
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO wall_state (id, layout, scene, revision, generation)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                layout = excluded.layout,
                scene = excluded.scene,
                revision = excluded.revision,
                generation = excluded.generation
            """,
            (
                json.dumps(
                    {
                        "schema": 2,
                        "kind": "physical",
                        "bounds": wall["layout"]["bounds"],
                        "slots": wall["layout"]["slots"],
                    }
                    if wall["layout"].get("kind") == "physical"
                    else wall["layout"],
                    sort_keys=True,
                ),
                json.dumps(wall["scene"], sort_keys=True),
                int(wall["revision"]),
                str(wall["generation"]),
            ),
        )


# ---------------------------------------------------------------------------
# named save/recall: saved layouts and scenes
# ---------------------------------------------------------------------------

# The (table, column) pair behind each snapshot kind. The four helpers below
# interpolate these into their statements, so they are module constants and
# never caller input — a name is always a bound parameter.
_SNAPSHOT_TABLES: dict[str, tuple[str, str]] = {
    "layout": ("saved_layouts", "layout"),
    "scene": ("saved_scenes", "content"),
}


def _load_all(kind: str) -> list[tuple[str, Any]]:
    """Every saved snapshot of ``kind`` as ``(name, payload)``, name-sorted.

    The order comes from the primary key's binary collation, so the listing
    is stable across reads and restarts. A damaged JSON row remains visible
    as ``None`` instead of preventing every other snapshot from being listed;
    the API marks that entry invalid so it can still be deleted or replaced.
    """
    table, column = _SNAPSHOT_TABLES[kind]
    with _connection() as connection:
        rows = connection.execute(
            f"SELECT name, {column} FROM {table} ORDER BY name"
        ).fetchall()
    result = []
    for name, document in rows:
        try:
            payload = json.loads(document)
        except json.JSONDecodeError:
            payload = None
        result.append((str(name), payload))
    return result


def _load_one(kind: str, name: str) -> dict[str, Any] | None:
    """The payload stored under ``name``, or None when it was never saved."""
    table, column = _SNAPSHOT_TABLES[kind]
    with _connection() as connection:
        row = connection.execute(
            f"SELECT {column} FROM {table} WHERE name = ?", (name,)
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(row[0])
    if payload is None:
        raise ValueError("saved snapshot payload is null")
    return payload


def _save_one(
    kind: str, name: str, payload: Mapping[str, Any], *, replace: bool
) -> bool:
    """Store one snapshot, overwriting an existing name only when allowed.

    Returns False when the name is taken and ``replace`` is false — the route
    turns that into a 409 instead of overwriting silently. The conflict is
    decided by the insert itself (``ON CONFLICT … DO NOTHING``: a ``rowcount``
    of 0 means the row already exists), so the check and the write are one
    atomic statement rather than a read that could be outrun; an allowed
    overwrite is then an explicit ``UPDATE``. Check, write, and overwrite all
    run in the single transaction ``_connection`` commits before returning,
    and none of them touches ``wall_state``.
    """
    table, column = _SNAPSHOT_TABLES[kind]
    document = json.dumps(payload, sort_keys=True)
    with _connection() as connection:
        inserted = connection.execute(
            f"INSERT INTO {table} (name, {column}) VALUES (?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, document),
        ).rowcount
        if inserted:
            return True
        if not replace:
            return False
        updated = connection.execute(
            f"UPDATE {table} SET {column} = ? WHERE name = ?", (document, name)
        ).rowcount
    return updated == 1


def _delete_one(kind: str, name: str) -> bool:
    """Drop one snapshot; False when no row carried that name (the caller 404s)."""
    table, _ = _SNAPSHOT_TABLES[kind]
    with _connection() as connection:
        removed = connection.execute(
            f"DELETE FROM {table} WHERE name = ?", (name,)
        ).rowcount
    return bool(removed)


def load_layouts() -> list[tuple[str, Any]]:
    """Every saved layout as ``(name, layout)``, name-sorted."""
    return _load_all("layout")


def load_layout(name: str) -> dict[str, Any] | None:
    """The saved layout ``name``, or None when it was never saved."""
    return _load_one("layout", name)


def save_layout(
    name: str, layout: Mapping[str, Any], *, replace: bool = False
) -> bool:
    """Save a layout snapshot; False when the name exists and ``replace`` is off."""
    return _save_one("layout", name, layout, replace=replace)


def delete_layout(name: str) -> bool:
    """Delete the layout snapshot ``name``; False when there was nothing to delete."""
    return _delete_one("layout", name)


def load_scenes() -> list[tuple[str, Any]]:
    """Every saved scene as ``(name, content)``, name-sorted."""
    return _load_all("scene")


def load_scene(name: str) -> dict[str, Any] | None:
    """The saved scene content ``name``, or None when it was never saved."""
    return _load_one("scene", name)


def save_scene(
    name: str, content: Mapping[str, Any], *, replace: bool = False
) -> bool:
    """Save a scene snapshot; False when the name exists and ``replace`` is off."""
    return _save_one("scene", name, content, replace=replace)


def delete_scene(name: str) -> bool:
    """Delete the scene snapshot ``name``; False when there was nothing to delete."""
    return _delete_one("scene", name)
