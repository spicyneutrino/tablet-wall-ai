"""Detached lifecycle proposals, without a database or socket engine."""

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

from tabletwall.device_lifecycle import (
    ForgetCommand,
    IdentifyCommand,
    LabelCommand,
    LifecycleError,
    RebindApply,
    RebindCommand,
    RebindInputs,
    SavedLayout,
    identify_remaining_ms,
    normalize_label,
    plan_forget,
    plan_rebind,
    plan_remove,
    preview_impact,
    preview_rebind,
)

OLD = "0f8fad5b-d9cb-469f-a165-70867728950e"
NEW = "1f8fad5b-d9cb-469f-a165-70867728950e"
OTHER = "2f8fad5b-d9cb-469f-a165-70867728950e"


def logical(device: str = OLD) -> dict[str, Any]:
    return {
        "kind": "logical",
        "width": 2000,
        "height": 1000,
        "sizing": {"mode": "tablets", "padding": 17},
        "placements": {
            device: {
                "device_id": device,
                "x": -12,
                "y": 32,
                "w": 1000,
                "h": 1000,
                "bezel": {"top": 3, "bottom": 7, "left": 8, "right": 9},
            }
        },
    }


def physical(
    profile: int = 1, calibration: int = 1, device: str = OLD
) -> dict[str, Any]:
    return {
        "kind": "physical",
        "bounds": {"x": -43.0, "y": 17.0, "width": 500.0, "height": 250.0},
        "sizing": {"mode": "tablets", "padding": 3.25},
        "slots": {
            device: {
                "profile_revision": profile,
                "calibration_revision": calibration,
                "center_x_mm": -10.25,
                "center_y_mm": 20.5,
                "mount_angle": 90.0,
                "nudge_x_mm": 1.2,
                "nudge_y_mm": -3.1,
                "participating": False,
            }
        },
    }


def profile(device: str, revision: int, provenance: str = "manual") -> dict[str, Any]:
    return {
        "device_id": device,
        "revision": revision,
        "active_width_mm": 100 + revision,
        "active_height_mm": 200,
        "bezels": {"top": 1, "bottom": 2, "left": 3, "right": 4},
        "panel_pixels": {"width": 600, "height": 800},
        "provenance": provenance,
        "label": "Profile, not roster name",
        "created_at": "historical",
    }


def calibration(
    device: str, revision: int, profile_revision: int, method: str = "ruler"
) -> dict[str, Any]:
    return {
        "device_id": device,
        "revision": revision,
        "profile_revision": profile_revision,
        "method": method,
        "viewport_width": 600,
        "viewport_height": 800,
        "mm_per_css": [0.2, 0.3],
        "created_at": "historical",
    }


def model_snapshot(
    profile_revision: int, calibration_revision: int, mode: str = "auto"
) -> dict[str, Any]:
    return {
        "mode": mode,
        "model_id": "historical-model",
        "profile_revision": profile_revision,
        "calibration_revision": calibration_revision,
        "model": {"label": "Archived model", "mm_per_css": [0.2, 0.3], "extra": [1, 2]},
    }


@pytest.fixture
def inputs() -> RebindInputs:
    return RebindInputs(
        base_etag='"config-1"',
        new_id=NEW,
        roster={
            OLD: {"number": 7, "label": "Old tablet", "device_id": OLD},
            NEW: {
                "number": 8,
                "label": "Replacement",
                "device_id": NEW,
                "caps": ["image"],
            },
            OTHER: {"number": 9, "label": None},
        },
        connections={NEW: "connection-new"},
        active_layout=logical(),
        saved_layouts={
            "logical": SavedLayout('"logical-1"', logical()),
            "physical-old": SavedLayout('"physical-1"', physical()),
            "physical-new": SavedLayout('"physical-2"', physical(3, 5)),
            "unselected": SavedLayout('"unselected-1"', physical(3, 5)),
        },
        profiles={OLD: {1: profile(OLD, 1), 3: profile(OLD, 3)}},
        calibrations={OLD: {1: calibration(OLD, 1, 1), 5: calibration(OLD, 5, 3)}},
        assignments={OLD: model_snapshot(3, 5, "explicit")},
        model_history={
            OLD: {
                "1": model_snapshot(1, 1, "explicit"),
                "5": model_snapshot(3, 5, "explicit"),
            }
        },
    )


