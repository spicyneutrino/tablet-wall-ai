"""Configured deployments reject foreign Host headers before route admission."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", "https://operator.wall.test:8444")
    monkeypatch.setenv("TABLET_WALL_TABLET_ORIGIN", "http://10.42.0.1:8080")


@pytest.mark.parametrize("host", ["operator.wall.test:8444", "10.42.0.1:8080",
    "127.0.0.1:8000", "localhost:8000", "[::1]:8000", "LOCALHOST.:8000"])
def test_configured_origins_and_loopback_hosts_are_admitted(configured, host):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert client.get("/operator-config", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("path", ["/api/v3/readiness", "/api/v3/config", "/diagnostics",
    "/wall", "/client/"])
def test_foreign_host_cannot_read_a_configured_loopback_backend(configured, path):
    with TestClient(main.app, base_url="http://rebind.attacker.invalid:8000",
                    client=("127.0.0.1", 50000)) as client:
        response = client.get(path)
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "storage" not in response.text and "attacker" not in response.text


@pytest.mark.parametrize("hosts", [[""], ["127.0.0.1", "operator.wall.test"],
    ["127.0.0.1@evil.invalid"], ["evil@127.0.0.1"], ["127.0.0.1/path"],
    ["127.0.0.1#evil"], ["127.0.0.1:999999"], [" 127.0.0.1"], ["127.0.0.1\t"]])
def test_malformed_or_ambiguous_host_is_refused(configured, hosts):
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        request = client.build_request("GET", "/operator-config")
        del request.headers["host"]
        request.headers.update([("host", host) for host in hosts])
        assert client.send(request).status_code == 400


def test_foreign_host_is_refused_before_device_socket_accept(configured):
    with TestClient(main.app, base_url="http://rebind.attacker.invalid") as client:
        with pytest.raises(WebSocketDisconnect) as caught:
            with client.websocket_connect("/ws/device?protocol=3"):
                pytest.fail("foreign Host must not upgrade")
    assert caught.value.code == 1008


def test_unconfigured_development_keeps_existing_host_behavior():
    with TestClient(main.app, base_url="http://development.test") as client:
        assert client.get("/operator-config").status_code == 200
