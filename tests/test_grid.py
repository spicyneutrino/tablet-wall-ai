"""Focused tests for the pure ordered grid helper."""

import json
from copy import deepcopy

import pytest

from tabletwall import grid
from tabletwall.tablet_models import BUILTINS

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
D = "44444444-4444-4444-8444-444444444444"
E = "55555555-5555-4555-8555-555555555555"
ALL = (A, B, C, D)
AIR = BUILTINS["ipad-air-2"]
PIXEL = BUILTINS["google-pixel-c"]
AIR_BODY = (
    AIR["active_width_mm"] + AIR["bezels"]["left"] + AIR["bezels"]["right"],
    AIR["active_height_mm"] + AIR["bezels"]["top"] + AIR["bezels"]["bottom"],
)
PIXEL_BODY = (
    PIXEL["active_width_mm"] + PIXEL["bezels"]["left"] + PIXEL["bezels"]["right"],
    PIXEL["active_height_mm"] + PIXEL["bezels"]["top"] + PIXEL["bezels"]["bottom"],
)


def viewport(model, orientation=0):
    width, height = model["screen_width"], model["screen_height"]
    if orientation in (90, 270):
        width, height = height, width
    return {
        "width": width,
        "height": height,
        "dpr": model["dpr"],
        "orientation": orientation,
        "mode": "fullscreen",
    }


def profile(model, revision=1, provenance="tablet-model"):
    return {
        "revision": revision,
        "active_width_mm": model["active_width_mm"],
        "active_height_mm": model["active_height_mm"],
        "bezels": dict(model["bezels"]),
        "provenance": provenance,
        "label": model["label"],
    }


def calibration(model, revision=1, orientation=0):
    live = viewport(model, orientation)
    return {
        "revision": revision,
        "profile_revision": revision,
        "method": "tablet-model approximate",
        "uncertainty_mm": 3.0,
        "viewport_width": live["width"],
        "viewport_height": live["height"],
        "dpr": live["dpr"],
        "orientation": orientation,
        "mode": "fullscreen",
    }


def make_device(
    device_id,
    model=None,
    *,
    online=True,
    orientation=0,
    revision=1,
    provenance="tablet-model",
    confirm_model=True,
    with_viewport=True,
    viewport_value=None,
):
    live = (
        viewport_value
        if viewport_value is not None
        else (viewport(model, orientation) if with_viewport and model else None)
    )
    if model is None:
        return grid.GridDevice(
            device_id, online, f"conn-{device_id[:8]}" if online else None, live
        )
    return grid.GridDevice(
        device_id,
        online,
        f"conn-{device_id[:8]}" if online else None,
        live,
        {revision: profile(model, revision, provenance)},
        {revision: calibration(model, revision, orientation)},
        model if confirm_model else None,
    )


def logical_inputs(devices, active=None, etag="etag-1"):
    return grid.GridInputs(
        active_layout=active
        or {"kind": "logical", "width": 1000, "height": 1000, "placements": {}},
        devices=devices,
        base_etag=etag,
    )


def command_payload(**overrides):
    payload = {
        "kind": "logical",
        "device_ids": list(ALL),
        "rows": 2,
        "columns": 2,
        "gap": 0,
        "padding": 0,
        "sizing": "tablets",
        "orientation": "preserve",
        "allow_empty_cells": False,
        "release_unselected": [],
    }
    payload.update(overrides)
    return payload


def command(**overrides):
    return grid.GridCommand.from_payload(command_payload(**overrides))


def pins(*device_ids, revision=1):
    return {
        device_id: {
            "profile_revision": revision,
            "calibration_revision": revision,
        }
        for device_id in device_ids
    }


def logical_active(placements=None, width=1000, height=1000):
    return {
        "kind": "logical",
        "width": width,
        "height": height,
        "placements": placements or {},
    }


def placement(device_id, width, height, bezel=None):
    return {
        "device_id": device_id,
        "x": 0,
        "y": 0,
        "w": width,
        "h": height,
        "bezel": bezel
        or {"left": 0, "top": 0, "right": 0, "bottom": 0},
    }


def invalid(call):
    with pytest.raises(grid.GridError) as caught:
        call()
    assert caught.value.status == 422
    return caught.value


