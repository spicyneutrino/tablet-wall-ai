"""Pure lifecycle decisions over detached roster, layout and history snapshots.

Connection keys represent owned sockets, including sockets with stale heartbeats.
History inputs must contain all revisions, not the latest-only display projections.
Plans own their nested payloads; callers may serialize them without changing inputs.
The integration owner rechecks guards and commits every plan write in one transaction.
"""

from __future__ import annotations

import math
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from tabletwall import layouts, tablet_models


class LifecycleError(ValueError):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = deepcopy(details or {})

    @property
    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), **deepcopy(self.details)}


def _device_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise LifecycleError(
            422, "invalid_device_id", "Device ID must be a UUID4"
        ) from None
    if parsed.version != 4 or str(parsed) != value:
        raise LifecycleError(
            422, "invalid_device_id", "Device ID must be a canonical UUID4"
        )
    return value


DeviceId = Annotated[str, AfterValidator(_device_id)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonemptyString = Annotated[str, Field(min_length=1)]


def normalize_label(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LifecycleError(422, "invalid_label", "Label must be a string or null")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
        raise LifecycleError(
            422, "invalid_label", "Label must not contain control characters"
        )
    label = value.strip()
    if len(label) > 80:
        raise LifecycleError(
            422, "invalid_label", "Label must be at most 80 Unicode characters"
        )
    return label or None


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class LabelCommand(_Request):
    label: str | None

    @field_validator("label")
    @classmethod
    def normalized_label(cls, value: str | None) -> str | None:
        return normalize_label(value)


class ForgetCommand(_Request):
    remove_active: bool
    saved_layouts: Literal["keep"]


class SavedSelection(_Request):
    name: NonemptyString
    etag: NonemptyString


class RebindCommand(_Request):
    replaces: DeviceId
    hardware: Literal["same_hardware", "different_hardware"]
    active: bool
    saved_layouts: list[SavedSelection]
    transfer_label: bool
    number: PositiveInt | None = None

    @field_validator("saved_layouts")
    @classmethod
    def unique_saved(cls, value: list[SavedSelection]) -> list[SavedSelection]:
        if len({item.name for item in value}) != len(value):
            raise ValueError("Saved layout names must be unique")
        return value


class RebindApply(RebindCommand):
    new_connection_id: NonemptyString | None


class IdentifyCommand(_Request):
    duration_ms: Annotated[int, Field(strict=True, ge=1000, le=10000)] = 5000


@dataclass(frozen=True)
class SavedLayout:
    etag: str
    layout: dict[str, Any] | None


@dataclass(frozen=True, kw_only=True)
class LifecycleInputs:
    base_etag: str
    roster: dict[str, dict[str, Any]]
    active_layout: dict[str, Any]
    saved_layouts: dict[str, SavedLayout]
    connections: dict[str, str]
    profiles: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    calibrations: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    assignments: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_history: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class RebindInputs(LifecycleInputs):
    new_id: str


@dataclass(frozen=True)
class SnapshotSummary:
    name: str
    etag: str
    kind: Literal["logical", "physical"] | None
    valid: bool


@dataclass(frozen=True)
class ImpactPreview:
    etag: str
    online: bool
    active_entry: dict[str, Any] | None
    saved_layouts: tuple[SnapshotSummary, ...]
    has_measurement_history: bool


@dataclass(frozen=True)
class ForgetPlan:
    device_id: str
    base_etag: str
    active_layout: dict[str, Any]
    active_changed: bool
    remaining_saved: tuple[SnapshotSummary, ...]
    delete_roster: bool = True
    keep_measurement_history: bool = True


@dataclass(frozen=True)
class RemovePlan:
    device_id: str
    base_etag: str
    active_layout: dict[str, Any]
    active_changed: bool


@dataclass(frozen=True)
class Conflict:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **deepcopy(self.details)}


@dataclass(frozen=True)
class MeasurementCopy:
    profile_offset: int
    calibration_offset: int
    profile_revision_map: dict[int, int]
    calibration_revision_map: dict[int, int]
    required_profiles: tuple[int, ...]
    required_calibrations: tuple[int, ...]
    model_history: dict[str, dict[str, Any]]
    assignment: dict[str, Any]


@dataclass(frozen=True)
class RebindPreview:
    base_etag: str
    old_id: str
    new_id: str
    affected_active: bool
    affected_saved: tuple[SnapshotSummary, ...]
    untouched_saved: tuple[SnapshotSummary, ...]
    conflicts: tuple[Conflict, ...]
    profile_revision_map: dict[int, int]
    calibration_revision_map: dict[int, int]
    label_after: str | None
    number_after: int | None
    old_offline: bool
    new_connection_id: str | None


@dataclass(frozen=True)
class RebindPlan:
    preview: RebindPreview
    active_layout: dict[str, Any]
    selected_snapshots: dict[str, dict[str, Any]]
    target_record: dict[str, Any]
    measurements: MeasurementCopy | None
    delete_roster_id: str


def _kind(layout: dict[str, Any]) -> Literal["logical", "physical"]:
    return "physical" if layout.get("kind") == "physical" else "logical"


def _entries(layout: dict[str, Any]) -> dict[str, Any]:
    bucket = layout.get("slots" if _kind(layout) == "physical" else "placements")
    return bucket if isinstance(bucket, dict) else {}


def _references(layout: dict[str, Any] | None, device_id: str) -> bool:
    # Inspect both maps so a damaged reverse-kind reservation stays visible.
    return isinstance(layout, dict) and any(
        isinstance(layout.get(key), dict) and device_id in layout[key]
        for key in ("slots", "placements")
    )


def _positive_revision(value: Any) -> bool:
    return type(value) is int and value > 0


def _finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _check_pair(
    device_id: str, profile_rev: Any, cal_rev: Any, inputs: LifecycleInputs
) -> None:
    profile = (
        inputs.profiles.get(device_id, {}).get(profile_rev)
        if _positive_revision(profile_rev)
        else None
    )
    cal = (
        inputs.calibrations.get(device_id, {}).get(cal_rev)
        if _positive_revision(cal_rev)
        else None
    )
    if (
        profile is None
        or cal is None
        or profile.get("device_id") != device_id
        or cal.get("device_id") != device_id
        or type(profile.get("revision")) is not int
        or profile.get("revision") != profile_rev
        or type(cal.get("revision")) is not int
        or cal.get("revision") != cal_rev
        or type(cal.get("profile_revision")) is not int
        or cal["profile_revision"] != profile_rev
    ):
        raise LifecycleError(
            422,
            "invalid_measurement_reference",
            "Profile/calibration references do not agree",
            details={
                "device_id": device_id,
                "profile_revision": profile_rev,
                "calibration_revision": cal_rev,
            },
        )


def _validate_layout(layout: dict[str, Any] | None, inputs: LifecycleInputs) -> None:
    if not isinstance(layout, dict) or layout.get("kind", "logical") not in ("logical", "physical"):
        raise LifecycleError(422, "damaged_layout", "Layout snapshot is damaged")
    physical = _kind(layout) == "physical"
    if ("placements" if physical else "slots") in layout:
        raise LifecycleError(422, "damaged_layout", "Layout snapshot is damaged")
    if physical:
        for device_id, entry in _entries(layout).items():
            if isinstance(entry, dict):
                _check_pair(device_id, entry.get("profile_revision"),
                            entry.get("calibration_revision"), inputs)
    try:
        geometry_keys = {"kind", "sizing"} | (
            {"bounds", "slots"} if physical else {"width", "height", "placements"}
        )
        layouts.normalize(
            {key: value for key, value in layout.items() if key in geometry_keys},
            profile_for=lambda device_id, revision: inputs.profiles.get(device_id, {}).get(revision),
            calibration_for=lambda device_id, revision: inputs.calibrations.get(device_id, {}).get(revision),
        )
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise LifecycleError(422, "damaged_layout", "Layout snapshot is damaged") from error


def _summary(
    name: str, snapshot: SavedLayout, inputs: LifecycleInputs
) -> SnapshotSummary:
    try:
        _validate_layout(snapshot.layout, inputs)
        valid = True
    except LifecycleError:
        valid = False
    kind = _kind(snapshot.layout) if isinstance(snapshot.layout, dict) else None
    return SnapshotSummary(name, snapshot.etag, kind, valid)


def _known(device_id: str, inputs: LifecycleInputs) -> bool:
    return (
        device_id in inputs.roster
        or _references(inputs.active_layout, device_id)
        or any(_references(s.layout, device_id) for s in inputs.saved_layouts.values())
    )


def preview_impact(device_id: str, inputs: LifecycleInputs) -> ImpactPreview:
    _device_id(device_id)
    if not _known(device_id, inputs):
        raise LifecycleError(404, "unknown_device", "Unknown device or reservation")
    return ImpactPreview(
        inputs.base_etag,
        device_id in inputs.connections,
        deepcopy(_entries(inputs.active_layout).get(device_id)),
        tuple(
            _summary(name, snapshot, inputs)
            for name, snapshot in sorted(inputs.saved_layouts.items())
            if _references(snapshot.layout, device_id)
        ),
        bool(inputs.profiles.get(device_id) or inputs.calibrations.get(device_id)),
    )


def plan_remove(device_id: str, inputs: LifecycleInputs) -> RemovePlan:
    preview_impact(device_id, inputs)
    layout = deepcopy(inputs.active_layout)
    changed = device_id in _entries(layout)
    _entries(layout).pop(device_id, None)
    return RemovePlan(device_id, inputs.base_etag, layout, changed)


def plan_forget(
    device_id: str, command: ForgetCommand, inputs: LifecycleInputs
) -> ForgetPlan:
    impact = preview_impact(device_id, inputs)
    if impact.online:
        raise LifecycleError(
            409, "old_connected", "Forget requires the owned socket to be absent"
        )
    if impact.active_entry is not None and not command.remove_active:
        raise LifecycleError(
            409,
            "active_removal_required",
            "Acknowledge removal of the active reservation",
        )
    removed = plan_remove(device_id, inputs)
    return ForgetPlan(
        device_id,
        inputs.base_etag,
        removed.active_layout,
        removed.active_changed,
        impact.saved_layouts,
    )


def _model_snapshots(
    device_id: str, inputs: LifecycleInputs
) -> dict[str, dict[str, Any]]:
    result = deepcopy(inputs.model_history.get(device_id, {}))
    current = inputs.assignments.get(device_id, {})
    if current.get("model"):
        revision = current.get("calibration_revision")
        if not _positive_revision(revision):
            raise LifecycleError(
                422,
                "invalid_model_history",
                "Model assignment has no calibration revision",
            )
        existing = result.get(str(revision))
        if existing is not None and existing != current:
            # Mode may change without producing a new measurement revision.
            if {k: v for k, v in existing.items() if k != "mode"} != {
                k: v for k, v in current.items() if k != "mode"
            }:
                raise LifecycleError(
                    422,
                    "invalid_model_history",
                    "Model history disagrees with its assignment",
                )
        result[str(revision)] = deepcopy(current)
    return result


def _validate_model_snapshots(
    device_id: str, snapshots: dict[str, dict[str, Any]], inputs: LifecycleInputs
) -> None:
    for key, snapshot in snapshots.items():
        if (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("model"), dict)
            or not snapshot["model"]
            or key != str(snapshot.get("calibration_revision"))
        ):
            raise LifecycleError(
                422, "invalid_model_history", "Model snapshot is damaged"
            )
        _check_pair(
            device_id,
            snapshot.get("profile_revision"),
            snapshot.get("calibration_revision"),
            inputs,
        )
    for revision, calibration in inputs.calibrations.get(device_id, {}).items():
        if (
            calibration.get("method") == "tablet-model approximate"
            and str(revision) not in snapshots
        ):
            raise LifecycleError(
                422,
                "missing_model_history",
                "Automatic calibration requires its historical model snapshot",
                details={"device_id": device_id, "calibration_revision": revision},
            )


