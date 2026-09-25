"""SQLite persistence for the wall state (PROTOCOL.md "Persistence").

One table, one row: the active layout, the active scene, the revision, and
the generation. Sockets, presence, heartbeat timestamps, and the device roster
stay in memory. Standard library ``sqlite3`` only — no new dependencies.

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

# The whole persisted state lives in a single row (the CHECK pins id to 1).
# ``layout`` and ``scene`` are JSON documents, so the schema does not need to
# know about placements, bezels, or content types — there is deliberately no
# migration framework here.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS wall_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    layout     TEXT NOT NULL,
    scene      TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    generation TEXT NOT NULL
)
"""


def db_path() -> str:
    """Where the wall state lives: ``TABLET_WALL_DB``, else ``tablet-wall.db``."""
    return os.environ.get("TABLET_WALL_DB") or DEFAULT_DB_FILENAME


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """A connection with the schema applied; commits on success, always closes.

    The commit happens inside the context, which is what makes "commit before
    notifying" hold: ``save_state`` returns only after the transaction is
    durable. An exception skips the commit and closing the connection rolls
    the open transaction back, so a failed write never half-persists.
    """
    connection = sqlite3.connect(db_path())
    try:
        connection.execute(_SCHEMA)
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

    Every mutating route calls this after the in-memory mutation and *before*
    its broadcast, so a controller is never told about state that would not
    survive a restart (PROTOCOL.md "Persistence").
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