# ---------------------------------------------------------------------------
# logical layouts
# ---------------------------------------------------------------------------


def test_logical_2x2_preserves_footprints_and_uses_submitted_order():
    footprints = {
        A: placement(A, 120, 90, {"left": 2, "top": 3, "right": 4, "bottom": 5}),
        B: placement(B, 100, 100),
        C: placement(C, 80, 70),
        D: placement(D, 60, 50),
    }
    order = [C, A, D, B]
    preview = grid.build_grid(
        command(
            device_ids=order,
            gap=10,
            padding=5,
            orientation="preserve",
        ),
        logical_inputs(
            [make_device(device_id, AIR) for device_id in ALL],
            active=logical_active(footprints),
        ),
    )
    layout = preview["layout"]
    assert preview["order"] == order
    assert list(layout["placements"]) == order
    assert preview["previous_kind"] == "logical"
    assert layout["kind"] == "logical"
    assert layout["sizing"] == {"mode": "tablets", "padding": 5}
    assert layout["width"] == 220
    assert layout["height"] == 210
    assert [
        (layout["placements"][device_id]["x"], layout["placements"][device_id]["y"])
        for device_id in order
    ] == [(5, 5), (95, 5), (5, 105), (75, 105)]
    assert layout["placements"][A]["bezel"] == {
        "left": 2, "top": 3, "right": 4, "bottom": 5
    }
    assert layout["placements"][B]["w"] == 100
    assert preview["reservations_removed"] == []


def test_logical_1x4_is_one_row_of_four_columns():
    preview = grid.build_grid(
        command(
            device_ids=ALL,
            rows=1,
            columns=4,
            gap=4,
            padding=2,
            logical_sizes={device_id: {"w": 10, "h": 20} for device_id in ALL},
        ),
        logical_inputs([make_device(device_id, AIR) for device_id in ALL]),
    )
    placements = preview["layout"]["placements"]
    assert [placements[device_id]["x"] for device_id in ALL] == [2, 16, 30, 44]
    assert {placements[device_id]["y"] for device_id in ALL} == {2}
    assert preview["layout"]["width"] == 56
    assert preview["layout"]["height"] == 24


def test_logical_sizes_are_suggested_only_when_needed():
    preview = grid.build_grid(
        command(
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="preserve",
        ),
        logical_inputs([make_device(A, AIR)]),
    )
    suggested = preview["layout"]["placements"][A]
    assert (suggested["w"], suggested["h"]) == (75, 100)
    assert any("suggested from the live viewport" in warning for warning in preview["warnings"])

    explicit = grid.build_grid(
        command(
            device_ids=[A],
            rows=1,
            columns=1,
            logical_sizes={A: {"w": 50, "h": 80}},
        ),
        logical_inputs([make_device(A, AIR)]),
    )
    assert (explicit["layout"]["placements"][A]["w"],
            explicit["layout"]["placements"][A]["h"]) == (50, 80)
    assert not any("suggested from the live viewport" in warning
                   for warning in explicit["warnings"])


def test_logical_orientation_presets_swap_only_suggestions():
    portrait = grid.build_grid(
        command(device_ids=[A], rows=1, columns=1, orientation="portrait"),
        logical_inputs([make_device(A, AIR, orientation=90)]),
    )
    assert (portrait["layout"]["placements"][A]["w"],
            portrait["layout"]["placements"][A]["h"]) == (75, 100)
    landscape = grid.build_grid(
        command(device_ids=[A], rows=1, columns=1, orientation="landscape"),
        logical_inputs([make_device(A, AIR, orientation=0)]),
    )
    assert (landscape["layout"]["placements"][A]["w"],
            landscape["layout"]["placements"][A]["h"]) == (100, 75)


def test_logical_requires_a_size_or_live_viewport():
    offline = grid.GridDevice(A, False, None, None)
    invalid(
        lambda: grid.build_grid(
            command(device_ids=[A], rows=1, columns=1),
            logical_inputs([offline]),
        )
    )


