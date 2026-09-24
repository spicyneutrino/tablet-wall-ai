"""Contract tests for the tablet-wall HTTP API.

These cover the behaviour the client and controller pages actually depend on.
The two placeholder endpoints (``POST /devices/{device_id}/color`` and
``GET /device/{device_id}``) are intentionally not tested here: they are stubs,
and pinning their current output would enshrine placeholder behaviour.
"""

from datetime import datetime, timedelta

import pytest


class TestRootAndStaticMounts:
    def test_root_returns_greeting(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello Tablet Wall"}

    @pytest.mark.parametrize(
        ("route", "expected_text"),
        [
            ("/client/", "This is Client Side"),
            ("/controller/", "This is controller side."),
        ],
    )
    def test_app_pages_are_served(self, client, route, expected_text):
        response = client.get(route)

        assert response.status_code == 200
        assert expected_text in response.text

    @pytest.mark.parametrize(
        "asset",
        [
            "/client/client.js",
            "/client/client.css",
            "/controller/controller.js",
            "/controller/controller.css",
        ],
    )
    def test_frontend_assets_are_reachable(self, client, asset):
        """Each page loads its script and stylesheet from the same mount."""
        response = client.get(asset)

        assert response.status_code == 200

    def test_unknown_route_returns_404(self, client):
        assert client.get("/nope").status_code == 404


class TestRegistration:
    def test_register_device_reports_success(self, client, device_payload):
        response = client.post("/devices/register", json=device_payload)

        assert response.status_code == 200
        assert response.json() == {
            "registered": True,
            "device": device_payload["device_id"],
        }

    def test_registered_device_appears_in_roster(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        roster = client.get("/devices").json()
        entry = roster[device_payload["device_id"]]

        assert entry["width"] == device_payload["width"]
        assert entry["height"] == device_payload["height"]
        assert entry["type"] == device_payload["device_type"]

    def test_registration_records_utc_last_seen(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        raw_last_seen = client.get("/devices").json()[device_payload["device_id"]]["last_seen"]
        last_seen = datetime.fromisoformat(raw_last_seen)

        assert last_seen.tzinfo is not None, "last_seen must be timezone-aware"
        assert last_seen.utcoffset() == timedelta(0), "last_seen must be UTC"

    def test_re_registration_updates_without_duplicating(self, client, device_payload):
        """A tablet that reloads re-registers with the same id."""
        client.post("/devices/register", json=device_payload)

        updated = {**device_payload, "width": 2048, "height": 1536}
        client.post("/devices/register", json=updated)

        roster = client.get("/devices").json()

        assert len(roster) == 1
        assert roster[device_payload["device_id"]]["width"] == 2048

    def test_empty_roster_returns_empty_object(self, client):
        assert client.get("/devices").json() == {}

    def test_get_register_endpoint_explains_post(self, client):
        response = client.get("/devices/register")

        assert response.status_code == 200
        assert response.json() == {"message": "Use POST to register a device"}


class TestRegistrationValidation:
    @pytest.mark.parametrize(
        "device_id",
        [
            "not-a-uuid",
            "",
            # A well-formed but non-v4 UUID: the schema asks specifically for v4.
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ],
    )
    def test_register_rejects_bad_device_id(self, client, device_payload, device_id):
        response = client.post(
            "/devices/register", json={**device_payload, "device_id": device_id}
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("missing", ["device_id", "width", "height", "device_type"])
    def test_register_rejects_missing_fields(self, client, device_payload, missing):
        payload = {key: value for key, value in device_payload.items() if key != missing}

        assert client.post("/devices/register", json=payload).status_code == 422

    def test_register_rejects_non_numeric_dimensions(self, client, device_payload):
        payload = {**device_payload, "width": "wide"}

        assert client.post("/devices/register", json=payload).status_code == 422

    def test_rejected_registration_leaves_roster_untouched(self, client, device_payload):
        client.post("/devices/register", json={**device_payload, "device_id": "bad"})

        assert client.get("/devices").json() == {}
