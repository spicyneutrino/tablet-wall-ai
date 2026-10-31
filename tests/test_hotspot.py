import argparse
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest

from deploy import hotspot


@pytest.fixture(autouse=True)
def isolated_runtime_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def args(**values):
    return argparse.Namespace(interface=None, data_dir=None, backend_port=None, tablet_port=None, **values)


def test_discovery_uses_access_point_instead_of_uplink_or_vpn(monkeypatch):
    def command(*argv):
        if argv[0] == "nmcli":
            return "uplink:wlan0\nhotspot:ap0\nvpn:tailscale0"
        assert argv == ("ip", "-j", "-4", "address", "show", "dev", "ap0")
        return json.dumps([{"addr_info": [{"local": "10.42.0.1", "scope": "global"}]}])

    def modes(argv, **kwargs):
        mode = "ap\n" if argv[-1] == "hotspot" else "infrastructure\n"
        return subprocess.CompletedProcess(argv, 0, stdout=mode, stderr="")

    monkeypatch.setattr(hotspot, "command", command)
    monkeypatch.setattr(hotspot.subprocess, "run", modes)
    assert hotspot.hotspot_address(None) == ("ap0", "10.42.0.1")
    with pytest.raises(ValueError, match="not an active NetworkManager hotspot"):
        hotspot.hotspot_address("wlan0")


def test_missing_hotspot_is_actionable(monkeypatch):
    monkeypatch.setattr(hotspot, "command", lambda *args: "")
    with pytest.raises(ValueError, match="Enable one hotspot"):
        hotspot.hotspot_address(None)


def test_saved_settings_rediscover_address_on_next_launch(tmp_path, monkeypatch):
    config = tmp_path / "hotspot.json"
    settings = hotspot.Settings("ap0", str(tmp_path / "wall"), 18000, 18080)
    config.write_text(json.dumps(hotspot.asdict(settings)))

    def discover(interface):
        assert interface == "ap0"
        return interface, "10.43.0.1"

    monkeypatch.setattr(hotspot, "hotspot_address", discover)
    loaded, address = hotspot.read_settings(config, args())
    assert loaded == settings
    assert address == "10.43.0.1"


@pytest.mark.parametrize("port", [0, -1, 65536, "8080", True])
def test_invalid_saved_ports_are_refused(tmp_path, monkeypatch, port):
    config = tmp_path / "hotspot.json"
    config.write_text(json.dumps({"tablet_port": port}))
    monkeypatch.setattr(hotspot, "hotspot_address", lambda _: ("ap0", "10.42.0.1"))
    with pytest.raises(ValueError, match="Ports must be integers"):
        hotspot.read_settings(config, args())


@pytest.mark.parametrize("already_open", [False, True])
def test_firewall_preserves_existing_rule_ownership(tmp_path, monkeypatch, already_open):
    mutations = []

    def command(*argv):
        if "--get-zone-of-interface=ap0" in argv:
            return "nm-shared"
        mutations.append(argv)
        return "success"

    monkeypatch.setattr(hotspot, "command", command)
    monkeypatch.setattr(hotspot.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0 if already_open else 1, "", ""))
    ownership = tmp_path / "firewall.json"
    hotspot.firewall_open("ap0", 8080, ownership)
    assert ownership.exists() is not already_open
    assert bool(mutations) is not already_open
    if mutations:
        assert mutations == [("firewall-cmd", "--zone=nm-shared", "--add-port=8080/tcp")]


def test_interrupted_firewall_change_is_recovered_before_reuse(tmp_path, monkeypatch):
    ownership = tmp_path / "firewall.json"
    ownership.write_text(json.dumps({"zone": "nm-shared", "port": 8080}))
    removed = []
    monkeypatch.setattr(hotspot, "command", lambda *argv: removed.append(argv))
    hotspot.recover_firewall(ownership)
    hotspot.recover_firewall(ownership)
    assert removed == [("firewall-cmd", "--zone=nm-shared", "--remove-port=8080/tcp")]
    assert not ownership.exists()


def test_occupied_port_does_not_touch_data_or_existing_server(tmp_path):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        settings = hotspot.Settings("ap0", str(tmp_path / "data"), server.getsockname()[1], 18080)
        with pytest.raises(RuntimeError, match="already in use"):
            hotspot.run(settings, "127.0.0.1", tmp_path / "hotspot.json")
        assert not (tmp_path / "data").exists()
        assert server.getsockname()[1] == settings.backend_port