def test_logical_fixed_keeps_current_logical_bounds_and_warns():
    preview = grid.build_grid(
        command(
            device_ids=[A, B],
            rows=1,
            columns=2,
            sizing="fixed",
            orientation="preserve",
        ),
        logical_inputs(
            [make_device(device_id, AIR) for device_id in ALL],
            active=logical_active(
                {A: placement(A, 120, 90), B: placement(B, 120, 90)},
                width=200,
                height=150,
            ),
        ),
    )
    assert preview["layout"]["width"] == 200
    assert preview["layout"]["height"] == 150
    assert any("outside the fixed bounds" in warning for warning in preview["warnings"])


def test_logical_fixed_refuses_to_borrow_physical_bounds():
    active = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 300.0, "height": 200.0},
        "slots": {},
        "sizing": {"mode": "tablets", "padding": 0.0},
    }
    invalid(
        lambda: grid.build_grid(
            command(
                device_ids=[A],
                rows=1,
                columns=1,
                sizing="fixed",
                logical_sizes={A: {"w": 10, "h": 10}},
            ),
            logical_inputs([make_device(A, AIR)], active=active),
        )
    )


# ---------------------------------------------------------------------------
# physical layouts
# ---------------------------------------------------------------------------


def test_physical_2x2_packs_measured_bodies_without_extra_bezels():
    ids = [B, D, A, C]
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=ids,
            orientation="auto",
            physical_revisions=pins(*ids),
        ),
        logical_inputs([make_device(device_id, AIR) for device_id in ids]),
    )
    layout = preview["layout"]
    assert preview["order"] == ids
    assert list(layout["slots"]) == ids
    assert layout["kind"] == "physical"
    assert layout["bounds"]["width"] == pytest.approx(AIR_BODY[0] * 2)
    assert layout["bounds"]["height"] == pytest.approx(AIR_BODY[1] * 2)
    slot = layout["slots"][B]
    assert slot["center_x_mm"] == pytest.approx(AIR_BODY[0] / 2)
    assert slot["center_y_mm"] == pytest.approx(AIR_BODY[1] / 2)
    assert slot["mount_angle"] == 0
    assert layout["slots"][D]["center_x_mm"] == pytest.approx(AIR_BODY[0] * 1.5)
    assert layout["slots"][A]["center_y_mm"] == pytest.approx(AIR_BODY[1] * 1.5)
    assert preview["previous_kind"] == "logical"
    assert any("estimated measurement" in warning for warning in preview["warnings"])
    assert len(preview["guards"]) == 4


def test_physical_gap_and_nudges_pack_effective_bodies():
    active = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 300.0, "height": 300.0},
        "slots": {
            A: {
                "center_x_mm": 10.0,
                "center_y_mm": 10.0,
                "mount_angle": 90,
                "nudge_x_mm": 5.0,
                "nudge_y_mm": -3.0,
                "profile_revision": 1,
                "calibration_revision": 1,
                "participating": False,
            }
        },
        "sizing": {"mode": "tablets", "padding": 0.0},
    }
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            gap=10,
            padding=20,
            orientation="preserve",
            physical_revisions=pins(A),
        ),
        logical_inputs([make_device(A, AIR)], active=active),
    )
    packed_width, packed_height = AIR_BODY[1], AIR_BODY[0]
    slot = preview["layout"]["slots"][A]
    assert slot["nudge_x_mm"] == 5.0
    assert slot["nudge_y_mm"] == -3.0
    assert slot["participating"] is False
    assert slot["center_x_mm"] == pytest.approx(packed_width / 2 - 5.0)
    assert slot["center_y_mm"] == pytest.approx(packed_height / 2 + 3.0)
    assert preview["layout"]["bounds"] == {
        "x": pytest.approx(-20.0),
        "y": pytest.approx(-20.0),
        "width": pytest.approx(packed_width + 40.0),
        "height": pytest.approx(packed_height + 40.0),
    }


