"""Pure ordered grid construction for the operator wall.

This module builds a detached layout proposal from a strict ``GridCommand`` and
already-resolved inputs. It never reads the database, the live wall, sockets,
or ``main``; it never mutates its arguments and never commits. The caller owns
ETag checks, revision increments, persistence, and broadcast.

Units stay separate. Logical layouts use whole logical units; physical layouts
use millimetres from pinned display profiles. No CSS-to-mm factor exists here.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from tabletwall import geometry
from tabletwall import sizing as wall_sizing

INVALID = "invalid"
CONFLICT = "conflict"
GUARD_CHANGED = "guard_changed"
MAX_COORDINATE = 2**53 - 1

_STATUS_BY_CODE = {INVALID: 422, CONFLICT: 409, GUARD_CHANGED: 412}

_VIEWPORT_KEYS = {"width", "height", "dpr", "orientation", "mode", "visual_scale"}
_GUARD_KEYS = {"connection_id", "viewport"}
_SIZE_KEYS = {"w", "h"}
_PIN_KEYS = {"profile_revision", "calibration_revision"}
_COMMAND_KEYS = {
    "kind", "device_ids", "rows", "columns", "gap", "padding", "sizing",
    "orientation", "allow_empty_cells", "release_unselected", "mount_angles",
    "logical_sizes", "physical_revisions", "guards",
}
_COMMAND_REQUIRED = {
    "kind", "device_ids", "rows", "columns", "gap", "padding", "sizing",
    "orientation", "allow_empty_cells", "release_unselected",
}


class GridError(ValueError):
    """A refused grid request, carrying the HTTP status its code maps to."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        conflicts: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.conflicts = [dict(conflict) for conflict in conflicts]

    @property
    def status(self) -> int:
        return _STATUS_BY_CODE.get(self.code, 422)


class ConnectionViewportGuard(TypedDict):
    connection_id: str | None
    viewport: dict[str, Any] | None


class GridPreview(TypedDict):
    layout: dict[str, Any]
    order: list[str]
    warnings: list[str]
    guards: dict[str, ConnectionViewportGuard]
    base_etag: str
    reservations_removed: list[str]
    previous_kind: str


@dataclass(frozen=True)
class MeasurementPins:
    profile_revision: int
    calibration_revision: int


@dataclass(frozen=True)
class GridDevice:
    """One detached tablet snapshot used by a grid command.

    ``profiles``/``calibrations`` are revision-keyed, already-pinned records.
    ``model`` is the confirmed built-in model snapshot (with
    ``portrait_angle``); pass ``None`` for an inferred or absent assignment.
    """

    device_id: str
    online: bool = False
    connection_id: str | None = None
    viewport: Mapping[str, Any] | None = None
    profiles: Mapping[int, Mapping[str, Any]] = field(default_factory=dict)
    calibrations: Mapping[int, Mapping[str, Any]] = field(default_factory=dict)
    model: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_id", _uuid4(self.device_id, "device_id"))
        object.__setattr__(self, "online", _bool(self.online, "online"))
        connection = self.connection_id
        if connection is not None:
            if not isinstance(connection, str) or not connection or len(connection) > 200:
                raise _invalid("connection_id must be a non-empty string or null")
        object.__setattr__(self, "connection_id", connection)
        object.__setattr__(self, "viewport", _viewport(self.viewport, "viewport"))
        object.__setattr__(
            self, "profiles", _revision_index(self.profiles, "profiles")
        )
        object.__setattr__(
            self, "calibrations", _revision_index(self.calibrations, "calibrations")
        )
        model = self.model
        if model is not None and not isinstance(model, Mapping):
            raise _invalid("model must be a mapping or null")
        object.__setattr__(self, "model", deepcopy(dict(model)) if model is not None else None)


@dataclass(frozen=True)
class GridInputs:
    """Detached inputs for one preview or apply call."""

    active_layout: Mapping[str, Any]
    devices: Sequence[GridDevice]
    base_etag: str

    def __post_init__(self) -> None:
        if not isinstance(self.active_layout, Mapping):
            raise _invalid("active_layout must be an object")
        object.__setattr__(
            self, "active_layout", deepcopy(dict(self.active_layout))
        )
        if isinstance(self.devices, (str, bytes)) or not isinstance(self.devices, Sequence):
            raise _invalid("devices must be an ordered list")
        devices = tuple(self.devices)
        if any(not isinstance(device, GridDevice) for device in devices):
            raise _invalid("devices must contain GridDevice records")
        seen: set[str] = set()
        for device in devices:
            if device.device_id in seen:
                raise _invalid(f"duplicate device input {device.device_id}")
            seen.add(device.device_id)
        object.__setattr__(self, "devices", devices)
        if not isinstance(self.base_etag, str) or not self.base_etag:
            raise _invalid("base_etag must be a non-empty string")


