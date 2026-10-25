"""Manifest 3: video objects and posters in the backup closure, and restore proof.

A 24 MiB stand-in object (not decodable, published through the real store)
exercises the large-media paths of backup, verify, restore and ranged serving
without an encoder; the real-ffmpeg round trip is in ``test_video_uploads.py``.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from deploy import backup
from tabletwall import media, persist
from video_fixtures import _ensure, fabricate_video, needs_ffmpeg

BIG = 24 * 1024 * 1024
OPERATOR_CREDENTIAL = "test-backup-video-credential-0123456789"
WALL = {
    "layout": {"width": 1000, "height": 500, "placements": {}},
    "scene": {"content": {"type": "color"}, "layout": "active"},
    "revision": 5,
    "generation": "gen12345",
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("TABLET_WALL_DB", str(source / "wall.db"))
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(source / "media"))
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(source / "assets"))
    (source / "assets").mkdir()
    persist.ensure_schema()
    media.ensure_dirs()
    persist.save_state(WALL)
    return source


def playlist(*object_ids: str) -> None:
    persist.save_meta("playlist", {
        "items": [{"asset": object_id, "dwell_ms": 60_000} for object_id in object_ids],
        "loop": False, "revision": 1,
    })


def snapshot(tmp_path: Path, source: Path, name: str = "snapshot") -> Path:
    destination = tmp_path / name
    assert backup.main([
        "backup", "--db", str(source / "wall.db"), "--assets", str(source / "assets"),
        "--media", str(source / "media"), "--dest", str(destination),
    ]) == 0
    return destination


def manifest_of(path: Path) -> dict:
    return json.loads((path / "manifest.json").read_text())


@pytest.fixture
def library(store, tmp_path):
    kept = fabricate_video(BIG, "kept.mp4")
    unused = fabricate_video(1024 * 1024, "unused.mp4")
    playlist(kept["id"])
    return store, kept, unused


def test_a_playlist_only_video_and_its_poster_are_in_the_closure_as_manifest_3(library, tmp_path):
    source, kept, unused = library
    path = snapshot(tmp_path, source)
    manifest = manifest_of(path)

    assert manifest["manifest_version"] == 3
    assert manifest["schema_version"] == persist.SCHEMA_VERSION
    assert manifest["references"] == [kept["id"]]
    assert [entry["asset_id"] for entry in manifest["media_assets"]] == [kept["asset_id"]]
    assert {rendition["role"] for rendition in manifest["media_assets"][0]["renditions"]} == {
        "video", "thumbnail",
    }
    objects = {entry["object_id"]: entry for entry in manifest["media_objects"]}
    assert set(objects) == {kept["id"], kept["poster"]["id"]}
    assert objects[kept["id"]]["mime"] == "video/mp4"
    assert objects[kept["id"]]["path"].endswith(".mp4") and objects[kept["id"]]["bytes"] == BIG
    assert objects[kept["poster"]["id"]]["path"].endswith(".jpg")
    assert manifest["omitted_media"] == [unused["asset_id"]]
    for entry in objects.values():
        assert (path / entry["path"]).is_file()
    assert not any(unused["id"].split(":")[1] in str(p) for p in path.rglob("*"))

    connection = sqlite3.connect(path / "database" / "wall.db")
    try:
        states = dict(connection.execute("SELECT asset_id, state FROM media_assets"))
        facts = connection.execute(
            "SELECT duration_ms, codec FROM media_video WHERE asset_id = ?", (kept["asset_id"],)
        ).fetchone()
    finally:
        connection.close()
    assert states == {kept["asset_id"]: "ready", unused["asset_id"]: "unavailable"}
    assert facts == (60_000, "avc1.64001E")
    assert backup.main(["verify", "--src", str(path)]) == 0


def test_restore_then_fetch_with_range_serves_the_same_bytes_and_validators(
    library, tmp_path, monkeypatch
):
    source, kept, unused = library
    with TestClient(main.app) as client:
        before = client.get(kept["url"], headers={"Range": "bytes=0-0"}).headers
    path = snapshot(tmp_path, source)

    restored = tmp_path / "restored"
    restored.mkdir()
    assert backup.main([
        "restore", "--src", str(path), "--db", str(restored / "wall.db"),
        "--assets", str(restored / "assets"), "--media", str(restored / "media"),
    ]) == 0
    monkeypatch.setenv("TABLET_WALL_DB", str(restored / "wall.db"))
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(restored / "media"))
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(restored / "assets"))

    original = (source / "media" / media.find_servable(kept["id"])["path"]).read_bytes()
    with TestClient(main.app) as client:
        assert media.list_assets()[0] == kept and len(media.list_assets()) == 1
        middle = client.get(kept["url"], headers={"Range": "bytes=10000000-10000099"})
        assert middle.status_code == 206
        assert middle.content == original[10_000_000:10_000_100]
        tail = client.get(kept["url"], headers={"Range": "bytes=-64"})
        assert tail.content == original[-64:]
        # The strong ETag is the content hash, so a client holding the
        # pre-restore validator keeps its range across the restore.
        resumed = client.get(
            kept["url"], headers={"Range": "bytes=5-9", "If-Range": before["etag"]}
        )
        assert resumed.status_code == 206 and resumed.headers["etag"] == before["etag"]
        whole = client.get(kept["url"])
        assert "sha256:" + hashlib.sha256(whole.content).hexdigest() == kept["id"]
        assert client.get(kept["poster"]["url"]).status_code == 200
        assert client.get(unused["url"]).status_code == 404
    assert media.verify_integrity() == []


def test_a_snapshot_with_no_video_stays_manifest_2(store, tmp_path):
    path = snapshot(tmp_path, store)
    assert manifest_of(path)["manifest_version"] == 2


def test_a_schema_2_database_backs_up_as_manifest_2(tmp_path, monkeypatch):
    source = tmp_path / "old"
    source.mkdir()
    monkeypatch.setenv("TABLET_WALL_DB", str(source / "wall.db"))
    connection = sqlite3.connect(source / "wall.db")
    for statement in persist._MIGRATION[:-1]:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO wall_state VALUES (1, ?, ?, 5, 'gen12345')",
        (json.dumps(WALL["layout"]), json.dumps(WALL["scene"])),
    )
    connection.execute("PRAGMA user_version = 2")
    connection.commit()
    connection.close()
    (source / "assets").mkdir()

    path = snapshot(tmp_path, source)
    manifest = manifest_of(path)
    assert (manifest["manifest_version"], manifest["schema_version"]) == (2, 2)
    assert backup.main(["verify", "--src", str(path)]) == 0


def test_a_version_2_reader_rule_refuses_video(library, tmp_path):
    source, _kept, _unused = library
    path = snapshot(tmp_path, source)
    manifest = manifest_of(path)
    manifest["manifest_version"] = 2
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(backup.BackupError, match="version 2 manifest cannot carry"):
        backup.verify_artifact(str(path))


def test_verify_refuses_a_damaged_or_missing_video_object(library, tmp_path):
    source, kept, _unused = library
    path = snapshot(tmp_path, source)
    relative = next(
        entry["path"] for entry in manifest_of(path)["media_objects"]
        if entry["object_id"] == kept["id"]
    )
    target = path / relative
    good = target.read_bytes()
    with open(target, "r+b") as handle:
        handle.seek(12345)
        handle.write(bytes([good[12345] ^ 0xFF]))
    with pytest.raises(backup.BackupError, match="does not match the manifest digest"):
        backup.verify_artifact(str(path))
    target.write_bytes(good)
    assert backup.main(["verify", "--src", str(path)]) == 0
    target.unlink()
    with pytest.raises(backup.BackupError, match="incomplete"):
        backup.verify_artifact(str(path))


def test_a_manifest_path_with_the_wrong_extension_is_refused(library, tmp_path):
    source, kept, _unused = library
    path = snapshot(tmp_path, source)
    manifest = manifest_of(path)
    for entry in manifest["media_objects"]:
        if entry["object_id"] == kept["id"]:
            entry["path"] = entry["path"][:-4] + ".jpg"
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(backup.BackupError, match=r"<hex>\.mp4"):
        backup.verify_artifact(str(path))


def test_a_corrupt_store_object_fails_the_backup_and_publishes_no_snapshot(library, tmp_path):
    source, kept, _unused = library
    live = source / "media" / media.find_servable(kept["id"])["path"]
    data = live.read_bytes()
    live.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))
    destination = tmp_path / "bad"
    assert backup.main([
        "backup", "--db", str(source / "wall.db"), "--assets", str(source / "assets"),
        "--media", str(source / "media"), "--dest", str(destination),
    ]) != 0
    assert not destination.exists()
    assert not [p for p in tmp_path.iterdir() if "incomplete" in p.name]


def _curated_still(source: Path) -> str:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), (9, 9, 9)).save(buffer, format="JPEG")
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    (source / "assets" / f"{digest}.jpg").write_bytes(buffer.getvalue())
    return "sha256:" + digest


def _add_playlist_to_artifact(path: Path, object_id: str) -> None:
    """Rewrite a finished artifact the way a pre-playlist tool could have left it.

    The artifact's database gains a playlist row that names ``object_id``, and
    the manifest's database digest is recomputed, so the artifact stays
    internally consistent while its scene-only reference set no longer equals
    the scenes-plus-playlist set.
    """
    database = path / "database" / "wall.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('playlist', ?)",
        (json.dumps({"items": [{"asset": object_id, "dwell_ms": 5000}], "loop": False}),),
    )
    connection.commit()
    connection.close()
    manifest = manifest_of(path)
    data = database.read_bytes()
    manifest["database"].update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_an_older_version_2_artifact_keeps_its_scene_only_meaning(store, tmp_path):
    still = _curated_still(store)
    path = snapshot(tmp_path, store)
    assert manifest_of(path)["manifest_version"] == 2
    _add_playlist_to_artifact(path, still)

    assert backup.main(["verify", "--src", str(path)]) == 0
    restored = tmp_path / "restored"
    restored.mkdir()
    assert backup.main([
        "restore", "--src", str(path), "--db", str(restored / "wall.db"),
        "--assets", str(restored / "assets"), "--media", str(restored / "media"),
    ]) == 0


def test_a_playlist_that_adds_a_reference_makes_a_version_3_snapshot(store, tmp_path):
    still = _curated_still(store)
    playlist(still)
    path = snapshot(tmp_path, store)
    manifest = manifest_of(path)
    assert manifest["manifest_version"] == 3
    assert manifest["references"] == [still]
    assert [entry["id"] for entry in manifest["assets"]] == [still]
    assert backup.main(["verify", "--src", str(path)]) == 0

    # A playlist that names nothing the scenes do not already hold changes nothing.
    persist.save_meta("playlist", {"items": [], "loop": False, "revision": 2})
    assert manifest_of(snapshot(tmp_path, store, "second"))["manifest_version"] == 2


def _still_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (48, 32), (20, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _operator_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "proxy")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", "http://testserver")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_CREDENTIAL", OPERATOR_CREDENTIAL)
    return {"Origin": "http://testserver", "X-Tablet-Wall-Operator": OPERATOR_CREDENTIAL}


@needs_ffmpeg
def test_a_real_h264_upload_restores_with_its_playlist_descriptor_and_bytes(
    store, tmp_path, monkeypatch
):
    """The real encoder round trip through backup and restore, at HTTP level.

    The decoded-browser proof is ``simulator/browser/restore_run.py``; this
    test keeps the same descriptor, closure and byte facts in the ordinary
    suite without launching Chromium.
    """
    clip = _ensure("baseline.mp4", tmp_path).read_bytes()
    headers = _operator_headers(monkeypatch)

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/uploads?name=clip.mp4", content=clip,
            headers={**headers, "Content-Type": "video/mp4"},
        )
        assert uploaded.status_code == 201, uploaded.text
        video = uploaded.json()["asset"]
        still_reply = client.post(
            "/uploads?name=still.jpg", content=_still_bytes(),
            headers={**headers, "Content-Type": "image/jpeg"},
        )
        assert still_reply.status_code == 201, still_reply.text
        still = still_reply.json()["asset"]
        etag = client.get("/api/v3/playlist").json()["etag"]
        saved = client.put(
            "/api/v3/playlist",
            json={
                "items": [
                    {"asset": video["id"], "dwell_ms": 5000},
                    {"asset": still["id"], "dwell_ms": 5000},
                ],
                "loop": False,
            },
            headers={**headers, "If-Match": etag},
        )
        assert saved.status_code == 200, saved.text
        document = saved.json()["playlist"]
        assert document["items"][0]["dwell_ms"] == video["durationMs"]

    path = snapshot(tmp_path, store)
    manifest = manifest_of(path)
    objects = {entry["object_id"]: entry for entry in manifest["media_objects"]}
    assert manifest["manifest_version"] == 3
    assert video["id"] in manifest["references"] and still["id"] in manifest["references"]
    assert {video["id"], video["poster"]["id"], still["id"]} <= set(objects)
    assert objects[video["id"]]["bytes"] == video["bytes"]
    assert objects[video["id"]]["sha256"] == video["id"].split(":", 1)[1]
    assert backup.main(["verify", "--src", str(path)]) == 0

    restored = tmp_path / "restored"
    restored.mkdir()
    assert backup.main([
        "restore", "--src", str(path), "--db", str(restored / "wall.db"),
        "--assets", str(restored / "assets"), "--media", str(restored / "media"),
    ]) == 0
    assert (restored / objects[video["id"]]["path"]).read_bytes() == (
        store / objects[video["id"]]["path"]
    ).read_bytes()

    monkeypatch.setenv("TABLET_WALL_DB", str(restored / "wall.db"))
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(restored / "media"))
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(restored / "assets"))
    with TestClient(main.app) as client:
        library = client.get("/media", headers=headers)
        assert library.status_code == 200, library.text
        entry = next(item for item in library.json()["assets"] if item["id"] == video["id"])
        assert (entry["kind"], entry["mime"], entry["bytes"]) == (
            "video", "video/mp4", video["bytes"],
        )
        assert (entry["intrinsicWidth"], entry["intrinsicHeight"]) == (
            video["intrinsicWidth"], video["intrinsicHeight"],
        )
        playlist = client.get("/api/v3/playlist").json()["playlist"]
        assert playlist["items"] == document["items"] and playlist["loop"] is False

        whole = client.get(video["url"])
        assert whole.status_code == 200
        assert hashlib.sha256(whole.content).hexdigest() == video["id"].split(":", 1)[1]
        ranged = client.get(video["url"], headers={"Range": "bytes=0-99"})
        assert ranged.status_code == 206
        assert ranged.content == whole.content[:100]
        assert ranged.headers["content-range"] == f"bytes 0-99/{video['bytes']}"
        head = client.head(video["url"])
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == str(video["bytes"])
        assert client.get(video["poster"]["url"]).status_code == 200
        assert client.get(still["url"]).status_code == 200