def test_physical_1x4_is_one_row_of_four_columns():
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=ALL,
            rows=1,
            columns=4,
            gap=5,
            orientation="auto",
            mount_angles={device_id: 90 for device_id in ALL},
            physical_revisions=pins(*ALL),
        ),
        logical_inputs([make_device(device_id, AIR) for device_id in ALL]),
    )
    slots = preview["layout"]["slots"]
    assert [slots[device_id]["mount_angle"] for device_id in ALL] == [90, 90, 90, 90]
    assert [slots[device_id]["center_x_mm"] for device_id in ALL] == pytest.approx(
        [AIR_BODY[1] / 2 + index * (AIR_BODY[1] + 5) for index in range(4)]
    )
    assert all(
        slots[device_id]["center_y_mm"] == pytest.approx(AIR_BODY[0] / 2)
        for device_id in ALL
    )
    assert preview["layout"]["bounds"]["width"] == pytest.approx(
        AIR_BODY[1] * 4 + 15
    )
    assert preview["layout"]["bounds"]["height"] == pytest.approx(AIR_BODY[0])


@pytest.mark.parametrize("model", [AIR, PIXEL], ids=["air2", "pixel-c"])
@pytest.mark.parametrize("orientation", [0, 90, 180, 270])
def test_physical_auto_quarter_turn_for_both_models(model, orientation):
    expected = (360 - 90 * (((model["portrait_angle"] - orientation) // 90) % 4)) % 360
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="auto",
            physical_revisions=pins(A),
        ),
        logical_inputs([make_device(A, model, orientation=orientation)]),
    )
    assert preview["layout"]["slots"][A]["mount_angle"] == expected


def test_physical_mixed_models_use_distinct_auto_angles_and_warn():
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A, B],
            rows=1,
            columns=2,
            orientation="auto",
            physical_revisions=pins(A, B),
        ),
        logical_inputs([make_device(A, AIR), make_device(B, PIXEL)]),
    )
    slots = preview["layout"]["slots"]
    assert slots[A]["mount_angle"] == 0
    assert slots[B]["mount_angle"] == 90
    assert preview["layout"]["bounds"]["width"] == pytest.approx(
        AIR_BODY[0] + PIXEL_BODY[1]
    )
    assert any("mixed body sizes" in warning for warning in preview["warnings"])


def test_physical_explicit_mount_overrides_auto_even_offline():
    device = make_device(A, AIR, online=False, with_viewport=False)
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="auto",
            mount_angles={A: 180},
            physical_revisions=pins(A),
        ),
        logical_inputs([device]),
    )
    assert preview["layout"]["slots"][A]["mount_angle"] == 180


@pytest.mark.parametrize(
    "device",
    [
        make_device(A, AIR, online=False, with_viewport=False),
        make_device(A, AIR, confirm_model=False),
        grid.GridDevice(
            A,
            True,
            "conn-a",
            None,
            {1: profile(AIR)},
            {1: calibration(AIR)},
            AIR,
        ),
    ],
    ids=["offline", "unconfirmed-model", "no-viewport"],
)
def test_physical_auto_requires_live_viewport_and_confirmed_model(device):
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                orientation="auto",
                physical_revisions=pins(A),
            ),
            logical_inputs([device]),
        )
    )


def test_physical_preserve_requires_existing_or_explicit_mount():
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                orientation="preserve",
                physical_revisions=pins(A),
            ),
            logical_inputs([make_device(A, AIR)]),
        )
    )
    offline = make_device(A, AIR, online=False, with_viewport=False)
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="preserve",
            mount_angles={A: 270},
            physical_revisions=pins(A),
        ),
        logical_inputs([offline]),
    )
    assert preview["layout"]["slots"][A]["mount_angle"] == 270

    active = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 300.0, "height": 300.0},
        "slots": {
            A: {
                "center_x_mm": 100.0,
                "center_y_mm": 100.0,
                "mount_angle": 270,
                "nudge_x_mm": 0.0,
                "nudge_y_mm": 0.0,
                "profile_revision": 1,
                "calibration_revision": 1,
                "participating": True,
            }
        },
    }
    preserved = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="preserve",
            physical_revisions=pins(A),
        ),
        logical_inputs([offline], active=active),
    )
    assert preserved["layout"]["slots"][A]["mount_angle"] == 270


