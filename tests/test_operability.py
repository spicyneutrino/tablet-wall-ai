"""Readiness projection: configured values, unknown values, and backup evidence.

These read the real environment contract and the real backup-directory
convention. They never write an operator backup or claim a restore happened;
an unrecorded rehearsal stays ``recorded: false``.
"""

from __future__ import annotations

import json
import os

import pytest

from tabletwall import operability, persist


@pytest.fixture(autouse=True)
def clean_operator_environment(monkeypatch):
    for name in (
        operability.TABLET_ORIGIN_ENV,
        operability.OPERATOR_ORIGIN_ENV,
        operability.UPLOAD_MODE_ENV,
        operability.AUTH_TOKEN_ENV,
        operability.WIFI_NAME_ENV,
        operability.BACKUP_DIR_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def snapshot(**overrides):
    values = {
        "generation": "abc12345",
        "revision": 7,
        "devices_total": 3,
        "devices_online": 2,
        "content_type": "color",
        "content_asset": None,
        "layout_kind": "logical",
        "schema_version": persist.SCHEMA_VERSION,
        "storage_readable": True,
    }
    values.update(overrides)
    return operability.WallSnapshot(**values)


def test_configured_environment_is_projected_without_guessing(monkeypatch, tmp_path):
    monkeypatch.setenv(operability.TABLET_ORIGIN_ENV, "http://10.42.0.1:8080")
    monkeypatch.setenv(operability.WIFI_NAME_ENV, "Wall-Lab")
    monkeypatch.setenv(operability.BACKUP_DIR_ENV, str(tmp_path / "backups"))
    config = operability.read_config()
    assert config.tablet_origin == "http://10.42.0.1:8080"
    assert config.wifi_name == "Wall-Lab"
    assert config.uploads == "disabled"
    assert config.authentication == "disabled"
    assert config.errors == ()
    assert config.secure_context is False


def test_missing_tablet_origin_is_an_actionable_error_not_a_guess():
    config = operability.read_config()
    body = operability.readiness(snapshot(), config)
    assert body["tablet_url"] is None
    assert body["join_qr_url"] is None
    assert any(operability.TABLET_ORIGIN_ENV in error for error in body["errors"])


@pytest.mark.parametrize(
    "origin",
    [
        "http://10.0.0.1:8080/client/",
        "http://user:secret@10.0.0.1:8080",
        "ftp://10.0.0.1:8080",
        " http://10.0.0.1:8080",
        "http://10.0.0.1:99999",
    ],
)
def test_invalid_tablet_origin_is_reported_and_not_used(monkeypatch, origin):
    monkeypatch.setenv(operability.TABLET_ORIGIN_ENV, origin)
    config = operability.read_config()
    assert config.tablet_origin is None
    assert config.errors


def test_unknown_wifi_and_backup_stay_unknown():
    body = operability.readiness(snapshot(), operability.read_config())
    assert body["wifi"] == {"name": None, "known": False}
    assert body["backup"] == {
        "last_manifest_at": None,
        "recorded": False,
        "scope": operability.BACKUP_SCOPE,
    }
    assert body["restore_rehearsal"] == {"completed_utc": None, "recorded": False}


def test_non_printable_wifi_name_is_not_reported(monkeypatch):
    monkeypatch.setenv(operability.WIFI_NAME_ENV, "bad\x1bname")
    assert operability.read_config().wifi_name is None


def test_wifi_name_is_not_queried_from_networkmanager(monkeypatch):
    monkeypatch.setenv(operability.WIFI_NAME_ENV, "Configured-SSID")

    def forbid(*_args, **_kwargs):
        raise AssertionError("operability must not shell out per readiness read")

    monkeypatch.setattr("subprocess.run", forbid)
    assert operability.read_config().wifi_name == "Configured-SSID"


def test_plain_http_warns_that_wake_lock_is_unavailable(monkeypatch):
    monkeypatch.setenv(operability.TABLET_ORIGIN_ENV, "http://10.42.0.1:8080")
    body = operability.readiness(snapshot(), operability.read_config())
    assert body["security"]["transport"] == "http"
    assert any("unavailable" in line.lower() for line in body["advice"])
    assert any("cannot wake" in line for line in body["advice"])


def test_https_context_calls_wake_lock_best_effort(monkeypatch):
    monkeypatch.setenv(operability.TABLET_ORIGIN_ENV, "https://10.42.0.1:8443")
    body = operability.readiness(snapshot(), operability.read_config())
    assert body["security"]["transport"] == "https"
    assert any("best effort" in line for line in body["advice"])


def test_shared_secret_is_not_described_as_authenticated_device_identity(monkeypatch):
    monkeypatch.setenv(operability.TABLET_ORIGIN_ENV, "http://10.42.0.1:8080")
    monkeypatch.setenv(operability.AUTH_TOKEN_ENV, "x" * 32)
    body = operability.readiness(snapshot(), operability.read_config())
    assert body["security"]["authentication"] == "shared-secret"
    assert "not a per-device identity" in body["security"]["trust"]


@pytest.mark.parametrize(
    ("content_type", "available", "expected"),
    [
        ("color", None, "solid colour"),
        ("calibration", None, "calibration"),
        ("image", True, "bytes are available"),
        ("image", False, "bytes are missing"),
    ],
)
def test_content_readiness_describes_what_is_actually_selected(
    content_type, available, expected
):
    asset = "sha256:" + "a" * 64 if content_type == "image" else None
    body = operability.readiness(
        snapshot(content_type=content_type, content_asset=asset),
        operability.read_config(),
        resolve=lambda _asset: bool(available),
    )
    assert body["content"]["type"] == content_type
    assert body["content"]["available"] == (available is not False)
    assert expected in body["content"]["summary"]


def test_newest_backup_manifest_is_read_without_verifying_or_writing(tmp_path):
    root = tmp_path / "backups"
    (root / "older").mkdir(parents=True)
    (root / "older" / "manifest.json").write_text(
        json.dumps({"created_utc": "2026-10-01T10:00:00Z"})
    )
    (root / "newer").mkdir()
    (root / "newer" / "manifest.json").write_text(
        json.dumps({"created_utc": "2026-10-31T18:30:00Z"})
    )
    (root / "manifest.json").write_text(
        json.dumps({"created_utc": "2026-10-15T00:00:00Z"})
    )
    assert operability._newest_manifest(str(root)) == "2026-10-31T18:30:00Z"


def test_broken_backup_manifest_does_not_become_a_recency_claim(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    (root / "manifest.json").write_text("{not json")
    assert operability._newest_manifest(str(root)) is None


def test_restore_rehearsal_is_reported_only_when_recorded(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    assert operability._restore_rehearsal(str(root)) is None
    (root / operability.RESTORE_REHEARSAL_NAME).write_text(
        json.dumps({"completed_utc": "2026-10-20T12:00:00Z"})
    )
    assert operability._restore_rehearsal(str(root)) == "2026-10-20T12:00:00Z"


def test_restore_rehearsal_without_a_timestamp_is_unknown(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    (root / operability.RESTORE_REHEARSAL_NAME).write_text(json.dumps({"note": "done"}))
    assert operability._restore_rehearsal(str(root)) is None


def test_health_reports_schema_and_counts_without_private_paths():
    body = operability.health(snapshot())
    assert body == {
        "ready": True,
        "schema": persist.SCHEMA_VERSION,
        "schema_expected": persist.SCHEMA_VERSION,
        "generation": "abc12345",
        "revision": 7,
        "counts": {"devices_online": 2, "devices_total": 3},
        "storage_readable": True,
    }
    assert not any(
        isinstance(value, str) and ("/" in value or "\\" in value)
        for value in body.values()
    )


def test_health_is_not_ready_without_storage_or_matching_schema():
    assert operability.health(snapshot(storage_readable=False))["ready"] is False
    assert operability.health(snapshot(schema_version=None))["ready"] is False
    assert operability.health(snapshot(schema_version=1))["ready"] is False


def test_live_snapshot_uses_the_process_state_and_store(isolated_registry):
    persist.ensure_schema()
    live = operability.live_snapshot()
    assert live.schema_version == persist.SCHEMA_VERSION
    assert live.storage_readable is True
    assert live.devices_total == 0
    assert live.generation


def test_live_snapshot_reports_unreadable_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("TABLET_WALL_DB", str(tmp_path / "missing" / "wall.db"))
    live = operability.live_snapshot()
    assert live.storage_readable is False
    assert live.schema_version is None


def test_missing_database_does_not_get_created_by_readiness(monkeypatch, tmp_path):
    database = tmp_path / "absent" / "wall.db"
    monkeypatch.setenv("TABLET_WALL_DB", str(database))
    operability.live_snapshot()
    assert not database.exists()
    assert not database.parent.exists()


def test_readiness_never_copies_an_asset_path_from_a_failure(tmp_path):
    body = operability.readiness(
        snapshot(content_type="image", content_asset="sha256:" + "b" * 64),
        operability.read_config(),
        resolve=lambda _asset: False,
    )
    text = json.dumps(body)
    assert "sha256:" + "b" * 64 not in text
    assert '"asset"' not in text


def test_operator_data_paths_are_reported_only_for_the_operator_projection():
    body = operability.readiness(snapshot(), operability.read_config())
    assert set(body["storage"]) == {
        "readable", "database", "assets", "media", "backup_dir"
    }
    assert os.path.basename(body["storage"]["database"])
    assert "database" not in operability.health(snapshot())
