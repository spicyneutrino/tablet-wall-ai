"""WAN-disconnected restart (R5): the app and a client need nothing but loopback.

The wall is seeded on a normal network, then everything is started again inside
a network namespace whose only interface is loopback (``unshare -rn``). The
probe shows the namespace really blocks the outside, boots the app twice,
loads every served page and runs the real ``client.js`` against it. Skipped
where unprivileged network namespaces, ``ip`` or ``node`` are unavailable.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from deploy import drill

ROOT = Path(__file__).resolve().parents[1]


def _can_unshare() -> bool:
    if not (shutil.which("unshare") and shutil.which("ip")):
        return False
    try:
        probe = subprocess.run(
            ["unshare", "-rn", "sh", "-c", "ip link set lo up"],
            capture_output=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = [
    pytest.mark.skipif(not _can_unshare(), reason="unprivileged network namespaces unavailable"),
    pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed"),
]


@pytest.fixture(scope="module")
def offline(tmp_path_factory):
    work = tmp_path_factory.mktemp("offline")
    assets = work / "assets"
    assets.mkdir()
    paths = {"db": work / "wall.db", "assets": assets, "media": work / "media"}
    seed = drill.Instance(paths["db"], assets, paths["media"])
    try:
        seed.start()
        expected = drill.populate(seed, assets)
    finally:
        seed.stop()

    device, (number, _x) = next(iter(drill.TABLETS.items()))
    config = {
        **{key: str(value) for key, value in paths.items()},
        "asset": expected["uploads"]["active"]["id"],
        "device": device,
        "number": number,
    }
    done = subprocess.run(
        ["unshare", "-rn", "sh", "-c",
         'ip link set lo up && exec "$0" "$@"', sys.executable,
         str(ROOT / "tests" / "offline_probe.py"), json.dumps(config)],
        cwd=ROOT, capture_output=True, text=True, timeout=240,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return expected, config, json.loads(done.stdout.splitlines()[-1])


def test_the_namespace_really_blocks_the_outside(offline):
    _expected, _config, result = offline
    assert result["wan_reachable"] == []


@pytest.mark.parametrize("phase", ["cold_start", "restart"])
def test_startup_restores_wall_playlist_and_media_offline(offline, phase):
    expected, config, result = offline
    seen = result[phase]["observed"]
    before = expected["snapshot"]
    assert seen["wall"] == before["wall"]
    assert seen["wall"]["scene"]["content"]["asset"] == config["asset"]
    assert seen["wall"]["placements"]  # the arrangement survived
    assert seen["layouts"] == before["layouts"]
    assert seen["scenes"] == before["scenes"]
    assert seen["playlist"] == before["playlist"]
    assert len(seen["playlist"]["items"]) == 2
    assert seen["library"] == [list(row) for row in before["library"]]
    status, sha = result[phase]["asset_sha"]
    assert (status, sha) == (200, config["asset"])  # bytes hash to their own ID


def test_served_pages_reference_nothing_outside_the_origin(offline):
    _expected, _config, result = offline
    pages = result["pages"]
    assert pages["foreign"] == []
    # The crawl really reached the pages and their scripts and styles.
    assert pages["fetched"]["/client/"] == "ok"
    assert pages["fetched"]["/controller/"] == "ok"
    assert all(state == "ok" for state in pages["fetched"].values()), pages["fetched"]
    assert any(path.endswith("client.js") for path in pages["fetched"])
    assert any(path.endswith("controller.js") for path in pages["fetched"])
    assert any(path.endswith(".css") for path in pages["fetched"])


def test_a_real_client_page_load_touches_only_its_own_origin(offline):
    _expected, config, result = offline
    client = result["client"]
    assert "error" not in client, client
    assert client["connected"] is True
    assert client["painted"] is True
    assert client["assets"] == [f"/assets/{config['asset']}"]
    hosts = {request["url"].split("/")[2] for request in client["requests"]}
    assert len(hosts) == 1, hosts  # one host:port, the loopback server's
    assert hosts.pop().startswith("127.0.0.1:")
    kinds = {request["kind"] for request in client["requests"]}
    assert kinds == {"fetch", "websocket"}