def test_physical_portrait_landscape_needs_a_compatible_angle():
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                orientation="landscape",
                physical_revisions=pins(A),
            ),
            logical_inputs([make_device(A, AIR)]),
        )
    )
    explicit = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="landscape",
            mount_angles={A: 90},
            physical_revisions=pins(A),
        ),
        logical_inputs([make_device(A, AIR)]),
    )
    assert explicit["layout"]["slots"][A]["mount_angle"] == 90

    active = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 300.0, "height": 300.0},
        "slots": {
            A: {
                "center_x_mm": 100.0,
                "center_y_mm": 100.0,
                "mount_angle": 90,
                "nudge_x_mm": 0.0,
                "nudge_y_mm": 0.0,
                "profile_revision": 1,
                "calibration_revision": 1,
                "participating": True,
            }
        },
    }
    retained = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A],
            rows=1,
            columns=1,
            orientation="landscape",
            physical_revisions=pins(A),
        ),
        logical_inputs(
            [make_device(A, AIR, confirm_model=False)],
            active=active,
        ),
    )
    assert retained["layout"]["slots"][A]["mount_angle"] == 90


def test_physical_fixed_uses_only_current_physical_bounds():
    active = {
        "kind": "physical",
        "bounds": {"x": 100.0, "y": 50.0, "width": 300.0, "height": 200.0},
        "slots": {},
        "sizing": {"mode": "tablets", "padding": 0.0},
    }
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A, B],
            rows=1,
            columns=2,
            sizing="fixed",
            mount_angles={A: 0, B: 0},
            physical_revisions=pins(A, B),
        ),
        logical_inputs([make_device(A, AIR), make_device(B, AIR)], active=active),
    )
    assert preview["layout"]["bounds"] == {
        "x": 100.0, "y": 50.0, "width": 300.0, "height": 200.0
    }
    assert preview["layout"]["slots"][A]["center_x_mm"] == pytest.approx(
        100 + AIR_BODY[0] / 2
    )
    outside = next(
        warning for warning in preview["warnings"]
        if "outside the fixed bounds" in warning
    )
    assert A in outside and B in outside


def test_physical_fixed_refuses_to_borrow_logical_bounds():
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                sizing="fixed",
                mount_angles={A: 0},
                physical_revisions=pins(A),
            ),
            logical_inputs([make_device(A, AIR)]),
        )
    )


# ---------------------------------------------------------------------------
# reservations and holes
# ---------------------------------------------------------------------------


def test_trailing_holes_require_explicit_acknowledgement():
    devices = [make_device(device_id, AIR) for device_id in ALL]
    invalid(
        lambda: grid.build_grid(
            command(device_ids=[A, B, C], rows=2, columns=2),
            logical_inputs(devices),
        )
    )
    preview = grid.build_grid(
        command(
            device_ids=[A, B, C],
            rows=2,
            columns=2,
            allow_empty_cells=True,
        ),
        logical_inputs(devices),
    )
    assert preview["layout"]["placements"][C]["x"] == 0
    assert preview["layout"]["placements"][C]["y"] == 100
    assert any("1 empty trailing cell" in warning for warning in preview["warnings"])


def test_unselected_active_reservations_require_exact_release():
    active = logical_active(
        {
            A: placement(A, 10, 10),
            B: placement(B, 10, 10),
            C: placement(C, 10, 10),
            D: placement(D, 10, 10),
        }
    )
    devices = [make_device(device_id, AIR) for device_id in ALL]
    with pytest.raises(grid.GridError) as caught:
        grid.build_grid(
            command(device_ids=[A, B], rows=1, columns=2),
            logical_inputs(devices, active=active),
        )
    assert caught.value.status == 409
    assert caught.value.code == grid.CONFLICT
    assert [item["device_id"] for item in caught.value.conflicts] == [C, D]

    preview = grid.build_grid(
        command(
            device_ids=[A, B],
            rows=1,
            columns=2,
            release_unselected=[D, C],
        ),
        logical_inputs(devices, active=active),
    )
    assert preview["reservations_removed"] == [C, D]

    with pytest.raises(grid.GridError) as caught:
        grid.build_grid(
            command(device_ids=[A, B], rows=1, columns=2, release_unselected=[C]),
            logical_inputs(devices, active=active),
        )
    assert caught.value.status == 409
    assert [item["device_id"] for item in caught.value.conflicts] == [D]

    invalid(
        lambda: grid.build_grid(
            command(
                device_ids=[A, B],
                rows=1,
                columns=2,
                release_unselected=[C, D, E],
            ),
            logical_inputs(devices, active=active),
        )
    )
    invalid(
        lambda: command(
            device_ids=[A, B],
            rows=1,
            columns=2,
            release_unselected=[A],
        )
    )


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def test_preview_guards_are_complete_and_exact():
    devices = [make_device(A, AIR), make_device(B, AIR)]
    inputs = logical_inputs(devices)
    preview = grid.build_grid(
        command(device_ids=[B, A], rows=1, columns=2), inputs
    )
    guards = preview["guards"]
    assert list(guards) == [B, A]
    assert guards[A] == {
        "connection_id": f"conn-{A[:8]}",
        "viewport": {
            "width": 768.0,
            "height": 1024.0,
            "dpr": 2.0,
            "orientation": 0,
            "mode": "fullscreen",
            "visual_scale": None,
        },
    }
    grid.validate_guards(guards, grid.connection_guards(inputs, [B, A]))