def command(inputs: RebindInputs, **changes: Any) -> RebindApply:
    data: dict[str, Any] = {
        "replaces": OLD,
        "hardware": "same_hardware",
        "active": True,
        "saved_layouts": [
            {"name": name, "etag": snapshot.etag}
            for name, snapshot in inputs.saved_layouts.items()
            if name != "unselected"
        ],
        "transfer_label": True,
        "new_connection_id": inputs.connections.get(NEW),
    }
    data.update(changes)
    return RebindApply.model_validate(data)


def test_rebind_refuses_negative_bezel_in_selected_snapshot(inputs):
    inputs.saved_layouts["logical"].layout["placements"][OLD]["bezel"]["left"] = -8
    with pytest.raises(LifecycleError) as caught:
        plan_rebind(command(inputs), inputs)
    assert caught.value.code == "damaged_layout"


def assert_error(status: int, code: str, function: Any, *args: Any) -> LifecycleError:
    with pytest.raises(LifecycleError) as caught:
        function(*args)
    assert caught.value.status == status
    assert caught.value.code == code
    assert caught.value.detail["message"]
    return caught.value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("  North wall ☕  ", "North wall ☕"),
        ("<script>alert('x')</script>&\"", "<script>alert('x')</script>&\""),
        ("界" * 80, "界" * 80),
        ("🙂" * 80, "🙂" * 80),
    ],
)
def test_label_normalization_keeps_text_as_data(raw, expected):
    assert normalize_label(raw) == expected
    assert LabelCommand(label=raw).label == expected


@pytest.mark.parametrize(
    "raw",
    [
        "界" * 81,
        "x\n",
        "\tx",
        "a\x00b",
        "a\x7fb",
        "a\x85b",
        "a\u202eb",
        "\ud800",
        True,
        12,
        [],
    ],
)
def test_label_rejects_controls_even_in_outer_whitespace(raw):
    assert_error(422, "invalid_label", normalize_label, raw)
    with pytest.raises(ValidationError):
        LabelCommand(label=raw)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (LabelCommand, {"label": "ok", "unknown": 1}),
        (ForgetCommand, {"remove_active": 1, "saved_layouts": "keep"}),
        (ForgetCommand, {"remove_active": True, "saved_layouts": "delete"}),
        (
            ForgetCommand,
            {"remove_active": True, "saved_layouts": "keep", "extra": False},
        ),
        (IdentifyCommand, {"duration_ms": True}),
        (IdentifyCommand, {"duration_ms": "5000"}),
        (IdentifyCommand, {"duration_ms": 999}),
        (IdentifyCommand, {"duration_ms": 10001}),
        (IdentifyCommand, {"duration_ms": 5000, "extra": 1}),
    ],
)
def test_requests_are_strict(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"active": 1},
        {"transfer_label": "yes"},
        {"number": True},
        {"number": 0},
        {"number": 1.0},
        {"replaces": True},
        {"replaces": "unknown"},
        {"replaces": "0f8fad5b-d9cb-169f-a165-70867728950e"},
        {"hardware": "guessed"},
        {"saved_layouts": "all"},
        {"unknown": 1},
        {"saved_layouts": [{"name": "logical", "etag": '"logical-1"', "extra": 1}]},
        {
            "saved_layouts": [
                {"name": "logical", "etag": "a"},
                {"name": "logical", "etag": "a"},
            ]
        },
    ],
)
def test_rebind_rejects_coercion_unknown_fields_and_implicit_selection(inputs, changes):
    with pytest.raises(ValidationError):
        command(inputs, **changes)


def test_apply_requires_explicit_connection_guard_including_null(inputs):
    data = command(inputs).model_dump()
    data.pop("new_connection_id")
    with pytest.raises(ValidationError):
        RebindApply.model_validate(data)
    preview_command = RebindCommand.model_validate(data)
    assert preview_rebind(preview_command, inputs).new_connection_id == "connection-new"
    offline = replace(inputs, connections={})
    assert plan_rebind(command(offline), offline).preview.new_connection_id is None