def _automatic_target(device_id: str, inputs: LifecycleInputs) -> bool:
    assignment = inputs.assignments.get(device_id, {})
    if (
        assignment.get("mode") != "auto"
        or not assignment.get("model_id")
        or not assignment.get("model")
    ):
        return False
    try:
        snapshots = _model_snapshots(device_id, inputs)
        _validate_model_snapshots(device_id, snapshots, inputs)
    except LifecycleError:
        return False
    profiles, calibrations = (
        inputs.profiles.get(device_id, {}),
        inputs.calibrations.get(device_id, {}),
    )
    if set(profiles) != {s["profile_revision"] for s in snapshots.values()} or set(
        calibrations
    ) != {s["calibration_revision"] for s in snapshots.values()}:
        return False
    return all(
        p.get("provenance") == "tablet-model" for p in profiles.values()
    ) and all(
        c.get("method") == "tablet-model approximate"
        and snapshots[str(rev)].get("mode") == "auto"
        for rev, c in calibrations.items()
    )


def _measurement_copy(
    old_id: str, new_id: str, layouts: list[dict[str, Any]], inputs: LifecycleInputs
) -> MeasurementCopy | None:
    profiles = inputs.profiles.get(old_id, {})
    calibrations = inputs.calibrations.get(old_id, {})
    snapshots = _model_snapshots(old_id, inputs)
    if not profiles and not calibrations and not snapshots:
        return None
    for revision, profile in profiles.items():
        if (
            not _positive_revision(revision)
            or profile.get("device_id") != old_id
            or type(profile.get("revision")) is not int
            or profile.get("revision") != revision
        ):
            raise LifecycleError(
                422, "invalid_measurement_reference", "Profile history is damaged"
            )
    for revision, calibration in calibrations.items():
        _check_pair(old_id, calibration.get("profile_revision"), revision, inputs)
        if str(revision) not in snapshots:
            inherited = tablet_models.snapshot_for_calibration(calibration, snapshots.values())
            if inherited is not None:
                snapshots[str(revision)] = inherited
    _validate_model_snapshots(old_id, snapshots, inputs)
    target_profiles, target_cals = (
        inputs.profiles.get(new_id, {}),
        inputs.calibrations.get(new_id, {}),
    )
    if (
        target_profiles
        or target_cals
        or inputs.model_history.get(new_id)
        or inputs.assignments.get(new_id, {}).get("model")
    ) and not _automatic_target(new_id, inputs):
        raise LifecycleError(
            409,
            "target_history_conflict",
            "Target has measurement history that is not known automatic model history",
        )
    profile_offset, cal_offset = (
        max(target_profiles, default=0),
        max(target_cals, default=0),
    )
    profile_map = {rev: rev + profile_offset for rev in sorted(profiles)}
    cal_map = {rev: rev + cal_offset for rev in sorted(calibrations)}
    required_profiles: set[int] = set()
    required_calibrations: set[int] = set()
    for layout in layouts:
        if _kind(layout) == "physical" and old_id in _entries(layout):
            slot = _entries(layout)[old_id]
            required_profiles.add(slot["profile_revision"])
            required_calibrations.add(slot["calibration_revision"])
    for snapshot in snapshots.values():
        snapshot["profile_revision"] = profile_map[snapshot["profile_revision"]]
        snapshot["calibration_revision"] = cal_map[snapshot["calibration_revision"]]
    assignment = deepcopy(
        inputs.assignments.get(old_id, {"mode": "manual", "model_id": None})
    )
    if assignment.get("model"):
        assignment["profile_revision"] = profile_map[assignment["profile_revision"]]
        assignment["calibration_revision"] = cal_map[assignment["calibration_revision"]]
    return MeasurementCopy(
        profile_offset,
        cal_offset,
        profile_map,
        cal_map,
        tuple(sorted(required_profiles)),
        tuple(sorted(required_calibrations)),
        {str(s["calibration_revision"]): s for s in snapshots.values()},
        assignment,
    )


