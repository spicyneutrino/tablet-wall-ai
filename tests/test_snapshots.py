"""Named save/recall: the saved layouts and scenes (Phase 2c).

The two snapshot resources are symmetric — ``GET`` lists, ``PUT`` saves the
*active* payload under a name, ``POST …/recall`` applies a saved one back,
``DELETE`` drops it — and they differ only in what they store and what a
recall may change. A layout snapshot is ``{width, height, placements}`` and
its recall re-arranges the wall; a scene snapshot is ``content`` only and its
recall touches nothing but the content (PROTOCOL.md "Recall semantics":
recalling content must never throw away placement work done afterwards).

Two rules are asserted throughout, because they are what makes saving a
snapshot safe at any moment:

* saving and deleting move **neither** the revision nor the generation and
  put no frame on any socket — they are pure inventory operations;
* recall is the only snapshot route that changes the wall, so it is the only
  one that commits through ``main._commit_wall`` (persistence before
  apply) and then broadcasts.

Restart persistence and the upgrade of a pre-snapshot database live in
``tests/test_persistence.py``; a recall whose write fails lives in
``tests/test_commit_boundary.py``.
"""

import hashlib
import io
import json
import sqlite3
from urllib.parse import quote

import pytest
from PIL import Image

import main
from tabletwall import persist

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
# A second tablet, so a test can build a reservation: a placement whose
# device has left the roster but whose slot stays on the wall.
GUEST_ID = "3f8fad5b-d9cb-469f-a165-70867728950e"

ZERO_BEZEL = {"top": 0, "right": 0, "bottom": 0, "left": 0}

RESOURCES = ["layouts", "scenes"]

# Every route that takes a name, so "malformed is 422" and "absent is 404"
# are proven on all six rather than on whichever one was written first.
NAME_ROUTES = [
    ("PUT", "/layouts/{name}"),
    ("POST", "/layouts/{name}/recall"),
    ("DELETE", "/layouts/{name}"),
    ("PUT", "/scenes/{name}"),
    ("POST", "/scenes/{name}/recall"),
    ("DELETE", "/scenes/{name}"),
]

VALID_NAMES = ["lobby", "Lobby 2", "9lives", "a.b_c-d", "x", "a" * 64]

MALFORMED_NAMES = [
    "   ",  # whitespace only: empty once trimmed
    "_leading",  # must start with a letter or digit
    "-dash",
    ".hidden",
    "café",  # ASCII only
    "has\ttab",  # space is allowed, a tab is not
    "bang!",  # punctuation outside . _ -
    "a" * 65,  # one over the 64-character cap
]


def controller_url() -> str:
    return "/ws/controller?protocol=2"


def device_url(caps: str | None = "calibration") -> str:
    url = f"/ws/device?device_id={DEVICE_ID}&protocol=2"
    if caps is not None:
        url += f"&caps={caps}"
    return url


def register(client, device_payload, device_id: str = DEVICE_ID) -> None:
    response = client.post(
        "/devices/register", json={**device_payload, "device_id": device_id}
    )
    assert response.status_code == 200


def place(client, rect: dict, device_id: str = DEVICE_ID) -> None:
    response = client.put(f"/devices/{device_id}/placement", json=rect)
    assert response.status_code == 200


def wall_state(client) -> dict:
    response = client.get("/wall")
    assert response.status_code == 200
    return response.json()


def path_for(resource: str, name: str) -> str:
    # Percent-encoded so names with spaces, tabs, or accents reach the route
    # as the characters they are (the server decodes the path before it
    # validates the name).
    return f"/{resource}/{quote(name, safe='')}"


def save_snapshot(client, resource: str, name: str, *, replace: bool | None = None):
    url = path_for(resource, name)
    if replace is not None:
        url += f"?replace={'true' if replace else 'false'}"
    return client.put(url)


def recall(client, resource: str, name: str):
    return client.post(f"{path_for(resource, name)}/recall")


def delete_snapshot(client, resource: str, name: str):
    return client.delete(path_for(resource, name))


def listing(client, resource: str) -> list[dict]:
    response = client.get(f"/{resource}")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {resource}, "the list is wrapped, not a bare array"
    return payload[resource]