@pytest.mark.parametrize("active", [logical(), physical()])
def test_impact_and_forget_preserve_all_saved_and_measurement_reservations(
    inputs, active
):
    inputs = replace(inputs, active_layout=active)
    before = deepcopy(inputs)
    impact = preview_impact(OLD, inputs)
    assert not impact.online
    assert impact.has_measurement_history
    assert (
        impact.active_entry
        == active["slots" if active["kind"] == "physical" else "placements"][OLD]
    )
    assert {s.name for s in impact.saved_layouts} == set(inputs.saved_layouts)
    assert_error(
        409,
        "active_removal_required",
        plan_forget,
        OLD,
        ForgetCommand(remove_active=False, saved_layouts="keep"),
        inputs,
    )
    plan = plan_forget(
        OLD, ForgetCommand(remove_active=True, saved_layouts="keep"), inputs
    )
    assert plan.active_changed and plan.delete_roster and plan.keep_measurement_history
    assert (
        OLD
        not in plan.active_layout[
            "slots" if active["kind"] == "physical" else "placements"
        ]
    )
    assert plan.remaining_saved == impact.saved_layouts
    assert inputs == before


def test_owned_socket_blocks_forget_and_rebind_despite_stale_roster(inputs):
    inputs.roster[OLD].update(online=False, last_seen="2000-01-01")
    inputs.connections[OLD] = "still-owned"
    assert preview_impact(OLD, inputs).online
    assert_error(
        409,
        "old_connected",
        plan_forget,
        OLD,
        ForgetCommand(remove_active=True, saved_layouts="keep"),
        inputs,
    )
    preview = preview_rebind(command(inputs), inputs)
    assert not preview.old_offline and preview.conflicts[0].code == "old_connected"
    assert_error(409, "old_connected", plan_rebind, command(inputs), inputs)


def test_history_alone_does_not_resurrect_forgotten_identity(inputs):
    forgotten = replace(
        inputs,
        roster={NEW: inputs.roster[NEW]},
        active_layout=logical(NEW),
        saved_layouts={},
    )
    assert_error(404, "unknown_device", preview_impact, OLD, forgotten)
    assert_error(404, "unknown_device", plan_rebind, command(forgotten), forgotten)
    reservation = replace(
        forgotten, saved_layouts={"saved": SavedLayout("digest", logical())}
    )
    assert preview_impact(OLD, reservation).has_measurement_history
    assert_error(
        409,
        "target_already_present",
        plan_rebind,
        command(
            reservation,
            active=False,
            saved_layouts=[{"name": "saved", "etag": "digest"}],
        ),
        reservation,
    )


def test_saved_only_identity_can_be_rebound_after_forget(inputs):
    inputs.roster.pop(OLD)
    inputs = replace(inputs, active_layout=logical(OTHER))
    plan = plan_rebind(command(inputs, active=False), inputs)
    assert plan.preview.number_after == 8
    assert plan.preview.label_after is None
    assert not plan.preview.affected_active


def test_remove_is_layout_only_and_does_not_recompute_tablet_sizing(inputs):
    before = deepcopy(inputs)
    plan = plan_remove(OLD, inputs)
    assert plan.active_changed
    expected = deepcopy(inputs.active_layout)
    expected["placements"].pop(OLD)
    assert plan.active_layout == expected
    assert inputs == before


def test_forget_without_active_needs_no_removal_acknowledgment(inputs):
    inputs = replace(inputs, active_layout=logical(OTHER))
    plan = plan_forget(
        OLD, ForgetCommand(remove_active=False, saved_layouts="keep"), inputs
    )
    assert not plan.active_changed
    assert len(plan.remaining_saved) == 4


def test_rebind_rewrites_mixed_selected_layouts_and_every_pinned_revision(inputs):
    before = deepcopy(inputs)
    plan = plan_rebind(command(inputs), inputs)
    assert plan.preview.profile_revision_map == {1: 1, 3: 3}
    assert plan.preview.calibration_revision_map == {1: 1, 5: 5}
    assert plan.measurements.required_profiles == (1, 3)
    assert plan.measurements.required_calibrations == (1, 5)
    assert plan.active_layout["placements"][NEW]["device_id"] == NEW
    assert OLD not in plan.active_layout["placements"]
    for name, rewritten in plan.selected_snapshots.items():
        original = deepcopy(inputs.saved_layouts[name].layout)
        bucket = "slots" if original["kind"] == "physical" else "placements"
        expected_entry = original[bucket].pop(OLD)
        if bucket == "placements":
            expected_entry["device_id"] = NEW
        original[bucket][NEW] = expected_entry
        assert rewritten == original
    assert [s.name for s in plan.preview.untouched_saved] == ["unselected"]
    assert "unselected" not in plan.selected_snapshots
    assert plan.target_record == {
        **inputs.roster[NEW],
        "number": 7,
        "label": "Old tablet",
    }
    assert plan.delete_roster_id == OLD
    assert inputs == before


