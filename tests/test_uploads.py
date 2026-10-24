"""The streamed upload route end to end (R1).

Admission is tested directly in ``test_media.py``. Here the TestClient is
pretended to be a loopback peer (its transport reports ``testclient``), so the
route, worker subprocess, publication, managed scene acceptance and byte
serving are exercised together.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
import tabletwall.media as media

ORIGIN = "https://operator.wall.test:8444"


def jpeg(width: int = 64, height: int = 48, colour=(30, 120, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)


def headers(**extra):
    return {"Origin": ORIGIN, "Content-Type": "image/jpeg", **extra}


def test_upload_publishes_serves_and_is_accepted_by_the_scene(operator):
    body = jpeg()
    with TestClient(main.app) as client:
        response = client.post("/uploads?name=phone.jpg", content=body, headers=headers())
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["state"] == "ready"
        descriptor = payload["asset"]
        assert descriptor["name"] == "phone.jpg"
        assert descriptor["mime"] == "image/jpeg"
        assert descriptor["url"] == f"/assets/{descriptor['id']}"
        assert descriptor["intrinsicWidth"] == 64
        assert descriptor["intrinsicHeight"] == 48
        assert descriptor["thumbnail"]["url"].startswith("/assets/sha256:")

        served = client.get(descriptor["url"])
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/jpeg")
        Image.open(BytesIO(served.content)).load()

        scene = client.put(
            "/scene",
            json={"content": {"type": "image", "asset": descriptor["id"], "fit": "cover"}},
            headers={"Origin": ORIGIN},
        )
        assert scene.status_code == 200, scene.text
        assert scene.json()["scene"]["content"]["asset"] == descriptor["id"]

        library = client.get("/media")
        assert library.status_code == 200
        assert [entry["asset_id"] for entry in library.json()["assets"]] == [
            descriptor["asset_id"]
        ]


def test_upload_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "disabled")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    with TestClient(main.app) as client:
        response = client.post("/uploads", content=jpeg(), headers=headers())
    assert response.status_code == 403


def test_upload_requires_the_operator_origin(operator):
    with TestClient(main.app) as client:
        response = client.post("/uploads", content=jpeg(), headers={"Content-Type": "image/jpeg"})
        wrong = client.post(
            "/uploads", content=jpeg(),
            headers={**headers(), "Origin": "https://evil.example"},
        )
    assert response.status_code == 403
    assert wrong.status_code == 403


def test_upload_rejects_a_non_image_media_type(operator):
    with TestClient(main.app) as client:
        response = client.post(
            "/uploads", content=b"hello",
            headers={**headers(), "Content-Type": "text/plain"},
        )
    assert response.status_code == 415


def test_upload_rejects_an_oversized_declared_and_streamed_body(operator, monkeypatch):
    monkeypatch.setattr(main, "MAX_SOURCE_BYTES", 10)
    monkeypatch.setattr(media, "MAX_SOURCE_BYTES", 10)
    with TestClient(main.app) as client:
        declared = client.post("/uploads", content=b"x" * 11, headers=headers())
        streamed = client.post("/uploads", content=b"x" * 11, headers={k: v for k, v in headers().items()})
    assert declared.status_code == 413
    assert streamed.status_code == 413


def test_a_phone_style_rotated_jpeg_arrives_upright_and_stripped(operator):
    source = Image.new("RGB", (4032, 3024), (20, 60, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise on display
    buffer = BytesIO()
    source.save(buffer, format="JPEG", quality=90, exif=exif)
    with TestClient(main.app) as client:
        response = client.post(
            "/uploads?name=phone.jpg", content=buffer.getvalue(), headers=headers()
        )
        assert response.status_code == 201, response.text
        descriptor = response.json()["asset"]
        # Upright source is 3024x4032; the 2048 display rendition is 1536x2048.
        assert (descriptor["intrinsicWidth"], descriptor["intrinsicHeight"]) == (1536, 2048)
        served = client.get(descriptor["url"])
        image = Image.open(BytesIO(served.content))
        assert image.size == (1536, 2048)
        assert image.getexif().get(0x0112) in (None, 1)
        assert "exif" not in image.info and "icc_profile" not in image.info


def test_upload_quota_exhaustion_is_a_507(operator, monkeypatch):
    monkeypatch.setattr(media, "QUOTA_BYTES", 1)
    monkeypatch.setattr(media, "FREE_RESERVE_BYTES", 0)
    with TestClient(main.app) as client:
        response = client.post("/uploads", content=jpeg(), headers=headers())
    assert response.status_code == 507
    assert "quota" in response.json()["detail"]


def test_worker_timeout_is_reported_and_leaves_no_asset(operator, monkeypatch):
    async def timeout(job):
        raise media.StoreError(422, "image processing exceeded 30 seconds")

    monkeypatch.setattr(media, "run_worker", timeout)
    with TestClient(main.app) as client:
        response = client.post("/uploads", content=jpeg(), headers=headers())
        library = client.get("/media")
    assert response.status_code == 422
    assert "30 seconds" in response.json()["detail"]
    assert library.json()["assets"] == []


def test_a_rejected_image_leaves_no_ready_asset(operator):
    with TestClient(main.app) as client:
        response = client.post(
            "/uploads?name=broken.jpg", content=b"not an image", headers=headers()
        )
        library = client.get("/media")
    assert response.status_code == 422
    assert "detail" in response.json()
    assert library.status_code == 200
    assert library.json()["assets"] == []
