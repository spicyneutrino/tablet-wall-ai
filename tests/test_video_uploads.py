"""The video upload route end to end (R4): admission, descriptor, refusal, crash.

The TestClient is pretended to be a loopback peer exactly as in
``test_uploads.py``; the route, the real ``python -m tabletwall.video`` worker,
publication, quota, byte serving and the still-only scene guard run together.
"""

import hashlib
import os
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
import tabletwall.media as media
import tabletwall.persist as persist
from video_fixtures import needs_ffmpeg, make_video, video_dir  # noqa: F401

ORIGIN = "https://operator.wall.test:8444"
STILL_KEYS = {"id", "asset_id", "name", "mime", "intrinsicWidth", "intrinsicHeight",
              "bytes", "url", "state", "created_at", "thumbnail"}
VIDEO_KEYS = {"kind", "durationMs", "codec", "profile", "level", "pixelFormat", "frameRate",
              "bitrate", "faststart", "audio", "poster"}

pytestmark = needs_ffmpeg


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)


def headers(content_type="video/mp4", **extra):
    return {"Origin": ORIGIN, "Content-Type": content_type, **extra}


def post_video(client, path: Path, name="clip.mp4", content_type="video/mp4"):
    return client.post(
        f"/uploads?name={name}", content=path.read_bytes(), headers=headers(content_type)
    )


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (30, 120, 200)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def media_files() -> list[str]:
    root = Path(media.media_dir())
    return sorted(
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.name != ".store.lock"
    )


def staging_entries() -> list[str]:
    return sorted(os.listdir(media.staging_dir()))


def test_upload_publishes_a_video_descriptor_that_matches_the_contract(operator, make_video):
    source = make_video("nonfaststart.mp4")
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, source, name="intro.mp4")
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["state"] == "ready"
        descriptor = payload["asset"]

        assert set(descriptor) == STILL_KEYS | VIDEO_KEYS
        assert descriptor["kind"] == "video"
        assert descriptor["mime"] == "video/mp4"
        assert descriptor["name"] == "intro.mp4"
        assert descriptor["url"] == f"/assets/{descriptor['id']}"
        assert descriptor["durationMs"] == 2000
        assert (descriptor["intrinsicWidth"], descriptor["intrinsicHeight"]) == (320, 240)
        assert descriptor["codec"] == "avc1.4D400C"
        assert descriptor["profile"] == "Main"
        assert descriptor["level"] == "1.2"
        assert descriptor["pixelFormat"] == "yuv420p"
        assert descriptor["frameRate"] == 15.0
        assert isinstance(descriptor["bitrate"], int) and descriptor["bitrate"] > 0
        assert descriptor["faststart"] is True
        assert descriptor["audio"] is False
        assert set(descriptor["poster"]) == {"id", "url", "width", "height"}
        assert descriptor["poster"] == descriptor["thumbnail"]
        assert descriptor["bytes"] <= 250 * 1024 * 1024

        body = client.get(descriptor["url"])
        assert body.status_code == 200
        assert len(body.content) == descriptor["bytes"]
        assert "sha256:" + hashlib.sha256(body.content).hexdigest() == descriptor["id"]
        poster = client.get(descriptor["poster"]["url"])
        assert poster.headers["content-type"] == "image/jpeg"
        assert Image.open(BytesIO(poster.content)).size == (
            descriptor["poster"]["width"], descriptor["poster"]["height"],
        )

        library = client.get("/media").json()["assets"]
        assert [entry["asset_id"] for entry in library] == [descriptor["asset_id"]]
        assert library[0] == descriptor
    assert staging_entries() == []


def test_stills_are_unchanged_next_to_a_video(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        still = client.post("/uploads?name=a.jpg", content=jpeg(), headers=headers("image/jpeg"))
        clip = post_video(client, make_video("baseline.mp4"))
        assert still.status_code == 201 and clip.status_code == 201
        descriptor = still.json()["asset"]
        assert set(descriptor) == STILL_KEYS
        assert "kind" not in descriptor
        by_id = {entry["asset_id"]: entry for entry in client.get("/media").json()["assets"]}
        assert set(by_id[descriptor["asset_id"]]) == STILL_KEYS
        assert by_id[clip.json()["asset"]["asset_id"]]["kind"] == "video"


def test_the_same_admission_gate_applies_to_video(monkeypatch, make_video):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "disabled")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    source = make_video("baseline.mp4")
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert post_video(client, source).status_code == 403
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        wrong_origin = client.post(
            "/uploads", content=source.read_bytes(),
            headers={"Origin": "https://evil.example", "Content-Type": "video/mp4"},
        )
        no_origin = client.post(
            "/uploads", content=source.read_bytes(), headers={"Content-Type": "video/mp4"}
        )
        monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
        remote = post_video(client, source)
        monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
        allowed = post_video(client, source)
    assert allowed.status_code == 201, allowed.text
    assert wrong_origin.status_code == 403
    assert no_origin.status_code == 403
    assert remote.status_code == 403
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert len(client.get("/media").json()["assets"]) == 1  # only the admitted upload


