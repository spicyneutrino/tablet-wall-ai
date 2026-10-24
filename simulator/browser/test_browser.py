import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from PIL import Image
import pytest

from simulator.browser import run
from simulator.browser.run import (
    REPO, artifact_directory, child_environment, exercise, expected_pixel,
    stop_server, write_fixture,
)


def test_signal_cancellation_keeps_event_reader_alive_during_cleanup(tmp_path, monkeypatch):
    evidence = []

    async def fake_exercise(artifacts, report, seconds):
        reader = asyncio.create_task(asyncio.sleep(60))
        loop = asyncio.get_running_loop()
        loop.call_later(.01, os.kill, os.getpid(), signal.SIGTERM)
        try:
            await asyncio.sleep(60)
        finally:
            loop.call_soon(os.kill, os.getpid(), signal.SIGTERM)
            await asyncio.sleep(.02)
            evidence.append(not reader.done())
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)

    monkeypatch.setattr(run, "exercise", fake_exercise)
    with pytest.raises(asyncio.CancelledError, match="SIGTERM"):
        asyncio.run(run.run_with_signals(tmp_path, {}))
    assert evidence == [True]


def test_browser_process_detection_handles_rewritten_chromium_argv(monkeypatch):
    commands = {
        "111": b"chrome --remote-debugging-pipe --no-startup-window\0",
        "222": b"chrome\0--remote-debugging-pipe\0--user-data-dir=/tmp/profile\0",
        "333": b"chrome --type=renderer --remote-debugging-pipe\0",
    }
    monkeypatch.setattr(run, "descendants", lambda pid: {int(pid): "1" for pid in commands})
    monkeypatch.setattr(Path, "read_bytes", lambda path: commands[path.parent.name])
    assert run.browser_processes() == [111, 222]


def test_artifacts_reject_repository_and_existing_directory(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        artifact_directory(REPO / "browser-output")
    link = tmp_path / "repository-link"
    link.symlink_to(REPO, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        artifact_directory(link / "browser-output")
    with pytest.raises(FileExistsError):
        artifact_directory(tmp_path)
    destination = artifact_directory(tmp_path / "new-run")
    marker = destination / "report.json"
    marker.write_text("keep me")
    with pytest.raises(FileExistsError):
        artifact_directory(destination)
    assert marker.read_text() == "keep me"


def test_child_environment_fences_operator_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TABLET_WALL_DB", "/operator/live.db")
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", "/operator/assets")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", "https://live.wall.test")
    monkeypatch.setenv("TABLET_WALL_TABLET_ORIGIN", "https://tablet.wall.test")
    monkeypatch.setenv("TABLET_WALL_FUTURE_OPTION", "untrusted")
    environment = child_environment(tmp_path)
    paths = {key: value for key, value in environment.items() if key.startswith("TABLET_WALL_")}
    assert paths == {
        "TABLET_WALL_DB": str(tmp_path / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(tmp_path / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(tmp_path / "media"),
    }
    assert os.environ["TABLET_WALL_DB"] == "/operator/live.db"


@pytest.mark.parametrize("name,x,y,rgb", [
    ("landscape", 2, 2, (41, 47, 46)),
    ("landscape", 797, 597, (106, 182, 126)),
    ("portrait", 2, 2, (119, 20, 65)),
    ("portrait", 747, 997, (184, 209, 167)),
    ("process-profile", 20, 20, (41, 20, 35)),
])
def test_hand_derived_pixel_anchors(name, x, y, rgb):
    assert expected_pixel(name, x, y) == rgb


def test_coded_png_anchors(tmp_path):
    fixture = tmp_path / "coded.png"
    write_fixture(fixture)
    with Image.open(fixture) as image:
        assert image.size == (1600, 800)
        assert image.getpixel((0, 0)) == (15, 20, 25)
        assert image.getpixel((1599, 799)) == (210, 209, 177)
        assert image.getpixel((799, 399)) == (106, 101, 93)


def test_stop_server_reaps_even_when_called_twice():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        stop_server(process)
        stop_server(process)
        assert process.returncode is not None
        assert not Path(f"/proc/{process.pid}").exists()
    finally:
        stop_server(process)


def test_partial_server_launch_cleanup(tmp_path):
    pytest.importorskip("playwright")
    report = {"checks": []}
    with pytest.raises(RuntimeError, match="injected partial launch failure"):
        asyncio.run(exercise(tmp_path, report, 6, fail_after_server=True))
    assert report["cleanup"]["server_reaped"]
    assert report["cleanup"]["temporary_root_removed"]
    assert report["cleanup"]["remaining_processes"] == {}
    assert report["cleanup"]["errors"] == []
    assert report["checks"][-1]["passed"]


def test_missing_browser_saves_failure_report_and_cleans_server(tmp_path):
    pytest.importorskip("playwright")
    destination = tmp_path / "missing-browser-report"
    result = subprocess.run(
        [sys.executable, str(REPO / "simulator/browser/run.py"), "--artifacts", str(destination)],
        env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "missing-browsers")},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 1, result.stderr
    report = json.loads((destination / "report.json").read_text())
    assert "Executable doesn't exist" in report["failure"]["message"]
    assert report["exit_code"] == 1
    assert report["cleanup"]["server_reaped"]
    assert report["cleanup"]["temporary_root_removed"]
    assert report["cleanup"]["remaining_processes"] == {}
    assert report["cleanup"]["errors"] == []
    assert (destination / "server.log").exists()
