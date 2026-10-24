"""Manifest 2: managed object closure, omitted uploads, and restore proof."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from deploy import backup
from tabletwall import media, persist


def _object(media_root: Path, payload: bytes) -> tuple[str, str, int]:
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"objects/{digest[:2]}/{digest}.jpg"
    target = media_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return "sha256:" + digest, relative, len(payload)


def _database(path: Path, display_id: str) -> None:
    os.environ["TABLET_WALL_DB"] = str(path)
    persist.ensure_schema()
    layout = {"width": 1000, "height": 500, "placements": {}}
    scene = {
        "content": {"type": "image", "asset": display_id, "fit": "cover",
                    "intrinsicWidth": 100, "intrinsicHeight": 50},
        "layout": "active",
    }
    with persist._connection() as connection:
        connection.execute(
            "INSERT INTO wall_state VALUES (1, ?, ?, ?, ?)",
            (json.dumps(layout), json.dumps(scene), 7, "gen12345"),
        )


def _insert_asset(connection, asset_id: str, objects: dict[str, tuple[str, str, int]],
                  display_id: str, state: str = "ready") -> None:
    now = "2026-10-24T00:00:00+00:00"
    for role, (object_id, relative, size) in objects.items():
        connection.execute(
            "INSERT OR IGNORE INTO media_objects "
            "(object_id, mime, bytes, width, height, path, created_at) "
            "VALUES (?, 'image/jpeg', ?, 100, 50, ?, ?)",
            (object_id, size, relative, now),
        )
    connection.execute(
        "INSERT INTO media_assets VALUES (?, ?, 'image', ?, 1, 100, 50, ?, ?, NULL, ?, ?)",
        (asset_id, "phone.jpg", state, objects["display"][0],
         objects["master"][0], now, now),
    )
    for role, (object_id, _relative, _size) in objects.items():
        connection.execute(
            "INSERT INTO media_renditions VALUES (?, ?, ?, 100, 50)",
            (asset_id, object_id, role),
        )


@pytest.fixture
def managed(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    objects = {
        role: _object(media_root, f"referenced:{role}".encode())
        for role in ("master", "display", "fallback", "thumbnail")
    }
    unused = {
        role: _object(media_root, f"unused:{role}".encode())
        for role in ("master", "display", "fallback", "thumbnail")
    }
    database = tmp_path / "wall.db"
    _database(database, objects["display"][0])
    assets = tmp_path / "assets"
    assets.mkdir()
    with persist._connection() as connection:
        _insert_asset(connection, "0f8fad5b-d9cb-469f-a165-70867728950e", objects,
                      objects["display"][0])
        _insert_asset(connection, "1f8fad5b-d9cb-469f-a165-70867728950e", unused,
                      unused["display"][0])
    return tmp_path, database, assets, media_root, objects, unused


def make_snapshot(tmp_path, database, assets, media_root) -> Path:
    destination = tmp_path / "snapshot"
    assert backup.main([
        "backup", "--db", str(database), "--assets", str(assets),
        "--media", str(media_root), "--dest", str(destination),
    ]) == 0
    return destination


def manifest_of(snapshot: Path) -> dict:
    return json.loads((snapshot / "manifest.json").read_text())


def test_manifest_2_records_closure_and_marks_unused_uploads(managed):
    tmp_path, database, assets, media_root, objects, unused = managed
    snapshot = make_snapshot(tmp_path, database, assets, media_root)
    manifest = manifest_of(snapshot)

    assert manifest["manifest_version"] == 2
    assert manifest["scope"] == "referenced"
    assert manifest["schema_version"] == 2
    assert manifest["references"] == [objects["display"][0]]
    assert {entry["asset_id"] for entry in manifest["media_assets"]} == {
        "0f8fad5b-d9cb-469f-a165-70867728950e"
    }
    stored_objects = {entry["object_id"] for entry in manifest["media_objects"]}
    assert stored_objects == {value[0] for value in objects.values()}
    assert set(manifest["omitted_media"]) == {"1f8fad5b-d9cb-469f-a165-70867728950e"}

    files = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*") if path.is_file()
    }
    expected = {f"media/{value[1]}" for value in objects.values()}
    assert expected <= files
    assert not any(unused["display"][0].split(":")[1] in name for name in files)
    assert not any("unused" in (snapshot / name).read_bytes().decode("latin-1", "ignore")
                   for name in files if name.startswith("media/"))

    # The captured database, not the live one, marks the omitted asset so a
    # restore cannot advertise bytes that were never copied.
    import sqlite3
    connection = sqlite3.connect(snapshot / "database" / "wall.db")
    try:
        state = connection.execute(
            "SELECT state FROM media_assets WHERE asset_id = ?",
            ("1f8fad5b-d9cb-469f-a165-70867728950e",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert state == "unavailable"


def test_manifest_2_verifies_and_restores_the_referenced_object(managed):
    tmp_path, database, assets, media_root, objects, unused = managed
    snapshot = make_snapshot(tmp_path, database, assets, media_root)
    assert backup.main(["verify", "--src", str(snapshot)]) == 0

    restored = tmp_path / "restored"
    restored.mkdir()
    new_db = restored / "wall.db"
    new_assets = restored / "assets"
    new_media = restored / "media"
    assert backup.main([
        "restore", "--src", str(snapshot), "--db", str(new_db),
        "--assets", str(new_assets), "--media", str(new_media),
    ]) == 0

    os.environ["TABLET_WALL_DB"] = str(new_db)
    os.environ["TABLET_WALL_MEDIA_DIR"] = str(new_media)
    fetched = media.fetch_object(objects["display"][0])
    assert fetched is not None
    assert fetched[0] == b"referenced:display"

    import sqlite3
    connection = sqlite3.connect(new_db)
    try:
        state = connection.execute(
            "SELECT state FROM media_assets WHERE asset_id = ?",
            ("1f8fad5b-d9cb-469f-a165-70867728950e",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert state == "unavailable"
    assert not any(new_media.rglob(unused["display"][0].split(":", 1)[1]))


def test_manifest_1_remains_readable_and_restorable_without_media(managed):
    tmp_path, database, assets, media_root, _objects, _unused = managed
    # Start from a snapshot with no managed references so its v1 equivalent is
    # complete: a manifest-1 artifact never claimed media closure.
    os.environ["TABLET_WALL_DB"] = str(database)
    with persist._connection() as connection:
        connection.execute("UPDATE wall_state SET scene = ? WHERE id = 1", (
            json.dumps({"content": {"type": "color"}, "layout": "active"}),
        ))
        connection.execute("DELETE FROM media_assets")
        connection.execute("DELETE FROM media_renditions")
        connection.execute("DELETE FROM media_objects")
    snapshot = make_snapshot(tmp_path, database, assets, media_root)
    manifest = manifest_of(snapshot)
    for key in ("schema_version", "pipeline_version", "scope", "media_objects",
                "media_assets", "omitted_media"):
        del manifest[key]
    manifest["manifest_version"] = 1
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for path in (snapshot / "media").rglob("*") if (snapshot / "media").exists() else []:
        if path.is_file():
            path.unlink()

    assert backup.main(["verify", "--src", str(snapshot)]) == 0
    new_db = tmp_path / "old-restore.db"
    new_assets = tmp_path / "old-assets"
    assert backup.main([
        "restore", "--src", str(snapshot), "--db", str(new_db),
        "--assets", str(new_assets),
    ]) == 0
    assert new_db.is_file()