def test_physical_active_with_logical_saved_reverse_kind_migration(inputs):
    inputs = replace(
        inputs,
        active_layout=physical(3, 5),
        saved_layouts={"logical": inputs.saved_layouts["logical"]},
    )
    plan = plan_rebind(command(inputs), inputs)
    assert OLD not in plan.active_layout["slots"] and NEW in plan.active_layout["slots"]
    assert plan.selected_snapshots["logical"]["placements"][NEW]["device_id"] == NEW
    assert plan.measurements.required_profiles == (3,)
    assert plan.measurements.required_calibrations == (5,)


def automatic_target(inputs: RebindInputs) -> None:
    inputs.profiles[NEW] = {2: profile(NEW, 2, "tablet-model")}
    inputs.calibrations[NEW] = {4: calibration(NEW, 4, 2, "tablet-model approximate")}
    inputs.assignments[NEW] = model_snapshot(2, 4)
    inputs.model_history[NEW] = {"4": model_snapshot(2, 4)}


def test_auto_target_offsets_map_all_rows_and_historical_model_snapshots(inputs):
    automatic_target(inputs)
    before = deepcopy(inputs)
    plan = plan_rebind(command(inputs), inputs)
    copy = plan.measurements
    assert (copy.profile_offset, copy.calibration_offset) == (2, 4)
    assert copy.profile_revision_map == {1: 3, 3: 5}
    assert copy.calibration_revision_map == {1: 5, 5: 9}
    assert (
        plan.selected_snapshots["physical-old"]["slots"][NEW]["calibration_revision"]
        == 5
    )
    assert (
        plan.selected_snapshots["physical-new"]["slots"][NEW]["profile_revision"] == 5
    )
    assert (
        plan.selected_snapshots["physical-new"]["slots"][NEW]["calibration_revision"]
        == 9
    )
    assert copy.model_history["5"]["profile_revision"] == 3
    assert copy.model_history["9"]["profile_revision"] == 5
    assert copy.model_history["5"]["model"] == inputs.model_history[OLD]["1"]["model"]
    assert copy.assignment["calibration_revision"] == 9
    assert inputs == before


@pytest.mark.parametrize(
    "damage",
    [
        "manual_assignment",
        "manual_profile",
        "manual_cal",
        "untracked_profile",
        "untracked_cal",
    ],
)
def test_target_manual_history_cannot_be_hidden_by_current_auto_assignment(
    inputs, damage
):
    automatic_target(inputs)
    if damage == "manual_assignment":
        inputs.assignments[NEW]["mode"] = "explicit"
    elif damage == "manual_profile":
        inputs.profiles[NEW][2]["provenance"] = "ruler"
    elif damage == "manual_cal":
        inputs.calibrations[NEW][4]["method"] = "ruler"
    elif damage == "untracked_profile":
        inputs.profiles[NEW][8] = profile(NEW, 8)
    else:
        inputs.calibrations[NEW][8] = calibration(NEW, 8, 2)
    assert (
        preview_rebind(command(inputs), inputs).conflicts[0].code
        == "target_history_conflict"
    )
    assert_error(409, "target_history_conflict", plan_rebind, command(inputs), inputs)


def test_target_history_without_assignment_conflicts(inputs):
    inputs.profiles[NEW] = {1: profile(NEW, 1)}
    assert_error(409, "target_history_conflict", plan_rebind, command(inputs), inputs)


@pytest.mark.parametrize(
    "changes", [{"new_id": OLD}, {"new_id": OTHER, "roster": {OLD: {}}}]
)
def test_rebind_requires_distinct_known_target(inputs, changes):
    inputs = replace(inputs, **changes)
    expected = (422, "self_rebind") if inputs.new_id == OLD else (404, "unknown_device")
    assert_error(*expected, plan_rebind, command(inputs), inputs)


