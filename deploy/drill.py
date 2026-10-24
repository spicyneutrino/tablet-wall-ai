"""Backup and recovery drill on a throwaway instance (Phase 3b / R5).

Boots a populated instance on temporary paths and a free loopback port, takes
a verified snapshot with ``deploy/backup.py`` while it runs, stops it, restores
into brand-new targets, boots the restored copy and compares what an operator
cares about: the wall, saved layouts and scenes, the playlist, the managed
media library and the bytes behind every image. It then re-registers the
tablets with the numbers they remember, as real tablets do after a restart.

    uv run python deploy/drill.py

It never touches the configured database, never binds port 8000 and removes
its temp directory. Exit 0 means every check passed; 1 prints each failure.

What it does not prove: the roster and display numbers are memory-only, so the
backup carries neither (tablets re-send their number; this checks that the
restored server honours it and that placements are still attached). It does
not exercise a real host, TLS, a real tablet, or elapsed time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_ORIGIN = "https://operator.drill.test:8444"
TABLETS = {  # device id -> (display number, wall x)
    "0f8fad5b-d9cb-469f-a165-70867728950e": (1, 0),
    "1f8fad5b-d9cb-469f-a165-70867728950e": (2, 1000),
    "2f8fad5b-d9cb-469f-a165-70867728950e": (3, 2000),
}

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def jpeg(colour: tuple[int, int, int], size: tuple[int, int] = (96, 64)) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


class Instance:
    """One uvicorn process on loopback, bound to the given data paths."""

    def __init__(self, db: Path, assets: Path, media: Path) -> None:
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = {
            **os.environ,
            "TABLET_WALL_DB": str(db),
            "TABLET_WALL_ASSET_DIR": str(assets),
            "TABLET_WALL_MEDIA_DIR": str(media),
            "TABLET_WALL_UPLOAD_MODE": "loopback",
            "TABLET_WALL_OPERATOR_ORIGIN": OPERATOR_ORIGIN,
        }
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--no-access-log"],
            cwd=ROOT, env=self.env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("the instance exited during startup")
            try:
                self.request("GET", "/wall")
                return
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        raise RuntimeError("the instance did not become ready")

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    def request(self, method: str, path: str, body=None, raw: bytes | None = None,
                headers: dict[str, str] | None = None):
        """``(status, parsed JSON or raw bytes)``; HTTP errors are returned."""
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        sent = dict(headers or {})
        if method != "GET":
            sent["Origin"] = OPERATOR_ORIGIN
        if body is not None:
            sent["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=sent)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        try:
            return status, json.loads(payload)
        except ValueError:
            return status, payload


def must(response, expected: int, what: str):
    status, payload = response
    if status != expected:
        raise RuntimeError(f"{what}: HTTP {status} {payload!r}")
    return payload


def populate(instance: Instance, assets: Path) -> dict:
    """Seed the wall the way an operator would; return the expected state."""
    api = instance.request
    uploads = {}
    for name, colour in (("active", (200, 40, 40)), ("saved", (40, 200, 40)),
                         ("playlist-only", (40, 40, 200)), ("unused", (200, 200, 40))):
        reply = must(
            api("POST", f"/uploads?name={name}.jpg", raw=jpeg(colour),
                headers={"Content-Type": "image/jpeg"}),
            201, f"upload {name}",
        )
        uploads[name] = reply["asset"]
    (assets / "curated.jpg").write_bytes(jpeg((120, 60, 180), (128, 64)))
    curated = must(api("GET", "/assets"), 200, "inventory")["assets"][0]

    for device_id, (number, x) in TABLETS.items():
        must(api("POST", "/devices/register", {
            "device_id": device_id, "width": 800, "height": 600,
            "device_type": "ipad", "number": number,
        }), 200, "register")
        must(api("PUT", f"/devices/{device_id}/placement", {
            "x": x, "y": 0, "w": 1000, "h": 1000,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }), 200, "place")
    must(api("PUT", "/wall", {"width": 3000, "height": 1000}), 200, "wall size")
    must(api("PUT", "/layouts/lobby"), 200, "save layout")

    for name, asset in (("curated-scene", curated), ("managed-scene", uploads["saved"])):
        must(api("PUT", "/scene", {"content": {"type": "image", "asset": asset["id"], "fit": "cover"}}),
             200, f"scene {name}")
        must(api("PUT", f"/scenes/{name}"), 200, f"save {name}")
    must(api("PUT", "/scene", {"content": {"type": "image", "asset": uploads["active"]["id"], "fit": "cover"}}),
         200, "active scene")

    etag = must(api("GET", "/api/v3/playlist"), 200, "playlist")["etag"]
    must(api("PUT", "/api/v3/playlist", {
        "items": [{"asset": uploads["playlist-only"]["id"], "dwell_ms": 1500},
                  {"asset": uploads["active"]["id"], "dwell_ms": 2500}],
        "loop": True,
    }, headers={"If-Match": etag}), 200, "save playlist")

    return {
        "uploads": uploads,
        "curated": curated,
        "snapshot": observe(instance),
    }


def observe(instance: Instance) -> dict:
    """Everything the drill compares between the source and the restored copy."""
    api = instance.request
    wall = must(api("GET", "/wall"), 200, "wall")
    wall.pop("generation")  # minted fresh on every start, by design
    library = must(api("GET", "/media"), 200, "library")["assets"]
    return {
        "wall": wall,
        "layouts": must(api("GET", "/layouts"), 200, "layouts"),
        "scenes": must(api("GET", "/scenes"), 200, "scenes"),
        "playlist": must(api("GET", "/api/v3/playlist"), 200, "playlist")["playlist"],
        "library": sorted((entry["asset_id"], entry["name"], entry["bytes"], entry["id"])
                          for entry in library),
    }


def served_sha(instance: Instance, asset_id: str):
    status, payload = instance.request("GET", f"/assets/{asset_id}")
    return status, (None if status != 200 else "sha256:" + hashlib.sha256(payload).hexdigest())


def run_tool(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("TABLET_WALL_DB", "TABLET_WALL_ASSET_DIR", "TABLET_WALL_MEDIA_DIR")}
    return subprocess.run(
        [sys.executable, str(ROOT / "deploy" / "backup.py"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


def drill(work: Path) -> None:
    source_assets = work / "source" / "assets"
    source_assets.mkdir(parents=True)
    source = Instance(work / "source" / "wall.db", source_assets, work / "source" / "media")
    restored: Instance | None = None
    try:
        print("1. populate a source instance")
        source.start()
        expected = populate(source, source_assets)
        uploads, curated = expected["uploads"], expected["curated"]
        wanted = {
            "active": uploads["active"], "saved": uploads["saved"],
            "playlist-only": uploads["playlist-only"],
        }
        original_bytes = {}
        for name, asset in {**wanted, "curated": curated}.items():
            status, sha = served_sha(source, asset["id"])
            original_bytes[name] = sha
            check(status == 200 and sha == asset["id"], f"source serves {name} with matching bytes")

        print("2. back up while it runs, then verify")
        began = time.monotonic()
        snapshot = work / "snapshot"
        done = run_tool("backup", "--db", str(work / "source" / "wall.db"),
                        "--assets", str(source_assets), "--media", str(work / "source" / "media"),
                        "--dest", str(snapshot))
        check(done.returncode == 0, f"backup exits 0 ({done.stderr.strip() or 'ok'})")
        done = run_tool("verify", "--src", str(snapshot))
        check(done.returncode == 0, f"verify exits 0 ({done.stderr.strip() or 'ok'})")
        manifest = json.loads((snapshot / "manifest.json").read_text())
        check(uploads["playlist-only"]["id"] in manifest["references"],
              "the playlist-only upload is in the snapshot closure")
        check(len(manifest["omitted_media"]) == 1, "only the unused upload is omitted")
        source.stop()

        print("3. restore into new targets (service stopped)")
        target = work / "restored"
        target.mkdir()
        done = run_tool("restore", "--src", str(snapshot), "--db", str(target / "wall.db"),
                        "--assets", str(target / "assets"), "--media", str(target / "media"))
        check(done.returncode == 0, f"restore exits 0 ({done.stderr.strip() or 'ok'})")
        again = run_tool("restore", "--src", str(snapshot), "--db", str(target / "wall.db"),
                         "--assets", str(target / "assets"), "--media", str(target / "media"))
        check(again.returncode == 1, "restore refuses to overwrite existing targets")

        print("4. boot the restored copy and compare")
        restored = Instance(target / "wall.db", target / "assets", target / "media")
        restored.start()
        seen = observe(restored)
        before = expected["snapshot"]
        check(seen["wall"] == before["wall"], "wall (size, placements, scene, revision) is identical")
        check(seen["layouts"] == before["layouts"], "saved layouts are identical")
        check(seen["scenes"] == before["scenes"], "saved scenes are identical")
        check(seen["playlist"] == before["playlist"], "playlist is identical")
        omitted = uploads["unused"]
        check(seen["library"] == [row for row in before["library"] if row[0] != omitted["asset_id"]],
              "library is the source library minus the deliberately omitted upload")
        for name, asset in {**wanted, "curated": curated}.items():
            status, sha = served_sha(restored, asset["id"])
            check(status == 200 and sha == original_bytes[name], f"restored bytes of {name} match the source")
        thumb = uploads["active"]["thumbnail"]["id"]
        check(served_sha(restored, thumb)[0] == 200, "a restored rendition (thumbnail) is served")
        check(served_sha(restored, omitted["id"])[0] == 404, "the omitted upload is not served")
        check(restored.request("GET", "/devices")[1] == {}, "the roster starts empty (it is memory-only)")

        print("5. tablets re-register with the numbers they remember")
        for device_id, (number, _x) in TABLETS.items():
            must(restored.request("POST", "/devices/register", {
                "device_id": device_id, "width": 800, "height": 600,
                "device_type": "ipad", "number": number,
            }), 200, "re-register")
        roster = restored.request("GET", "/devices")[1]
        placements = restored.request("GET", "/wall")[1]["placements"]
        for device_id, (number, x) in TABLETS.items():
            check(roster[device_id]["number"] == number, f"tablet {number} keeps its number")
            check(placements.get(device_id, {}).get("x") == x, f"tablet {number} keeps its placement")
        print(f"   backup, restore and boot took {time.monotonic() - began:.1f}s")
    finally:
        source.stop()
        if restored is not None:
            restored.stop()


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="tablet-wall-drill-"))
    try:
        drill(work)
    except Exception as error:  # a seeding or boot failure is a failed drill
        failures.append(f"drill aborted: {error}")
        print(f"FAIL drill aborted: {error}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("\ndrill passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
