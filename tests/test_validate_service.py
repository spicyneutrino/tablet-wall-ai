"""Operator-filled units must preserve the deployment boundary."""

from pathlib import Path

import pytest

from deploy.validate_service import main, validate_service

TEMPLATE = Path(__file__).resolve().parents[1] / "deploy/tablet-wall.service.example"


def filled_unit(scope="user"):
    text = TEMPLATE.read_text().replace("/REPLACE/with/checkout/of/tablet-wall-ai", "/srv/wall")
    text = text.replace("/REPLACE/with/data-dir", "/srv/wall-data")
    text = text.replace("REPLACE-operator-host.example", "operator.example")
    text = text.replace("REPLACE-tablet-host.example", "tablet.example")
    text = text.replace("# [Install]", "[Install]").replace(
        "# WantedBy=multi-user.target", "WantedBy=" + ("default.target" if scope == "user" else "multi-user.target")
    )
    if scope == "system":
        text = text.replace("[Service]", "[Service]\nUser=wall\nGroup=wall")
    return text


@pytest.mark.parametrize("scope", ["user", "system"])
def test_filled_reference_passes(scope):
    assert validate_service(filled_unit(scope), scope=scope) == []


def test_shipped_template_fails():
    errors = validate_service(TEMPLATE.read_text(), scope="user")
    assert any("placeholder" in error for error in errors)
    assert any("Install.WantedBy" in error for error in errors)


@pytest.mark.parametrize(("old", "new", "message"), [
    ("--host 127.0.0.1", "--host 0.0.0.0", "bind"),
    ("--port 8000", "--port 8000 --workers=2", "single worker"),
    ("https://operator.example:8444", "https://operator.example:8444/", "bare HTTPS"),
    ("TABLET_WALL_DB=/srv/wall-data/wall.db", "TABLET_WALL_DB=wall.db", "absolute path"),
    ("TABLET_WALL_UPLOAD_MODE=disabled", "TABLET_WALL_UPLOAD_MODE=loopback", "upload mode"),
    ("[Service]", "[Service]\nUser=root", "must not set User"),
    ("Restart=on-failure", "ExecStart=/bin/true", "exactly one"),
])
def test_unsafe_edits_fail(old, new, message):
    assert any(message in error for error in validate_service(filled_unit().replace(old, new), scope="user"))


def test_system_scope_requires_nonroot_account():
    assert any("non-root" in error for error in validate_service(filled_unit("system").replace("User=wall", "User=root"), scope="system"))


def test_cli_exit_codes(tmp_path, capsys):
    path = tmp_path / "wall.service"
    assert main([str(path), "--scope", "user"]) == 2
    path.write_text(TEMPLATE.read_text())
    assert main([str(path), "--scope", "user"]) == 1
    path.write_text(filled_unit())
    assert main([str(path), "--scope", "user"]) == 0
    assert "Static service checks passed" in capsys.readouterr().out


@pytest.mark.parametrize(("old", "new", "message"), [
    ("WorkingDirectory=/srv/wall", "WorkingDirectory=wall", "WorkingDirectory must be absolute"),
    ("/srv/wall/.venv/bin/fastapi run", "/bin/sh run", "must be fastapi"),
    ("TABLET_WALL_MEDIA_DIR=/srv/wall-data/media", "TABLET_WALL_MEDIA_DIR=/srv/wall-data/assets", "paths must be different"),
    ("https://operator.example:8444", "https://operator.example:99999", "bare HTTPS"),
    ("https://tablet.example:8443", "https://operator.example:8444", "origins must be different"),
    ("Restart=on-failure", "Environment=TABLET_WALL_DB=/duplicate", "duplicate environment"),
    ("Restart=on-failure", 'Environment="broken', "invalid Environment"),
    ("Restart=on-failure", "Bad directive", "key=value"),
    ("--port 8000", '--port "broken', "ExecStart:"),
])
def test_malformed_units_fail(old, new, message):
    assert any(message in error for error in validate_service(filled_unit().replace(old, new), scope="user"))