def stored_payload(client, resource: str, name: str) -> dict | None:
    key = "layout" if resource == "layouts" else "content"
    for entry in listing(client, resource):
        if entry["name"] == name:
            return entry[key]
    return None


def active_payload(client, resource: str) -> dict:
    """What saving *right now* would store: the live layout or the live content."""
    wall = wall_state(client)
    if resource == "layouts":
        return {
            "width": wall["width"],
            "height": wall["height"],
            "placements": wall["placements"],
        }
    return wall["scene"]["content"]


def change_payload(client, resource: str) -> None:
    """Move the active payload on, so the next save differs from the last one."""
    if resource == "layouts":
        assert client.put("/wall", json={"width": 3000}).status_code == 200
    else:
        assert (
            client.put("/scene", json={"content": {"type": "calibration"}}).status_code
            == 200
        )


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (64, 48)) -> bytes:
    """A freshly encoded still image — real bytes, not a stub."""
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, fmt)
    return buffer.getvalue()


def digest(data: bytes) -> str:
    """The content ID for these bytes, computed the way the server does."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def put_file(directory, name: str, data: bytes):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


class TestLayoutSnapshots:
    def test_the_list_starts_empty_and_is_wrapped(self, client):
        response = client.get("/layouts")

        assert response.status_code == 200
        assert response.json() == {"layouts": []}

    def test_saving_stores_the_active_layout_exactly(self, client, device_payload):
        register(client, device_payload)
        place(client, {"x": 10, "y": 20, "w": 300, "h": 200, "bezel": {"top": 5}})
        assert client.put("/wall", json={"width": 3456, "height": 1789}).status_code == 200

        response = save_snapshot(client, "layouts", "lobby")

        assert response.status_code == 200
        assert response.json() == {"saved": True, "name": "lobby"}
        assert listing(client, "layouts") == [
            {
                "name": "lobby",
                "layout": {
                    "width": 3456,
                    "height": 1789,
                    "placements": {
                        DEVICE_ID: {
                            "device_id": DEVICE_ID,
                            "x": 10,
                            "y": 20,
                            "w": 300,
                            "h": 200,
                            "bezel": {**ZERO_BEZEL, "top": 5},
                        }
                    },
                },
            }
        ]

    def test_recall_returns_the_full_wall_state_and_restores_the_arrangement(
        self, client, device_payload
    ):
        register(client, device_payload)
        place(client, {"x": 0, "y": 0, "w": 1000, "h": 1000})
        assert client.put("/wall", json={"width": 3000, "height": 1500}).status_code == 200
        assert save_snapshot(client, "layouts", "one").status_code == 200

        # Move away from the snapshot in every direction it owns …
        assert client.put("/wall", json={"width": 1000, "height": 500}).status_code == 200
        place(client, {"x": 5, "y": 5, "w": 10, "h": 10})
        before = wall_state(client)

        response = recall(client, "layouts", "one")

        assert response.status_code == 200
        recalled = response.json()
        # A full wall state, not a summary: the caller never has to re-read it.
        assert set(recalled) == {
            "width",
            "height",
            "revision",
            "generation",
            "placements",
            "scene",
        }
        assert recalled["width"] == 3000
        assert recalled["height"] == 1500
        assert recalled["placements"] == {
            DEVICE_ID: {
                "device_id": DEVICE_ID,
                "x": 0,
                "y": 0,
                "w": 1000,
                "h": 1000,
                "bezel": dict(ZERO_BEZEL),
            }
        }
        assert recalled["revision"] == before["revision"] + 1
        assert recalled["generation"] == before["generation"]
        assert recalled["scene"] == before["scene"], "a layout recall never touches content"
        # The response *is* the state: reading it back must agree.
        assert wall_state(client) == recalled

    def test_delete_removes_it_and_a_second_delete_is_404(self, client):
        assert save_snapshot(client, "layouts", "one").status_code == 200

        response = delete_snapshot(client, "layouts", "one")

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "name": "one"}
        assert listing(client, "layouts") == []
        assert delete_snapshot(client, "layouts", "one").status_code == 404

    def test_the_listing_is_sorted_by_name(self, client):
        """A stable order, so a controller can render the list without sorting."""
        for name in ("beta", "Alpha", "gamma", "9lives"):
            assert save_snapshot(client, "layouts", name).status_code == 200

        assert [entry["name"] for entry in listing(client, "layouts")] == [
            "9lives",
            "Alpha",
            "beta",
            "gamma",
        ]


class TestSceneSnapshots:
    def test_the_list_starts_empty_and_is_wrapped(self, client):
        response = client.get("/scenes")

        assert response.status_code == 200
        assert response.json() == {"scenes": []}

    def test_saving_stores_the_active_content_only(self, client):
        assert (
            client.put("/scene", json={"content": {"type": "calibration"}}).status_code
            == 200
        )

        response = save_snapshot(client, "scenes", "calib")

        assert response.status_code == 200
        assert response.json() == {"saved": True, "name": "calib"}
        assert listing(client, "scenes") == [
            {"name": "calib", "content": {"type": "calibration"}}
        ], "no layout, no revision, no URL — content and nothing else"

    def test_recall_applies_the_content_onto_the_active_layout(
        self, client, device_payload
    ):
        register(client, device_payload)
        place(client, {"x": 0, "y": 0, "w": 1000, "h": 1000})
        assert (
            client.put("/scene", json={"content": {"type": "calibration"}}).status_code
            == 200
        )
        assert save_snapshot(client, "scenes", "calib").status_code == 200

        # The operator changed their mind about both the content and the
        # arrangement after saving — only the content may be taken back.
        assert client.put("/scene", json={"content": {"type": "color"}}).status_code == 200
        assert client.put("/wall", json={"width": 3000}).status_code == 200
        before = wall_state(client)

        response = recall(client, "scenes", "calib")

        assert response.status_code == 200
        recalled = response.json()
        assert recalled["scene"] == {"content": {"type": "calibration"}, "layout": "active"}
        assert recalled["width"] == before["width"] == 3000, "the arrangement is untouched"
        assert recalled["placements"] == before["placements"]
        assert recalled["revision"] == before["revision"] + 1
        assert recalled["generation"] == before["generation"]
        assert wall_state(client) == recalled

    def test_delete_leaves_the_active_scene_showing(self, client):
        assert (
            client.put("/scene", json={"content": {"type": "calibration"}}).status_code
            == 200
        )
        assert save_snapshot(client, "scenes", "calib").status_code == 200
        before = wall_state(client)

        response = delete_snapshot(client, "scenes", "calib")

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "name": "calib"}
        assert listing(client, "scenes") == []
        # Deleting a snapshot is inventory work: the wall keeps showing what
        # it was showing, at the same revision.
        assert wall_state(client) == before
        assert delete_snapshot(client, "scenes", "calib").status_code == 404


class TestTheTwoResourcesAreSeparate:
    @pytest.mark.parametrize("name", ["one", "Two three", "a" * 64])
    def test_one_name_lives_in_both_lists_with_only_its_own_payload(
        self, client, name
    ):
        assert save_snapshot(client, "layouts", name).status_code == 200
        assert save_snapshot(client, "scenes", name).status_code == 200

        layout_entries = listing(client, "layouts")
        scene_entries = listing(client, "scenes")
        assert [entry["name"] for entry in layout_entries] == [name]
        assert [entry["name"] for entry in scene_entries] == [name]

        layout_entry, scene_entry = layout_entries[0], scene_entries[0]
        assert set(layout_entry) == {"name", "layout"}, (
            "a layout entry carries no content"
        )
        assert set(scene_entry) == {"name", "content"}, (
            "a scene entry carries no arrangement"
        )
        assert set(layout_entry["layout"]) == {"width", "height", "placements"}
        assert set(scene_entry["content"]) == {"type"}

    def test_deleting_one_leaves_the_other_recallable(self, client):
        assert save_snapshot(client, "layouts", "one").status_code == 200
        assert save_snapshot(client, "scenes", "one").status_code == 200

        assert delete_snapshot(client, "layouts", "one").status_code == 200

        assert listing(client, "layouts") == []
        assert [entry["name"] for entry in listing(client, "scenes")] == ["one"]
        assert recall(client, "scenes", "one").status_code == 200
        assert delete_snapshot(client, "layouts", "one").status_code == 404, (
            "the layout name is gone while the scene name survives"
        )

    def test_recalling_a_layout_leaves_the_content_alone(self, client):
        assert (
            client.put("/scene", json={"content": {"type": "calibration"}}).status_code
            == 200
        )
        assert save_snapshot(client, "layouts", "one").status_code == 200
        content_before = wall_state(client)["scene"]

        assert recall(client, "layouts", "one").status_code == 200

        assert wall_state(client)["scene"] == content_before

    def test_recalling_a_scene_leaves_the_arrangement_alone(self, client):
        assert client.put("/wall", json={"width": 3000, "height": 1500}).status_code == 200
        assert save_snapshot(client, "scenes", "one").status_code == 200
        layout_before = {
            key: wall_state(client)[key] for key in ("width", "height", "placements")
        }

        assert recall(client, "scenes", "one").status_code == 200

        wall = wall_state(client)
        assert {key: wall[key] for key in layout_before} == layout_before


class TestNames:
    @pytest.mark.parametrize("name", VALID_NAMES)
    def test_a_valid_name_is_saved_recalled_and_listed_verbatim(self, client, name):
        for resource in RESOURCES:
            response = save_snapshot(client, resource, name)
            assert response.status_code == 200
            assert response.json() == {"saved": True, "name": name}
            assert [entry["name"] for entry in listing(client, resource)] == [name]

        assert recall(client, "layouts", name).status_code == 200
        assert recall(client, "scenes", name).status_code == 200

    def test_outer_whitespace_is_trimmed_to_the_canonical_name(self, client):
        response = save_snapshot(client, "layouts", "  Lobby  ")

        assert response.status_code == 200
        assert response.json() == {"saved": True, "name": "Lobby"}, (
            "the canonical name is the trimmed one"
        )
        assert [entry["name"] for entry in listing(client, "layouts")] == ["Lobby"]
        # The padded spelling addresses the very same saved item …
        assert recall(client, "layouts", "  Lobby  ").status_code == 200
        assert delete_snapshot(client, "layouts", " Lobby ").status_code == 200
        assert listing(client, "layouts") == []

    @pytest.mark.parametrize(("method", "template"), NAME_ROUTES)
    @pytest.mark.parametrize("name", MALFORMED_NAMES)
    def test_a_malformed_name_is_422_everywhere_and_stores_nothing(
        self, client, method, template, name
    ):
        """Malformed beats absent: a bad name never becomes a 404, and the
        request is refused before it can reach the database."""
        before = wall_state(client)

        response = client.request(method, template.format(name=quote(name, safe="")))

        assert response.status_code == 422
        assert listing(client, "layouts") == []
        assert listing(client, "scenes") == []
        assert wall_state(client) == before

    @pytest.mark.parametrize("resource", RESOURCES)
    @pytest.mark.parametrize("route", ["recall", "delete"])
    def test_a_valid_name_that_was_never_saved_is_404(self, client, resource, route):
        response = (
            recall(client, resource, "absent")
            if route == "recall"
            else delete_snapshot(client, resource, "absent")
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("resource", RESOURCES)
    def test_names_are_case_sensitive(self, client, resource):
        assert save_snapshot(client, resource, "Lobby").status_code == 200

        assert recall(client, resource, "lobby").status_code == 404
        assert delete_snapshot(client, resource, "LOBBY").status_code == 404
        assert recall(client, resource, "Lobby").status_code == 200
        assert [entry["name"] for entry in listing(client, resource)] == ["Lobby"]


class TestConflicts:
    @pytest.mark.parametrize("resource", RESOURCES)
    def test_saving_a_taken_name_is_409_and_the_first_snapshot_wins(
        self, client, resource
    ):
        assert save_snapshot(client, resource, "one").status_code == 200
        original = stored_payload(client, resource, "one")
        change_payload(client, resource)

        response = save_snapshot(client, resource, "one")

        assert response.status_code == 409
        assert stored_payload(client, resource, "one") == original, (
            "a refused save must not overwrite what was already there"
        )

    @pytest.mark.parametrize("resource", RESOURCES)
    def test_replace_false_is_explicitly_still_a_conflict(self, client, resource):
        assert save_snapshot(client, resource, "one").status_code == 200
        original = stored_payload(client, resource, "one")
        change_payload(client, resource)

        response = save_snapshot(client, resource, "one", replace=False)

        assert response.status_code == 409
        assert stored_payload(client, resource, "one") == original

    @pytest.mark.parametrize("resource", RESOURCES)
    def test_replace_true_overwrites_in_place(self, client, resource):
        assert save_snapshot(client, resource, "one").status_code == 200
        change_payload(client, resource)

        response = save_snapshot(client, resource, "one", replace=True)

        assert response.status_code == 200
        assert response.json() == {"saved": True, "name": "one"}
        assert stored_payload(client, resource, "one") == active_payload(
            client, resource
        ), "the overwrite stored the payload that was active at that moment"
        assert len(listing(client, resource)) == 1, "an overwrite never duplicates"

    @pytest.mark.parametrize("resource", RESOURCES)
    def test_replace_true_on_a_free_name_still_saves(self, client, resource):
        response = save_snapshot(client, resource, "fresh", replace=True)

        assert response.status_code == 200
        assert stored_payload(client, resource, "fresh") == active_payload(
            client, resource
        )


class TestLayoutRecallSemantics:
    def test_recall_restores_a_reservation_whose_device_left_the_roster(
        self, client, device_payload
    ):
        """A saved slot belongs to an absent tablet too.

        The roster is memory-only, so after a restart every placement is a
        reservation until its tablet re-registers; recalling the layout must
        bring those slots back rather than only the ones whose device happens
        to be known right now.
        """
        register(client, device_payload)
        place(client, {"x": 0, "y": 0, "w": 1000, "h": 1000})
        assert save_snapshot(client, "layouts", "one").status_code == 200

        # The roster forgets the tablet (a restart, in miniature) while the
        # placement stays: from here on it is a vacancy, not a device.
        assert main.devices.pop(DEVICE_ID) is not None
        assert client.delete(f"/devices/{DEVICE_ID}/placement").status_code == 200

        response = recall(client, "layouts", "one")

        assert response.status_code == 200
        assert response.json()["placements"] == {
            DEVICE_ID: {
                "device_id": DEVICE_ID,
                "x": 0,
                "y": 0,
                "w": 1000,
                "h": 1000,
                "bezel": dict(ZERO_BEZEL),
            }
        }
        assert DEVICE_ID not in client.get("/devices").json(), (
            "recalling a layout must not re-register anything"
        )

    def test_recall_replaces_the_placements_it_does_not_mention(
        self, client, device_payload
    ):
        """Exactly what was saved comes back — nothing added, nothing carried.

        A slot placed after the save belongs to an arrangement the operator
        has moved on from, so recalling an older layout drops it: keeping a
        reservation they want is a decision made *before* the recall (release
        it, or save the layout again), not a side effect of it
        (PROTOCOL.md "Named snapshots": recall "replaces dimensions and all
        placements").
        """
        register(client, device_payload)
        register(client, device_payload, GUEST_ID)
        place(client, {"x": 0, "y": 0, "w": 1000, "h": 1000})
        assert save_snapshot(client, "layouts", "one").status_code == 200

        # A second slot added after the save, whose tablet has since left the
        # roster — the one case where "saved" and "live" disagree.
        place(client, {"x": 1000, "y": 0, "w": 1000, "h": 1000}, GUEST_ID)
        assert main.devices.pop(GUEST_ID) is not None

        response = recall(client, "layouts", "one")

        assert response.status_code == 200
        assert set(response.json()["placements"]) == {DEVICE_ID}, (
            "recall restores the saved map, not the live one merged with it"
        )


class TestSceneRecallSemantics:
    def test_a_saved_image_scene_recalls_even_when_the_file_is_gone(
        self, client, asset_dir, monkeypatch
    ):
        """No inventory check: a missing file stays an explicit broken scene.

        ``PUT /scene`` rejects an unknown asset (422) because that is a new
        claim about the world. A recall re-applies a claim the server already
        accepted, so it must succeed regardless of what the directory holds
        now — the client then reports the failure, exactly as it does for a
        file deleted after ``PUT /scene``.
        """
        data = image_bytes()
        path = put_file(asset_dir, "poster.png", data)
        asset_id = digest(data)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        ).status_code == 200
        assert save_snapshot(client, "scenes", "poster").status_code == 200
        path.unlink()

        def unexpected_scan(*args, **kwargs):
            raise AssertionError("recalling a scene must not consult the inventory")

        monkeypatch.setattr(main.assets, "find", unexpected_scan)

        response = recall(client, "scenes", "poster")

        assert response.status_code == 200
        content = response.json()["scene"]["content"]
        assert content["type"] == "image", (
            "a missing file must not fall back to colour"
        )
        assert content["asset"] == asset_id
        assert content["intrinsicWidth"] == 64
        assert content["intrinsicHeight"] == 48
        assert content["url"] == f"/assets/{asset_id}", (
            "the URL is composed on the way out of the response, never stored"
        )
        assert "url" not in persist.load_state()["scene"]["content"]
        assert "url" not in main.wall["scene"]["content"]

    def test_the_saved_content_never_carries_a_projected_url(
        self, client, asset_dir
    ):
        data = image_bytes()
        put_file(asset_dir, "poster.png", data)
        asset_id = digest(data)
        assert client.put(
            "/scene", json={"content": {"type": "image", "asset": asset_id}}
        ).status_code == 200

        assert save_snapshot(client, "scenes", "poster").status_code == 200

        stored = stored_payload(client, "scenes", "poster")
        assert stored == {
            "type": "image",
            "asset": asset_id,
            "fit": "cover",
            "intrinsicWidth": 64,
            "intrinsicHeight": 48,
        }
        assert "url" in client.get("/wall").json()["scene"]["content"], (
            "the wire descriptor still carries its composed URL"
        )
        assert "url" not in persist.load_state()["scene"]["content"]


class TestCorruptSnapshotRecall:
    @pytest.mark.parametrize(
        ("resource", "table", "column", "document"),
        [
            (
                "layouts",
                "saved_layouts",
                "layout",
                {
                    "width": 2000,
                    "height": 1000,
                    "placements": {
                        DEVICE_ID: {
                            "device_id": DEVICE_ID,
                            "x": 0,
                            "y": 0,
                            "w": 500,
                            "h": 500,
                            # A missing bezel would break every subsequent
                            # GET /wall *after* a successful commit.
                        }
                    },
                },
            ),
            (
                "scenes",
                "saved_scenes",
                "content",
                {
                    "type": "image",
                    "asset": "sha256:invalid",
                    "fit": "cover",
                    "intrinsicWidth": 1,
                    "intrinsicHeight": 1,
                },
            ),
            ("layouts", "saved_layouts", "layout", "{not json"),
            ("scenes", "saved_scenes", "content", "{not json"),
            ("layouts", "saved_layouts", "layout", "null"),
            ("scenes", "saved_scenes", "content", "null"),
        ],
    )
    def test_corrupt_saved_payload_cannot_poison_active_wall(
        self, client, resource, table, column, document
    ):
        assert save_snapshot(client, resource, "corrupt").status_code == 200
        assert save_snapshot(client, resource, "healthy").status_code == 200
        before = wall_state(client)
        persisted_before = persist.load_state()
        with sqlite3.connect(persist.db_path()) as connection:
            connection.execute(
                f"UPDATE {table} SET {column} = ? WHERE name = ?",
                (json.dumps(document) if isinstance(document, dict) else document, "corrupt"),
            )

        response = recall(client, resource, "corrupt")

        assert response.status_code == 409
        entries = listing(client, resource)
        key = "layout" if resource == "layouts" else "content"
        assert [entry["name"] for entry in entries] == ["corrupt", "healthy"]
        assert entries[0] == {"name": "corrupt", key: None, "invalid": True}
        assert entries[1][key] is not None
        assert delete_snapshot(client, resource, "corrupt").status_code == 200
        assert [entry["name"] for entry in listing(client, resource)] == ["healthy"]
        assert wall_state(client) == before
        assert persist.load_state() == persisted_before


class TestRevisionAndGeneration:
    @pytest.mark.parametrize("resource", RESOURCES)
    def test_saving_and_deleting_move_neither_revision_nor_generation(
        self, client, resource
    ):
        before = wall_state(client)

        assert save_snapshot(client, resource, "one").status_code == 200
        assert save_snapshot(client, resource, "two").status_code == 200
        after_saves = wall_state(client)
        assert delete_snapshot(client, resource, "one").status_code == 200
        after_deletes = wall_state(client)

        assert after_saves == after_deletes == before, (
            "snapshot inventory is invisible to the wall's ordering token"
        )

    def test_a_recall_bumps_the_revision_exactly_once_and_keeps_the_generation(
        self, client
    ):
        assert save_snapshot(client, "layouts", "one").status_code == 200
        assert save_snapshot(client, "scenes", "one").status_code == 200
        before = wall_state(client)

        first = recall(client, "layouts", "one")
        second = recall(client, "scenes", "one")

        assert first.status_code == second.status_code == 200
        assert first.json()["revision"] == before["revision"] + 1
        assert second.json()["revision"] == before["revision"] + 2
        assert first.json()["generation"] == second.json()["generation"] == before["generation"]
        # The database agrees with memory, so a restart will not disagree.
        assert persist.load_state()["revision"] == before["revision"] + 2


class TestBroadcast:
    def test_snapshots_put_no_frame_on_the_controller_socket(
        self, client, device_payload
    ):
        register(client, device_payload)

        with client.websocket_connect(controller_url()) as controller:
            controller.receive_json()  # snapshot

            assert save_snapshot(client, "layouts", "one").status_code == 200
            assert save_snapshot(client, "scenes", "one").status_code == 200
            assert delete_snapshot(client, "layouts", "one").status_code == 200
            assert delete_snapshot(client, "scenes", "one").status_code == 200

            # Nothing was queued, so a roster event raised *afterwards* is
            # the next frame out of the socket.
            register(client, device_payload)
            event = controller.receive_json()

        assert event["type"] == "device_updated"
        assert event["device"]["device_id"] == DEVICE_ID

    def test_snapshots_put_no_frame_on_the_device_socket(self, client, device_payload):
        register(client, device_payload)

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall

            assert save_snapshot(client, "layouts", "one").status_code == 200
            assert save_snapshot(client, "scenes", "one").status_code == 200
            assert delete_snapshot(client, "layouts", "one").status_code == 200
            assert delete_snapshot(client, "scenes", "one").status_code == 200

            # The colour command does not persist, so it still succeeds — and
            # being the *next* frame proves no wall frame was queued.
            assert client.post(
                f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"}
            ).status_code == 200
            frame = device.receive_json()

        assert frame == {"type": "set_color", "color": "#3b82f6"}

    def test_a_recall_pushes_the_new_wall_to_a_v2_controller(self, client):
        assert client.put("/wall", json={"width": 3333}).status_code == 200
        assert save_snapshot(client, "layouts", "one").status_code == 200
        assert client.put("/wall", json={"width": 2000}).status_code == 200
        assert save_snapshot(client, "scenes", "one").status_code == 200

        with client.websocket_connect(controller_url()) as controller:
            controller.receive_json()  # snapshot

            layout_recall = recall(client, "layouts", "one")
            first = controller.receive_json()
            scene_recall = recall(client, "scenes", "one")
            second = controller.receive_json()

        assert first["type"] == "wall_updated"
        assert first["wall"]["revision"] == layout_recall.json()["revision"]
        assert first["wall"]["width"] == 3333, "the recalled arrangement, not the live one"
        assert second["type"] == "wall_updated"
        assert second["wall"]["revision"] == scene_recall.json()["revision"]

    def test_a_recall_pushes_a_wall_frame_to_the_device(self, client, device_payload):
        register(client, device_payload)
        place(client, {"x": 0, "y": 0, "w": 1000, "h": 1000})
        assert save_snapshot(client, "layouts", "one").status_code == 200
        # Move the tablet off its saved slot, so the frame below can only be
        # the recall's doing.
        place(client, {"x": 500, "y": 500, "w": 10, "h": 10})

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall

            response = recall(client, "layouts", "one")
            frame = device.receive_json()

        assert frame["type"] == "wall"
        assert frame["revision"] == response.json()["revision"]
        assert frame["generation"] == response.json()["generation"]
        assert frame["placement"] == {
            "x": 0,
            "y": 0,
            "w": 1000,
            "h": 1000,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_a_v1_controller_hears_nothing_about_a_recall(self, client, device_payload):
        register(client, device_payload)
        assert save_snapshot(client, "layouts", "one").status_code == 200

        with client.websocket_connect("/ws/controller") as controller:
            controller.receive_json()  # snapshot (version 1: no wall)

            assert recall(client, "layouts", "one").status_code == 200
            register(client, device_payload)
            event = controller.receive_json()

        assert event["type"] == "device_updated", (
            "no wall_updated frame reached a version-1 socket"
        )
