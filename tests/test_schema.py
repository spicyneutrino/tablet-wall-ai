"""Schema gate: version 0 to 1, backup, refusal, and concurrent startup.

The database is the one durable record. These tests pin the boundary that
decides whether this build may write to it at all: a new file migrates, an old
file is backed up first, a future or malformed file is refused, and two
initializers cannot both migrate.
"""

import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

import main
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


def test_a_new_database_reaches_schema_3(tmp_path, monkeypatch):
    path = tmp_path / "new.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    assert persist.ensure_schema() == 3
    assert _version(path) == 3
    assert {"wall_state", "saved_layouts", "saved_scenes", "media_assets",
            "media_objects", "media_renditions", "schema_meta",
            "display_profiles", "calibrations", "media_video"} <= _tables(path)
    assert not list(tmp_path.glob("*.bak"))


def test_an_existing_schema_0_database_is_backed_up_before_ddl_and_keeps_its_documents(
    tmp_path, monkeypatch
):
    path = tmp_path / "old.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    assert persist.load_state() == WALL
    assert _version(path) == 3
    backups = list(tmp_path.glob("old.db.pre-schema-3.*.bak"))
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
    connection.execute("PRAGMA user_version = 4")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    monkeypatch.setenv("TABLET_WALL_DB", str(path))

    with pytest.raises(persist.SchemaError, match="newer"):
        persist.ensure_schema()
    assert _version(path) == 4
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
    assert _version(path) == 3
    assert {"saved_layouts", "saved_scenes", "media_assets", "display_profiles"} <= _tables(path)
    assert len(list(tmp_path.glob("pre-snapshot.db.pre-schema-3.*.bak"))) == 1


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
    backups = list(tmp_path.glob("old.db.pre-schema-3.*.bak"))
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
    assert results == [3, 3, 3, 3]
    assert len(list(tmp_path.glob("race.db.pre-schema-3.*.bak"))) == 1
    assert persist.load_state() == WALL


def test_a_direct_save_without_lifespan_migrates_first(tmp_path, monkeypatch):
    path = tmp_path / "direct.db"
    _legacy_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    changed = {**WALL, "revision": WALL["revision"] + 1}

    persist.save_state(changed)
    assert _version(path) == 3
    assert persist.load_state() == changed


def test_schema_2_missing_a_media_table_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "damaged.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    persist.ensure_schema()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE media_renditions")
    connection.commit()
    connection.close()

    with pytest.raises(persist.SchemaError, match="missing required tables"):
        persist.ensure_schema()


def _schema_1_database(path: Path, *, damaged_scene: str | None = None) -> None:
    connection = sqlite3.connect(path)
    try:
        for statement in persist._MIGRATION[:7]:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (json.dumps(WALL["layout"]), json.dumps(WALL["scene"]),
             WALL["revision"], WALL["generation"]),
        )
        if damaged_scene is not None:
            connection.execute(
                "INSERT INTO saved_scenes (name, content) VALUES ('broken', ?)",
                (damaged_scene,),
            )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()


def test_schema_1_to_3_is_additive_and_keeps_documents_byte_for_byte(
    tmp_path, monkeypatch
):
    path = tmp_path / "schema1.db"
    _schema_1_database(path, damaged_scene="{not valid json")
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    before_wall = sqlite3.connect(path).execute(
        "SELECT layout, scene FROM wall_state"
    ).fetchone()
    before_scene = sqlite3.connect(path).execute(
        "SELECT content FROM saved_scenes WHERE name = 'broken'"
    ).fetchone()[0]

    assert persist.ensure_schema() == 3
    assert _version(path) == 3
    assert {"display_profiles", "calibrations", "media_video"} <= _tables(path)
    assert len(list(tmp_path.glob("schema1.db.pre-schema-3.*.bak"))) == 1
    after_wall = sqlite3.connect(path).execute(
        "SELECT layout, scene FROM wall_state"
    ).fetchone()
    after_scene = sqlite3.connect(path).execute(
        "SELECT content FROM saved_scenes WHERE name = 'broken'"
    ).fetchone()[0]
    assert after_wall == before_wall
    assert after_scene == before_scene
    assert persist.load_scenes() == [("broken", None)]


def test_a_physical_layout_round_trips_and_is_stored_as_an_envelope(tmp_path, monkeypatch):
    path = tmp_path / "physical.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    physical = {
        "layout": {
            "kind": "physical",
            "bounds": {"x": 0, "y": 0, "width": 1200, "height": 800},
            "slots": {
                "0f8fad5b-d9cb-469f-a165-70867728950e": {
                    "center_x_mm": 300, "center_y_mm": 400, "mount_angle": 0,
                    "nudge_x_mm": 0, "nudge_y_mm": 0,
                    "profile_revision": 1, "calibration_revision": 1,
                    "participating": True,
                }
            },
        },
        "scene": {"content": {"type": "color"}, "layout": "active"},
        "revision": 3,
        "generation": "physical",
    }
    persist.save_state(physical)
    assert persist.load_state() == physical
    connection = sqlite3.connect(path)
    try:
        stored = json.loads(connection.execute("SELECT layout FROM wall_state").fetchone()[0])
    finally:
        connection.close()
    assert stored["schema"] == 2 and stored["kind"] == "physical"
    assert "width" not in stored


def test_schema_2_missing_calibrations_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "damaged2.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    persist.ensure_schema()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE calibrations")
    connection.commit()
    connection.close()
    with pytest.raises(persist.SchemaError, match="missing required tables"):
        persist.ensure_schema()


def _schema_2_database(path: Path) -> None:
    """A production-shaped schema 2 file: every table but ``media_video``."""
    connection = sqlite3.connect(path)
    try:
        for statement in persist._MIGRATION[:-1]:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (json.dumps(WALL["layout"]), json.dumps(WALL["scene"]),
             WALL["revision"], WALL["generation"]),
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    finally:
        connection.close()