def _rewrite(
    layout: dict[str, Any],
    old_id: str,
    new_id: str,
    measurements: MeasurementCopy | None,
) -> dict[str, Any]:
    result = deepcopy(layout)
    entries = _entries(result)
    if old_id not in entries:
        return result
    entry = entries.pop(old_id)
    if _kind(result) == "logical":
        entry["device_id"] = new_id
    elif measurements is not None:
        entry["profile_revision"] = measurements.profile_revision_map[
            entry["profile_revision"]
        ]
        entry["calibration_revision"] = measurements.calibration_revision_map[
            entry["calibration_revision"]
        ]
    entries[new_id] = entry
    return result


def _build_rebind(command: RebindCommand, inputs: RebindInputs) -> RebindPlan:
    old_id, new_id = command.replaces, _device_id(inputs.new_id)
    if old_id == new_id:
        raise LifecycleError(
            422, "self_rebind", "Replacement must have a different identity"
        )
    if new_id not in inputs.roster or not _known(old_id, inputs):
        raise LifecycleError(
            404, "unknown_device", "Unknown replacement device or old reservation"
        )
    selected: dict[str, dict[str, Any]] = {}
    for selection in command.saved_layouts:
        snapshot = inputs.saved_layouts.get(selection.name)
        if snapshot is None:
            raise LifecycleError(
                404,
                "unknown_snapshot",
                "Selected saved layout is absent",
                details={"name": selection.name},
            )
        if snapshot.etag != selection.etag:
            raise LifecycleError(
                412,
                "snapshot_changed",
                "Selected saved layout changed",
                details={"name": selection.name},
            )
        try:
            _validate_layout(snapshot.layout, inputs)
        except LifecycleError as error:
            raise LifecycleError(
                error.status,
                error.code,
                str(error),
                details={**error.details, "name": selection.name},
            ) from error
        assert snapshot.layout is not None
        if not _references(snapshot.layout, old_id):
            raise LifecycleError(
                422,
                "snapshot_not_referencing_source",
                "Selected layout does not reference the old identity",
                details={"name": selection.name},
            )
        selected[selection.name] = snapshot.layout
    if command.active:
        _validate_layout(inputs.active_layout, inputs)
    conflicts: list[Conflict] = []
    if old_id in inputs.connections:
        conflicts.append(
            Conflict(
                "old_connected", "Rebind requires the old owned socket to be absent"
            )
        )
    if _references(inputs.active_layout, new_id):
        conflicts.append(
            Conflict(
                "target_already_present",
                "Target is already in the active layout",
                {"layout": "active"},
            )
        )
    for name, layout in selected.items():
        if _references(layout, new_id):
            conflicts.append(
                Conflict(
                    "target_already_present",
                    "Target is already in a selected saved layout",
                    {"name": name},
                )
            )
    layouts = ([inputs.active_layout] if command.active else []) + list(
        selected.values()
    )
    physical_names = (
        ["active"]
        if command.active and _kind(inputs.active_layout) == "physical"
        else []
    ) + [name for name, layout in selected.items() if _kind(layout) == "physical"]
    measurements = None
    if command.hardware == "different_hardware" and physical_names:
        conflicts.append(
            Conflict(
                "physical_rebuild_required",
                "Different hardware requires separately calibrated physical drafts",
                {"layouts": physical_names},
            )
        )
    elif command.hardware == "same_hardware":
        try:
            measurements = _measurement_copy(old_id, new_id, layouts, inputs)
        except LifecycleError as error:
            if error.status != 409:
                raise
            conflicts.append(Conflict(error.code, str(error), error.details))
    old_record, target = inputs.roster.get(old_id, {}), deepcopy(inputs.roster[new_id])
    number = (
        command.number
        if command.number is not None
        else old_record.get("number", target.get("number"))
    )
    if number is None:
        number = target.get("number")
    if number is not None and not _positive_revision(number):
        raise LifecycleError(
            422, "invalid_number", "Display number must be a positive integer"
        )
    if number is not None and any(
        record.get("number") == number
        for key, record in inputs.roster.items()
        if key not in (old_id, new_id)
    ):
        conflicts.append(
            Conflict(
                "number_in_use",
                "Requested display number is in use",
                {"number": number},
            )
        )
    label = normalize_label(
        old_record.get("label") if command.transfer_label else target.get("label")
    )
    target.update(label=label, number=number)
    if "device_id" in target:
        target["device_id"] = new_id
    summaries = {
        name: _summary(name, snapshot, inputs)
        for name, snapshot in sorted(inputs.saved_layouts.items())
        if _references(snapshot.layout, old_id)
    }
    preview = RebindPreview(
        inputs.base_etag,
        old_id,
        new_id,
        command.active and old_id in _entries(inputs.active_layout),
        tuple(summaries[name] for name in selected),
        tuple(summary for name, summary in summaries.items() if name not in selected),
        tuple(conflicts),
        deepcopy(measurements.profile_revision_map) if measurements else {},
        deepcopy(measurements.calibration_revision_map) if measurements else {},
        label,
        number,
        old_id not in inputs.connections,
        inputs.connections.get(new_id),
    )
    return RebindPlan(
        preview,
        _rewrite(inputs.active_layout, old_id, new_id, measurements)
        if command.active
        else deepcopy(inputs.active_layout),
        {
            name: _rewrite(layout, old_id, new_id, measurements)
            for name, layout in selected.items()
        },
        target,
        measurements,
        old_id,
    )


