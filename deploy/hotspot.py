"""Run the tablet-only HTTP ingress on an active NetworkManager hotspot."""

import argparse
import base64
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from deploy import log_rotation


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    interface: str
    data_dir: str
    backend_port: int = 8000
    tablet_port: int = 8080


def command(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def hotspot_address(interface: str | None) -> tuple[str, str]:
    active = command("nmcli", "-t", "-f", "UUID,DEVICE", "connection", "show", "--active")
    candidates = []
    for line in active.splitlines():
        uuid, device = line.split(":", 1)
        result = subprocess.run(
            ["nmcli", "-g", "802-11-wireless.mode", "connection", "show", uuid],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip() == "ap":
            candidates.append(device)
    if interface:
        if interface not in candidates:
            raise ValueError(f"{interface} is not an active NetworkManager hotspot. Enable the hotspot first.")
    elif len(candidates) == 1:
        interface = candidates[0]
    else:
        raise ValueError("Enable one hotspot, or select an active hotspot with --interface.")
    records = json.loads(command("ip", "-j", "-4", "address", "show", "dev", interface))
    addresses = [entry["local"] for record in records for entry in record["addr_info"]
                 if entry.get("scope") == "global"]
    if len(addresses) != 1:
        raise ValueError(f"{interface} must have exactly one IPv4 address.")
    address = ipaddress.IPv4Address(addresses[0])
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError(f"{interface} must have a private hotspot IPv4 address.")
    return interface, str(address)


def hotspot_name(interface: str) -> str | None:
    """The SSID NetworkManager reports for this access point, or unknown.

    Discovered once per launch, never per API read. A missing SSID is not a
    startup failure: the readiness card says unknown instead of guessing.
    """
    try:
        active = command("nmcli", "-t", "-f", "UUID,DEVICE", "connection", "show", "--active")
        for line in active.splitlines():
            uuid, _, device = line.partition(":")
            if device != interface:
                continue
            name = command(
                "nmcli", "-g", "802-11-wireless.ssid", "connection", "show", uuid
            ).strip()
            if name and len(name) <= 64 and name.isprintable():
                return name
            return None
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None
    return None


def read_settings(path: Path, args: argparse.Namespace) -> tuple[Settings, str]:
    saved = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(saved, dict):
        raise ValueError(f"{path} must contain a settings object.")
    interface, address = hotspot_address(args.interface or saved.get("interface"))
    default_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "tablet-wall-ai"
    settings = Settings(
        interface=interface,
        data_dir=str(Path(args.data_dir or saved.get("data_dir", default_data)).expanduser().resolve()),
        backend_port=args.backend_port if args.backend_port is not None else saved.get("backend_port", 8000),
        tablet_port=args.tablet_port if args.tablet_port is not None else saved.get("tablet_port", 8080),
    )
    for port in (settings.backend_port, settings.tablet_port):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Ports must be integers between 1024 and 65535.")
    if settings.backend_port == settings.tablet_port:
        raise ValueError("The backend and tablet ports must differ.")
    return settings, address


def proxy_config(address: str, port: int) -> str:
    rules = json.dumps(str(ROOT / "deploy/tablet-routes.caddy"))
    return f'''{{
    admin off
    auto_https off
    persist_config off
    grace_period 2s
}}
http://{address}:{port} {{
    bind {address}
    import {rules}
}}
'''


def recover_firewall(ownership_path: Path) -> None:
    if not ownership_path.exists():
        return
    owned = json.loads(ownership_path.read_text())
    command("firewall-cmd", f"--zone={owned['zone']}", f"--remove-port={owned['port']}/tcp")
    ownership_path.unlink()


def firewall_open(interface: str, port: int, ownership_path: Path) -> None:
    zone = command("firewall-cmd", f"--get-zone-of-interface={interface}")
    if not zone or zone == "no zone":
        raise ValueError(f"{interface} has no firewalld zone. Assign its hotspot zone first.")
    result = subprocess.run(
        ["firewall-cmd", f"--zone={zone}", f"--query-port={port}/tcp"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Cannot query the hotspot firewall.")
    if result.returncode == 0:
        return
    save_json(ownership_path, {"zone": zone, "port": port})
    command("firewall-cmd", f"--zone={zone}", f"--add-port={port}/tcp")


def http_request(origin: str, path: str, method: str = "GET", body: str | None = None):
    url = urlsplit(origin)
    connection = http.client.HTTPConnection(str(url.hostname), url.port, timeout=2)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def startup_checks(tablet: str, operator: str) -> None:
    status, _, data = http_request(operator, "/operator-config")
    if status != 200 or json.loads(data).get("tablet_origin") != tablet:
        raise RuntimeError("The controller does not advertise the hotspot origin.")
    for path in ("/client/", "/client/client.js", "/client/client.css", "/client/view.js"):
        status, _, data = http_request(tablet, path)
        if status != 200 or not data:
            raise RuntimeError(f"Tablet page check failed: {path} returned {status}.")
    status, headers, _ = http_request(tablet, "/client")
    if status != 308 or headers.get("Location") != "/client/":
        raise RuntimeError("The /client to /client/ redirect is missing.")
    status, _, _ = http_request(tablet, "/devices/register", "POST", "{}")
    if status != 422:
        raise RuntimeError(f"Registration check returned {status}, expected payload validation.")
    for path in ("/controller/", "/wall", "/devices", "/ws/controller", "/docs"):
        status, _, _ = http_request(tablet, path)
        if status != 403:
            raise RuntimeError(f"The tablet listener exposes an operator route: {path}.")
    url = urlsplit(tablet)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        "GET /ws/device?device_id=00000000-0000-4000-8000-000000000001&protocol=2 HTTP/1.1\r\n"
        f"Host: {url.netloc}\r\nOrigin: {tablet}\r\nConnection: Upgrade\r\n"
        f"Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n"
    )
    with socket.create_connection((str(url.hostname), url.port or 80), timeout=3) as connection:
        connection.sendall(request.encode())
        reply = b""
        while b"\r\n\r\n" not in reply and len(reply) < 8192:
            chunk = connection.recv(4096)
            if not chunk:
                break
            reply += chunk
    expected = base64.b64encode(hashlib.sha1(
        (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
    ).digest())
    if b" 101 " not in reply.split(b"\r\n", 1)[0] or expected not in reply:
        raise RuntimeError("The tablet WebSocket upgrade failed.")


def check_servers(children: list[subprocess.Popen[bytes]], logs: tuple[log_rotation.LogPump, ...]) -> None:
    for log in logs:
        log.check()
    if any(child.poll() is not None for child in children):
        raise RuntimeError("A server stopped. See backend.log and caddy.log.")


def wait_for(origin: str, children: list[subprocess.Popen[bytes]], stopped: threading.Event,
             logs: tuple[log_rotation.LogPump, ...] = ()) -> None:
    deadline = time.monotonic() + 20
    while not stopped.is_set() and time.monotonic() < deadline:
        check_servers(children, logs)
        try:
            http_request(origin, "/client/")
            return
        except (OSError, http.client.HTTPException):
            stopped.wait(.1)
    raise RuntimeError("Startup stopped or timed out. See backend.log and caddy.log.")


def run(settings: Settings, address: str, config_path: Path,
        wifi_name: str | None = None) -> None:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache")) / "tablet-wall-ai"
    runtime.mkdir(parents=True, exist_ok=True)
    port_path = runtime / f"hotspot-{settings.tablet_port}"
    with port_path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A hotspot launcher already owns this tablet port.") from None
        _run(settings, address, config_path, port_path.with_suffix(".firewall.json"), wifi_name)


def preflight(settings: Settings, address: str, wifi_name: str | None) -> None:
    """Print the settings this launch will actually use, before it binds."""
    tablet = f"http://{address}:{settings.tablet_port}/client/"
    operator = f"http://127.0.0.1:{settings.backend_port}"
    print(f"Preflight: interface {settings.interface}; hotspot address {address}\n"
          f"  Tablet URL: {tablet}\n"
          f"  Controller (this computer only): {operator}/controller/physical.html\n"
          f"  Wi-Fi network: {wifi_name or 'unknown'}\n"
          f"  Data and logs: {settings.data_dir} "
          "(wall.db, assets/, media/, backend.log, caddy.log)\n"
          "  Security: HTTP trusted-hotspot trial; app authentication unset; "
          "managed uploads disabled; not safe on shared or venue Wi-Fi.",
          flush=True)


def spawn_logged(argv: list[str], env: dict[str, str],
                 log: log_rotation.LogPump) -> subprocess.Popen[bytes]:
    """Start a child whose stdout and stderr flow through one bounded log."""
    child = subprocess.Popen(
        argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if child.stdout is None:
        raise RuntimeError("Could not capture the server's output.")
    log.attach(child.stdout)
    return child


def stop_children(children: list[subprocess.Popen[bytes]]) -> None:
    """Terminate children before their log pipes are joined.

    Joining a reader first would wait for a live child's pipe to reach EOF and
    turn every stop into a timeout. Killing is idempotent, so the outer cleanup
    can call this again for a launch that failed before the log block.
    """
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def readiness_summary(operator: str) -> dict | None:
    """The readiness projection when the app mounts it; otherwise unknown."""
    try:
        status, _, data = http_request(operator, "/api/v3/readiness")
        if status != 200:
            return None
        value = json.loads(data)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return value if isinstance(value, dict) else None


def _run(settings: Settings, address: str, config_path: Path, ownership_path: Path,
         wifi_name: str | None = None) -> None:
    tablet = f"http://{address}:{settings.tablet_port}"
    operator = f"http://127.0.0.1:{settings.backend_port}"
    for host, port in (("127.0.0.1", settings.backend_port), (address, settings.tablet_port)):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError as error:
                raise RuntimeError(f"{host}:{port} is already in use. Stop its existing server first.") from error
    recover_firewall(ownership_path)
    recover_firewall(config_path.with_suffix(".firewall.json"))
    data = Path(settings.data_dir)
    for path in (data, data / "assets", data / "media"):
        path.mkdir(parents=True, exist_ok=True)
    proxy_path = config_path.with_suffix(".Caddyfile")
    proxy_path.write_text(proxy_config(address, settings.tablet_port))
    env = {
        **os.environ,
        "TABLET_WALL_DB": str(data / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(data / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(data / "media"),
        "TABLET_WALL_TABLET_ORIGIN": tablet,
        "TABLET_WALL_OPERATOR_ORIGIN": operator,
        "WALL_BACKEND_PORT": str(settings.backend_port),
    }
    if wifi_name:
        env["TABLET_WALL_WIFI_NAME"] = wifi_name
    caddy = os.environ.get("CADDY_BIN", "caddy")
    validation = subprocess.run(
        [caddy, "validate", "--config", str(proxy_path), "--adapter", "caddyfile"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    if validation.returncode:
        raise RuntimeError(f"Caddy configuration failed validation: {validation.stderr.strip()}")
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    children: list[subprocess.Popen[bytes]] = []
    try:
        firewall_open(settings.interface, settings.tablet_port, ownership_path)
        with log_rotation.LogPump(data / "backend.log") as backend_log, \
                log_rotation.LogPump(data / "caddy.log") as proxy_log:
            try:
                children.append(spawn_logged(
                    [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                     "--port", str(settings.backend_port)],
                    env, backend_log,
                ))
                wait_for(operator, children, stopped, (backend_log, proxy_log))
                children.append(spawn_logged(
                    [caddy, "run", "--config", str(proxy_path), "--adapter", "caddyfile"],
                    env, proxy_log,
                ))
                wait_for(tablet, children, stopped, (backend_log, proxy_log))
                startup_checks(tablet, operator)
                save_json(config_path, asdict(settings))
                readiness = readiness_summary(operator)
                print(f"Ready. Tablet page, redirect, registration, WebSocket, and route restrictions passed.\n"
                      f"Tablets on {settings.interface}: {tablet}/client/\n"
                      f"Controller on this computer only: {operator}/controller/physical.html\n"
                      f"Wi-Fi network: {wifi_name or 'unknown'}\n"
                      f"Data and logs: {data}\nSettings: {config_path}\n"
                      "HTTP trial: keep tablet screens awake manually. Press Ctrl+C to stop.", flush=True)
                if readiness is None:
                    print("Content readiness: unknown (the readiness endpoint is not mounted).",
                          flush=True)
                else:
                    content = readiness.get("content")
                    summary = content.get("summary") if isinstance(content, dict) else None
                    backup = readiness.get("backup")
                    rehearsal = readiness.get("restore_rehearsal")
                    last_backup = (
                        backup.get("last_manifest_at") if isinstance(backup, dict) else None
                    )
                    last_rehearsal = (
                        rehearsal.get("completed_utc")
                        if isinstance(rehearsal, dict) else None
                    )
                    print(f"Content: {summary or 'unknown'}\n"
                          f"Backup: {last_backup or 'unknown (set TABLET_WALL_BACKUP_DIR)'}\n"
                          f"Restore rehearsal: {last_rehearsal or 'not recorded'}\n"
                          f"Readiness card: {operator}/api/v3/readiness\n"
                          f"Join QR (local image): {operator}/api/v3/join-qr", flush=True)
                while not stopped.wait(.5):
                    check_servers(children, (backend_log, proxy_log))
            finally:
                # Stop writers before the log readers are joined, so a normal
                # stop reaches EOF instead of waiting on a live pipe.
                stop_children(children)
    finally:
        stop_children(children)
        try:
            recover_firewall(ownership_path)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"Could not remove the temporary firewall rule: {error}", file=sys.stderr)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", help="active hotspot interface; discovered on first launch")
    parser.add_argument("--data-dir", help="persistent database, assets, media, and logs directory")
    parser.add_argument("--backend-port", type=int)
    parser.add_argument("--tablet-port", type=int)
    default_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tablet-wall-ai/hotspot.json"
    parser.add_argument("--config", type=Path, default=default_config)
    args = parser.parse_args()
    try:
        for executable in ("nmcli", "ip", "firewall-cmd", os.environ.get("CADDY_BIN", "caddy")):
            if shutil.which(executable) is None:
                raise ValueError(f"Install {executable} before running make hotspot.")
        if os.environ.get("TABLET_WALL_AUTH_TOKEN") or os.environ.get("TABLET_WALL_UPLOAD_MODE", "disabled") != "disabled":
            raise ValueError("This HTTP trial needs authentication unset and uploads disabled. Use the HTTPS deployment for authenticated operation.")
        config_path = args.config.expanduser().resolve()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.with_suffix(".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("This hotspot launcher is already running.") from None
            settings, address = read_settings(config_path, args)
            wifi_name = os.environ.get("TABLET_WALL_WIFI_NAME") or hotspot_name(settings.interface)
            preflight(settings, address, wifi_name)
            run(settings, address, config_path, wifi_name)
        return 0
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError, http.client.HTTPException) as error:
        print(f"Hotspot startup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