def test_different_configs_cannot_share_firewall_port(tmp_path, monkeypatch):
    runtime = tmp_path / "tablet-wall-ai"
    runtime.mkdir()
    port_path = runtime / "hotspot-18080.lock"
    with port_path.open("a") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def unexpected_run(*args):
            pytest.fail("The second launcher reached firewall setup")
        monkeypatch.setattr(hotspot, "_run", unexpected_run)
        with pytest.raises(RuntimeError, match="already owns this tablet port"):
            hotspot.run(hotspot.Settings("ap1", str(tmp_path / "other-data"), 18001, 18080),
                        "10.43.0.1", tmp_path / "other-config.json")


def test_occupied_port_does_not_remove_a_firewall_rule(tmp_path, monkeypatch):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        def unexpected_recovery(*args):
            pytest.fail("An occupied port must not trigger firewall recovery")
        monkeypatch.setattr(hotspot, "recover_firewall", unexpected_recovery)
        settings = hotspot.Settings("ap0", str(tmp_path / "data"), server.getsockname()[1], 18080)
        with pytest.raises(RuntimeError, match="already in use"):
            hotspot.run(settings, "127.0.0.1", tmp_path / "hotspot.json")


def test_recently_closed_port_can_restart(tmp_path, monkeypatch):
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen()
        client = socket.create_connection(("127.0.0.1", port))
        accepted, _ = server.accept()
        accepted.close()
        client.close()
    monkeypatch.setattr(hotspot.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, "", ""))

    def firewall(*args):
        raise RuntimeError("Reached firewall setup after port checks")

    monkeypatch.setattr(hotspot, "firewall_open", firewall)
    settings = hotspot.Settings("ap0", str(tmp_path / "data"), port, free_port())
    with pytest.raises(RuntimeError, match="Reached firewall setup"):
        hotspot.run(settings, "127.0.0.1", tmp_path / "hotspot.json")


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


@pytest.mark.skipif(shutil.which("caddy") is None, reason="Caddy is not installed")
def test_real_launcher_checks_persists_restarts_and_cleans_up(tmp_path):
    backend_port, tablet_port = free_port(), free_port()
    data = tmp_path / "data"
    config = tmp_path / "hotspot.json"
    removed = tmp_path / "firewall-removed"
    settings = hotspot.Settings("ap-test", str(data), backend_port, tablet_port)
    code = f'''
from pathlib import Path
from deploy import hotspot
hotspot.firewall_open = lambda interface, port, ownership: ownership.write_text('{{"zone":"test-zone","port":' + str(port) + '}}')
hotspot.command = lambda *args: Path({str(removed)!r}).write_text(" ".join(args))
hotspot.run(hotspot.Settings(**{hotspot.asdict(settings)!r}), "127.0.0.1", Path({str(config)!r}))
'''
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("TABLET_WALL_", "WALL_"))}
    operator = f"http://127.0.0.1:{backend_port}"
    tablet = f"http://127.0.0.1:{tablet_port}"
    for iteration in range(2):
        config.unlink(missing_ok=True)
        with (tmp_path / "launcher.log").open("w") as output:
            process = subprocess.Popen([sys.executable, "-c", code], cwd=hotspot.ROOT,
                                       env=env, stdout=output, stderr=output)
            try:
                deadline = time.monotonic() + 20
                while not config.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.1)
                assert config.exists(), (tmp_path / "launcher.log").read_text() + (data / "caddy.log").read_text()
                assert json.loads(config.read_text()) == hotspot.asdict(settings)
                assert "Ready." in (tmp_path / "launcher.log").read_text()
                redirect = httpx.get(tablet + "/client", follow_redirects=False)
                assert redirect.status_code == 308
                assert redirect.headers["location"] == "/client/"
                assert httpx.get(tablet + "/client", follow_redirects=True).status_code == 200
                assert httpx.get(tablet + "/client/?calibrate=1").status_code == 200
                assert httpx.get(tablet + "/client/ruler.js").status_code == 200
                assert httpx.get(tablet + "/controller/").status_code == 403
                if iteration == 0:
                    changed = httpx.put(operator + "/wall", json={"width": 2345, "height": 1234},
                                        headers={"Origin": operator})
                    assert changed.status_code == 200, changed.text
                else:
                    assert httpx.get(operator + "/wall").json()["width"] == 2345
            finally:
                process.terminate()
                process.wait(timeout=15)
        assert process.returncode == 0
        assert removed.read_text() == f"firewall-cmd --zone=test-zone --remove-port={tablet_port}/tcp"
        for port in (backend_port, tablet_port):
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", port)) != 0
