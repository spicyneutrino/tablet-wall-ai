"""Prospective operator ruler checks and immutable calibration saves."""

import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
from tabletwall import displays, media, persist
from tabletwall.calibration_health import check_ruler_scale
from tabletwall.routes.calibration_check import create_router

DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"
PATH = "/api/v3/calibration-check"


def body(**overrides):
    value = dict(device_id=DEVICE, profile_revision=1, quarter_turn=0, axis="x",
                 span_px=600, span_mm=120, span_error_mm=0.5,
                 usable_width_px=600, usable_height_px=800)
    return value | overrides


def save_profile(width=120, height=200):
    return displays.save_profile(
        DEVICE, active_width_mm=width, active_height_mm=height,
        bezels=dict(left=0, top=0, right=0, bottom=0), panel_pixels=None,
        label="supplied", provenance="model")


def test_revision_outside_sqlite_range_is_a_controlled_validation_error(operator):
    with persist._connection() as connection:
        before = list(connection.iterdump())
    response = operator.post("/api/v3/calibration-check", json=body(profile_revision=10**100))
    assert response.status_code == 422
    with persist._connection() as connection:
        assert list(connection.iterdump()) == before


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    monkeypatch.delenv(media.OPERATOR_CREDENTIAL_ENV, raising=False)
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "disabled")
    save_profile()
    app = FastAPI()
    app.include_router(create_router())
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("quarter", [0, 1, 2, 3])
def test_real_helper_with_exact_pinned_profile_and_native_axes(operator, axis, quarter):
    save_profile(999, 888)
    request = body(axis=axis, quarter_turn=quarter)
    result = operator.post(PATH, json=request)
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    value = result.json()
    width, height = (200, 120) if quarter % 2 else (120, 200)
    expected = check_ruler_scale(
        span_px=600, span_mm=120, span_error_mm=0.5, axis=axis,
        usable_width_px=600, usable_height_px=800,
        supplied_width_mm=width, supplied_height_mm=height)
    assert {key: value[key] for key in expected} == expected
    assert value["profile"]["revision"] == 1
    assert value["profile"]["active_width_mm"] == 120
    assert value["profile"]["native_axis"] == (
        ("height" if quarter % 2 else "width") if axis == "x"
        else ("width" if quarter % 2 else "height"))


def test_disagreement_has_choices_and_changes_nothing(operator):
    with persist._connection() as connection:
        before = list(connection.iterdump())
    result = operator.post(PATH, json=body(span_mm=150)).json()
    assert result["comparison"]["supplied_mm"] == 120
    assert result["comparison"]["implied_mm"] == 150
    assert result["derived"]["mm_per_css"] == 0.25
    assert result["extrapolated_uncertainty"]["measured_mm"] == 0.5
    assert result["decision"]["required"] is True
    assert {choice["id"] for choice in result["decision"]["choices"]} == {
        "keep_supplied", "use_ruler", "remeasure"}
    assert result["decision"]["saved"] is False
    with persist._connection() as connection:
        assert list(connection.iterdump()) == before


@pytest.mark.parametrize("changes", [
    {"span_px": 0}, {"span_mm": -1}, {"span_error_mm": -1},
    {"span_px": 601}, {"axis": "z"}, {"quarter_turn": 4},
    {"profile_revision": True}, {"span_mm": "120"}, {"span_error_mm": False},
    {"span_px": 10**100}, {"span_mm": 10**100},
    {"usable_width_px": 1000001}, {"device_id": "not-a-uuid"},
    {"profileRevision": 1}, {"supplied_width_mm": 999}, {"span_count": 2},
    {"viewport": {"width": 600, "height": 800}},
])
def test_strict_body_rejects_invalid_values_and_aliases(operator, changes):
    result = operator.post(PATH, json=body(**changes))
    assert result.status_code == 422, result.text
    assert "detail" in result.json()


@pytest.mark.parametrize("field", list(body()))
def test_all_fields_are_explicit(operator, field):
    request = body()
    request.pop(field)
    assert operator.post(PATH, json=request).status_code == 422