def test_schema_2_to_3_is_backed_up_first_and_only_adds_the_video_table(
    tmp_path, monkeypatch
):
    path = tmp_path / "schema2.db"
    _schema_2_database(path)
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    before = _tables(path)
    assert "media_video" not in before

    assert persist.ensure_schema() == 3
    assert _version(path) == 3
    assert _tables(path) == before | {"media_video"}
    backups = list(tmp_path.glob("schema2.db.pre-schema-3.*.bak"))
    assert len(backups) == 1
    assert _version(backups[0]) == 2
    assert "media_video" not in _tables(backups[0])
    assert persist.load_state() == WALL


def test_schema_3_missing_media_video_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "damaged3.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(path))
    persist.ensure_schema()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE media_video")
    connection.commit()
    connection.close()
    with pytest.raises(persist.SchemaError, match="media_video"):
        persist.ensure_schema()


# ---------------------------------------------------------------------------
# startup validation and generation-only save (M7-01)
# ---------------------------------------------------------------------------

_DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"


def _seed_and_copy(tmp_path, monkeypatch, layout, scene, *, revision=7,
                   generation="old-generation"):
    """Write one schema-3 row, then run startup against a byte copy of it."""
    source = tmp_path / "source.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(source))
    persist.ensure_schema()
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (json.dumps(layout, sort_keys=True), json.dumps(scene, sort_keys=True),
             revision, generation),
        )
        connection.commit()
    finally:
        connection.close()
    candidate = tmp_path / "candidate.db"
    shutil.copy2(source, candidate)
    monkeypatch.setenv("TABLET_WALL_DB", str(candidate))
    return candidate


def _wall_row(path: Path) -> tuple[str, str, int, str]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT layout, scene, revision, generation FROM wall_state WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()


def _logical_layout() -> dict:
    return {"width": 2000, "height": 1000, "placements": {}}


def test_startup_refuses_a_malformed_logical_placement_before_any_write(
    tmp_path, monkeypatch
):
    layout = {
        "width": 2000,
        "height": 1000,
        "placements": {
            _DEVICE: {
                "device_id": _DEVICE, "x": 0, "y": 0, "w": 100, "h": 100,
                # The left bezel consumes the whole visible width.
                "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 100},
            }
        },
    }
    path = _seed_and_copy(
        tmp_path, monkeypatch, layout,
        {"content": {"type": "color"}, "layout": "active"},
    )
    before = _wall_row(path)

    with pytest.raises(persist.SchemaError, match="visible rectangle"):
        main._restore_wall_state()

    assert _wall_row(path) == before


@pytest.mark.parametrize("content", [
    {"type": "image", "asset": "sha256:" + "a" * 64},
    {"type": "image", "asset": "not-an-id", "intrinsicWidth": 10, "intrinsicHeight": 10},
    {"type": "image", "asset": "sha256:" + "a" * 64,
     "intrinsicWidth": 10, "intrinsicHeight": 10, "fit": "stretch"},
    {"type": "image", "asset": "sha256:" + "a" * 64,
     "intrinsicWidth": 10, "intrinsicHeight": 10, "background": "red"},
    {"type": "future"},
])
def test_startup_refuses_malformed_scene_content_before_any_write(
    tmp_path, monkeypatch, content
):
    path = _seed_and_copy(
        tmp_path, monkeypatch, _logical_layout(),
        {"content": content, "layout": "active"},
    )
    before = _wall_row(path)

    with pytest.raises(persist.SchemaError):
        main._restore_wall_state()

    assert _wall_row(path) == before


def test_startup_preserves_legacy_documents_and_updates_only_the_generation(
    tmp_path, monkeypatch
):
    layout = {
        **_logical_layout(),
        "legacyNote": {"kept": ["byte", "for", "byte"]},
    }
    scene = {
        "content": {
            "type": "image", "asset": "sha256:" + "a" * 64,
            "intrinsicWidth": 16, "intrinsicHeight": 9,
            # A legitimate legacy image may omit both fit and background.
        },
        "layout": "active",
        "legacyNote": "keep me",
    }
    path = _seed_and_copy(tmp_path, monkeypatch, layout, scene)
    before_layout, before_scene, before_revision, before_generation = _wall_row(path)

    main._restore_wall_state()

    after_layout, after_scene, after_revision, after_generation = _wall_row(path)
    assert (after_layout, after_scene, after_revision) == (
        before_layout, before_scene, before_revision)
    assert after_generation != before_generation
    restored = persist.load_state()
    assert restored["layout"]["legacyNote"] == layout["legacyNote"]
    assert restored["scene"]["content"] == scene["content"]


def test_startup_accepts_a_schema_2_envelope_and_preserves_its_stored_bytes(
    tmp_path, monkeypatch
):
    stored_layout = {
        "schema": 2, "kind": "logical",
        "data": {**_logical_layout(), "legacyNote": "inside the envelope"},
    }
    stored_scene = {
        "kind": "static",
        "content": {"type": "color"},
        "layout": "active",
        "legacyNote": "outside the runtime shape",
    }
    path = _seed_and_copy(tmp_path, monkeypatch, stored_layout, stored_scene)
    before_layout, before_scene, before_revision, _ = _wall_row(path)

    main._restore_wall_state()

    after_layout, after_scene, after_revision, _ = _wall_row(path)
    assert (after_layout, after_scene, after_revision) == (
        before_layout, before_scene, before_revision)
    assert persist.load_state()["scene"] == {
        "content": {"type": "color"}, "layout": "active"}
    assert persist.load_state()["layout"]["legacyNote"] == "inside the envelope"
