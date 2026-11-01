"""Shared pytest fixtures for the tablet-wall-ai API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import main
from tabletwall import writer, render_status


def _clear_state() -> None:
    render_status.reset()
    main.identify_commands.clear()
    main.devices.clear()
    main.device_sockets.clear()
    main.controller_sockets.clear()
    main.controller_protocols.clear()
    main._playback_session = None
    writer.clear()
    # The wall is module-level state too: reset it to the PROTOCOL.md defaults
    # (revision 0, no placements) so no test sees another test's mutations.
    main.wall.clear()
    main.wall.update(main._fresh_wall())


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch) -> Iterator[None]:
    """Keep the in-memory state *and* the database from leaking between tests.

    ``main.devices`` and ``main.wall`` are module-level mutable state, so
    without this every test would see the devices registered — and the wall
    mutations made — by the tests that ran before it. The WebSocket registries
    are cleared too: a socket left over from an earlier test would make its
    device look online.

    ``TABLET_WALL_DB`` points at a per-test file under ``tmp_path``, so the
    suite never opens a real ``tablet-wall.db`` in the repository and no test
    can read another test's persisted wall. ``TABLET_WALL_ASSET_DIR`` points
    at a per-test directory for the same reason: no test may read a real
    ``./assets`` curated by the operator (and a directory that does not exist
    yet is simply an empty inventory).
    """
    monkeypatch.setenv("TABLET_WALL_DB", str(tmp_path / "tablet-wall.db"))
    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("TABLET_WALL_MEDIA_DIR", str(tmp_path / "media"))
    # Deployment environment must not change the existing API contract tests;
    # security-specific cases opt in to these origin settings explicitly.
    monkeypatch.delenv("TABLET_WALL_OPERATOR_ORIGIN", raising=False)
    monkeypatch.delenv("TABLET_WALL_TABLET_ORIGIN", raising=False)
    monkeypatch.delenv("TABLET_WALL_AUTH_TOKEN", raising=False)
    _clear_state()
    yield
    _clear_state()


@pytest.fixture
def asset_dir(tmp_path):
    """An existing, empty asset directory for ``TABLET_WALL_ASSET_DIR``.

    Tests fill it with files of their own; ``tmp_path`` keeps every test's
    files to itself.
    """
    path = tmp_path / "assets"
    path.mkdir(exist_ok=True)
    return path


@pytest.fixture
def client(isolated_registry) -> Iterator[TestClient]:
    """An HTTP client bound to the app, without starting a network server.

    Depends on ``isolated_registry`` explicitly so the database path is set
    before this fixture starts the app: entering ``TestClient`` runs the
    lifespan, which loads the persisted wall from ``TABLET_WALL_DB``.
    """
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def device_payload() -> dict[str, object]:
    """A representative valid registration body."""
    return {
        "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
        "width": 1024,
        "height": 768,
        "device_type": "ipad",
    }