@pytest.mark.parametrize(
    ("guard", "actual"), [(None, "new"), ("old", "new"), ("old", None)]
)
def test_changed_target_connection_is_precondition_failure(inputs, guard, actual):
    inputs.connections.clear()
    if actual is not None:
        inputs.connections[NEW] = actual
    assert_error(
        412,
        "connection_changed",
        plan_rebind,
        command(inputs, new_connection_id=guard),
        inputs,
    )


@pytest.mark.parametrize("active", [False, True])
def test_target_in_active_conflicts_even_if_active_is_excluded(inputs, active):
    inputs.active_layout["placements"][NEW] = logical(NEW)["placements"][NEW]
    assert_error(
        409,
        "target_already_present",
        plan_rebind,
        command(inputs, active=active),
        inputs,
    )


@pytest.mark.parametrize("name", ["logical", "physical-old"])
def test_target_in_selected_saved_conflicts(inputs, name):
    snapshot = inputs.saved_layouts[name].layout
    bucket = "slots" if snapshot["kind"] == "physical" else "placements"
    snapshot[bucket][NEW] = deepcopy(snapshot[bucket][OLD])
    if bucket == "slots":
        inputs.profiles[NEW] = {1: profile(NEW, 1)}
        inputs.calibrations[NEW] = {1: calibration(NEW, 1, 1)}
    else:
        snapshot[bucket][NEW]["device_id"] = NEW
    assert_error(409, "target_already_present", plan_rebind, command(inputs), inputs)


def test_unselected_target_collision_remains_untouched(inputs):
    inputs.saved_layouts["unselected"].layout["slots"][NEW] = physical(device=NEW)[
        "slots"
    ][NEW]
    plan = plan_rebind(command(inputs), inputs)
    assert "unselected" not in plan.selected_snapshots
    assert not plan.preview.untouched_saved[0].valid


def test_snapshot_digest_conflicts_and_missing_selection(inputs):
    assert_error(
        412,
        "snapshot_changed",
        plan_rebind,
        command(inputs, saved_layouts=[{"name": "logical", "etag": "old"}]),
        inputs,
    )
    assert_error(
        404,
        "unknown_snapshot",
        plan_rebind,
        command(inputs, saved_layouts=[{"name": "missing", "etag": "old"}]),
        inputs,
    )


@pytest.mark.parametrize(
    "damage",
    [
        "null",
        "wrong_kind_map",
        "missing_bounds",
        "bad_boolean",
        "bad_logical_id",
        "bad_sizing",
        "bad_revision",
    ],
)
def test_selected_damaged_snapshot_is_refused_and_unselected_stays_visible(
    inputs, damage
):
    name = "physical-old"
    broken = inputs.saved_layouts[name].layout
    if damage == "null":
        inputs.saved_layouts[name] = SavedLayout('"physical-1"', None)
    elif damage == "wrong_kind_map":
        broken["kind"] = "logical"
    elif damage == "missing_bounds":
        broken.pop("bounds")
    elif damage == "bad_boolean":
        broken["slots"][OLD]["participating"] = 1
    elif damage == "bad_logical_id":
        name = "logical"
        inputs.saved_layouts[name].layout["placements"][OLD]["device_id"] = NEW
    elif damage == "bad_sizing":
        broken["sizing"]["padding"] = True
    else:
        broken["slots"][OLD]["profile_revision"] = True
    with pytest.raises(LifecycleError) as caught:
        plan_rebind(command(inputs), inputs)
    assert caught.value.status == 422
    assert caught.value.details["name"] == name
    selected = [{"name": "physical-new", "etag": '"physical-2"'}]
    plan = plan_rebind(command(inputs, saved_layouts=selected), inputs)
    assert name not in plan.selected_snapshots


@pytest.mark.parametrize(
    "damage",
    [
        "missing_profile",
        "missing_calibration",
        "mismatch",
        "wrong_owner",
        "bad_model_history",
    ],
)
def test_missing_or_mismatched_history_refuses_without_mutation(inputs, damage):
    if damage == "missing_profile":
        del inputs.profiles[OLD][1]
    elif damage == "missing_calibration":
        del inputs.calibrations[OLD][1]
    elif damage == "mismatch":
        inputs.calibrations[OLD][1]["profile_revision"] = 3
    elif damage == "wrong_owner":
        inputs.profiles[OLD][1]["device_id"] = OTHER
    else:
        inputs.model_history[OLD]["1"]["profile_revision"] = 3
    before = deepcopy(inputs)
    with pytest.raises(LifecycleError) as caught:
        plan_rebind(command(inputs), inputs)
    assert caught.value.status == 422
    assert inputs == before


