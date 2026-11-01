"""Images-only operator inventory and authoritative v3 scene updates."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from threading import Event

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from tabletwall import assets, media, persist, playback
from video_fixtures import make_video as make_video, needs_ffmpeg, video_dir as video_dir

ORIGIN = "https://operator.wall.test:8444"
CREDENTIAL = "private-test-operator-credential"
IMAGE_KEYS = {"id", "name", "width", "height", "url", "thumbnail_url", "source"}


@pytest.fixture
def image_environment(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "disabled")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_CREDENTIAL", CREDENTIAL)


@pytest.fixture
def operator(image_environment):
    with TestClient(main.app, client=("127.0.0.1", 50000)) as client:
        yield client


def image_bytes(size=(80, 40), color="red", format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=format)
    return buffer.getvalue()


def curated(asset_dir, name="curated.png", size=(80, 40), color="red"):
    body = image_bytes(size, color)
    (asset_dir / name).write_bytes(body)
    asset_id = "sha256:" + hashlib.sha256(body).hexdigest()
    return next(entry for entry in assets.list_assets() if entry["id"] == asset_id)


def upload(client, monkeypatch, size=(96, 48), color="blue", name="managed.jpg"):
    with monkeypatch.context() as settings:
        settings.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
        settings.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
        response = client.post(
            "/uploads", params={"name": name}, content=image_bytes(size, color, "JPEG"),
            headers={"Content-Type": "image/jpeg", "Origin": ORIGIN},
        )
    assert response.status_code == 201, response.text
    return response.json()["asset"]


def select(client, asset_id, etag=None):
    if etag is None:
        etag = client.get("/api/v3/config").json()["etag"]
    return client.put(
        "/api/v3/scene", json={"content": {"type": "image", "asset": asset_id}},
        headers={"If-Match": etag},
    )


def test_empty_library_is_useful_with_uploads_disabled(operator):
    response = operator.get("/api/v3/images")
    assert response.status_code == 200
    assert response.json() == {"images": []}
    assert response.headers["cache-control"] == "no-store"


def test_selecting_a_static_image_stops_an_experimental_presentation(operator, asset_dir):
    entry = curated(asset_dir)
    main._playback_session = playback.start(
        [{"asset": entry["id"], "dwell_ms": 1000}], False,
        ["0f8fad5b-d9cb-469f-a165-70867728950e"], main._now_ms(),
        generation=main.wall["generation"], clock_epoch="test",
    )
    assert select(operator, entry["id"]).status_code == 200
    assert main._playback_session is None
    assert operator.get("/api/v3/playback").json()["state"] == "stopped"
    assert operator.get("/api/v3/config").json()["scene"]["content"]["asset"] == entry["id"]


def test_inventory_merges_deduplicates_and_serves_real_metadata(
    operator, asset_dir, monkeypatch, tmp_path
):
    local = curated(asset_dir)
    managed = upload(operator, monkeypatch)
    duplicate = operator.get(managed["url"]).content
    (asset_dir / "duplicate.jpg").write_bytes(duplicate)
    (asset_dir / "other-name.png").write_bytes((asset_dir / "curated.png").read_bytes())
    repeated = upload(operator, monkeypatch, name="again.jpg")
    assert repeated["id"] == managed["id"]

    response = operator.get("/api/v3/images")
    assert response.status_code == 200
    rows = response.json()["images"]
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {local["id"], managed["id"]}
    assert by_id[local["id"]]["source"] == "curated"
    assert by_id[local["id"]]["thumbnail_url"] == local["url"]
    assert by_id[managed["id"]]["source"] == "managed"
    assert by_id[managed["id"]]["thumbnail_url"] == managed["thumbnail"]["url"]
    assert operator.get("/api/v3/images").json() == response.json()
    for row in rows:
        assert set(row) == IMAGE_KEYS
        body = operator.get(row["url"]).content
        assert "sha256:" + hashlib.sha256(body).hexdigest() == row["id"]
        assert Image.open(BytesIO(body)).size == (row["width"], row["height"])
        assert operator.get(row["thumbnail_url"]).status_code == 200
    assert str(tmp_path) not in response.text
    assert CREDENTIAL not in response.text


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.7"])
@pytest.mark.parametrize("headers", [
    {"Forwarded": "for=127.0.0.1"},
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Forwarded-Host": "operator.wall.test"},
    {"X-Tablet-Wall-Operator": "forged"},
])
def test_forged_operator_headers_cannot_read_inventory(image_environment, host, headers):
    with TestClient(main.app, client=(host, 50001)) as client:
        assert client.get("/api/v3/images", headers=headers).status_code == 403


def test_remote_inventory_requires_exactly_one_operator_credential(image_environment):
    with TestClient(main.app, client=("192.0.2.7", 50001)) as client:
        assert client.get("/api/v3/images").status_code == 403
        accepted = client.get(
            "/api/v3/images", headers={"X-Tablet-Wall-Operator": CREDENTIAL}
        )
        assert accepted.status_code == 200
        assert accepted.json() == {"images": []}
        assert client.get("/api/v3/images", headers=[
            ("X-Tablet-Wall-Operator", CREDENTIAL),
            ("X-Tablet-Wall-Operator", CREDENTIAL),
        ]).status_code == 403


def test_inventory_excludes_unready_images(operator, monkeypatch):
    still = upload(operator, monkeypatch)
    with persist._connection() as connection:
        connection.execute(
            "UPDATE media_assets SET state = 'unavailable' WHERE asset_id = ?",
            (still["asset_id"],),
        )
    assert operator.get("/api/v3/images").json() == {"images": []}


@needs_ffmpeg
def test_inventory_and_scene_exclude_videos_and_their_posters(operator, monkeypatch, make_video):
    still = upload(operator, monkeypatch)
    with monkeypatch.context() as settings:
        settings.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
        settings.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
        response = operator.post(
            "/uploads?name=clip.mp4", content=make_video("baseline.mp4").read_bytes(),
            headers={"Content-Type": "video/mp4", "Origin": ORIGIN},
        )
    assert response.status_code == 201, response.text
    video = response.json()["asset"]
    rows = operator.get("/api/v3/images").json()["images"]
    assert [row["id"] for row in rows] == [still["id"]]
    before = operator.get("/api/v3/config").json()
    for object_id in (video["id"], video["poster"]["id"]):
        assert select(operator, object_id).status_code == 422
    assert operator.get("/api/v3/config").json() == before


@pytest.mark.parametrize("mode", ["logical", "physical"])
def test_scene_a_to_b_and_restart_expose_the_real_scene(image_environment, asset_dir, mode):
    first = curated(asset_dir)
    second = curated(asset_dir, "second.png", (45, 90), "green")
    with TestClient(main.app) as client:
        selected = select(client, first["id"])
        assert selected.status_code == 200, selected.text
        before = selected.json()
        if mode == "physical":
            switched = client.put("/api/v3/layout", json={
                "bounds": {"x": 0, "y": 0, "width": 300, "height": 200}, "slots": {},
            }, headers={"If-Match": before["etag"]})
            assert switched.status_code == 200, switched.text
            before = switched.json()
        assert before["scene"]["content"]["asset"] == first["id"]
        changed = select(client, second["id"], before["etag"])
        assert changed.status_code == 200, changed.text
        after = changed.json()
        assert after["layout"] == before["layout"]
        assert after["layout"]["kind"] == mode
        assert after["revision"] == before["revision"] + 1
        assert after["etag"] != before["etag"]
        assert changed.headers["etag"] == after["etag"]
        assert after["scene"]["content"] == {
            "type": "image", "asset": second["id"], "fit": "cover",
            "intrinsicWidth": 45, "intrinsicHeight": 90, "url": second["url"],
        }
        assert client.get("/api/v3/config").json() == after
        stored = persist.load_state()
        assert "url" not in stored["scene"]["content"]
    main.wall.clear()
    main.wall.update(main._fresh_wall())
    with TestClient(main.app) as restarted:
        restored = restarted.get("/api/v3/config").json()
        assert restored["scene"] == after["scene"]
        assert restored["layout"] == after["layout"]
        assert restored["revision"] == after["revision"]
        assert restored["generation"] != after["generation"]
        assert select(restarted, first["id"], after["etag"]).status_code == 412


def test_managed_selection_preserves_immutable_object_metadata(operator, monkeypatch):
    managed = upload(operator, monkeypatch, (3000, 1500))
    original = deepcopy(media.find_object(managed["id"]))
    response = select(operator, managed["id"])
    assert response.status_code == 200, response.text
    content = response.json()["scene"]["content"]
    assert (content["intrinsicWidth"], content["intrinsicHeight"]) == (2048, 1024)
    assert content["url"] == managed["url"]
    assert Image.open(BytesIO(operator.get(content["url"]).content)).size == (2048, 1024)
    assert media.find_object(managed["id"]) == original
    assert operator.get("/wall").json()["scene"] == response.json()["scene"]


def test_invalid_asset_missing_and_stale_etags_never_mutate(operator, asset_dir):
    entry = curated(asset_dir)
    before = operator.get("/api/v3/config").json()
    body = {"content": {"type": "image", "asset": entry["id"]}}
    assert operator.put("/api/v3/scene", json=body).status_code == 428
    assert select(operator, entry["id"], "stale").status_code == 412
    assert select(operator, "sha256:" + "0" * 64, before["etag"]).status_code == 422
    assert operator.get("/api/v3/config").json() == before
    accepted = select(operator, entry["id"], before["etag"])
    assert accepted.status_code == 200
    stored = persist.load_state()
    assert select(operator, entry["id"], before["etag"]).status_code == 412
    assert persist.load_state() == stored


@pytest.mark.parametrize("content", [
    {"type": "image", "asset": "sha256:" + "0" * 64, "url": "https://evil.example"},
    {"type": "image", "asset": "sha256:" + "0" * 64, "intrinsicWidth": 1},
    {"type": "image", "asset": "sha256:" + "0" * 64, "intrinsicHeight": 1},
    {"type": "image", "asset": "../secret"},
    {"type": "video", "asset": "sha256:" + "0" * 64},
    {"type": "color", "fit": "cover"},
])
def test_v3_reuses_legacy_scene_validation(operator, content):
    before = operator.get("/api/v3/config").json()
    for path in ("/scene", "/api/v3/scene"):
        assert operator.put(path, json={"content": content}, headers={
            "If-Match": before["etag"],
        }).status_code == 422
    assert operator.get("/api/v3/config").json() == before


def test_a_change_during_resolution_refuses_the_stale_commit(operator, asset_dir, monkeypatch):
    entry = curated(asset_dir)
    etag = operator.get("/api/v3/config").json()["etag"]
    resolving, resume = Event(), Event()
    find = media.find_object

    def delayed_find(asset_id):
        resolving.set()
        assert resume.wait(5)
        return find(asset_id)

    monkeypatch.setattr(media, "find_object", delayed_find)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(select, operator, entry["id"], etag)
        try:
            assert resolving.wait(5)
            changed = operator.put("/api/v3/scene", json={
                "content": {"type": "calibration"},
            }, headers={"If-Match": etag})
            assert changed.status_code == 200
        finally:
            resume.set()
        assert pending.result(timeout=5).status_code == 412
    assert operator.get("/api/v3/config").json() == changed.json()


def test_scene_commit_precedes_notification_and_failed_commit_changes_nothing(
    operator, asset_dir, monkeypatch
):
    entry = curated(asset_dir)
    notifications = []

    async def notified():
        stored = persist.load_state()
        assert stored["scene"] == main.wall["scene"]
        assert stored["revision"] == main.wall["revision"]
        notifications.append(stored)

    monkeypatch.setattr(main, "_broadcast_wall", notified)
    assert select(operator, entry["id"]).status_code == 200
    assert len(notifications) == 1
    before = operator.get("/api/v3/config").json()
    stored = persist.load_state()

    def failed_save(_state):
        raise RuntimeError("private test disk full")

    monkeypatch.setattr(main, "save_state", failed_save)
    with pytest.raises(RuntimeError, match="private test disk full"):
        select(operator, entry["id"])
    assert operator.get("/api/v3/config").json() == before
    assert persist.load_state() == stored
    assert len(notifications) == 1
