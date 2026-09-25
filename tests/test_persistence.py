"""Persistence tests (PROTOCOL.md "Persistence").

A restart is simulated the way the contract describes it: mutate through one
``TestClient``, let it close, then construct a fresh ``TestClient`` against
the same database file. The autouse ``isolated_registry`` fixture in
``conftest.py`` points ``TABLET_WALL_DB`` at a per-test file under
``tmp_path``, so nothing here — and nothing anywhere else in the suite — ever
opens a real ``tablet-wall.db`` in the repository.

The roster, sockets, presence, and heartbeats are deliberately *not*
persisted, so every test that needs a device after a restart re-registers it,
exactly as a real client does before every connection attempt.

The last class covers the *other* way state reaches a running server: a
database file written before the snapshot tables existed, which must gain
them without losing the row it already holds.
"""

import json
import sqlite3

from fastapi.testclient import TestClient

import main
from tabletwall import persist

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"

ZERO_BEZEL = {"top": 0, "right": 0, "bottom": 0, "left": 0}


def device_url(device_id: str = DEVICE_ID, caps: str | None = None) -> str:
    url = f"/ws/device?device_id={device_id}&protocol=2"
    if caps is not None:
        url += f"&caps={caps}"
    return url


def register(client, device_payload, device_id: str = DEVICE_ID) -> None:
    response = client.post(
        "/devices/register", json={**device_payload, "device_id": device_id}
    )
    assert response.status_code == 200


def wall_state(client) -> dict:
    response = client.get("/wall")
    assert response.status_code == 200
    return response.json()


def accepts_frame(held: dict, frame: dict) -> bool:
    """The client's acceptance rule, verbatim from PROTOCOL.md.

    "Client rendering contract" item 2 plus "Revision and generation": ignore
    a frame whose revision is not newer than the one held — unless the
    generation differs, in which case accept it and reset the held revision.
    """
    if frame["generation"] != held["generation"]:
        return True
    return frame["revision"] > held["revision"]


class TestStateSurvivesARestart:
    def test_state_written_by_one_request_is_loaded_by_a_fresh_app_instance(
        self
    ):
        """Write, close, construct a new TestClient against the same DB file."""
        with TestClient(main.app) as first:
            assert first.put("/wall", json={"width": 3333}).status_code == 200
            written = wall_state(first)

        with TestClient(main.app) as second:
            loaded = wall_state(second)

        assert loaded["width"] == 3333
        assert loaded["height"] == written["height"] == 1000
        assert loaded["revision"] == written["revision"] == 1

    def test_generation_differs_across_a_restart_while_the_revision_continues(
        self
    ):
        with TestClient(main.app) as first:
            assert first.put("/wall", json={"width": 3000}).status_code == 200
            before = wall_state(first)

        with TestClient(main.app) as second:
            after_restart = wall_state(second)
            assert second.put("/wall", json={"height": 900}).status_code == 200
            after_change = wall_state(second)

        # A new lineage on every start …
        assert after_restart["generation"] != before["generation"]
        # … but the revision continues from the persisted row, never resets.
        assert after_restart["revision"] == before["revision"] == 1
        assert after_change["generation"] == after_restart["generation"]
        assert after_change["revision"] == before["revision"] + 1
        assert after_change["width"] == 3000
        assert after_change["height"] == 900

    def test_layout_placements_and_scene_round_trip(self, device_payload):
        placement = {"x": 10, "y": 20, "w": 300, "h": 200, "bezel": {"top": 5}}

        with TestClient(main.app) as first:
            register(first, device_payload)
            assert first.put(
                "/wall", json={"width": 3456, "height": 1789}
            ).status_code == 200
            assert first.put(
                f"/devices/{DEVICE_ID}/placement", json=placement
            ).status_code == 200
            assert first.put(
                "/scene", json={"content": {"type": "calibration"}}
            ).status_code == 200
            before = wall_state(first)

        with TestClient(main.app) as second:
            after = wall_state(second)

        assert after["width"] == 3456
        assert after["height"] == 1789
        assert after["placements"] == before["placements"] == {
            DEVICE_ID: {
                "device_id": DEVICE_ID,
                "x": 10,
                "y": 20,
                "w": 300,
                "h": 200,
                "bezel": {**ZERO_BEZEL, "top": 5},
            }
        }
        assert after["scene"] == before["scene"] == {
            "content": {"type": "calibration"},
            "layout": "active",
        }
        assert after["revision"] == before["revision"] == 3
        assert after["generation"] != before["generation"], (
            "the roster is memory-only, but the wall's lineage still turns "
            "over on every start"
        )

    def test_the_persisted_wall_is_replayed_to_a_connecting_device(
        self, device_payload
    ):
        """Load happens in the lifespan, before a socket can be accepted."""
        with TestClient(main.app) as first:
            register(first, device_payload)
            assert first.put("/wall", json={"width": 2400, "height": 1350}).status_code == 200
            assert first.put(
                f"/devices/{DEVICE_ID}/placement",
                json={"x": 0, "y": 0, "w": 1200, "h": 1350},
            ).status_code == 200
            assert first.put(
                "/scene", json={"content": {"type": "calibration"}}
            ).status_code == 200
            before = wall_state(first)

        with TestClient(main.app) as second:
            # The roster is not persisted: the tablet re-registers, per the
            # protocol, and must then be handed the *persisted* wall.
            register(second, device_payload)
            with second.websocket_connect(device_url(caps="calibration")) as device:
                device.receive_json()  # welcome
                frame = device.receive_json()  # wall
            generation = wall_state(second)["generation"]

        assert frame["type"] == "wall"
        assert frame["revision"] == before["revision"] == 3
        assert frame["generation"] == generation != before["generation"]
        assert frame["wall"] == {"width": 2400, "height": 1350}
        assert frame["scene"] == {
            "content": {"type": "calibration"},
            "layout": "active",
        }
        assert frame["placement"] == {
            "x": 0,
            "y": 0,
            "w": 1200,
            "h": 1350,
            "bezel": dict(ZERO_BEZEL),
        }