@dataclass(frozen=True)
class GridCommand:
    """A strict ``GridCommand``; build one with :meth:`from_payload`."""

    kind: Literal["logical", "physical"]
    device_ids: tuple[str, ...]
    rows: int
    columns: int
    gap: float
    padding: float
    sizing: Literal["tablets", "fixed"]
    orientation: Literal["preserve", "auto", "portrait", "landscape"]
    allow_empty_cells: bool
    release_unselected: tuple[str, ...]
    mount_angles: Mapping[str, int] = field(default_factory=dict)
    logical_sizes: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    physical_revisions: Mapping[str, MeasurementPins] = field(default_factory=dict)
    guards: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = _choice(self.kind, ("logical", "physical"), "kind")
        device_ids = _uuid_list(self.device_ids, "device_ids")
        if not device_ids:
            raise _invalid("device_ids must select at least one tablet")
        if len(set(device_ids)) != len(device_ids):
            raise _invalid("device_ids must not contain duplicates")
        rows = _positive_int(self.rows, "rows")
        columns = _positive_int(self.columns, "columns")
        capacity = rows * columns
        if len(device_ids) > capacity:
            raise _invalid(
                f"{len(device_ids)} tablets do not fit in {rows} x {columns} cells"
            )
        allow_empty = _bool(self.allow_empty_cells, "allow_empty_cells")
        if len(device_ids) < capacity and not allow_empty:
            raise _invalid(
                "the grid has trailing holes; set allow_empty_cells to accept them"
            )
        gap = _number(self.gap, "gap", nonnegative=True)
        padding = _number(self.padding, "padding", nonnegative=True)
        if kind == "logical":
            if not float(gap).is_integer():
                raise _invalid("logical gap must be a whole number of logical units")
            if not float(padding).is_integer():
                raise _invalid("logical padding must be a whole number of logical units")
            gap, padding = int(gap), int(padding)
        sizing = _choice(self.sizing, ("tablets", "fixed"), "sizing")
        orientation = _choice(
            self.orientation, ("preserve", "auto", "portrait", "landscape"),
            "orientation",
        )
        release = _uuid_list(self.release_unselected, "release_unselected")
        if len(set(release)) != len(release):
            raise _invalid("release_unselected must not contain duplicates")
        if set(release) & set(device_ids):
            raise _invalid("release_unselected cannot name a selected tablet")
        mounts = _angle_map(self.mount_angles, "mount_angles")
        sizes = _size_map(self.logical_sizes, "logical_sizes")
        pins = _pins_map(self.physical_revisions, "physical_revisions")
        guards = _guard_map(self.guards, "guards")
        if kind == "logical" and mounts:
            raise _invalid("logical grids do not take mount_angles")
        if kind == "logical" and pins:
            raise _invalid("logical grids do not take physical_revisions")
        if kind == "physical" and sizes:
            raise _invalid("physical grids do not take logical_sizes")
        selected = set(device_ids)
        for label, mapping in (
            ("mount_angles", mounts),
            ("logical_sizes", sizes),
            ("physical_revisions", pins),
            ("guards", guards),
        ):
            extras = [device_id for device_id in mapping if device_id not in selected]
            if extras:
                raise _invalid(f"{label} names an unselected tablet {extras[0]}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "device_ids", device_ids)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "gap", gap)
        object.__setattr__(self, "padding", padding)
        object.__setattr__(self, "sizing", sizing)
        object.__setattr__(self, "orientation", orientation)
        object.__setattr__(self, "allow_empty_cells", allow_empty)
        object.__setattr__(self, "release_unselected", release)
        object.__setattr__(self, "mount_angles", mounts)
        object.__setattr__(self, "logical_sizes", sizes)
        object.__setattr__(self, "physical_revisions", pins)
        object.__setattr__(self, "guards", guards)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GridCommand:
        """Parse an untrusted request body, rejecting unknown or missing keys."""
        if not isinstance(payload, Mapping):
            raise _invalid("grid command must be an object")
        unknown = sorted(set(payload) - _COMMAND_KEYS)
        if unknown:
            raise _invalid(f"grid command has unknown key {unknown[0]}")
        missing = sorted(_COMMAND_REQUIRED - set(payload))
        if missing:
            raise _invalid(f"grid command is missing {missing[0]}")
        return cls(
            kind=payload["kind"],
            device_ids=payload["device_ids"],
            rows=payload["rows"],
            columns=payload["columns"],
            gap=payload["gap"],
            padding=payload["padding"],
            sizing=payload["sizing"],
            orientation=payload["orientation"],
            allow_empty_cells=payload["allow_empty_cells"],
            release_unselected=payload["release_unselected"],
            mount_angles=payload.get("mount_angles", {}),
            logical_sizes=payload.get("logical_sizes", {}),
            physical_revisions=payload.get("physical_revisions", {}),
            guards=payload.get("guards", {}),
        )


def confirmed_model(assignment: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return a model snapshot only when explicit confirmation assigned it.

    Automatic model matches remain suggestions until the operator confirms
    them, so their scale cannot drive automatic wall orientation.
    """
    if not isinstance(assignment, Mapping) or assignment.get("mode") != "explicit":
        return None
    model = assignment.get("model")
    return deepcopy(dict(model)) if isinstance(model, Mapping) else None


def build_grid(command: GridCommand, inputs: GridInputs) -> GridPreview:
    """Build one complete detached layout proposal. No writes or sends."""
    if not isinstance(command, GridCommand):
        raise _invalid("command must be a GridCommand")
    if not isinstance(inputs, GridInputs):
        raise _invalid("inputs must be GridInputs")
    active = deepcopy(dict(inputs.active_layout))
    previous_kind = _previous_kind(active)
    device_map = {device.device_id: device for device in inputs.devices}
    unknown = [device_id for device_id in command.device_ids if device_id not in device_map]
    if unknown:
        raise _invalid(f"selected tablet {unknown[0]} is not available")

    reservations = _reservation_ids(active, previous_kind)
    removed = _resolve_releases(command, reservations)
    warnings: list[str] = []
    holes = command.rows * command.columns - len(command.device_ids)
    if holes:
        warnings.append(
            f"{holes} empty trailing cell(s) after the last tablet"
        )

    if command.kind == "logical":
        layout = _build_logical(command, inputs, active, previous_kind, warnings)
    else:
        layout = _build_physical(command, inputs, active, previous_kind, warnings)

    def check_geometry(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                check_geometry(child)
        elif type(value) in (int, float):
            _number(value, "computed geometry")

    check_geometry(layout)

    return {
        "layout": layout,
        "order": list(command.device_ids),
        "warnings": warnings,
        "guards": connection_guards(inputs, command.device_ids),
        "base_etag": inputs.base_etag,
        "reservations_removed": removed,
        "previous_kind": previous_kind,
    }


def connection_guards(
    inputs: GridInputs, device_ids: Sequence[str]
) -> dict[str, ConnectionViewportGuard]:
    """The exact current connection/viewport guard for every requested tablet."""
    device_map = {device.device_id: device for device in inputs.devices}
    guards: dict[str, ConnectionViewportGuard] = {}
    for device_id in device_ids:
        device = device_map.get(device_id)
        if device is None:
            raise _invalid(f"selected tablet {device_id} is not available")
        guards[device_id] = {
            "connection_id": device.connection_id,
            "viewport": (
                deepcopy(dict(device.viewport))
                if device.viewport is not None
                else None
            ),
        }
    return guards


def validate_guards(
    expected: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
) -> None:
    """Require the preview's complete guards to still match exactly.

    A mismatch is a stale draft: the caller maps :attr:`GridError.status`
    (412) rather than recomputing the layout from newer telemetry.
    """
    if not isinstance(expected, Mapping) or not isinstance(current, Mapping):
        raise _invalid("guards must be objects")
    conflicts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for device_id in (*expected, *current):
        if device_id in seen:
            continue
        seen.add(device_id)
        if device_id not in current:
            conflicts.append({"device_id": device_id, "fields": ["missing"]})
            continue
        if device_id not in expected:
            conflicts.append({"device_id": device_id, "fields": ["unexpected"]})
            continue
        expected_guard = expected[device_id]
        current_guard = current[device_id]
        fields = [
            field_name
            for field_name in ("connection_id", "viewport")
            if not isinstance(expected_guard, Mapping)
            or not isinstance(current_guard, Mapping)
            or expected_guard.get(field_name) != current_guard.get(field_name)
        ]
        if fields:
            conflicts.append({"device_id": device_id, "fields": fields})
    if conflicts:
        raise GridError(
            GUARD_CHANGED,
            "connection or viewport changed since preview",
            conflicts=conflicts,
        )


# ---------------------------------------------------------------------------
# logical construction
# ---------------------------------------------------------------------------


def _build_logical(
    command: GridCommand,
    inputs: GridInputs,
    active: dict[str, Any],
    previous_kind: str,
    warnings: list[str],
) -> dict[str, Any]:
    placements_active = (
        active["placements"] if previous_kind == "logical" else {}
    )
    device_map = {device.device_id: device for device in inputs.devices}
    placements: dict[str, dict[str, Any]] = {}
    suggested: list[str] = []
    aspect_mismatch: list[str] = []
    rotated: list[str] = []
    for device_id in command.device_ids:
        existing = _placement(placements_active.get(device_id), device_id)
        explicit = command.logical_sizes.get(device_id)
        is_suggested = False
        if explicit is not None:
            width, height = explicit
            bezel = _reuse_logical_bezel(existing, width, height, device_id)
        elif existing is not None:
            width, height = existing["w"], existing["h"]
            bezel = existing["bezel"]
        else:
            device = device_map[device_id]
            viewport = device.viewport
            if viewport is None or not device.online or device.connection_id is None:
                raise _invalid(
                    f"tablet {device_id} needs an explicit logical size or a live viewport"
                )
            width, height = _suggest_logical_size(viewport, command.orientation)
            bezel = {"left": 0, "top": 0, "right": 0, "bottom": 0}
            suggested.append(device_id)
            is_suggested = True
        if width - bezel["left"] - bezel["right"] <= 0:
            raise _invalid(
                f"tablet {device_id} logical bezels leave no positive active width"
            )
        if height - bezel["top"] - bezel["bottom"] <= 0:
            raise _invalid(
                f"tablet {device_id} logical bezels leave no positive active height"
            )
        if command.orientation == "portrait" and width > height:
            rotated.append(device_id)
        elif command.orientation == "landscape" and height > width:
            rotated.append(device_id)
        if not is_suggested:
            viewport = device_map[device_id].viewport
            if viewport is not None and _aspect_mismatch(width, height, viewport):
                aspect_mismatch.append(device_id)
        placements[device_id] = {
            "device_id": device_id,
            "x": 0,
            "y": 0,
            "w": width,
            "h": height,
            "bezel": dict(bezel),
        }

    layout: dict[str, Any] = {
        "kind": "logical",
        "width": 1,
        "height": 1,
        "placements": placements,
        "sizing": {"mode": command.sizing, "padding": int(command.padding)},
    }
    row_widths = _pack_logical(
        placements, command.device_ids, command.columns, int(command.gap)
    )
    if command.sizing == "tablets":
        try:
            wall_sizing.fit_logical(layout)
        except ValueError as error:
            raise _invalid(str(error)) from error
    else:
        if previous_kind != "logical":
            raise _invalid("fixed logical sizing needs current logical bounds")
        layout["width"] = _positive_int(active.get("width"), "active logical width")
        layout["height"] = _positive_int(active.get("height"), "active logical height")

    shapes = {(placement["w"], placement["h"]) for placement in placements.values()}
    if len(shapes) > 1:
        warnings.append(
            "mixed logical footprint sizes can leave holes and an uneven edge"
        )
    if len(set(row_widths)) > 1:
        warnings.append("rows have unequal widths; the right edge is uneven")
    if suggested:
        warnings.append(
            "logical footprint(s) suggested from the live viewport for "
            + ", ".join(suggested)
            + "; review them before Apply"
        )
    if rotated:
        warnings.append(
            "requested orientation conflicts with the preserved or explicit "
            "footprint for "
            + ", ".join(rotated)
            + "; rotate the device or choose a new logical size"
        )
    if aspect_mismatch:
        warnings.append(
            "logical footprint aspect differs from the live viewport for "
            + ", ".join(aspect_mismatch)
            + "; the client will letterbox or crop"
        )
    if command.sizing == "fixed":
        outside = [
            device_id
            for device_id, placement in placements.items()
            if placement["x"] + placement["w"] > layout["width"]
            or placement["y"] + placement["h"] > layout["height"]
        ]
        if outside:
            warnings.append(
                "logical placements extend outside the fixed bounds for "
                + ", ".join(outside)
            )
    return layout


def _pack_logical(
    placements: dict[str, dict[str, Any]],
    order: Sequence[str],
    columns: int,
    gap: int,
) -> list[int]:
    row_widths: list[int] = []
    y = 0
    for start in range(0, len(order), columns):
        row = order[start:start + columns]
        row_height = max(placements[device_id]["h"] for device_id in row)
        x = 0
        for device_id in row:
            placement = placements[device_id]
            placement["x"] = x
            placement["y"] = y
            x += placement["w"] + gap
        row_widths.append(x - gap)
        y += row_height + gap
    return row_widths


def _placement(value: Any, device_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid(f"active placement for {device_id} is invalid")
    width = _positive_int(value.get("w"), f"active placement width for {device_id}")
    height = _positive_int(value.get("h"), f"active placement height for {device_id}")
    bezel = _logical_bezel(value.get("bezel"), f"active placement bezel for {device_id}")
    return {"w": width, "h": height, "bezel": bezel}


def _reuse_logical_bezel(
    existing: Mapping[str, Any] | None, width: int, height: int, device_id: str
) -> dict[str, int]:
    if existing is None:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}
    bezel = dict(existing["bezel"])
    if width - bezel["left"] - bezel["right"] <= 0 or height - bezel["top"] - bezel["bottom"] <= 0:
        raise _invalid(
            f"tablet {device_id} logical bezels do not fit the requested size"
        )
    return bezel


def _logical_bezel(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} is missing")
    allowed = {"left", "top", "right", "bottom"}
    unknown = set(value) - allowed
    if unknown:
        raise _invalid(f"{label} has unknown key {sorted(unknown)[0]}")
    return {
        edge: _nonnegative_int(value.get(edge, 0), f"{label} {edge}")
        for edge in ("left", "top", "right", "bottom")
    }


def _suggest_logical_size(
    viewport: Mapping[str, Any], orientation: str
) -> tuple[int, int]:
    view_width = float(viewport["width"])
    view_height = float(viewport["height"])
    if view_width >= view_height:
        width, height = 100, max(1, round(100 * view_height / view_width))
    else:
        width, height = max(1, round(100 * view_width / view_height)), 100
    if orientation == "portrait" and width > height:
        width, height = height, width
    elif orientation == "landscape" and height > width:
        width, height = height, width
    return width, height


def _aspect_mismatch(
    width: int, height: int, viewport: Mapping[str, Any]
) -> bool:
    view_ratio = float(viewport["width"]) / float(viewport["height"])
    ratio = width / height
    return abs(ratio / view_ratio - 1) > 0.01


# ---------------------------------------------------------------------------
# physical construction
# ---------------------------------------------------------------------------


@dataclass
class _PhysicalBody:
    device_id: str
    body_width: float
    body_height: float
    packed_width: float
    packed_height: float
    angle: float
    nudge_x: float
    nudge_y: float
    profile_revision: int
    calibration_revision: int
    participating: bool
    estimated: bool


def _build_physical(
    command: GridCommand,
    inputs: GridInputs,
    active: dict[str, Any],
    previous_kind: str,
    warnings: list[str],
) -> dict[str, Any]:
    slots_active = active["slots"] if previous_kind == "physical" else {}
    device_map = {device.device_id: device for device in inputs.devices}
    origin_x = origin_y = 0.0
    fixed_bounds: dict[str, float] = {}
    if command.sizing == "fixed":
        if previous_kind != "physical":
            raise _invalid("fixed physical sizing needs current physical bounds")
        fixed_bounds = _bounds(active.get("bounds"), "active physical bounds")
        origin_x, origin_y = fixed_bounds["x"], fixed_bounds["y"]
    bodies: list[_PhysicalBody] = []
    estimated: list[str] = []
    for device_id in command.device_ids:
        device = device_map[device_id]
        pins = command.physical_revisions.get(device_id)
        if pins is None:
            raise _invalid(
                f"tablet {device_id} needs pinned profile and calibration revisions"
            )
        profile = device.profiles.get(pins.profile_revision)
        calibration = device.calibrations.get(pins.calibration_revision)
        if profile is None:
            raise _invalid(
                f"tablet {device_id} has no profile revision {pins.profile_revision}"
            )
        if calibration is None:
            raise _invalid(
                f"tablet {device_id} has no calibration revision "
                f"{pins.calibration_revision}"
            )
        if calibration.get("profile_revision") != pins.profile_revision:
            raise _invalid(
                f"tablet {device_id} calibration does not match its profile revision"
            )
        body_width, body_height = _profile_body(profile, device_id)
        existing = _slot(slots_active.get(device_id), device_id)
        angle = _mount_angle(
            command, device, existing, body_width, body_height, device_id
        )
        packed_width, packed_height = _rotated_body(body_width, body_height, angle)
        bodies.append(
            _PhysicalBody(
                device_id=device_id,
                body_width=body_width,
                body_height=body_height,
                packed_width=packed_width,
                packed_height=packed_height,
                angle=angle,
                nudge_x=existing["nudge_x"] if existing else 0.0,
                nudge_y=existing["nudge_y"] if existing else 0.0,
                profile_revision=pins.profile_revision,
                calibration_revision=pins.calibration_revision,
                participating=existing["participating"] if existing else True,
                estimated=_estimated_measurement(profile, calibration),
            )
        )
        if bodies[-1].estimated:
            estimated.append(device_id)

    row_widths, centers = _pack_physical(
        bodies, command.columns, command.gap, origin_x, origin_y
    )
    slots = {
        body.device_id: {
            "center_x_mm": centers[index][0] - body.nudge_x,
            "center_y_mm": centers[index][1] - body.nudge_y,
            "mount_angle": _json_number(body.angle),
            "nudge_x_mm": body.nudge_x,
            "nudge_y_mm": body.nudge_y,
            "profile_revision": body.profile_revision,
            "calibration_revision": body.calibration_revision,
            "participating": body.participating,
        }
        for index, body in enumerate(bodies)
    }
    layout: dict[str, Any] = {
        "kind": "physical",
        "bounds": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "slots": slots,
        "sizing": {"mode": command.sizing, "padding": float(command.padding)},
    }
    if command.sizing == "tablets":
        profiles = {
            device_id: device.profiles
            for device_id, device in device_map.items()
        }

        def profile_for(device_id: str, revision: int) -> dict[str, Any] | None:
            record = profiles.get(device_id, {}).get(revision)
            return dict(record) if record is not None else None

        try:
            wall_sizing.fit_physical(layout, profile_for)
        except ValueError as error:
            raise _invalid(str(error)) from error
    else:
        layout["bounds"] = fixed_bounds

    shapes = {(body.packed_width, body.packed_height) for body in bodies}
    if len(shapes) > 1:
        warnings.append(
            "mixed body sizes or orientations can leave holes and an uneven "
            "edge; only equal aspect-matched bodies promise full rectangular "
            "coverage"
        )
    if len(set(row_widths)) > 1:
        warnings.append("rows have unequal widths; the right edge is uneven")
    if estimated:
        warnings.append(
            "estimated measurement used for " + ", ".join(estimated)
            + "; confirm the model or measure the tablet"
        )
    if command.sizing == "fixed":
        outside = [
            body.device_id
            for index, body in enumerate(bodies)
            if _outside_fixed(layout["bounds"], body, centers[index])
        ]
        if outside:
            warnings.append(
                "physical bodies extend outside the fixed bounds for "
                + ", ".join(outside)
            )
    return layout


def _pack_physical(
    bodies: Sequence[_PhysicalBody],
    columns: int,
    gap: float,
    origin_x: float,
    origin_y: float,
) -> tuple[list[float], list[tuple[float, float]]]:
    row_widths: list[float] = []
    centers: list[tuple[float, float]] = []
    y = float(origin_y)
    for start in range(0, len(bodies), columns):
        row = bodies[start:start + columns]
        row_height = max(body.packed_height for body in row)
        x = float(origin_x)
        for body in row:
            centers.append((x + body.packed_width / 2, y + body.packed_height / 2))
            x += body.packed_width + gap
        row_widths.append(x - gap - origin_x)
        y += row_height + gap
    return row_widths, centers


def _slot(value: Any, device_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid(f"active slot for {device_id} is invalid")
    angle = _finite(value.get("mount_angle"), f"active mount angle for {device_id}")
    return {
        "mount_angle": angle,
        "nudge_x": _finite(value.get("nudge_x_mm", 0), f"active nudge x for {device_id}"),
        "nudge_y": _finite(value.get("nudge_y_mm", 0), f"active nudge y for {device_id}"),
        "participating": _bool(
            value.get("participating", True),
            f"active participation for {device_id}",
        ),
    }


def _profile_body(profile: Mapping[str, Any], device_id: str) -> tuple[float, float]:
    active_width = _positive_number(
        profile.get("active_width_mm"), f"profile active width for {device_id}"
    )
    active_height = _positive_number(
        profile.get("active_height_mm"), f"profile active height for {device_id}"
    )
    bezels_value = profile.get("bezels")
    if not isinstance(bezels_value, Mapping):
        raise _invalid(f"profile bezels for {device_id} are missing")
    unknown = set(bezels_value) - {"left", "top", "right", "bottom"}
    if unknown:
        raise _invalid(f"profile bezels for {device_id} have an unknown edge")
    bezels = {
        edge: _number(
            bezels_value.get(edge, 0),
            f"profile {edge} bezel for {device_id}",
            nonnegative=True,
        )
        for edge in ("left", "top", "right", "bottom")
    }
    try:
        body_width, body_height, _origin = geometry.body_geometry(
            active_width, active_height, bezels
        )
    except ValueError as error:
        raise _invalid(str(error)) from error
    return body_width, body_height


def _mount_angle(
    command: GridCommand,
    device: GridDevice,
    existing: Mapping[str, Any] | None,
    body_width: float,
    body_height: float,
    device_id: str,
) -> float:
    explicit = command.mount_angles.get(device_id)
    if explicit is not None:
        return float(explicit)
    if command.orientation == "preserve":
        if existing is None:
            raise _invalid(
                f"tablet {device_id} has no existing mount; supply an explicit angle"
            )
        return float(existing["mount_angle"])
    if command.orientation == "auto":
        return float(_auto_angle(device, device_id))
    current = existing["mount_angle"] if existing is not None else None
    if current is not None and _aspect_matches(
        body_width, body_height, float(current), command.orientation
    ):
        return float(current)
    auto = _auto_angle(device, device_id)
    if _aspect_matches(body_width, body_height, float(auto), command.orientation):
        return float(auto)
    raise _invalid(
        f"tablet {device_id} needs an explicit 90/270 mount angle for the "
        f"requested {command.orientation} aspect"
    )


def _auto_angle(device: GridDevice, device_id: str) -> int:
    if not device.online:
        raise _invalid(
            f"tablet {device_id} is offline; automatic orientation needs a live viewport"
        )
    if device.viewport is None:
        raise _invalid(
            f"tablet {device_id} has no live viewport for automatic orientation"
        )
    if device.model is None:
        raise _invalid(
            f"tablet {device_id} has no confirmed model for automatic orientation"
        )
    portrait_angle = device.model.get("portrait_angle")
    if portrait_angle not in (0, 90, 180, 270):
        raise _invalid(
            f"tablet {device_id} confirmed model has no valid portrait_angle"
        )
    orientation = int(device.viewport["orientation"])
    quarter = ((int(portrait_angle) - orientation) // 90) % 4
    return (360 - 90 * quarter) % 360


def _aspect_matches(
    body_width: float, body_height: float, angle: float, orientation: str
) -> bool:
    packed_width, packed_height = _rotated_body(body_width, body_height, angle)
    if orientation == "portrait":
        return packed_height >= packed_width
    return packed_width >= packed_height


def _rotated_body(width: float, height: float, angle: float) -> tuple[float, float]:
    radians = math.radians(angle)
    return (
        abs(math.cos(radians)) * width + abs(math.sin(radians)) * height,
        abs(math.sin(radians)) * width + abs(math.cos(radians)) * height,
    )


def _outside_fixed(
    bounds: Mapping[str, Any], body: _PhysicalBody, center: tuple[float, float]
) -> bool:
    half_x, half_y = _rotated_body(
        body.body_width, body.body_height, body.angle
    )
    half_x, half_y = half_x / 2, half_y / 2
    center_x, center_y = center
    tolerance = 1e-6
    return (
        center_x - half_x < bounds["x"] - tolerance
        or center_y - half_y < bounds["y"] - tolerance
        or center_x + half_x > bounds["x"] + bounds["width"] + tolerance
        or center_y + half_y > bounds["y"] + bounds["height"] + tolerance
    )


def _estimated_measurement(
    profile: Mapping[str, Any], calibration: Mapping[str, Any]
) -> bool:
    if profile.get("provenance") == "tablet-model":
        return True
    method = calibration.get("method")
    if isinstance(method, str) and "approximate" in method.lower():
        return True
    uncertainty = calibration.get("uncertainty_mm", 0)
    return (
        isinstance(uncertainty, (int, float))
        and not isinstance(uncertainty, bool)
        and uncertainty > 0
    )


# ---------------------------------------------------------------------------
# shared validation and release handling
# ---------------------------------------------------------------------------


def _previous_kind(active: Mapping[str, Any]) -> str:
    kind = active.get("kind", "logical")
    if kind == "logical":
        if not isinstance(active.get("placements"), Mapping):
            raise _invalid("active logical layout has no placements")
        _positive_int(active.get("width"), "active logical width")
        _positive_int(active.get("height"), "active logical height")
        return "logical"
    if kind == "physical":
        if not isinstance(active.get("slots"), Mapping):
            raise _invalid("active physical layout has no slots")
        _bounds(active.get("bounds"), "active physical bounds")
        return "physical"
    raise _invalid("active layout kind must be logical or physical")


def _reservation_ids(active: Mapping[str, Any], kind: str) -> list[str]:
    bucket = active["slots"] if kind == "physical" else active["placements"]
    return [str(device_id) for device_id in bucket]


def _resolve_releases(command: GridCommand, reservations: Sequence[str]) -> list[str]:
    selected = set(command.device_ids)
    unselected = [device_id for device_id in reservations if device_id not in selected]
    released = list(command.release_unselected)
    extras = [device_id for device_id in released if device_id not in unselected]
    if extras:
        raise _invalid(
            f"release_unselected names a tablet that is not an active reservation: {extras[0]}"
        )
    missing = [device_id for device_id in unselected if device_id not in set(released)]
    if missing:
        raise GridError(
            CONFLICT,
            "unselected active reservations must be released explicitly",
            conflicts=[{"device_id": device_id} for device_id in missing],
        )
    return unselected


def _bounds(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} are missing")
    unknown = set(value) - {"x", "y", "width", "height"}
    if unknown:
        raise _invalid(f"{label} have an unknown key")
    width = _positive_number(value.get("width"), f"{label} width")
    height = _positive_number(value.get("height"), f"{label} height")
    return {
        "x": _finite(value.get("x"), f"{label} x"),
        "y": _finite(value.get("y"), f"{label} y"),
        "width": width,
        "height": height,
    }


def _viewport(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object or null")
    unknown = set(value) - _VIEWPORT_KEYS
    if unknown:
        raise _invalid(f"{label} has unknown key {sorted(unknown)[0]}")
    missing = {"width", "height", "dpr", "orientation", "mode"} - set(value)
    if missing:
        raise _invalid(f"{label} is missing {sorted(missing)[0]}")
    orientation = value["orientation"]
    if isinstance(orientation, bool) or not isinstance(orientation, int):
        raise _invalid(f"{label} orientation must be 0, 90, 180 or 270")
    if orientation % 360 not in (0, 90, 180, 270):
        raise _invalid(f"{label} orientation must be 0, 90, 180 or 270")
    mode = value["mode"]
    if mode not in ("tab", "fullscreen", "standalone"):
        raise _invalid(f"{label} mode is not supported")
    visual = value.get("visual_scale")
    return {
        "width": _positive_number(value["width"], f"{label} width"),
        "height": _positive_number(value["height"], f"{label} height"),
        "dpr": _positive_number(value["dpr"], f"{label} dpr"),
        "orientation": int(orientation) % 360,
        "mode": str(mode),
        "visual_scale": (
            _positive_number(visual, f"{label} visual_scale")
            if visual is not None
            else None
        ),
    }


def _guard_map(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object")
    guards: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        device_id = _uuid4(key, f"{label} key")
        if not isinstance(item, Mapping):
            raise _invalid(f"{label} for {device_id} must be an object")
        unknown = set(item) - _GUARD_KEYS
        if unknown:
            raise _invalid(f"{label} for {device_id} has unknown key")
        if _GUARD_KEYS - set(item):
            raise _invalid(f"{label} for {device_id} is incomplete")
        connection = item["connection_id"]
        if connection is not None and (
            not isinstance(connection, str) or not connection or len(connection) > 200
        ):
            raise _invalid(f"{label} connection_id for {device_id} is invalid")
        guards[device_id] = {
            "connection_id": connection,
            "viewport": _viewport(item["viewport"], f"{label} viewport for {device_id}"),
        }
    return guards


def _angle_map(value: Any, label: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object")
    angles: dict[str, int] = {}
    for key, angle in value.items():
        device_id = _uuid4(key, f"{label} key")
        if isinstance(angle, bool) or not isinstance(angle, int):
            raise _invalid(f"{label} for {device_id} must be 0, 90, 180 or 270")
        if angle % 360 not in (0, 90, 180, 270):
            raise _invalid(f"{label} for {device_id} must be 0, 90, 180 or 270")
        angles[device_id] = int(angle) % 360
    return angles


def _size_map(value: Any, label: str) -> dict[str, tuple[int, int]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object")
    sizes: dict[str, tuple[int, int]] = {}
    for key, item in value.items():
        device_id = _uuid4(key, f"{label} key")
        if isinstance(item, (tuple, list)) and not isinstance(item, (str, bytes)):
            if len(item) != 2:
                raise _invalid(f"{label} for {device_id} must be a w/h pair")
            sizes[device_id] = (
                _positive_int(item[0], f"{label} width for {device_id}"),
                _positive_int(item[1], f"{label} height for {device_id}"),
            )
            continue
        if not isinstance(item, Mapping):
            raise _invalid(f"{label} for {device_id} must be an object")
        unknown = set(item) - _SIZE_KEYS
        if unknown:
            raise _invalid(f"{label} for {device_id} has unknown key")
        if _SIZE_KEYS - set(item):
            raise _invalid(f"{label} for {device_id} is incomplete")
        sizes[device_id] = (
            _positive_int(item["w"], f"{label} width for {device_id}"),
            _positive_int(item["h"], f"{label} height for {device_id}"),
        )
    return sizes


def _pins_map(value: Any, label: str) -> dict[str, MeasurementPins]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object")
    pins: dict[str, MeasurementPins] = {}
    for key, item in value.items():
        device_id = _uuid4(key, f"{label} key")
        if isinstance(item, MeasurementPins):
            pins[device_id] = item
            continue
        if not isinstance(item, Mapping):
            raise _invalid(f"{label} for {device_id} must be an object")
        unknown = set(item) - _PIN_KEYS
        if unknown:
            raise _invalid(f"{label} for {device_id} has unknown key")
        if _PIN_KEYS - set(item):
            raise _invalid(f"{label} for {device_id} is incomplete")
        pins[device_id] = MeasurementPins(
            profile_revision=_positive_int(
                item["profile_revision"], f"{label} profile revision for {device_id}"
            ),
            calibration_revision=_positive_int(
                item["calibration_revision"],
                f"{label} calibration revision for {device_id}",
            ),
        )
    return pins


def _revision_index(value: Any, label: str) -> dict[int, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} must be an object")
    records: dict[int, dict[str, Any]] = {}
    for revision, record in value.items():
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise _invalid(f"{label} revisions must be positive integers")
        if not isinstance(record, Mapping):
            raise _invalid(f"{label} revision {revision} must be an object")
        records[revision] = deepcopy(dict(record))
    return records


def _uuid_list(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _invalid(f"{label} must be an array")
    return tuple(_uuid4(item, label) for item in value)


def _uuid4(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise _invalid(f"{label} must contain UUID4 strings")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise _invalid(f"{label} must contain UUID4 strings") from error
    if parsed.version != 4:
        raise _invalid(f"{label} must contain UUID4 strings")
    return str(parsed)


def _choice(value: Any, allowed: Sequence[str], label: str) -> Any:
    if value not in allowed:
        raise _invalid(f"{label} must be one of {', '.join(allowed)}")
    return value


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(f"{label} must be a boolean")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_COORDINATE:
        raise _invalid(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COORDINATE:
        raise _invalid(f"{label} must be a non-negative integer")
    return value


def _number(
    value: Any, label: str, *, nonnegative: bool = False
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"{label} must be a finite number")
    if abs(value) > MAX_COORDINATE or not math.isfinite(value):
        raise _invalid(f"{label} exceeds the exactly representable coordinate range")
    if nonnegative and value < 0:
        raise _invalid(f"{label} must be non-negative")
    return float(value)


def _positive_number(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0:
        raise _invalid(f"{label} must be positive")
    return result


def _finite(value: Any, label: str) -> float:
    return _number(value, label)


def _json_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else float(value)


def _invalid(message: str) -> GridError:
    return GridError(INVALID, message)