def test_explicit_number_and_label_choices(inputs):
    plan = plan_rebind(command(inputs, number=15, transfer_label=False), inputs)
    assert plan.target_record["label"] == "Replacement"
    assert plan.target_record["number"] == 15
    assert_error(409, "number_in_use", plan_rebind, command(inputs, number=9), inputs)


def test_label_markup_is_preserved_as_data_in_rebind(inputs):
    label = "<img src=x onerror=alert(1)>"
    inputs.roster[OLD]["label"] = label
    assert plan_rebind(command(inputs), inputs).preview.label_after == label


def test_different_hardware_refuses_all_selected_physical_layouts(inputs):
    inputs = replace(inputs, active_layout=physical())
    cmd = command(inputs, hardware="different_hardware")
    preview = preview_rebind(cmd, inputs)
    conflict = next(
        c for c in preview.conflicts if c.code == "physical_rebuild_required"
    )
    assert set(conflict.details["layouts"]) == {
        "active",
        "physical-old",
        "physical-new",
    }
    assert preview.profile_revision_map == preview.calibration_revision_map == {}
    assert_error(409, "physical_rebuild_required", plan_rebind, cmd, inputs)


def test_different_hardware_may_migrate_logical_and_leave_physical_reservations(inputs):
    inputs.profiles[NEW] = {7: profile(NEW, 7)}
    before = deepcopy(inputs)
    plan = plan_rebind(
        command(
            inputs,
            hardware="different_hardware",
            saved_layouts=[{"name": "logical", "etag": '"logical-1"'}],
        ),
        inputs,
    )
    assert plan.measurements is None
    assert (
        plan.preview.profile_revision_map == plan.preview.calibration_revision_map == {}
    )
    assert set(s.name for s in plan.preview.untouched_saved) == {
        "physical-old",
        "physical-new",
        "unselected",
    }
    assert plan.active_layout["placements"][NEW]["device_id"] == NEW
    assert inputs == before


def test_different_hardware_can_exclude_physical_active(inputs):
    inputs = replace(inputs, active_layout=physical())
    plan = plan_rebind(
        command(
            inputs,
            hardware="different_hardware",
            active=False,
            saved_layouts=[{"name": "logical", "etag": '"logical-1"'}],
        ),
        inputs,
    )
    assert plan.active_layout == inputs.active_layout
    assert not plan.preview.affected_active
    assert plan.measurements is None


def test_empty_histories_support_logical_same_hardware_rebind(inputs):
    inputs = replace(
        inputs,
        profiles={},
        calibrations={},
        assignments={},
        model_history={},
        saved_layouts={"logical": inputs.saved_layouts["logical"]},
    )
    plan = plan_rebind(command(inputs), inputs)
    assert plan.measurements is None
    assert plan.preview.profile_revision_map == {}


def test_plans_and_previews_own_all_nested_values(inputs):
    inputs.active_layout["scene_extension"] = {
        "content": {"image": "A&<raw>\u0000", "extra": [1, {"b": 2}]}
    }
    before = deepcopy(inputs)
    plan = plan_rebind(command(inputs), inputs)
    impact = preview_impact(OLD, inputs)
    plan.active_layout["placements"][NEW]["bezel"]["left"] = 123
    plan.active_layout["scene_extension"]["content"]["extra"][1]["b"] = 3
    plan.selected_snapshots["logical"]["placements"][NEW]["x"] = 999
    plan.target_record["caps"].append("mutated")
    plan.measurements.model_history["1"]["model"]["extra"].append(3)
    plan.preview.profile_revision_map[1] = 999
    impact.active_entry["bezel"]["top"] = 999
    assert plan.measurements.profile_revision_map[1] == 1
    assert inputs == before
    fresh = plan_rebind(command(inputs), inputs)
    inputs.active_layout["placements"][OLD]["x"] = 777
    inputs.assignments[OLD]["model"]["extra"].append(55)
    assert fresh.active_layout["placements"][NEW]["x"] == -12
    assert fresh.measurements.assignment["model"]["extra"] == [1, 2]