def test_quicktime_content_type_is_accepted_and_stored_as_mp4(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, make_video("quicktime.mov"), "phone.mov", "video/quicktime")
        assert response.status_code == 201, response.text
        assert response.json()["asset"]["mime"] == "video/mp4"


@pytest.mark.parametrize(
    ("name", "fragment"),
    [("hevc.mp4", "HEVC"), ("vp9.webm", "WebM"), ("tenbit.mp4", "yuv420p10le"),
     ("oversize.mp4", "2560x1440"), ("truncated_faststart.mp4", "truncated"),
     ("audio.m4a", "no video"), ("garbage.bin", "not an MP4"), ("ffconcat.txt", "not an MP4")],
)
def test_a_rejected_video_leaves_nothing_behind(operator, make_video, name, fragment):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, make_video(name), name)
        library = client.get("/media")
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert library.json()["assets"] == []
    assert media_files() == []
    assert staging_entries() == []


def test_a_url_or_concat_looking_name_is_only_a_label(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, make_video("baseline.mp4"), name="concat:/etc/hostname|x.mp4")
        assert response.status_code == 201, response.text
        assert response.json()["asset"]["name"] == "hostname|x.mp4"
        again = post_video(client, make_video("baseline.mp4"), name="http://evil.example/a.mp4")
        assert again.status_code == 201
        assert again.json()["asset"]["name"] == "a.mp4"


def test_unsupported_media_types_are_415_and_the_video_cap_is_enforced(operator, monkeypatch):
    monkeypatch.setattr(main, "MAX_VIDEO_BYTES", 1000)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert client.post("/uploads", content=b"x", headers=headers("text/plain")).status_code == 415
        assert client.post("/uploads", content=b"x", headers=headers("video/webm")).status_code == 415
        declared = client.post("/uploads", content=b"x" * 1001, headers=headers())
        assert declared.status_code == 413
        assert "video is larger than" in declared.json()["detail"]

        def chunks():
            for _ in range(11):
                yield b"x" * 100

        streamed = client.post("/uploads", content=chunks(), headers=headers())
    assert streamed.status_code == 413
    assert staging_entries() == []


def test_the_filename_suffix_and_declared_type_never_decide_admission(operator):
    """The browser may pick its wait from a suffix; the server reads type and bytes."""
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        still = client.post(
            "/uploads?name=clip.mp4", content=jpeg(), headers=headers("image/jpeg")
        )
        assert still.status_code == 201, still.text
        assert set(still.json()["asset"]) == STILL_KEYS

        refused = client.post(
            "/uploads?name=still.png", content=jpeg(), headers=headers("video/mp4")
        )
        assert refused.status_code == 422
        assert "not an MP4" in refused.json()["detail"]
        assert [entry["id"] for entry in client.get("/media").json()["assets"]] == [
            still.json()["asset"]["id"]
        ]


def test_the_still_cap_does_not_apply_to_a_video(operator, make_video, monkeypatch):
    monkeypatch.setattr(main, "MAX_SOURCE_BYTES", 10)
    monkeypatch.setattr(media, "MAX_SOURCE_BYTES", 10)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert post_video(client, make_video("baseline.mp4")).status_code == 201


def test_quota_exhaustion_is_a_507_and_leaves_no_objects(operator, make_video, monkeypatch):
    monkeypatch.setattr(media, "QUOTA_BYTES", 1)
    monkeypatch.setattr(media, "FREE_RESERVE_BYTES", 0)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, make_video("baseline.mp4"))
        library = client.get("/media")
    assert response.status_code == 507
    assert "quota" in response.json()["detail"]
    assert library.json()["assets"] == []
    assert media_files() == [] and staging_entries() == []


def test_the_quota_reserves_room_for_the_remuxed_copy(operator, make_video, monkeypatch):
    source = make_video("baseline.mp4")
    size = source.stat().st_size
    # Room for the source alone, not for source plus the remux output.
    monkeypatch.setattr(media, "QUOTA_BYTES", size + size // 2)
    monkeypatch.setattr(media, "FREE_RESERVE_BYTES", 0)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, source)
    assert response.status_code == 507
    assert media_files() == [] and staging_entries() == []


