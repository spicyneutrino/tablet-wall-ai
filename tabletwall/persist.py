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

import json
import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

DEFAULT_DB_FILENAME = "tablet-wall.db"

# The whole persisted wall state lives in a single row (the CHECK pins id to
# 1). ``layout`` and ``scene`` are JSON documents, so the schema does not need
# to know about placements, bezels, or content types — there is deliberately
# no migration framework here.
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
# the wall row stores its layout and scene. ``IF NOT EXISTS`` *is* the
# migration — a database created before these tables existed gains them on its
# next connection, and nothing in the migration reads or rewrites the
# ``wall_state`` row, so an upgraded file keeps its state byte for byte.
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

# Applied in order, one statement per ``execute`` call — never
# ``executescript``, which implicitly commits any pending transaction before
# running and would violate the persist-before-apply boundary.
_MIGRATION = (_SCHEMA, _SAVED_LAYOUTS_SCHEMA, _SAVED_SCENES_SCHEMA)


def db_path() -> str:
    """Where the wall state lives: ``TABLET_WALL_DB``, else ``tablet-wall.db``."""
    return os.environ.get("TABLET_WALL_DB") or DEFAULT_DB_FILENAME


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """A connection with the schema applied; commits on success, always closes.

    The schema statements run first, so a brand-new file and an older file
    alike reach the body of the context with every table present (see
    ``_MIGRATION``). The commit happens inside the context, which is what
    makes "commit before notifying" hold: ``save_state`` and the snapshot
    saves return only after their transaction is durable. An exception skips
    the commit and closing the connection rolls the open transaction back, so
    a failed write never half-persists.
    """
    connection = sqlite3.connect(db_path())
    try:
        for statement in _MIGRATION:
            connection.execute(statement)
        yield connection
        connection.commit()
    finally:
        connection.close()


def load_state() -> dict[str, Any] | None:
    """The persisted wall state, or None when the database has no row yet.

    Called from the lifespan before the app accepts a socket. A row that
    cannot be read raises instead of being papered over with defaults: serving
    defaults would then silently overwrite real state on the next save.
    """
    with _connection() as connection:
        row = connection.execute(
            "SELECT layout, scene, revision, generation FROM wall_state WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "layout": json.loads(row[0]),
        "scene": json.loads(row[1]),
        "revision": int(row[2]),
        "generation": str(row[3]),
    }


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
                json.dumps(wall["layout"], sort_keys=True),
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