def test_identify_validation_and_monotonic_expiration():
    assert IdentifyCommand().duration_ms == 5000
    assert identify_remaining_ms(12, 10, 5000) == 2000
    assert identify_remaining_ms(12, 13, 5000) == 0
    assert identify_remaining_ms(12, 1, 5000) == 5000
    assert identify_remaining_ms(12, 12, 5000) == 0
    assert_error(422, "invalid_identify", identify_remaining_ms, float("nan"), 1, 5000)
    assert_error(422, "invalid_identify", identify_remaining_ms, 1, float("inf"), 5000)
    assert_error(422, "invalid_identify", identify_remaining_ms, 1, 1, True)


def test_incomplete_automatic_target_history_is_a_conflict(inputs):
    automatic_target(inputs)
    inputs.assignments[NEW] = model_snapshot(2, 8)
    inputs.calibrations[NEW][8] = calibration(NEW, 8, 2, "tablet-model approximate")
    inputs.model_history[NEW] = {}
    assert_error(409, "target_history_conflict", plan_rebind, command(inputs), inputs)


def test_missing_historical_model_snapshot_never_uses_todays_model(inputs):
    inputs.calibrations[OLD][1]["method"] = "tablet-model approximate"
    del inputs.model_history[OLD]["1"]
    assert_error(422, "missing_model_history", plan_rebind, command(inputs), inputs)


def test_current_assignment_alone_can_supply_its_historical_model_snapshot(inputs):
    del inputs.model_history[OLD]["5"]
    plan = plan_rebind(command(inputs), inputs)
    assert plan.measurements.model_history["5"] == inputs.assignments[OLD]


def test_auto_assignment_mode_change_preserves_measurement_snapshot(inputs):
    inputs.assignments[OLD]["mode"] = "auto"
    plan = plan_rebind(command(inputs), inputs)
    assert plan.measurements.assignment["mode"] == "auto"
    assert plan.measurements.model_history["5"]["mode"] == "auto"


def test_active_and_saved_snapshots_keep_content_bytes_and_unrelated_entries(inputs):
    content = {"image": "A&<raw>\u0000", "utf8": "界", "extra": [1, {"b": 2}]}
    for layout in [inputs.active_layout, inputs.saved_layouts["logical"].layout]:
        layout["content_extension"] = deepcopy(content)
        layout["placements"][OTHER] = logical(OTHER)["placements"][OTHER]
    plan = plan_rebind(command(inputs), inputs)
    for layout in [plan.active_layout, plan.selected_snapshots["logical"]]:
        assert layout["content_extension"] == content
        assert layout["placements"][OTHER] == logical(OTHER)["placements"][OTHER]


def test_preview_reports_all_conflicts_without_mutating_inputs(inputs):
    inputs.connections[OLD] = "owned"
    inputs.active_layout["placements"][NEW] = logical(NEW)["placements"][NEW]
    before = deepcopy(inputs)
    preview = preview_rebind(command(inputs, number=9), inputs)
    assert {c.code for c in preview.conflicts} == {
        "old_connected",
        "target_already_present",
        "number_in_use",
    }
    assert inputs == before


def test_planning_never_reads_database_or_global_state(inputs, monkeypatch):
    from tabletwall import displays, persist, state, tablet_models

    def unexpected(*args, **kwargs):
        raise AssertionError("Planner accessed application state")

    monkeypatch.setattr(persist, "_connection", unexpected)
    monkeypatch.setattr(displays, "profile", unexpected)
    monkeypatch.setattr(displays, "calibration", unexpected)
    monkeypatch.setattr(tablet_models, "assignments", unexpected)
    monkeypatch.setattr(state, "devices", {})
    monkeypatch.setattr(state, "wall", {})
    monkeypatch.setattr(state, "device_sockets", {OLD: object()})
    assert plan_rebind(command(inputs), inputs).preview.old_offline
    assert not preview_impact(OLD, inputs).online
    assert plan_forget(
        OLD, ForgetCommand(remove_active=True, saved_layouts="keep"), inputs
    ).active_changed
    assert plan_remove(OLD, inputs).active_changed
