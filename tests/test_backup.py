"""Phase 3b verified backup tooling (``deploy/backup.py``).

The contract under test, in the order the tool itself orders it:

* ``backup`` snapshots the live database with SQLite's **online backup
  API** (never a raw file copy), reads image references **from the snapshot**,
  copies only the referenced curated files, writes a versioned manifest with
  relative paths/lengths/digests and no machine paths, verifies the staging
  directory in full, and only then publishes it with one rename — so a failed
  or interrupted run never leaves a completed artifact at the destination.
* ``verify`` re-derives every claim: manifest safety, no symlinks or strays,
  digests, SQLite integrity, expected tables, reference closure.
* ``restore`` accepts only brand-new targets (no ``--force``), refuses while
  the environment still names them for the service, rolls back only what that
  run created, and never claims an atomic cutover — the help says so.

Every test builds its own database and asset directory under ``tmp_path``;
the shared ``isolated_registry`` fixture in ``conftest.py`` keeps
``TABLET_WALL_DB``/``TABLET_WALL_ASSET_DIR`` pointed at per-test paths too, so
nothing here can reach a real ``tablet-wall.db`` or a curated ``./assets``.
"""

import ast
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from deploy import backup

ROOT = Path(__file__).resolve().parents[1]

TABLES = ("wall_state", "saved_layouts", "saved_scenes")
SCHEMA = {
    "wall_state": """
        CREATE TABLE IF NOT EXISTS wall_state (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            layout     TEXT NOT NULL,
            scene      TEXT NOT NULL,
            revision   INTEGER NOT NULL,
            generation TEXT NOT NULL
        )
    """,
    "saved_layouts": (
        "CREATE TABLE IF NOT EXISTS saved_layouts "
        "(name TEXT PRIMARY KEY, layout TEXT NOT NULL)"
    ),
    "saved_scenes": (
        "CREATE TABLE IF NOT EXISTS saved_scenes "
        "(name TEXT PRIMARY KEY, content TEXT NOT NULL)"
    ),
}


# ---------------------------------------------------------------------------
# helpers: real image bytes, live-shaped databases, snapshots, CLI runs
# ---------------------------------------------------------------------------


def image_bytes(
    fmt: str = "PNG", color: str = "red", size: tuple[int, int] = (64, 48)
) -> bytes:
    """A freshly encoded still image — real bytes, not a stub."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    return buffer.getvalue()


def content_id(data: bytes) -> str:
    """The content ID for these bytes, computed the way the server does."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def image_content(asset_id: str, *, width: int = 64, height: int = 48) -> dict:
    """Persisted image content exactly as ``PUT /scene`` stores it: the ID,
    the fit, and the derived intrinsic dimensions — never a URL."""
    return {
        "type": "image",
        "asset": asset_id,
        "fit": "cover",
        "intrinsicWidth": width,
        "intrinsicHeight": height,
    }


def image_scene(asset_id: str, **dimensions) -> dict:
    """The persisted shape of an image scene (no projected URL, ever)."""
    return {"content": image_content(asset_id, **dimensions), "layout": "active"}


