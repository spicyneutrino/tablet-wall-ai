"""Ruler calibration saves are tied to the selected tablet's live viewport."""

import pytest


DEVICE = "10000000-0000-4000-8000-000000000001"


def measured_profile(client):
    client.post("/devices/register", json={
        "device_id": DEVICE, "width": 600, "height": 800, "device_type": "fixture",
    }).raise_for_status()
    config = client.get("/api/v3/config").json()
    response = client.put(f"/api/v3/displays/{DEVICE}", headers={"If-Match": config["etag"]}, json={
        "active_width_mm": 120, "active_height_mm": 160,
        "bezels": {"top": 0, "left": 0, "right": 0, "bottom": 0},
        "label": "fixture", "provenance": "ruler fixture",
    })
    response.raise_for_status()
    return response.json()["etag"]


def ruler_calibration():
    return {
        "profile_revision": 1, "viewport_width": 600, "viewport_height": 800,
        "dpr": 2, "orientation": 0, "mode": "tab", "quarter_turn": 0,
        "panel_offset_mm": [0, 0], "mm_per_css": [.2, .2],
        "anchor_edge": "top-left", "uncertainty_mm": .5,
        "method": "ruler-measured", "viewport_guard": True,
    }


def test_ruler_save_refuses_offline_tablet_without_creating_calibration(client):
    etag = measured_profile(client)
    response = client.put(f"/api/v3/calibrations/{DEVICE}", json=ruler_calibration(),
                          headers={"If-Match": etag})
    assert response.status_code == 409
    assert client.get("/api/v3/config").json()["calibrations"] == []


@pytest.mark.parametrize("change", [{"viewport_width": 1440}, {"dpr": 1}, {"mode": "fullscreen"}])
def test_ruler_save_refuses_controller_metrics_or_changed_tablet(client, change):
    etag = measured_profile(client)
    url = f"/ws/device?device_id={DEVICE}&protocol=3&w=600&h=800&dpr=2&orientation=0&mode=tab"
    with client.websocket_connect(url):
        body = {**ruler_calibration(), **change}
        response = client.put(f"/api/v3/calibrations/{DEVICE}", json=body,
                              headers={"If-Match": etag})
        assert response.status_code == 409
        assert client.get("/api/v3/config").json()["calibrations"] == []


def test_ruler_save_matches_tablet_instead_of_controller_and_keeps_manual_compatibility(client):
    etag = measured_profile(client)
    url = f"/ws/device?device_id={DEVICE}&protocol=3&w=600&h=800&dpr=2&orientation=0&mode=tab"
    with client.websocket_connect(url):
        response = client.put(f"/api/v3/calibrations/{DEVICE}", json=ruler_calibration(),
                              headers={"If-Match": etag})
        assert response.status_code == 200, response.text
        assert response.json()["calibration"]["viewport_width"] == 600
        assert response.json()["calibration"]["dpr"] == 2
        etag = response.json()["etag"]
    body = ruler_calibration()
    body.pop("viewport_guard")
    response = client.put(f"/api/v3/calibrations/{DEVICE}", json=body,
                          headers={"If-Match": etag})
    assert response.status_code == 200, response.text