def preview_rebind(command: RebindCommand, inputs: RebindInputs) -> RebindPreview:
    return _build_rebind(command, inputs).preview


def plan_rebind(command: RebindApply, inputs: RebindInputs) -> RebindPlan:
    """Rebuild a proposal from current inputs after the parent checks the global ETag."""
    plan = _build_rebind(command, inputs)
    if command.new_connection_id != inputs.connections.get(inputs.new_id):
        raise LifecycleError(
            412, "connection_changed", "Target connection changed since preview"
        )
    if plan.preview.conflicts:
        first = plan.preview.conflicts[0]
        raise LifecycleError(
            409,
            first.code,
            first.message,
            details={"conflicts": [c.payload() for c in plan.preview.conflicts]},
        )
    return plan


def identify_remaining_ms(
    expires_mono: float, now_mono: float, duration_ms: int
) -> float:
    """Stamp a queued Identify using server monotonic seconds, without extending expiry."""
    if (
        not _finite(expires_mono)
        or not _finite(now_mono)
        or type(duration_ms) is not int
        or not 1000 <= duration_ms <= 10000
    ):
        raise LifecycleError(
            422, "invalid_identify", "Identify expiry and duration are invalid"
        )
    return min(float(duration_ms), max(0.0, (expires_mono - now_mono) * 1000))