def test_validate_guards_rejects_changes_with_412():
    devices = [make_device(A, AIR), make_device(B, AIR)]
    inputs = logical_inputs(devices)
    preview = grid.build_grid(command(device_ids=[A, B], rows=1, columns=2), inputs)

    changed_viewport = [
        make_device(A, AIR, viewport_value={
            **viewport(AIR), "width": 800.0,
        }),
        make_device(B, AIR),
    ]
    with pytest.raises(grid.GridError) as caught:
        grid.validate_guards(
            preview["guards"],
            grid.connection_guards(logical_inputs(changed_viewport), [A, B]),
        )
    assert caught.value.status == 412
    assert caught.value.code == grid.GUARD_CHANGED
    assert caught.value.conflicts == [{"device_id": A, "fields": ["viewport"]}]

    changed_connection = [
        grid.GridDevice(
            A, True, "other-connection", viewport(AIR),
            {1: profile(AIR)}, {1: calibration(AIR)}, AIR,
        ),
        make_device(B, AIR),
    ]
    with pytest.raises(grid.GridError) as caught:
        grid.validate_guards(
            preview["guards"],
            grid.connection_guards(logical_inputs(changed_connection), [A, B]),
        )
    assert caught.value.conflicts == [
        {"device_id": A, "fields": ["connection_id"]}
    ]

    with pytest.raises(grid.GridError) as caught:
        grid.validate_guards(
            {}, grid.connection_guards(inputs, [A, B])
        )
    assert caught.value.status == 412
    assert {item["device_id"] for item in caught.value.conflicts} == {A, B}


def test_preview_uses_current_guards_not_submitted_ones():
    devices = [make_device(A, AIR), make_device(B, AIR)]
    inputs = logical_inputs(devices)
    current = grid.connection_guards(inputs, [A, B])
    stale = {
        A: {"connection_id": "stale", "viewport": None},
        B: {"connection_id": "stale", "viewport": None},
    }
    preview = grid.build_grid(
        command(
            device_ids=[A, B],
            rows=1,
            columns=2,
            guards=stale,
        ),
        inputs,
    )
    assert preview["guards"] == current


# ---------------------------------------------------------------------------
# strict command and input behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {**command_payload(), "extra": True},
        {key: value for key, value in command_payload().items() if key != "rows"},
        command_payload(device_ids=[]),
        command_payload(device_ids=[A, A, B, C]),
        command_payload(rows=True),
        command_payload(rows=2.0),
        command_payload(gap=True),
        command_payload(gap=float("nan")),
        command_payload(padding=-1),
        command_payload(device_ids=[A, B, C], rows=1, columns=2),
        command_payload(kind="logical", mount_angles={A: 90}),
        command_payload(kind="logical", physical_revisions=pins(A)),
        command_payload(kind="physical", logical_sizes={A: {"w": 1, "h": 1}},
                        physical_revisions=pins(*ALL)),
        command_payload(logical_sizes={E: {"w": 1, "h": 1}}),
        command_payload(logical_sizes={A: {"w": True, "h": 1}}),
        command_payload(guards={
            A: {"connection_id": "c", "viewport": {
                "width": True, "height": 1, "dpr": 1,
                "orientation": 0, "mode": "fullscreen",
            }},
        }),
    ],
)
def test_strict_command_rejections(payload):
    invalid(lambda: grid.GridCommand.from_payload(payload))


