"""Trust boundaries for the isolated acceptance evidence, not application behavior."""

import json
import os
import signal
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator/browser"))
import redesign_acceptance as driver  # noqa: E402


def test_existing_artifacts_refused_before_any_launch(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("existing operator evidence")
    result = subprocess.run(
        [
            "rtk",
            "proxy",
            sys.executable,
            str(Path(driver.__file__)),
            "--artifacts",
            str(tmp_path),
            "--scenario",
            "first-wall",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "FileExistsError" in result.stderr
    assert list(tmp_path.iterdir()) == [marker]
    assert marker.read_text() == "existing operator evidence"


def test_no_arbitrary_server_option(tmp_path):
    result = subprocess.run(
        [
            "rtk",
            "proxy",
            sys.executable,
            str(Path(driver.__file__)),
            "--artifacts",
            str(tmp_path / "new"),
            "--url",
            "http://127.0.0.1:8000",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --url" in result.stderr
    assert not (tmp_path / "new").exists()


def test_launch_profile_is_private_and_does_not_inherit_admission(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TABLET_WALL_DB", "/must-not-open-live.db")
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "proxy")
    monkeypatch.setenv("TABLET_WALL_AUTH_TOKEN", "must-not-inherit")
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", "/must-not-open-images")
    before = dict(os.environ)
    for enabled in (True, False):
        env = driver.child_environment(tmp_path, 35719, enabled)
        assert env["TABLET_WALL_DB"] == str(tmp_path / "wall.db")
        assert env["TABLET_WALL_ASSET_DIR"] == str(tmp_path / "assets")
        assert env["TABLET_WALL_BACKUP_DIR"] == str(tmp_path / "backups")
        assert env["TABLET_WALL_OPERATOR_ORIGIN"] == "http://127.0.0.1:35719"
        assert env["TABLET_WALL_UPLOAD_MODE"] == ("loopback" if enabled else "disabled")
        assert "TABLET_WALL_AUTH_TOKEN" not in env
        for key in (
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "XDG_RUNTIME_DIR",
        ):
            assert Path(env[key]).is_relative_to(tmp_path)
            assert Path(env[key]).is_dir()
    assert dict(os.environ) == before


def test_identity_changes_for_dirty_bytes_without_new_commit(tmp_path):
    def git(*args):
        return subprocess.check_output(
            ["rtk", "proxy", "git", *args], cwd=tmp_path, text=True
        )

    git("init", "-q")
    source = tmp_path / "source.js"
    source.write_text("old bytes")
    git("add", "source.js")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    before = driver.source_identity(tmp_path)
    source.write_text("new bytes")
    (tmp_path / "untracked.css").write_text("dirty styling")
    after = driver.source_identity(tmp_path)
    assert before["head"] == after["head"]
    assert before["source_sha256"] != after["source_sha256"]
    assert after["source_hashes"]["source.js"] == driver.digest(source)
    assert "untracked.css" in after["source_hashes"]
    assert (
        " M source.js" in after["dirty_status"]
        or "M source.js" in after["dirty_status"]
    )
    assert "operator_accessibility.py" in " ".join(after["driver_hashes"])


def test_bounded_wait_does_not_turn_timeout_into_success():
    with pytest.raises(AssertionError, match="bounded wait expired"):
        driver.wait_until(lambda: False, lambda _: None, timeout=0)


def test_injected_failure_scope_does_not_hide_unrelated_http(tmp_path):
    rig = driver.Rig(tmp_path, "fault-scope")
    with rig.fault("third assignment conflicts", [(r"/tablet-assignments/", [412])]):
        assert rig.expected_failures(
            "http://127.0.0.1/api/v3/tablet-assignments/a", status=412
        )
        assert not rig.expected_failures(
            "http://127.0.0.1/api/v3/tablet-assignments/a", status=500
        )
        assert not rig.expected_failures(
            "http://127.0.0.1/controller/physical.js", status=404
        )
    assert not rig.expected_failures(
        "http://127.0.0.1/api/v3/tablet-assignments/a", status=412
    )


@pytest.mark.timeout(90)
def test_real_failure_captured_before_actual_cleanup(tmp_path):
    def fail(rig):
        rig.check(
            False, "deliberate driver trust failure", {"expected_fixture_failure": True}
        )

    result = driver.run_scenario(tmp_path / "run", "capture-test", fail)
    assert result["pass"] is False
    report = json.loads((tmp_path / "run/results.json").read_text())
    assert any(
        row["name"] == "deliberate driver trust failure" and not row["pass"]
        for row in report["checks"]
    )
    assert (tmp_path / "run/failure.json").exists()
    assert list((tmp_path / "run").glob("*failure*-viewport.png"))
    assert (tmp_path / "run/trace-0.zip").stat().st_size > 100
    assert (tmp_path / "run/final-config.json").exists()
    cleanup = report["cleanup"]
    assert (
        cleanup["browser_disconnected"]
        and cleanup["private_data_removed"]
        and cleanup["port_closed"]
    )
    assert not cleanup["remaining_owned_browser_pids"]
    identity = json.loads((tmp_path / "run/identity.json").read_text())
    assert (
        identity["application_sha256"] == driver.source_identity()["application_sha256"]
    )
    for name, value in identity["loaded_driver_hashes"].items():
        assert driver.digest(tmp_path / "run/driver" / name) == value
    assert all(
        not server["alive"] and server["exit"] in (0, -signal.SIGTERM)
        for server in identity["servers"]
    )
    assert all(
        not server["remaining_owned_process_group"] for server in identity["servers"]
    )
    assert (
        len(identity["clients"]) == len({row["id"] for row in identity["clients"]}) == 4
    )


@pytest.mark.timeout(90)
def test_real_race_records_both_authorities_and_retained_intent(tmp_path):
    result = driver.run_scenario(tmp_path / "run", "race-test", driver.race_suite)
    assert not any(
        row["name"] == "scenario interrupted" for row in result["failures"]
    ), result["failures"]
    checks = json.loads((tmp_path / "run/results.json").read_text())["checks"]
    assert next(
        row
        for row in checks
        if row["name"] == "Old GET cannot regress newer WS name or keyed dirty form"
    )["pass"]
    events = json.loads((tmp_path / "run/evidence.json").read_text())
    race = next(row for row in events if "race" in row)
    assert race["old"]["etag"] != race["new"]["etag"]
    assert race["new"]["device_labels"] != race["old"]["device_labels"]
    assert race["new"]["revision"] == race["old"]["revision"]
    assert list((tmp_path / "run").glob("*final-*-ax.yml"))
