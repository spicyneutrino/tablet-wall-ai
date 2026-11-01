"""``/healthz``, readiness, and join-QR routes with injected readers.

The routes are exercised on a private app that mounts only this router, so the
test does not depend on ``main`` wiring them yet. Admission still runs through
the real ``media.admit_operator_read``.
"""

from __future__ import annotations

import io

import pytest
import zxingcpp
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from tabletwall import media, operability
from tabletwall.routes import health

TABLET = "http://10.42.0.1:8080"


def snapshot(**overrides):
    values = {
        "generation": "abc12345",
        "revision": 4,
        "devices_total": 2,
        "devices_online": 1,
        "content_type": "image",
        "content_asset": "sha256:" + "a" * 64,
        "layout_kind": "physical",
        "schema_version": 3,
        "storage_readable": True,
    }
    values.update(overrides)
    return operability.WallSnapshot(**values)


def config(**overrides):
    values = {
        "tablet_origin": TABLET,
        "operator_origin": "http://127.0.0.1:8000",
        "uploads": "disabled",
        "authentication": "disabled",
        "wifi_name": "Wall-Lab",
        "backup_dir": None,
        "errors": (),
    }
    values.update(overrides)
    return operability.Config(**values)


def app_for(state, settings=None, resolve=lambda _asset: True):
    application = FastAPI()
    application.include_router(health.create_router(
        read_state=lambda: state() if callable(state) else state,
        read_config=lambda: settings() if callable(settings) else (settings or config()),
        resolve_asset=resolve,
    ))
    return application


@pytest.fixture(autouse=True)
def loopback_operator(monkeypatch):
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    monkeypatch.delenv(media.OPERATOR_CREDENTIAL_ENV, raising=False)


def test_healthz_reports_ready_state_without_paths_or_secrets():
    with TestClient(app_for(snapshot())) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["ready"] is True
    assert body["schema"] == 3
    assert body["generation"] == "abc12345"
    assert body["revision"] == 4
    assert body["counts"] == {"devices_online": 1, "devices_total": 2}
    text = response.text
    assert "/tmp" not in text and "wall.db" not in text
    assert "assets" not in body and "media" not in body


def test_healthz_is_503_when_storage_or_schema_is_not_ready():
    with TestClient(app_for(snapshot(storage_readable=False))) as client:
        assert client.get("/healthz").status_code == 503
        assert client.get("/healthz").json()["ready"] is False
    with TestClient(app_for(snapshot(schema_version=1))) as client:
        assert client.get("/healthz").status_code == 503


def test_healthz_answers_503_without_leaking_the_state_error():
    def broken():
        raise RuntimeError("cannot open /private/operator/wall.db")

    with TestClient(app_for(broken)) as client:
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"ready": False, "error": "live state is unavailable"}
    assert "private" not in response.text


def test_all_three_routes_are_operator_admitted(monkeypatch):
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
    with TestClient(app_for(snapshot())) as client:
        for path in ("/healthz", "/api/v3/readiness", "/api/v3/join-qr"):
            response = client.get(path)
            assert response.status_code == 403, path
            assert response.headers["Cache-Control"] == "no-store"


def test_proxy_credential_admits_the_operator_routes(monkeypatch):
    credential = "health-credential-0123456789"
    monkeypatch.setenv(media.OPERATOR_CREDENTIAL_ENV, credential)
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
    with TestClient(app_for(snapshot())) as client:
        headers = {media.CREDENTIAL_HEADER: credential}
        assert client.get("/healthz", headers=headers).status_code == 200
        assert client.get("/api/v3/readiness", headers=headers).status_code == 200


def test_readiness_has_the_exact_tablet_url_and_join_qr_route():
    with TestClient(app_for(snapshot())) as client:
        response = client.get("/api/v3/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["tablet_url"] == f"{TABLET}/client/"
    assert body["join_qr_url"] == "/api/v3/join-qr"
    assert body["wifi"] == {"name": "Wall-Lab", "known": True}
    assert body["security"]["uploads"] == "disabled"
    assert body["security"]["authentication"] == "disabled"
    assert body["content"]["available"] is True
    assert body["storage"]["database"]
    assert body["backup"]["recorded"] is False
    assert body["restore_rehearsal"]["recorded"] is False


def test_readiness_stays_answerable_when_live_state_fails():
    def broken():
        raise RuntimeError("state exploded")

    with TestClient(app_for(broken)) as client:
        response = client.get("/api/v3/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["content"]["type"] == "unknown"
    assert body["wall"]["generation"] is None
    assert body["errors"] == ["live state is unavailable"]
    assert body["tablet_url"] == f"{TABLET}/client/"


def test_join_qr_is_a_png_of_exactly_the_join_url():
    with TestClient(app_for(snapshot())) as client:
        response = client.get("/api/v3/join-qr")
        readiness = client.get("/api/v3/readiness").json()
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")

    decoded = zxingcpp.read_barcode(Image.open(io.BytesIO(response.content)))
    assert decoded is not None, "independent decoder found no QR code"
    assert decoded.format == zxingcpp.BarcodeFormat.QRCode
    assert decoded.text == readiness["tablet_url"]
    assert decoded.text == f"{TABLET}/client/"
    assert "@" not in decoded.text and "token" not in decoded.text.lower()


def test_join_qr_is_503_with_an_actionable_error_when_unconfigured():
    with TestClient(app_for(snapshot(), config(tablet_origin=None))) as client:
        response = client.get("/api/v3/join-qr")
    assert response.status_code == 503
    assert operability.TABLET_ORIGIN_ENV in response.json()["detail"]


def test_join_qr_does_not_use_the_operator_origin_or_a_query():
    settings = config(tablet_origin="http://10.42.0.9:9090")
    with TestClient(app_for(snapshot(), settings)) as client:
        png = client.get("/api/v3/join-qr").content
    decoded = zxingcpp.read_barcode(Image.open(io.BytesIO(png)))
    assert decoded.text == "http://10.42.0.9:9090/client/"


def test_healthz_and_readiness_are_cheap_enough_to_avoid_asset_resolution():
    calls: list[str] = []

    def resolve(asset_id):
        calls.append(asset_id)
        return True

    with TestClient(app_for(snapshot(), resolve=resolve)) as client:
        client.get("/healthz")
        assert calls == []
        client.get("/api/v3/readiness")
        assert calls == ["sha256:" + "a" * 64]
