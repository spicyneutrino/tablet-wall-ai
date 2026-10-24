"""Schema gate: version 0 to 1, backup, refusal, and concurrent startup.

The database is the one durable record. These tests pin the boundary that
decides whether this build may write to it at all: a new file migrates, an old
file is backed up first, a future or malformed file is refused, and two
initializers cannot both migrate.
"""

import json
import sqlite3
import threading
from pathlib import Path

import pytest

import tabletwall.persist as persist

WALL = {
    "layout": {"width": 2000, "height": 1000, "placements": {}},
    "scene": {"content": {"type": "color"}, "layout": "active"},
    "revision": 7,
    "generation": "abcd1234",
}


def _legacy_database(path: Path, *, all_tables: bool = True) -> None:
    """Create the pre-media schema, with one complete wall row."""
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE wall_state (id INTEGER PRIMARY KEY CHECK (id = 1), "
            "layout TEXT NOT NULL, scene TEXT NOT NULL, "
            "revision INTEGER NOT NULL, generation TEXT NOT NULL)"
        )
        if all_tables:
            connection.execute(
                "CREATE TABLE saved_layouts (name TEXT PRIMARY KEY, layout TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE saved_scenes (name TEXT PRIMARY KEY, content TEXT NOT NULL)"
            )
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (
                json.dumps(WALL["layout"]),
                json.dumps(WALL["scene"]),
                WALL["revision"],
                WALL["generation"],
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _version(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()


def test_a_new_database_reaches_schema_1(tmp_path, monkeypatch):
    path = tmp_path / "new.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    assert persist.ensure_schema() == 1
    assert _version(path) == 1
    assert {"wall_state", "saved_layouts", "saved_scenes", "media_assets",
            "media_objects", "media_renditions", "schema_meta"} <= _tables(path)
    assert not list(tmp_path.glob("*.bak"))


def test_an_existing_schema_0_database_is_backed_up_before_ddl_and_keeps_its_documents(
    tmp_path, monkeypatch
):
    path = tmp_path / "old.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    assert persist.load_state() == WALL
    assert _version(path) == 1
    backups = list(tmp_path.glob("old.db.pre-schema-1.*.bak"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600
    # The backup is a real schema-0 copy, not an empty placeholder.
    assert _version(backups[0]) == 0
    connection = sqlite3.connect(backups[0])
    try:
        copy = connection.execute(
            "SELECT layout, revision FROM wall_state WHERE id = 1"
        ).fetchone()
        assert json.loads(copy[0]) == WALL["layout"]
        assert copy[1] == WALL["revision"]
    finally:
        connection.close()


def test_a_future_schema_is_refused_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "future.db"
    _legacy_database(path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 2")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    with pytest.raises(persist.SchemaError, match="newer"):
        persist.ensure_schema()
    assert _version(path) == 2
    assert path.read_bytes() == before


def test_an_existing_database_missing_required_tables_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "partial.db"
    _legacy_database(path, all_tables=False)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE wall_state")
    connection.execute("CREATE TABLE unrelated (value TEXT)")
    connection.commit()
    connection.close()
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    with pytest.raises(persist.SchemaError, match="not this application"):
        persist.ensure_schema()
    assert _version(path) == 0
    assert "media_assets" not in _tables(path)
    assert not list(tmp_path.glob("*.bak"))


def test_a_pre_snapshot_database_gains_the_snapshot_and_media_tables(
    tmp_path, monkeypatch
):
    path = tmp_path / "pre-snapshot.db"
    _legacy_database(path, all_tables=False)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    assert persist.load_state() == WALL
    assert _version(path) == 1
    assert {"saved_layouts", "saved_scenes", "media_assets"} <= _tables(path)
    assert len(list(tmp_path.glob("pre-snapshot.db.pre-schema-1.*.bak"))) == 1


def test_a_corrupt_wall_row_refuses_load(tmp_path, monkeypatch):
    path = tmp_path / "corrupt.db"
    _legacy_database(path)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE wall_state SET layout = '{not json' WHERE id = 1")
    connection.commit()
    connection.close()
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    with pytest.raises(persist.SchemaError, match="not valid"):
        persist.load_state()


def test_a_failed_backup_does_not_migrate(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    def fail(_connection):
        raise persist.SchemaError("injected backup failure")

    monkeypatch.setattr(persist, "_write_migration_backup", fail)
    with pytest.raises(persist.SchemaError, match="injected"):
        persist.ensure_schema()
    assert _version(path) == 0
    assert "media_assets" not in _tables(path)


def test_a_failed_ddl_rolls_back_the_version_and_the_tables(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    monkeypatch.setattr(
        persist, "_MIGRATION", persist._MIGRATION + ("CREATE TABLE broken (",)
    )

    with pytest.raises(sqlite3.OperationalError):
        persist.ensure_schema()
    assert _version(path) == 0
    assert "media_assets" not in _tables(path)
    # The rollback copy still exists and still opens as schema 0.
    backups = list(tmp_path.glob("old.db.pre-schema-1.*.bak"))
    assert len(backups) == 1
    assert _version(backups[0]) == 0


def test_two_concurrent_initializers_migrate_once(tmp_path, monkeypatch):
    path = tmp_path / "race.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    results: list[int] = []
    errors: list[BaseException] = []

    def initialize() -> None:
        try:
            results.append(persist.ensure_schema())
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    threads = [threading.Thread(target=initialize) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == [1, 1, 1, 1]
    assert len(list(tmp_path.glob("race.db.pre-schema-1.*.bak"))) == 1
    assert persist.load_state() == WALL


def test_a_direct_save_without_lifespan_migrates_first(tmp_path, monkeypatch):
    path = tmp_path / "direct.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    changed = {**WALL, "revision": WALL["revision"] + 1}

    persist.save_state(changed)
    assert _version(path) == 1
    assert persist.load_state() == changed


def test_schema_1_missing_a_media_table_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "damaged.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    persist.ensure_schema()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE media_renditions")
    connection.commit()
    connection.close()

    with pytest.raises(persist.SchemaError, match="missing required tables"):
        persist.ensure_schema()