class TestGenerationForcesResynchronisation:
    def test_a_client_holding_a_high_revision_accepts_a_lower_revision_frame(
        self, device_payload, monkeypatch, tmp_path
    ):
        """The failure mode the generation exists for.

        A tablet holds revision 2 of generation A, then meets a server that
        came back from a wiped database at revision 0 of generation B: the
        frame must be accepted, not rejected forever as stale.
        """
        with TestClient(main.app) as first:
            assert first.put("/wall", json={"width": 3000}).status_code == 200
            assert first.put("/wall", json={"height": 1500}).status_code == 200
            register(first, device_payload)
            with first.websocket_connect(device_url()) as device:
                device.receive_json()  # welcome
                held = device.receive_json()  # wall: revision 2, generation A
        assert held["revision"] == 2

        # A wiped/rolled-back database: the same path, no rows, so the server
        # comes back at revision 0 with a brand-new generation.
        monkeypatch.setenv("TABLET_WALL_DB", str(tmp_path / "wiped.db"))
        with TestClient(main.app) as second:
            register(second, device_payload)
            with second.websocket_connect(device_url()) as device:
                device.receive_json()  # welcome
                restored = device.receive_json()  # wall: revision 0, generation B

        assert restored["revision"] < held["revision"]
        assert restored["generation"] != held["generation"]
        assert accepts_frame(held, restored) is True, (
            "a generation change must make the client accept a lower revision"
        )

        # The rule is not "accept everything": a frame that is no newer from
        # the *same* generation is still ignored, and a newer one is accepted.
        assert accepts_frame(held, {**held, "revision": 2}) is False
        assert accepts_frame(held, {**held, "revision": 3}) is True
        stale_same_generation = {**restored, "generation": held["generation"]}
        assert accepts_frame(held, stale_same_generation) is False


class TestDatabaseLocation:
    def test_the_suite_points_the_database_at_a_per_test_tmp_path(self, tmp_path):
        """conftest isolates every test: the running app never touches a real
        ``tablet-wall.db`` in the repository."""
        assert persist.db_path() == str(tmp_path / "tablet-wall.db")

    def test_db_path_is_taken_from_the_environment(self, monkeypatch, tmp_path):
        custom = tmp_path / "elsewhere.db"
        monkeypatch.setenv("TABLET_WALL_DB", str(custom))

        assert persist.db_path() == str(custom)
        with TestClient(main.app) as client:
            assert client.put("/wall", json={"width": 4242}).status_code == 200

        assert custom.exists(), "the state must be written where env points"
        assert persist.load_state()["layout"]["width"] == 4242

    def test_db_path_defaults_to_tablet_wall_db(self, monkeypatch):
        monkeypatch.delenv("TABLET_WALL_DB", raising=False)

        # No app is started in this test on purpose: loading would *create*
        # that file, and the suite must never touch the repository's default.
        assert persist.db_path() == "tablet-wall.db"