def test_a_crash_after_the_objects_are_linked_but_before_the_commit_publishes_nothing(
    operator, make_video, monkeypatch
):
    source = make_video("baseline.mp4")
    real_connection = persist._connection

    def crash():
        raise RuntimeError("simulated power loss before the commit")

    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        monkeypatch.setattr(persist, "_connection", crash)
        failed = post_video(client, source)
        monkeypatch.setattr(persist, "_connection", real_connection)
        assert failed.status_code == 500

        # Objects reached the immutable tree, but no row lists them: nothing
        # serves them and nothing counts them as a library entry.
        orphans = [path for path in media_files() if path.startswith("objects/")]
        assert any(path.endswith(".mp4") for path in orphans)
        assert client.get("/media").json()["assets"] == []
        digest = next(Path(path).stem for path in orphans if path.endswith(".mp4"))
        assert client.get(f"/assets/sha256:{digest}").status_code == 404
        assert staging_entries() == []

        # The retry reuses the identical object and publishes cleanly.
        retried = post_video(client, source)
        assert retried.status_code == 201, retried.text
        assert retried.json()["asset"]["id"] == f"sha256:{digest}"
        assert client.get(retried.json()["asset"]["url"]).status_code == 200


def test_a_worker_crash_before_publication_is_a_clean_failure(operator, make_video, monkeypatch):
    async def explode(job):
        raise RuntimeError("worker vanished")

    monkeypatch.setattr(media, "run_video_worker", explode)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        response = post_video(client, make_video("baseline.mp4"))
        library = client.get("/media")
    assert response.status_code == 500
    assert library.json()["assets"] == []
    assert media_files() == [] and staging_entries() == []


def test_a_video_or_poster_is_never_a_still_scene_image(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        descriptor = post_video(client, make_video("baseline.mp4")).json()["asset"]
        still = client.post("/uploads", content=jpeg(), headers=headers("image/jpeg")).json()["asset"]
        for object_id in (descriptor["id"], descriptor["poster"]["id"]):
            refused = client.put(
                "/scene",
                json={"content": {"type": "image", "asset": object_id, "fit": "cover"}},
                headers={"Origin": ORIGIN},
            )
            assert refused.status_code == 422, object_id
        accepted = client.put(
            "/scene",
            json={"content": {"type": "image", "asset": still["id"], "fit": "cover"}},
            headers={"Origin": ORIGIN},
        )
        assert accepted.status_code == 200


def test_the_playlist_hook_returns_the_duration_for_a_content_id(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        descriptor = post_video(client, make_video("baseline.mp4")).json()["asset"]
        still = client.post("/uploads", content=jpeg(), headers=headers("image/jpeg")).json()["asset"]
    assert media.video_duration_ms(descriptor["id"]) == 2000
    assert media.video_descriptor(descriptor["id"]) == descriptor
    assert media.video_duration_ms(still["id"]) is None
    assert media.video_duration_ms(descriptor["poster"]["id"]) is None
    assert media.video_duration_ms("sha256:" + "0" * 64) is None
    assert media.video_duration_ms("not-an-id") is None
    assert media.video_duration_ms(descriptor["asset_id"]) is None  # the UUID is not the content id


def test_verify_reports_a_corrupt_video_without_touching_it(operator, make_video):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        descriptor = post_video(client, make_video("baseline.mp4")).json()["asset"]
        clean = client.post("/media/verify", headers={"Origin": ORIGIN}).json()
        assert clean == {"ok": True, "problems": []}
        path = os.path.join(media.media_dir(), media.find_servable(descriptor["id"])["path"])
        with open(path, "r+b") as handle:
            data = handle.read()
            handle.seek(len(data) // 2)
            handle.write(bytes([data[len(data) // 2] ^ 0xFF]))
        dirty = client.post("/media/verify", headers={"Origin": ORIGIN}).json()
        assert dirty["ok"] is False
        assert [problem["object_id"] for problem in dirty["problems"]] == [descriptor["id"]]
        assert os.path.exists(path)


def test_an_uploaded_video_survives_backup_and_restore_and_is_served_with_ranges(
    operator, make_video, tmp_path, monkeypatch
):
    from deploy import backup

    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        descriptor = post_video(client, make_video("hd.mp4")).json()["asset"]
        original = client.get(descriptor["url"]).content
    persist.save_meta("playlist", {
        "items": [{"asset": descriptor["id"], "dwell_ms": descriptor["durationMs"]}],
        "loop": False, "revision": 1,
    })
    snapshot = tmp_path / "snapshot"
    assert backup.main([
        "backup", "--db", persist.db_path(), "--assets", os.environ["TABLET_WALL_ASSET_DIR"],
        "--media", media.media_dir(), "--dest", str(snapshot),
    ]) == 0

    restored = tmp_path / "restored"
    restored.mkdir()
    assert backup.main([
        "restore", "--src", str(snapshot), "--db", str(restored / "wall.db"),
        "--assets", str(restored / "assets"), "--media", str(restored / "media"),
    ]) == 0
    monkeypatch.setenv("TABLET_WALL_DB", str(restored / "wall.db"))
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(restored / "media"))
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(restored / "assets"))

    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert media.list_assets() == [descriptor]
        part = client.get(descriptor["url"], headers={"Range": "bytes=100-299"})
        assert part.status_code == 206 and part.content == original[100:300]
        assert client.get(descriptor["poster"]["url"]).status_code == 200
    assert media.verify_integrity() == []