def test_logical_gap_and_padding_are_whole_units():
    command(gap=1.0, padding=2.0)
    invalid(lambda: command(gap=1.5))
    invalid(lambda: command(padding=0.5))


def test_unknown_selected_device_is_rejected():
    invalid(
        lambda: grid.build_grid(
            command(device_ids=[E], rows=1, columns=1),
            logical_inputs([make_device(A, AIR)]),
        )
    )


def test_direct_typed_construction_normalizes_pins_and_size_pairs():
    physical = grid.GridCommand(
        kind="physical",
        device_ids=(A,),
        rows=1,
        columns=1,
        gap=0,
        padding=0,
        sizing="tablets",
        orientation="auto",
        allow_empty_cells=False,
        release_unselected=(),
        physical_revisions={A: grid.MeasurementPins(1, 2)},
    )
    assert physical.physical_revisions[A] == grid.MeasurementPins(1, 2)
    logical = grid.GridCommand(
        kind="logical",
        device_ids=(A,),
        rows=1,
        columns=1,
        gap=0,
        padding=0,
        sizing="tablets",
        orientation="preserve",
        allow_empty_cells=False,
        release_unselected=(),
        logical_sizes={A: (10, 20)},
    )
    assert logical.logical_sizes[A] == (10, 20)


def test_confirmed_model_only_trusts_explicit_assignments():
    assert grid.confirmed_model(
        {"mode": "explicit", "model": dict(AIR)}
    ) == AIR
    assert grid.confirmed_model({"mode": "auto", "model": dict(AIR)}) is None
    assert grid.confirmed_model({"mode": "explicit", "model": None}) is None
    assert grid.confirmed_model(None) is None


def test_missing_or_incomplete_pins_are_rejected():
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                orientation="auto",
            ),
            logical_inputs([make_device(A, AIR)]),
        )
    )
    device = grid.GridDevice(
        A, True, "conn-a", viewport(AIR),
        {1: profile(AIR, provenance="manual")},
        {}, AIR,
    )
    invalid(
        lambda: grid.build_grid(
            command(
                kind="physical",
                device_ids=[A],
                rows=1,
                columns=1,
                orientation="auto",
                physical_revisions=pins(A),
            ),
            logical_inputs([device]),
        )
    )


def test_inputs_and_command_are_not_mutated_by_build():
    payload = command_payload(
        kind="physical",
        device_ids=[B, A],
        rows=1,
        columns=2,
        orientation="auto",
        physical_revisions=pins(A, B),
    )
    active = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 300.0, "height": 300.0},
        "slots": {
            A: {
                "center_x_mm": 100.0,
                "center_y_mm": 100.0,
                "mount_angle": 0,
                "nudge_x_mm": 1.0,
                "nudge_y_mm": 2.0,
                "profile_revision": 1,
                "calibration_revision": 1,
                "participating": True,
            }
        },
    }
    devices = [make_device(A, AIR), make_device(B, AIR)]
    before = deepcopy((payload, active, devices))
    parsed = grid.GridCommand.from_payload(payload)
    inputs = grid.GridInputs(active_layout=active, devices=devices, base_etag="e")
    first = grid.build_grid(parsed, inputs)
    saved = deepcopy(first)
    assert deepcopy(payload) == before[0]
    assert deepcopy(active) == before[1]
    assert [device.device_id for device in before[2]] == [A, B]

    first["layout"]["slots"][A]["center_x_mm"] = -999.0
    first["warnings"].append("changed")
    second = grid.build_grid(parsed, inputs)
    assert second == saved


def test_preview_is_json_ready():
    preview = grid.build_grid(
        command(
            kind="physical",
            device_ids=[A, B],
            rows=1,
            columns=2,
            orientation="auto",
            physical_revisions=pins(A, B),
        ),
        logical_inputs([make_device(A, AIR), make_device(B, PIXEL)]),
    )
    encoded = json.dumps(preview)
    assert json.loads(encoded)["base_etag"] == "etag-1"
    assert json.loads(encoded)["order"] == [A, B]