class TestSnapshotsSurviveARestart:
    def test_saved_layouts_and_scenes_are_listed_and_recallable_after_a_restart(
        self, device_payload
    ):
        with TestClient(main.app) as first:
            register(first, device_payload)
            assert first.put(
                "/wall", json={"width": 3456, "height": 1789}
            ).status_code == 200
            assert first.put(
                f"/devices/{DEVICE_ID}/placement",
                json={"x": 10, "y": 20, "w": 300, "h": 200, "bezel": {"top": 5}},
            ).status_code == 200
            assert first.put(
                "/scene", json={"content": {"type": "calibration"}}
            ).status_code == 200
            assert first.put("/layouts/lobby").status_code == 200
            assert first.put("/scenes/calib").status_code == 200
            layouts_before = first.get("/layouts").json()
            scenes_before = first.get("/scenes").json()

        with TestClient(main.app) as second:
            # Both listings come back byte for byte …
            assert second.get("/layouts").json() == layouts_before
            assert second.get("/scenes").json() == scenes_before

            # … the arrangement recalls, placement and bezel included — the
            # tablet has not re-registered, so that placement is a
            # reservation, and recalling must bring it back anyway …
            recalled = second.post("/layouts/lobby/recall")
            assert recalled.status_code == 200
            assert recalled.json()["width"] == 3456
            assert recalled.json()["height"] == 1789
            assert recalled.json()["placements"] == {
                DEVICE_ID: {
                    "device_id": DEVICE_ID,
                    "x": 10,
                    "y": 20,
                    "w": 300,
                    "h": 200,
                    "bezel": {**ZERO_BEZEL, "top": 5},
                }
            }
            # … and so does the content, onto whatever is active by then.
            scene = second.post("/scenes/calib/recall")
            assert scene.status_code == 200
            assert scene.json()["scene"] == {
                "content": {"type": "calibration"},
                "layout": "active",
            }


# ---------------------------------------------------------------------------
# upgrading a database written before the snapshot tables existed
# ---------------------------------------------------------------------------


def write_pre_snapshot_database(path) -> dict[str, object]:
    """A database exactly as Phase 2b wrote it: one table, no snapshot tables.

    Written without going anywhere near ``tabletwall.persist`` on purpose —
    the schema under test has to be the historical one, not the current one.
    Returns the state that row holds.
    """
    layout = {"width": 4321, "height": 1000, "placements": {}}
    scene = {"content": {"type": "calibration"}, "layout": "active"}
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE wall_state (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                layout     TEXT NOT NULL,
                scene      TEXT NOT NULL,
                revision   INTEGER NOT NULL,
                generation TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO wall_state (id, layout, scene, revision, generation)
            VALUES (1, ?, ?, ?, ?)
            """,
            (
                json.dumps(layout, sort_keys=True),
                json.dumps(scene, sort_keys=True),
                5,
                "abcd1234",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return {
        "layout": layout,
        "scene": scene,
        "revision": 5,
        "generation": "abcd1234",
    }


def table_names(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def wall_row(path) -> tuple:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT id, layout, scene, revision, generation FROM wall_state WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()
    return row


class TestSchemaUpgrade:
    def test_an_old_database_gains_the_snapshot_tables_and_keeps_its_row(
        self, tmp_path, monkeypatch
    ):
        """The migration is additive: three ``CREATE TABLE IF NOT EXISTS``
        statements, none of which reads or writes ``wall_state``."""
        db = tmp_path / "phase-2b.db"
        expected = write_pre_snapshot_database(db)
        monkeypatch.setenv("TABLET_WALL_DB", str(db))
        row_before = wall_row(db)
        assert table_names(db) == {"wall_state"}, "the fixture really is pre-snapshot"

        # The first connection applies the migration and still reads the row …
        assert persist.load_state() == expected

        # … the old row is byte for byte what it was …
        assert table_names(db) == {"wall_state", "saved_layouts", "saved_scenes"}
        assert wall_row(db) == row_before

        # … and the new tables work straight away.
        assert persist.save_layout("lobby", expected["layout"]) is True
        assert persist.save_scene("calib", expected["scene"]) is True
        assert persist.load_layout("lobby") == expected["layout"]
        assert persist.load_scene("calib") == expected["scene"]
        assert [name for name, _ in persist.load_layouts()] == ["lobby"]
        assert [name for name, _ in persist.load_scenes()] == ["calib"]
        assert wall_row(db) == row_before, (
            "writing a snapshot must not touch the wall row either"
        )

    def test_the_app_starts_on_an_old_database_and_saves_snapshots_into_it(
        self, tmp_path, monkeypatch
    ):
        """End to end: the upgraded file serves its old state *and* new ones."""
        db = tmp_path / "phase-2b.db"
        expected = write_pre_snapshot_database(db)
        monkeypatch.setenv("TABLET_WALL_DB", str(db))

        with TestClient(main.app) as first:
            wall = first.get("/wall").json()
            assert wall["width"] == expected["layout"]["width"]
            assert wall["revision"] == expected["revision"], (
                "the revision continues from the old row"
            )
            assert wall["generation"] != expected["generation"], (
                "but every start mints a new lineage"
            )
            assert first.put("/layouts/lobby").status_code == 200

        with TestClient(main.app) as second:
            assert second.get("/layouts").json() == {
                "layouts": [{"name": "lobby", "layout": expected["layout"]}]
            }
            recalled = second.post("/layouts/lobby/recall")
            assert recalled.status_code == 200
            assert recalled.json()["width"] == expected["layout"]["width"]
            assert second.delete("/layouts/lobby").status_code == 200

        assert persist.load_state()["layout"] == expected["layout"]
        assert persist.load_state()["scene"] == expected["scene"]