def write_database(
    path: Path,
    *,
    scene: dict | str | None = None,
    saved: dict[str, dict | str] | None = None,
    revision: int = 7,
    generation: str = "source-generation",
    tables: tuple[str, ...] = TABLES,
) -> None:
    """Create a database exactly shaped like the application's, or a subset
    of its schema when a test needs a file missing expected tables.

    A ``str`` value for ``scene``/a saved snapshot is written verbatim, which
    is how the tests plant unreadable JSON the app itself could never write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for table in tables:
            connection.execute(SCHEMA[table])
        if scene is None:
            scene = {"content": {"type": "color", "color": "#101018"}, "layout": "active"}
        if "wall_state" in tables:
            connection.execute("DELETE FROM wall_state")
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (
                json.dumps({"width": 2400, "height": 1350, "placements": {}}),
                scene if isinstance(scene, str) else json.dumps(scene, sort_keys=True),
                revision,
                generation,
            ),
        )
        for name, content in (saved or {}).items():
            connection.execute(
                "INSERT OR REPLACE INTO saved_scenes VALUES (?, ?)",
                (
                    name,
                    content
                    if isinstance(content, str)
                    else json.dumps(content, sort_keys=True),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def make_source(
    tmp_path: Path,
    *,
    active: dict,
    saved: dict | None = None,
    assets_files: dict[str, bytes] | None = None,
    revision: int = 7,
    generation: str = "source-generation",
    tables: tuple[str, ...] = TABLES,
) -> tuple[Path, Path]:
    """A live-shaped ``{tmp_path}/live`` holding the database and asset dir."""
    live = tmp_path / "live"
    assets = live / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name, data in (assets_files or {}).items():
        (assets / name).write_bytes(data)
    database = live / "wall.db"
    write_database(
        database,
        scene=active,
        saved=saved,
        revision=revision,
        generation=generation,
        tables=tables,
    )
    return database, assets


def run(*argv: object) -> int:
    """Invoke the CLI the way an operator does; returns its exit code."""
    return backup.main([str(argument) for argument in argv])


def make_snapshot(tmp_path: Path, database: Path, assets: Path) -> Path:
    """A verified snapshot under ``{tmp_path}/backups/snap``."""
    parent = tmp_path / "backups"
    parent.mkdir(exist_ok=True)
    destination = parent / "snap"
    assert run(
        "backup",
        "--db",
        database,
        "--assets",
        assets,
        "--dest",
        destination,
    ) == 0
    return destination


def open_readonly(path: Path) -> sqlite3.Connection:
    """A read-only connection to an existing file — ``mode=ro`` never creates."""
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def manifest_of(snapshot: Path) -> dict:
    return json.loads((snapshot / "manifest.json").read_text())


def rewrite_manifest(snapshot: Path, mutate) -> None:
    """Load, mutate and rewrite a manifest — the tamper tool for these tests."""
    manifest = manifest_of(snapshot)
    mutate(manifest)
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2))


def staging_leftovers(destination: Path) -> list[Path]:
    return [
        entry
        for entry in destination.parent.iterdir()
        if entry.name.startswith(f".{destination.name}.incomplete-")
    ]


@pytest.fixture
def referenced(tmp_path):
    """Three images and a source database referencing two of them.

    Returns ``(active_id, saved_id, orphan_id, database, assets)``: the active
    scene points at the JPEG, the saved scene at one PNG, and a third image
    sits unreferenced in the asset directory to prove it is never claimed.
    """
    active_data = image_bytes("JPEG", color="blue")
    saved_data = image_bytes("PNG", color="red")
    orphan_data = image_bytes("PNG", color="green")
    active_id, saved_id, orphan_id = (
        content_id(active_data),
        content_id(saved_data),
        content_id(orphan_data),
    )
    database, assets = make_source(
        tmp_path,
        active=image_scene(active_id),
        saved={"poster": image_content(saved_id)},
        assets_files={
            "sky.jpg": active_data,
            "poster.png": saved_data,
            "orphan.png": orphan_data,
        },
    )
    return active_id, saved_id, orphan_id, database, assets


# ---------------------------------------------------------------------------
# backup: the happy path
# ---------------------------------------------------------------------------


class TestBackupProducesACompleteVerifiedSnapshot:
    def test_the_snapshot_holds_the_database_and_only_referenced_assets(
        self, tmp_path, referenced
    ):
        active_id, saved_id, orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)

        assert (snapshot / "manifest.json").is_file()
        assert (snapshot / "database" / "wall.db").is_file()
        manifest = manifest_of(snapshot)
        assert set(manifest["references"]) == {active_id, saved_id}
        assert orphan_id not in manifest["references"], "unreferenced: not claimed"

        stored = sorted(entry["path"] for entry in manifest["assets"])
        assert stored == sorted(
            [
                f"assets/{active_id.split(':')[1]}.jpg",
                f"assets/{saved_id.split(':')[1]}.png",
            ]
        )
        actual_files = sorted(
            path.relative_to(snapshot).as_posix()
            for path in snapshot.rglob("*")
            if path.is_file()
        )
        assert actual_files == sorted(stored + ["database/wall.db", "manifest.json"])
        artifact_bytes = b"".join(
            path.read_bytes() for path in snapshot.rglob("*") if path.is_file()
        )
        assert orphan_id.split(":")[1].encode() not in artifact_bytes, (
            "an unreferenced file's bytes must be nowhere in the artifact"
        )

    def test_the_manifest_records_relative_paths_lengths_and_digests(
        self, tmp_path, referenced
    ):
        active_id, saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        text = (snapshot / "manifest.json").read_text()
        manifest = json.loads(text)

        assert str(tmp_path) not in text, "no machine paths in the manifest"
        assert manifest["manifest_version"] == backup.MANIFEST_VERSION
        assert manifest["revision"] == 7
        assert isinstance(manifest["created_utc"], str)

        database_entry = manifest["database"]
        assert database_entry["path"] == "database/wall.db"
        database_bytes = (snapshot / database_entry["path"]).read_bytes()
        assert database_entry["bytes"] == len(database_bytes)
        assert database_entry["sha256"] == hashlib.sha256(database_bytes).hexdigest()

        assert len(manifest["assets"]) == 2
        for entry in manifest["assets"]:
            assert entry["path"].startswith("assets/")
            assert entry["path"].split("/")[1] == entry["id"].split(":")[1] + os.path.splitext(
                entry["path"]
            )[1]
            payload = (snapshot / entry["path"]).read_bytes()
            assert entry["bytes"] == len(payload)
            assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
            assert entry["sha256"] == entry["id"].split(":")[1]

    def test_the_snapshot_database_is_a_readable_consistent_copy(
        self, tmp_path, referenced
    ):
        _active_id, saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)

        copy = snapshot / "database" / "wall.db"
        connection = open_readonly(copy)
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert tables == set(TABLES)
            scene, revision, generation = connection.execute(
                "SELECT scene, revision, generation FROM wall_state WHERE id = 1"
            ).fetchone()
            assert json.loads(scene)["content"]["asset"] != saved_id
            assert revision == 7
            assert generation == "source-generation"
            saved = dict(connection.execute("SELECT name, content FROM saved_scenes"))
        finally:
            connection.close()
        assert json.loads(saved["poster"])["asset"] == saved_id

    def test_verify_accepts_the_snapshot_just_taken(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)

        assert run("verify", "--src", snapshot) == 0
        output = capsys.readouterr().out
        assert f"verified: {snapshot}" in output

    def test_a_wall_without_image_references_needs_no_asset_directory(
        self, tmp_path, capsys
    ):
        """A colour wall backs up even though ``--assets`` never existed."""
        database, _assets = make_source(
            tmp_path,
            active={"content": {"type": "color", "color": "#000000"}, "layout": "active"},
            assets_files={},
        )
        missing = tmp_path / "never-created"
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", missing, "--dest", destination
        ) == 0
        manifest = manifest_of(destination)
        assert manifest["references"] == []
        assert manifest["assets"] == []
        assert not (destination / "assets").exists() or not any(
            (destination / "assets").iterdir()
        )

    def test_the_sources_are_left_byte_for_byte_untouched(
        self, tmp_path, referenced
    ):
        """No raw copy, no journal, no migration: the live pair never changes."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced

        def fingerprint() -> dict[str, str]:
            state = {}
            for path in sorted(database.parent.iterdir()):
                if path.is_file():
                    state[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                else:
                    for child in sorted(path.iterdir()):
                        state[f"{path.name}/{child.name}"] = hashlib.sha256(
                            child.read_bytes()
                        ).hexdigest()
            return state

        before = fingerprint()
        assert make_snapshot(tmp_path, database, assets).exists()
        after = fingerprint()
        assert before == after, "backup must not write to its sources"


# ---------------------------------------------------------------------------
# backup: refusals, all decided before any write
# ---------------------------------------------------------------------------


class TestBackupRefusesWithoutWritingAnything:
    def test_an_existing_destination_is_refused_and_left_alone(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()
        destination.mkdir()
        sentinel = destination / "previous-backup.txt"
        sentinel.write_text("kept")

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "already exists" in capsys.readouterr().err
        assert sentinel.read_text() == "kept"
        assert staging_leftovers(destination) == []

    def test_a_missing_source_database_is_refused(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, _database, assets = referenced
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup",
            "--db",
            tmp_path / "nope.db",
            "--assets",
            assets,
            "--dest",
            destination,
        ) == 1
        assert "does not exist" in capsys.readouterr().err
        assert not destination.exists()
        assert staging_leftovers(destination) == []

    def test_a_source_database_without_the_expected_tables_is_refused(
        self, tmp_path, capsys
    ):
        """A file missing ``saved_scenes`` is not this application's database."""
        database, assets = make_source(
            tmp_path,
            active=image_scene(content_id(image_bytes())),
            tables=("wall_state",),
        )
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "missing expected table" in capsys.readouterr().err
        assert not destination.exists()

    def test_a_file_that_is_not_a_database_is_refused(self, tmp_path, capsys):
        database = tmp_path / "live" / "wall.db"
        database.parent.mkdir()
        database.write_bytes(b"this is not a SQLite file at all")
        assets = tmp_path / "live" / "assets"
        assets.mkdir()
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "error:" in capsys.readouterr().err
        assert not destination.exists()

    def test_an_asset_path_that_is_a_file_is_refused(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, _assets = referenced
        decoy = tmp_path / "not-a-directory"
        decoy.write_text("plain file")
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", decoy, "--dest", destination
        ) == 1
        assert "not a directory" in capsys.readouterr().err
        assert not destination.exists()

    def test_a_destination_whose_parent_is_missing_is_refused(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        destination = tmp_path / "no-such-parent" / "snap"

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "parent directory does not exist" in capsys.readouterr().err
        assert not destination.parent.exists()


# ---------------------------------------------------------------------------
# backup: references come from the snapshot
# ---------------------------------------------------------------------------


class TestReferencesAreReadFromTheSnapshot:
    def test_active_and_saved_scene_references_are_both_covered(
        self, tmp_path, referenced
    ):
        active_id, saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        manifest = manifest_of(snapshot)

        copy = snapshot / "database" / "wall.db"
        connection = open_readonly(copy)
        try:
            scene = json.loads(
                connection.execute(
                    "SELECT scene FROM wall_state WHERE id = 1"
                ).fetchone()[0]
            )
            saved = {
                name: json.loads(content)
                for name, content in connection.execute(
                    "SELECT name, content FROM saved_scenes"
                )
            }
        finally:
            connection.close()

        assert scene["content"]["asset"] == active_id
        assert saved["poster"]["asset"] == saved_id
        assert set(manifest["references"]) == {active_id, saved_id}, (
            "both the active scene and saved_scenes.content drive the copies"
        )

    @pytest.mark.parametrize("where", ["active", "saved"])
    def test_unreadable_json_where_references_live_fails_the_backup(
        self, tmp_path, capsys, where
    ):
        """Fail closed: unreadable documents have unknown references."""
        if where == "active":
            database, assets = make_source(tmp_path, active="not json at all")
        else:
            database, assets = make_source(
                tmp_path,
                active=image_scene(content_id(image_bytes())),
                saved={"broken": "{not json"},
            )
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "not readable JSON" in capsys.readouterr().err
        assert not destination.exists()

    def test_a_malformed_asset_reference_fails_the_backup(self, tmp_path, capsys):
        """An ``asset`` that is not a content ID cannot be copied or verified."""
        database, assets = make_source(
            tmp_path,
            active=image_scene(content_id(image_bytes())),
            saved={"dubious": {"type": "image", "asset": "sha256:not-a-hash"}},
        )
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "invalid asset reference" in capsys.readouterr().err
        assert not destination.exists()


# ---------------------------------------------------------------------------
# backup: every referenced file must be present, readable and matching
# ---------------------------------------------------------------------------


class TestReferencedAssetsMustBePresentAndMatch:
    @pytest.mark.parametrize(
        "layout", ["the-file-is-gone", "the-directory-is-emptied", "the-directory-is-absent"]
    )
    def test_a_missing_referenced_asset_fails_without_a_completed_artifact(
        self, tmp_path, referenced, capsys, layout
    ):
        active_id, saved_id, _orphan_id, database, assets = referenced
        if layout == "the-file-is-gone":
            (assets / "sky.jpg").unlink()
        elif layout == "the-directory-is-emptied":
            for path in assets.iterdir():
                path.unlink()
        else:
            shutil.rmtree(assets)
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        error = capsys.readouterr().err
        assert "missing" in error
        assert active_id in error or saved_id in error, (
            "the failure names a reference that could not be resolved"
        )
        assert not destination.exists(), "a failed backup never completes"
        assert staging_leftovers(destination) == [], "staging is removed on failure"

    def test_bytes_that_do_not_match_the_reference_fail_the_backup(
        self, tmp_path, referenced, capsys
    ):
        active_id, _saved_id, _orphan_id, database, assets = referenced
        for path in assets.iterdir():
            path.unlink()
        # Right name, wrong bytes: nothing in the directory carries the ID.
        (assets / "sky.jpg").write_bytes(image_bytes("JPEG", color="yellow"))
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "missing or unreadable" in capsys.readouterr().err
        assert not destination.exists()

    def test_bytes_behind_a_symlink_are_never_copied(self, tmp_path, referenced, capsys):
        """Only the file itself is an asset — a link out never satisfies a ref."""
        active_id, _saved_id, _orphan_id, database, assets = referenced
        for path in assets.iterdir():
            path.unlink()
        outside = tmp_path / "outside.png"
        outside.write_bytes(image_bytes("PNG", color="blue"))
        (assets / "sky.jpg").symlink_to(outside)
        (assets / "decoy.png").write_bytes(image_bytes("PNG", color="yellow"))
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "missing or unreadable" in capsys.readouterr().err
        assert not destination.exists()
        assert outside.exists(), "the link target is never touched"

    def test_referenced_bytes_must_be_a_curated_jpeg_or_png(
        self, tmp_path, capsys
    ):
        """Correct hash in a non-image file: the inventory could not serve it,
        so the reference is broken and the backup must say so."""
        data = image_bytes("JPEG", color="blue")
        asset_id = content_id(data)
        database, assets = make_source(tmp_path, active=image_scene(asset_id))
        (assets / "data.bin").write_bytes(data)
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        assert "not a curated JPEG/PNG" in capsys.readouterr().err
        assert not destination.exists()


# ---------------------------------------------------------------------------
# backup: the online API and concurrent writers
# ---------------------------------------------------------------------------


class TestTheSnapshotUsesSqliteOnlineBackup:
    def test_the_snapshot_is_taken_with_the_online_backup_api(
        self, tmp_path, referenced, monkeypatch
    ):
        """The memo's first rule: never a raw file copy of a live database.

        ``sqlite3.Connection`` is an immutable C type in Python 3.13, so the
        spy wraps the read-only source connection instead: every byte still
        travels through ``Connection.backup``, and this records that it did.
        """
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        calls: list[tuple] = []
        original_connect_ro = backup._connect_ro

        class SpyConnection:
            def __init__(self, real):
                self._real = real

            def backup(self, *args, **kwargs):
                calls.append(args)
                return self._real.backup(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._real, name)

        monkeypatch.setattr(
            backup,
            "_connect_ro",
            lambda path: SpyConnection(original_connect_ro(path)),
        )
        assert make_snapshot(tmp_path, database, assets).exists()
        assert calls, "Connection.backup must be how the snapshot is taken"

    def test_a_concurrent_writer_yields_one_consistent_committed_snapshot(
        self, tmp_path, referenced
    ):
        """A writer committing throughout: the snapshot is one committed state.

        The invariant is cross-row — the active scene and a saved scene are
        updated in the *same* transaction, alternating between two images —
        so a torn copy could only pass by luck. SQLite has no hard deadline
        here either: the backup waits the writer out rather than failing.
        """
        active_id, saved_id, _orphan_id, database, assets = referenced
        # The invariant: this saved scene and the active scene are rewritten
        # together in one transaction, alternating between the two images.

        stop = threading.Event()
        progress = [0]

        def writer() -> None:
            connection = sqlite3.connect(str(database), timeout=10)
            try:
                while not stop.is_set():
                    target = active_id if progress[0] % 2 == 0 else saved_id
                    connection.execute("BEGIN")
                    connection.execute(
                        "UPDATE wall_state SET scene = ?, revision = revision + 1 "
                        "WHERE id = 1",
                        (json.dumps(image_scene(target)),),
                    )
                    connection.execute(
                        "UPDATE saved_scenes SET content = ? WHERE name = 'poster'",
                        (json.dumps(image_content(target)),),
                    )
                    connection.commit()
                    progress[0] += 1
                    time.sleep(0.005)
            finally:
                connection.close()

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while progress[0] < 5 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert progress[0] >= 5, "the writer must really be running"

            snapshot = make_snapshot(tmp_path, database, assets)
        finally:
            stop.set()
            thread.join(timeout=15)
        assert not thread.is_alive()
        assert progress[0] >= 5
        assert run("verify", "--src", snapshot) == 0

        connection = open_readonly(snapshot / "database" / "wall.db")
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            active = json.loads(
                connection.execute(
                    "SELECT scene FROM wall_state WHERE id = 1"
                ).fetchone()[0]
            )["content"]["asset"]
            paired = json.loads(
                connection.execute(
                    "SELECT content FROM saved_scenes WHERE name = 'poster'"
                ).fetchone()[0]
            )["asset"]
            revision = connection.execute(
                "SELECT revision FROM wall_state WHERE id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        assert active == paired, "one transaction, one state — never torn"
        assert active in {active_id, saved_id}
        assert isinstance(revision, int) and revision >= 7


# ---------------------------------------------------------------------------
# verify: corruption of each kind is refused
# ---------------------------------------------------------------------------


class TestVerifyRejectsCorruption:
    def test_a_missing_manifest_is_not_a_complete_artifact(
        self, tmp_path, referenced, capsys
    ):
        """An interrupted run never writes its manifest — never complete."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        (snapshot / "manifest.json").unlink()

        assert run("verify", "--src", snapshot) == 1
        assert "manifest.json is missing" in capsys.readouterr().err

    def test_unparsable_manifest_json_fails_verify(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        (snapshot / "manifest.json").write_text("{ this is not json")

        assert run("verify", "--src", snapshot) == 1
        assert "not valid JSON" in capsys.readouterr().err

    def test_an_unsupported_manifest_version_fails_verify(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        rewrite_manifest(snapshot, lambda manifest: manifest.update(manifest_version=99))

        assert run("verify", "--src", snapshot) == 1
        assert "unsupported manifest version" in capsys.readouterr().err

    def test_a_corrupted_asset_file_fails_verify(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        manifest = manifest_of(snapshot)
        victim = snapshot / manifest["assets"][0]["path"]
        payload = bytearray(victim.read_bytes())
        payload[10] ^= 0xFF
        victim.write_bytes(bytes(payload))

        assert run("verify", "--src", snapshot) == 1
        assert "does not match the manifest digest" in capsys.readouterr().err

    def test_a_corrupted_database_file_fails_verify(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        victim = snapshot / "database" / "wall.db"
        payload = bytearray(victim.read_bytes())
        payload[len(payload) // 2] ^= 0xFF
        victim.write_bytes(bytes(payload))

        assert run("verify", "--src", snapshot) == 1
        assert "does not match the manifest digest" in capsys.readouterr().err

    def test_a_database_failing_sqlite_integrity_fails_verify(
        self, tmp_path, referenced, capsys
    ):
        """A digest that *matches* a broken database still fails: page-level
        integrity is checked, not just agreement with the manifest."""
        active_id, _saved_id, _orphan_id, database, assets = referenced
        # Enough rows that page 2 holds real btree content to damage.
        extra = {
            f"scene-{index}": {"type": "color", "color": f"#{index:06x}"}
            for index in range(60)
        }
        write_database(
            database,
            scene=image_scene(active_id),
            saved=extra,
        )
        snapshot = make_snapshot(tmp_path, database, assets)
        victim = snapshot / "database" / "wall.db"
        payload = bytearray(victim.read_bytes())
        assert len(payload) > 8192
        payload[4100:4400] = bytes(300)  # past the page-1 header: pages, not magic
        victim.write_bytes(bytes(payload))

        def reseal(manifest: dict) -> None:
            damaged = victim.read_bytes()
            manifest["database"]["bytes"] = len(damaged)
            manifest["database"]["sha256"] = hashlib.sha256(damaged).hexdigest()

        rewrite_manifest(snapshot, reseal)

        assert run("verify", "--src", snapshot) == 1
        assert "integrity check failed" in capsys.readouterr().err

    def test_manifest_references_must_agree_with_the_database(
        self, tmp_path, referenced, capsys
    ):
        """True closure: digests all match, but the database names a reference
        the manifest does not claim — the snapshot must not verify."""
        active_id, saved_id, orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        copy = snapshot / "database" / "wall.db"
        connection = sqlite3.connect(copy)
        try:
            connection.execute(
                "INSERT INTO saved_scenes VALUES (?, ?)",
                ("surprise", json.dumps(image_content(orphan_id))),
            )
            connection.commit()
        finally:
            connection.close()

        def reseal(manifest: dict) -> None:
            updated = copy.read_bytes()
            manifest["database"]["bytes"] = len(updated)
            manifest["database"]["sha256"] = hashlib.sha256(updated).hexdigest()

        rewrite_manifest(snapshot, reseal)

        assert run("verify", "--src", snapshot) == 1
        assert "reference closure failed" in capsys.readouterr().err
        # The manifest itself is still internally consistent: the disagreement
        # is between it and the database, which is the point of the test.
        manifest = manifest_of(snapshot)
        assert set(manifest["references"]) == {active_id, saved_id}

    def test_manifest_revision_must_agree_with_the_database(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        rewrite_manifest(snapshot, lambda manifest: manifest.update(revision=999))

        assert run("verify", "--src", snapshot) == 1
        assert "does not match the database revision" in capsys.readouterr().err

    def test_an_unlisted_file_in_the_artifact_fails_verify(
        self, tmp_path, referenced, capsys
    ):
        """Unreferenced files are not claimed — in the artifact either."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        (snapshot / "assets" / "smuggled.png").write_bytes(image_bytes("PNG"))

        assert run("verify", "--src", snapshot) == 1
        assert "unexpected file" in capsys.readouterr().err

    def test_a_missing_asset_file_fails_verify(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        manifest = manifest_of(snapshot)
        (snapshot / manifest["assets"][0]["path"]).unlink()

        assert run("verify", "--src", snapshot) == 1
        assert "incomplete; missing" in capsys.readouterr().err

    def test_an_interrupted_backup_staging_directory_is_refused(
        self, tmp_path, referenced, monkeypatch, capsys
    ):
        """Simulated SIGKILL: cleanup never runs, so a staging directory with
        partial content survives — and is never the destination, and never
        verifies as complete."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        monkeypatch.setattr(backup, "_remove_staging", lambda path, ino: None)

        def interrupted(source, target, **kwargs):
            raise backup.BackupError("simulated interruption")

        monkeypatch.setattr(backup, "_copy_verified", interrupted)
        assert run(
            "backup", "--db", database, "--assets", assets, "--dest", destination
        ) == 1
        capsys.readouterr()

        assert not destination.exists(), "an interrupted run never completes"
        leftovers = staging_leftovers(destination)
        assert len(leftovers) == 1
        assert run("verify", "--src", leftovers[0]) == 1
        assert "manifest.json is missing" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# verify: hostile paths and links are refused before anything is read
# ---------------------------------------------------------------------------


class TestMaliciousArtifactsAreRefused:
    @pytest.mark.parametrize(
        ("field", "hostile"),
        [
            ("database", "../../etc/passwd"),
            ("database", "/etc/passwd"),
            ("database", "database/../../wall.db"),
            ("asset", "../outside.png"),
            ("asset", "/etc/passwd"),
        ],
    )
    def test_hostile_manifest_paths_are_refused(
        self, tmp_path, referenced, capsys, field, hostile
    ):
        active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)

        def poison(manifest: dict) -> None:
            if field == "database":
                manifest["database"]["path"] = hostile
            else:
                manifest["assets"][0]["path"] = hostile

        rewrite_manifest(snapshot, poison)

        assert run("verify", "--src", snapshot) == 1
        assert "not a safe relative path" in capsys.readouterr().err

    def test_a_symlinked_asset_file_fails_verify(self, tmp_path, referenced, capsys):
        """Same bytes, link instead of file: refused as structure, not content."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        manifest = manifest_of(snapshot)
        victim = snapshot / manifest["assets"][0]["path"]
        outside = tmp_path / "outside.png"
        outside.write_bytes(victim.read_bytes())
        victim.unlink()
        victim.symlink_to(outside)

        assert run("verify", "--src", snapshot) == 1
        assert "symlink" in capsys.readouterr().err

    def test_a_symlinked_database_file_fails_verify(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        victim = snapshot / "database" / "wall.db"
        outside = tmp_path / "elsewhere.db"
        outside.write_bytes(victim.read_bytes())
        victim.unlink()
        victim.symlink_to(outside)

        assert run("verify", "--src", snapshot) == 1
        assert "symlink" in capsys.readouterr().err

    def test_a_symlinked_directory_fails_verify(self, tmp_path, referenced, capsys):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        victim = snapshot / "assets"
        elsewhere = tmp_path / "elsewhere-assets"
        elsewhere.mkdir()
        for path in victim.iterdir():
            path.rename(elsewhere / path.name)
        victim.rmdir()
        victim.symlink_to(elsewhere, target_is_directory=True)

        assert run("verify", "--src", snapshot) == 1
        assert "symlinked directory" in capsys.readouterr().err

    def test_a_manifest_with_a_traversal_path_is_refused_by_restore(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        rewrite_manifest(
            snapshot, lambda manifest: manifest["database"].update(path="../../../etc/passwd")
        )
        new_db = tmp_path / "restored" / "wall.db"
        new_assets = tmp_path / "restored" / "assets"
        new_db.parent.mkdir()

        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "not a safe relative path" in capsys.readouterr().err
        assert not new_db.exists() and not new_assets.exists()

    def test_an_unverifiable_snapshot_creates_no_restore_targets(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        manifest = manifest_of(snapshot)
        victim = snapshot / manifest["assets"][0]["path"]
        payload = bytearray(victim.read_bytes())
        payload[10] ^= 0xFF
        victim.write_bytes(bytes(payload))
        new_db = tmp_path / "restored" / "wall.db"
        new_assets = tmp_path / "restored" / "assets"
        new_db.parent.mkdir()

        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "does not match the manifest digest" in capsys.readouterr().err
        assert not new_db.exists() and not new_assets.exists()


# ---------------------------------------------------------------------------
# restore: new targets only, verified first, rolled back on failure
# ---------------------------------------------------------------------------


class TestRestore:
    def test_restore_reproduces_the_wall_and_its_images_on_a_restart(
        self, tmp_path, referenced, monkeypatch
    ):
        """The whole contract end to end: backup, verify, restore, restart.

        The restored pair is then handed to the real application: a fresh
        process mints a new generation (so clients resynchronise), keeps the
        revision, still knows both scenes, and serves each image only when
        its bytes hash to the very ID the scene references.
        """
        active_id, saved_id, orphan_id, database, assets = referenced
        active_bytes = (assets / "sky.jpg").read_bytes()
        saved_bytes = (assets / "poster.png").read_bytes()
        snapshot = make_snapshot(tmp_path, database, assets)
        assert run("verify", "--src", snapshot) == 0

        restored_root = tmp_path / "restored"
        restored_root.mkdir()
        new_db = restored_root / "wall.db"
        new_assets = restored_root / "assets"
        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 0

        # Restored bytes match the reference IDs, by name and by hash.
        manifest = manifest_of(snapshot)
        stored = {path.name for path in new_assets.iterdir()}
        assert stored == {os.path.basename(entry["path"]) for entry in manifest["assets"]}
        expected = {active_id: (active_bytes, ".jpg"), saved_id: (saved_bytes, ".png")}
        assert orphan_id.split(":")[1] not in "".join(stored), "not copied"
        for asset_id, (payload, extension) in expected.items():
            restored = (new_assets / (asset_id.split(":")[1] + extension)).read_bytes()
            assert restored == payload, "byte-identical to the source"
            assert content_id(restored) == asset_id, "hashing to the referenced ID"

        monkeypatch.setenv("TABLET_WALL_DB", str(new_db))
        monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(new_assets))
        with TestClient(main.app) as client:
            wall = client.get("/wall").json()
            assert wall["generation"] != "source-generation", (
                "a restart on the restored database starts a new generation"
            )
            assert wall["revision"] == 7, "the revision itself is preserved"
            assert wall["scene"]["content"]["asset"] == active_id
            assert wall["scene"]["content"]["url"] == f"/assets/{active_id}"

            scenes = client.get("/scenes").json()["scenes"]
            assert [entry["name"] for entry in scenes] == ["poster"]
            assert scenes[0]["content"]["asset"] == saved_id

            for asset_id, payload in (
                (active_id, active_bytes),
                (saved_id, saved_bytes),
            ):
                served = client.get(f"/assets/{asset_id}")
                assert served.status_code == 200
                assert served.content == payload, (
                    "serving re-hashes: these bytes really are that ID"
                )

    def test_restore_refuses_an_existing_database_target(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        restored = tmp_path / "restored"
        restored.mkdir()
        new_db = restored / "wall.db"
        new_db.write_text("the operator's current database")
        new_assets = restored / "assets"

        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "database target already exists" in capsys.readouterr().err
        assert new_db.read_text() == "the operator's current database"
        assert not new_assets.exists(), "no sibling target is created either"

    def test_restore_refuses_an_existing_assets_target_before_creating_the_other(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        restored = tmp_path / "restored"
        restored.mkdir()
        new_db = restored / "wall.db"
        new_assets = restored / "assets"
        new_assets.mkdir()
        (new_assets / "keepme.png").write_bytes(b"kept")

        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "asset directory target already exists" in capsys.readouterr().err
        assert not new_db.exists(), "every target check runs before any write"
        assert (new_assets / "keepme.png").read_bytes() == b"kept"

    @pytest.mark.parametrize("variable", ["TABLET_WALL_DB", "TABLET_WALL_ASSET_DIR"])
    def test_restore_refuses_targets_the_environment_still_names(
        self, tmp_path, referenced, monkeypatch, capsys, variable
    ):
        """The best-effort "stop the service first" guard."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        restored = tmp_path / "restored"
        restored.mkdir()
        new_db = restored / "wall.db"
        new_assets = restored / "assets"
        monkeypatch.setenv(
            variable, str(new_db if variable == "TABLET_WALL_DB" else new_assets)
        )

        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        error = capsys.readouterr().err
        assert variable in error and "stop the wall service" in error
        assert not new_db.exists() and not new_assets.exists()

    def test_restore_refuses_a_target_inside_the_snapshot(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)

        assert run(
            "restore",
            "--src",
            snapshot,
            "--db",
            snapshot / "wall.db",
            "--assets",
            snapshot.parent / "assets",
        ) == 1
        assert "inside the snapshot" in capsys.readouterr().err
        assert not (snapshot / "wall.db").exists()

    def test_restore_refuses_a_missing_snapshot(self, tmp_path, capsys):
        restored = tmp_path / "restored"
        restored.mkdir()

        assert run(
            "restore",
            "--src",
            tmp_path / "no-such-backup",
            "--db",
            restored / "wall.db",
            "--assets",
            restored / "assets",
        ) == 1
        assert "artifact directory does not exist" in capsys.readouterr().err
        assert not (restored / "wall.db").exists()
        assert not (restored / "assets").exists()

    def test_restore_refuses_two_targets_that_are_the_same_path(
        self, tmp_path, referenced, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        same = tmp_path / "restored"
        same.mkdir()

        assert run(
            "restore", "--src", snapshot, "--db", same, "--assets", same
        ) == 1
        assert "two different paths" in capsys.readouterr().err
        assert list(same.iterdir()) == []

    def test_a_failure_at_the_final_check_rolls_back_only_new_targets(
        self, tmp_path, referenced, monkeypatch, capsys
    ):
        """Rollback reaches this run's creations and nothing else: a
        neighbour that existed before is left exactly as it was."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        restored = tmp_path / "restored"
        restored.mkdir()
        neighbour = restored / "pre-existing.txt"
        neighbour.write_text("untouched")
        new_db = restored / "wall.db"
        new_assets = restored / "assets"

        def explode(db_target, assets_target, manifest):
            raise backup.BackupError("simulated failure after both targets exist")

        monkeypatch.setattr(backup, "_check_restored", explode)
        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "simulated failure" in capsys.readouterr().err
        assert not new_db.exists(), "the database this run created is rolled back"
        assert not new_assets.exists(), "so is the asset directory"
        assert neighbour.read_text() == "untouched"

    def test_a_failure_while_copying_an_asset_rolls_back_the_new_targets(
        self, tmp_path, referenced, monkeypatch, capsys
    ):
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        snapshot = make_snapshot(tmp_path, database, assets)
        restored = tmp_path / "restored"
        restored.mkdir()
        neighbour = restored / "pre-existing.txt"
        neighbour.write_text("untouched")
        new_db = restored / "wall.db"
        new_assets = restored / "assets"
        original = backup._copy_verified

        def fail_for_assets(source, target, **kwargs):
            if os.path.dirname(target) == str(new_assets):
                raise backup.BackupError("simulated failure mid-restore")
            return original(source, target, **kwargs)

        monkeypatch.setattr(backup, "_copy_verified", fail_for_assets)
        assert run(
            "restore", "--src", snapshot, "--db", new_db, "--assets", new_assets
        ) == 1
        assert "simulated failure" in capsys.readouterr().err
        assert not new_db.exists(), "the database created earlier in the run goes too"
        assert not new_assets.exists()
        assert neighbour.read_text() == "untouched"


# ---------------------------------------------------------------------------
# the command-line contract itself
# ---------------------------------------------------------------------------


class TestCommandLineContract:
    def test_restore_help_documents_no_atomic_cutover_and_a_stopped_service(
        self, tmp_path, capsys
    ):
        with pytest.raises(SystemExit) as excinfo:
            run("restore", "--help")
        assert excinfo.value.code == 0
        help_text = capsys.readouterr().out
        assert "no atomic cutover" in help_text
        assert "Stop the wall service" in help_text
        assert "never overwrites" in help_text or "nothing that exists" in help_text

    def test_force_is_not_an_option(self, tmp_path, capsys):
        """No ``--force``, no overwrite switch: parsing refuses it outright."""
        with pytest.raises(SystemExit) as excinfo:
            run(
                "restore",
                "--src",
                tmp_path / "src",
                "--db",
                tmp_path / "db",
                "--assets",
                tmp_path / "assets",
                "--force",
            )
        assert excinfo.value.code == 2
        assert "unrecognized arguments" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "argv",
        [
            (),
            ("backup",),
            ("backup", "--db", "x"),
            ("verify",),
            ("restore", "--src", "x"),
            ("nonsense-command",),
        ],
    )
    def test_missing_or_unknown_arguments_are_usage_errors(self, argv):
        with pytest.raises(SystemExit) as excinfo:
            run(*argv)
        assert excinfo.value.code == 2

    def test_the_top_level_help_lists_the_three_commands(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            run("--help")
        assert excinfo.value.code == 0
        help_text = capsys.readouterr().out
        for command in ("backup", "verify", "restore"):
            assert command in help_text

    def test_the_tool_imports_only_the_standard_library(self):
        """The memo's constraint, enforced by parsing the file itself."""
        source = (ROOT / "deploy" / "backup.py").read_text()
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, "no relative imports in a deploy script"
                imported.add((node.module or "").split(".")[0])
        assert imported <= sys.stdlib_module_names, sorted(
            imported - sys.stdlib_module_names
        )

    def test_the_script_runs_as_documented_from_the_command_line(
        self, tmp_path, referenced
    ):
        """``python deploy/backup.py backup …`` — as OPERATIONS.md links it."""
        _active_id, _saved_id, _orphan_id, database, assets = referenced
        destination = tmp_path / "backups" / "snap"
        destination.parent.mkdir()

        backup_run = subprocess.run(
            [
                sys.executable,
                str(ROOT / "deploy" / "backup.py"),
                "backup",
                "--db",
                str(database),
                "--assets",
                str(assets),
                "--dest",
                str(destination),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert backup_run.returncode == 0, backup_run.stderr
        assert destination.is_dir()

        verify_run = subprocess.run(
            [
                sys.executable,
                str(ROOT / "deploy" / "backup.py"),
                "verify",
                "--src",
                str(destination),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert verify_run.returncode == 0, verify_run.stderr
        assert "verified:" in verify_run.stdout