def test_missing_profile_is_explicit(operator):
    response = operator.post(PATH, json=body(profile_revision=9))
    assert response.status_code == 404
    assert "profile revision" in response.json()["detail"]


def test_operator_admission_is_independent_of_uploads(operator, monkeypatch):
    assert operator.post(PATH, json=body()).status_code == 200
    assert operator.post(PATH, json=body(), headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
    assert operator.post(PATH, json=body()).status_code == 403


def test_authenticated_operator_listener(operator, monkeypatch):
    monkeypatch.setenv(media.OPERATOR_CREDENTIAL_ENV, "fixture-credential")
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
    assert operator.post(PATH, json=body(), headers={media.CREDENTIAL_HEADER: "fixture-credential"}).status_code == 200
    assert operator.post(PATH, json=body(), headers={media.CREDENTIAL_HEADER: "wrong"}).status_code == 403


def test_main_origin_fence_applies_when_parent_mounts(operator, monkeypatch):
    app = FastAPI()
    app.middleware("http")(main.operator_origin_guard)
    app.include_router(create_router())
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", "http://127.0.0.1:9876")
    with TestClient(app) as client:
        for headers in [{}, {"Origin": "http://tablet.example"}]:
            assert client.post(PATH, json=body(), headers=headers).status_code == 403
        assert client.post(PATH, json=body(), headers={"Origin": "http://127.0.0.1:9876"}).status_code == 200


def test_ruler_save_appends_revision_without_changing_profile_or_layout_pins(operator, client):
    config = client.get("/api/v3/config").json()
    calibration = dict(profile_revision=1, viewport_width=600, viewport_height=800,
                       dpr=2, orientation=0, mode="fullscreen", quarter_turn=0,
                       panel_offset_mm=[0, 0], mm_per_css=[0.2, 0.25],
                       anchor_edge="top-left", uncertainty_mm=3, method="model")
    saved = client.put(f"/api/v3/calibrations/{DEVICE}", json=calibration,
                       headers={"If-Match": config["etag"]})
    assert saved.status_code == 200, saved.text
    first = saved.json()["calibration"]
    slot = dict(center_x_mm=60, center_y_mm=100, mount_angle=0, nudge_x_mm=0,
                nudge_y_mm=0, profile_revision=1, calibration_revision=first["revision"], participating=True)
    arranged = client.put("/api/v3/layout", json=dict(bounds=dict(x=0, y=0, width=120, height=200), slots={DEVICE: slot}),
                          headers={"If-Match": saved.json()["etag"]})
    assert arranged.status_code == 200, arranged.text
    archived = client.put("/api/v3/layouts/supplied-return-point", headers={"If-Match": arranged.json()["etag"]})
    assert archived.status_code == 200, archived.text
    saved_layout = persist.load_layout("supplied-return-point")
    before = copy.deepcopy(main.wall)
    profile = displays.profile(DEVICE, 1)
    checked = operator.post(PATH, json=body(span_mm=150)).json()
    calibration.update(mm_per_css=[checked["derived"]["mm_per_css"], 0.25], method="ruler-measured")
    etag = client.get("/api/v3/config").json()["etag"]
    saved = client.put(f"/api/v3/calibrations/{DEVICE}", json=calibration,
                       headers={"If-Match": etag})
    assert saved.status_code == 200, saved.text
    assert saved.json()["calibration"]["revision"] == first["revision"] + 1
    assert displays.calibration(DEVICE, first["revision"]) == first
    assert displays.profile(DEVICE, 1) == profile
    assert main.wall == before
    assert persist.load_layout("supplied-return-point") == saved_layout


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999", "9" * 400])
def test_nonfinite_and_overflow_inputs_are_explicit_errors(operator, value):
    import json

    raw = json.dumps(body()).replace('"span_mm": 120', '"span_mm": ' + value)
    response = operator.post(PATH, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert "detail" in response.json()


@pytest.mark.parametrize("raw", ["{", "null", "[]", '"string"'])
def test_malformed_or_nonobject_body(operator, raw):
    response = operator.post(PATH, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
