"""Process ownership must cover startup through shutdown."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from tabletwall import workers


def test_second_app_lifespan_is_refused_until_first_stops():
    with TestClient(main.app) as first:
        with pytest.raises(RuntimeError, match="one worker"):
            with TestClient(main.app):
                pass
        assert first.get("/wall").status_code == 200
    with TestClient(main.app) as restarted:
        assert restarted.get("/wall").status_code == 200


def test_runtime_lock_excludes_another_process_and_releases_after_crash():
    program = (
        "from tabletwall.workers import single_worker\n"
        "with single_worker():\n"
        " print('owned', flush=True)\n"
        " input()\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", program], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "owned"
        with pytest.raises(RuntimeError, match="--workers 1"):
            with workers.single_worker():
                pass
    finally:
        child.kill()
        child.communicate(timeout=10)
    with workers.single_worker():
        pass


def test_startup_failure_releases_runtime_ownership(monkeypatch):
    def fail():
        raise RuntimeError("injected startup failure")

    with monkeypatch.context() as patch:
        patch.setattr(main.assets, "refresh", fail)
        with pytest.raises(RuntimeError, match="injected"):
            with TestClient(main.app):
                pass
    with TestClient(main.app) as restarted:
        assert restarted.get("/wall").status_code == 200


def test_static_mounts_work_when_imported_outside_repository(tmp_path):
    environment = dict(os.environ, PYTHONPATH=str(Path(main.__file__).resolve().parent))
    result = subprocess.run(
        [sys.executable, "-c", (
            "import main\n"
            "from fastapi.testclient import TestClient\n"
            "with TestClient(main.app) as client:\n"
            " assert client.get('/client/').status_code == 200\n"
            " assert client.get('/controller/').status_code == 200\n"
        )], cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
