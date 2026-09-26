"""The simulator's scenarios: numbered blocks that together exercise the app.

Each scenario is a plain function ``f(ctx)`` registered with
``@scenario(id, title)``. Checks go through the context: the first failing
check aborts *that* scenario (later checks in it would be measuring a broken
premise) while every other scenario still runs, so one report still shows
the whole surface.

What the scenarios deliberately do **not** do is reimplement the server:
expected values are either read back from HTTP, recomputed here from
PROTOCOL.md's rules with independent arithmetic (the auto grid, the tiling
areas), or hand-derived constants for the default 18-tablet fleet (the seam
crops). A check that merely re-ran the server's own code would prove
nothing.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from starlette.websockets import WebSocketDisconnect

from geometry import (
    adjacent_pairs,
    centred_cover,
    seam_gap,
    tiling_report,
    visible_rect,
)
from harness import (
    DEFAULT_WAIT_S,
    SOCKET_CLOSED,
    VirtualDevice,
    deterministic_device_id,
    write_png,
)
from report import Recorder

# The wall this run works on. Scenario 08 puts these dimensions on the wire;
# everything after them (bands, grids, anchors) is derived from them.
WALL_W = 2400
WALL_H = 1200

# Cells used by the hand-placed arrangements: 400x300 is exactly 4:3, the
# aspect of the plain tablets in the fleet.
CELL_W = 400
CELL_H = 300
BAND_COLS = 6


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    id: str
    title: str
    run: Callable[["Ctx"], None]


SCENARIOS: list[Scenario] = []


def scenario(scenario_id: str, title: str) -> Callable[[Callable[["Ctx"], None]], Callable[["Ctx"], None]]:
    def decorate(func: Callable[["Ctx"], None]) -> Callable[["Ctx"], None]:
        SCENARIOS.append(Scenario(scenario_id, title, func))
        return func

    return decorate


def frame_device_id(frame: dict[str, Any]) -> str | None:
    """The device a frame is about, whichever shape the server used.

    ``device_offline``/``device_removed`` carry ``device_id`` at the top
    level; ``device_online``/``device_updated`` carry a whole record under
    ``device``. Scenarios filter on this rather than on one shape.
    """
    direct = frame.get("device_id")
    if isinstance(direct, str):
        return direct
    record = frame.get("device")
    if isinstance(record, dict):
        nested = record.get("device_id")
        if isinstance(nested, str):
            return nested
    return None


class Ctx:
    """Everything a scenario may touch: the harness, the fleet, the recorder."""

    def __init__(self, harness: Any, recorder: Recorder, timeout: float = DEFAULT_WAIT_S) -> None:
        self.harness = harness
        self.rec = recorder
        self.devices: list[VirtualDevice] = harness.devices
        self.n = len(harness.devices)
        self.timeout = timeout

    # -- checks ------------------------------------------------------------
    def expect(
        self,
        name: str,
        ok: bool,
        expected: Any = None,
        actual: Any = None,
        detail: str = "",
    ) -> None:
        self.rec.expect(name, ok, expected=expected, actual=actual, detail=detail)

    def eq(self, name: str, actual: Any, expected: Any, detail: str = "") -> None:
        self.rec.eq(name, actual, expected, detail=detail)

    def close(self, name: str, actual: Any, expected: Any, tol: float = 1e-9, detail: str = "") -> None:
        ok = abs(float(actual) - float(expected)) <= tol
        self.rec.expect(
            name,
            ok,
            expected=f"{expected} (±{tol})",
            actual=actual,
            detail=detail,
        )

    def note(self, name: str, value: Any, unit: str = "") -> None:
        self.rec.note(name, value, unit=unit)

    # -- fleet / wall ------------------------------------------------------
    def device(self, slot: int) -> VirtualDevice:
        return self.devices[slot]

    @property
    def wall(self) -> dict[str, Any]:
        return self.harness.wall()

    def controller(self, label: str = "v2") -> Any:
        """A long-lived v2 controller, opening (and consuming) one on demand."""
        pump = self.harness.controllers.get(label)
        if pump is None:
            pump = self.harness.open_controller(label, protocol=2)
            pump.next_frame(
                predicate=lambda f: f.get("type") == "snapshot",
                timeout=self.timeout,
                what="snapshot",
            )
        return pump

    # -- frames ------------------------------------------------------------
    def wall_frame(
        self,
        device: VirtualDevice,
        revision: int | None = None,
        timeout: float | None = None,
        what: str = "wall frame",
    ) -> dict[str, Any]:
        """This device's next ``wall`` frame, optionally at an exact revision."""

        def match(frame: dict[str, Any]) -> bool:
            return frame.get("type") == "wall" and (
                revision is None or frame.get("revision") == revision
            )

        return device.pump.next_frame(
            timeout or self.timeout, predicate=match, what=what
        )

    def wall_frames(
        self,
        devices: Iterable[VirtualDevice] | None = None,
        revision: int | None = None,
        timeout: float | None = None,
        what: str = "wall frame",
    ) -> dict[str, dict[str, Any]]:
        """``{device_id: frame}`` for every device in ``devices``."""
        targets = list(devices) if devices is not None else self.devices
        deadline = time.monotonic() + (timeout or self.timeout)
        out: dict[str, dict[str, Any]] = {}
        for device in targets:
            remaining = max(0.1, deadline - time.monotonic())
            out[device.device_id] = self.wall_frame(
                device, revision=revision, timeout=remaining, what=what
            )
        return out

    def expect_event(
        self,
        pump: Any,
        event_type: str,
        device_id: str | None = None,
        timeout: float | None = None,
        what: str = "",
    ) -> dict[str, Any]:
        """A controller/device frame of ``event_type`` (optionally about one device).

        The device id is nested for roster events (``{"device": {...}}``) and
        top-level for socket events (``device_offline``), so both shapes are
        accepted rather than assuming one.
        """

        def match(frame: dict[str, Any]) -> bool:
            if frame.get("type") != event_type:
                return False
            return device_id is None or frame_device_id(frame) == device_id

        return pump.next_frame(
            timeout or self.timeout,
            predicate=match,
            what=what or f"{event_type} frame",
        )

    def raw_close_code(self, url: str) -> int | None:
        """Open a throwaway socket and report the close code the server used."""
        try:
            with self.harness.raw_connect(url) as session:
                try:
                    session.receive_json()
                except WebSocketDisconnect as exc:
                    return exc.code
                return None
        except WebSocketDisconnect as exc:
            return exc.code


# ---------------------------------------------------------------------------
# fleet geometry helpers (independent recomputations)
# ---------------------------------------------------------------------------


def _auto_columns(n: int, wall_w: int, wall_h: int, target_aspect: float = 4 / 3) -> int:
    """A ``columns`` value that both divides ``n`` and suits the wall.

    The server tiles ``columns x rows`` with ``rows = ceil(n / columns)``,
    so a ``columns`` that *divides* ``n`` means the grid has exactly ``n``
    cells and covers the whole wall — which is what lets "tiles exactly" be
    asserted as an equality. Among those divisors we take the one whose cell
    aspect is closest to the fleet's dominant viewport (4:3), so the numbers
    below stay close to what a real operator would pick.
    """
    divisors = [d for d in range(1, n + 1) if n % d == 0]

    def cell_aspect(columns: int) -> float:
        rows = n // columns
        return (wall_w / columns) / (wall_h / rows)

    return min(divisors, key=lambda c: abs(cell_aspect(c) - target_aspect))


def _grid_edges(count: int, wall: int) -> list[int]:
    """The server's rounded cell edges: ``round(i * wall / count)``."""
    return [round(i * wall / count) for i in range(count + 1)]


def _expected_grid(
    n: int, columns: int, wall_w: int, wall_h: int
) -> tuple[dict[int, dict[str, int]], list[int], list[int]]:
    """Recompute what ``POST /wall/auto`` must assign, cell by cell.

    Straight from PROTOCOL.md: index ``i`` lands in column ``i % columns``,
    row ``i // columns``, and the cell spans one rounded interval of the wall
    on each axis. Online order is registration order, which is fleet order.
    """
    rows = max(1, -(-n // columns))
    xs = _grid_edges(columns, wall_w)
    ys = _grid_edges(rows, wall_h)
    cells: dict[int, dict[str, int]] = {}
    for index in range(n):
        column = index % columns
        row = index // columns
        cells[index] = {
            "x": xs[column],
            "y": ys[row],
            "w": xs[column + 1] - xs[column],
            "h": ys[row + 1] - ys[row],
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }
    return cells, xs, ys


def _band_cells(n: int) -> dict[int, dict[str, int]]:
    """The hand-placed band: ``BAND_COLS`` columns of 400x300 cells."""
    cells: dict[int, dict[str, int]] = {}
    for index in range(n):
        cells[index] = {
            "x": (index % BAND_COLS) * CELL_W,
            "y": (index // BAND_COLS) * CELL_H,
            "w": CELL_W,
            "h": CELL_H,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }
    return cells


def _placement_from(cell: dict[str, int]) -> dict[str, Any]:
    return {"x": cell["x"], "y": cell["y"], "w": cell["w"], "h": cell["h"], "bezel": dict(cell["bezel"])}


# ---------------------------------------------------------------------------
# 01 — isolation
# ---------------------------------------------------------------------------


@scenario("01_isolation", "Temporary database and asset directory; nothing touches production data")
def isolation(ctx: Ctx) -> None:
    work = str(ctx.harness.work_dir)
    database = ctx.harness.env["TABLET_WALL_DB"]
    assets = ctx.harness.env["TABLET_WALL_ASSET_DIR"]
    ctx.expect(
        "database is a file in the temporary work dir",
        database.startswith(work) and database.endswith("tablet-wall.db"),
        expected=f"{work}/…/tablet-wall.db",
        actual=database,
    )
    ctx.expect(
        "asset directory is in the temporary work dir",
        assets.startswith(work),
        expected=f"{work}/…",
        actual=assets,
    )

    # The app must read exactly those paths (they are read at call time).
    import tabletwall.assets as assets_module
    import tabletwall.persist as persist_module

    ctx.eq("persist.db_path() matches the environment", persist_module.db_path(), database)
    ctx.eq("assets.asset_dir() matches the environment", assets_module.asset_dir(), assets)

    # A developer's ambient origin fences must not change what is exercised.
    for name in ("TABLET_WALL_OPERATOR_ORIGIN", "TABLET_WALL_TABLET_ORIGIN"):
        ctx.expect(
            f"{name} is cleared for this run",
            os.environ.get(name) is None,
            expected=None,
            actual=os.environ.get(name),
        )

    wall = ctx.wall
    ctx.eq("a brand-new temporary database starts at revision 0", wall["revision"], 0)
    ctx.expect(
        "generation token present",
        isinstance(wall["generation"], str) and len(wall["generation"]) == 8,
        expected="8 hex chars",
        actual=wall.get("generation"),
    )
    ctx.eq("default wall dimensions on first boot", (wall["width"], wall["height"]), (2000, 1000))
    ctx.eq("default scene content", wall["scene"]["content"], {"type": "color"})
    ctx.eq("no placements on first boot", wall["placements"], {})


# ---------------------------------------------------------------------------
# 02 — bulk registration
# ---------------------------------------------------------------------------


@scenario("02_registration", "Every virtual tablet registers and appears in the roster")
def registration(ctx: Ctx) -> None:
    ctx.harness.register_all()
    roster = ctx.harness.roster()
    ctx.eq("roster holds every fleet device", len(roster), ctx.n)

    for device in ctx.devices:
        record = roster.get(device.device_id)
        if record is None:
            ctx.expect(f"{device.label} is registered", False, expected="record", actual=None)
            continue
        ctx.eq(
            f"{device.label} record shape",
            (
                record["width"],
                record["height"],
                record["type"],
                record["color"],
                record["online"],
                record["protocol"],
                record["caps"],
            ),
            (device.width, device.height, device.device_type, None, False, None, []),
        )

    single = ctx.harness.get(f"/device/{ctx.devices[0].device_id}")
    ctx.eq("GET /device/{id} answers 200", single.status_code, 200)
    ctx.eq("GET /device/{id} returns the same record", single.json()["device_id"], ctx.devices[0].device_id)
    ctx.eq(
        "GET /device/{unknown} is 404",
        ctx.harness.get(f"/device/{deterministic_device_id('nobody')}").status_code,
        404,
    )
    ctx.eq(
        "GET /devices/register documents the POST",
        ctx.harness.get("/devices/register").json()["message"],
        "Use POST to register a device",
    )

    # A device added and removed again leaves the fleet untouched.
    extra = deterministic_device_id("temporary-guest")
    created = ctx.harness.post(
        "/devices/register",
        json={"device_id": extra, "width": 640, "height": 480, "device_type": "guest"},
    )
    ctx.eq("an extra device can register", created.status_code, 200)
    ctx.eq("roster grew by one", len(ctx.harness.roster()), ctx.n + 1)
    removed = ctx.harness.delete(f"/devices/{extra}")
    ctx.eq("removing it succeeds", removed.json(), {"removed": True, "device_id": extra})
    ctx.eq("roster is back to the fleet", len(ctx.harness.roster()), ctx.n)
    ctx.eq(
        "removing it twice is 404",
        ctx.harness.delete(f"/devices/{extra}").status_code,
        404,
    )


# ---------------------------------------------------------------------------
# 03 — registration validation
# ---------------------------------------------------------------------------


@scenario("03_registration_validation", "Bad registration bodies are rejected with 422")
def registration_validation(ctx: Ctx) -> None:
    body = ctx.devices[0].registration()

    def post(payload: dict[str, Any]) -> Any:
        return ctx.harness.post("/devices/register", json=payload)

    bad_uuid = dict(body, device_id="not-a-uuid")
    ctx.eq("a malformed id is 422", post(bad_uuid).status_code, 422)

    version_one = dict(body, device_id="11111111-1111-1111-1111-111111111111")
    ctx.eq("a version-1 UUID is 422", post(version_one).status_code, 422)

    missing = {key: value for key, value in body.items() if key != "device_type"}
    ctx.eq("a missing field is 422", post(missing).status_code, 422)

    wrong_type = dict(body, width="wide")
    ctx.eq("a non-integer dimension is 422", post(wrong_type).status_code, 422)

    # Registration deliberately tolerates unknown keys (unlike the PUT
    # bodies, which are ``extra="forbid"``): check the real contract rather
    # than the stricter one, and check that the key never reaches the record.
    extra = dict(body, colour="#ff0000")
    ctx.eq("an unknown key is accepted on registration", post(extra).status_code, 200)
    ctx.expect(
        "the unknown key never reaches the record",
        "colour" not in ctx.harness.roster()[body["device_id"]],
        expected="no 'colour' key",
        actual=sorted(ctx.harness.roster()[body["device_id"]]),
    )

    ctx.eq(
        "a rejected body did not join the roster",
        len(ctx.harness.roster()),
        ctx.n,
        detail="422 must not half-register anything",
    )
    again = post(body)
    ctx.eq("re-registering the same device is 200", again.status_code, 200)
    ctx.eq("re-registration is idempotent", len(ctx.harness.roster()), ctx.n)


# ---------------------------------------------------------------------------
# 04 — controller snapshot
# ---------------------------------------------------------------------------


@scenario("04_controller_snapshot", "A v2 controller's first frame is a full snapshot")
def controller_snapshot(ctx: Ctx) -> None:
    wall = ctx.wall
    pump = ctx.harness.open_controller("v2", protocol=2)
    snapshot = pump.next_frame(predicate=lambda f: f.get("type") == "snapshot", what="snapshot")
    ctx.eq("snapshot lists the whole roster", len(snapshot["devices"]), ctx.n)
    ctx.eq("every roster entry starts offline", {d["online"] for d in snapshot["devices"]}, {False})
    ctx.expect(
        "v2 snapshot carries the wall",
        isinstance(snapshot.get("wall"), dict),
        expected="wall object",
        actual=snapshot.get("wall"),
    )
    ctx.eq("snapshot wall revision matches GET /wall", snapshot["wall"]["revision"], wall["revision"])
    ctx.eq("snapshot wall generation matches GET /wall", snapshot["wall"]["generation"], wall["generation"])
    ctx.eq(
        "snapshot device ids match the roster",
        sorted(d["device_id"] for d in snapshot["devices"]),
        sorted(ctx.harness.roster()),
    )
    ctx.eq("no stray frame precedes the snapshot", pump.frames_within(0.2), [])


# ---------------------------------------------------------------------------
# 05 — device handshake
# ---------------------------------------------------------------------------


@scenario("05_device_handshake", "welcome + wall replay for every tablet; handshake rejections")
def device_handshake(ctx: Ctx) -> None:
    wall = ctx.wall
    controller = ctx.controller("v2")
    controller.drain()

    welcomes = ctx.harness.connect_all()
    ctx.eq("every tablet got a socket", len(welcomes), ctx.n)

    for device, welcome in welcomes:
        ctx.eq(f"{device.label} welcome type", welcome["type"], "welcome")
        ctx.eq(f"{device.label} welcome id", welcome["device_id"], device.device_id)
        ctx.eq(f"{device.label} heartbeat interval", welcome["heartbeat_interval_ms"], 5000)
        ctx.eq(f"{device.label} negotiated protocol 2", welcome.get("protocol"), 2)
        ctx.eq(f"{device.label} server caps", welcome.get("server_caps"), ["calibration", "image"])

    # Reconnect-safe replay: the very next frame is the whole wall, at the
    # revision GET /wall reports right now, with no placement yet.
    for device in ctx.devices:
        frame = ctx.wall_frame(device, revision=wall["revision"], what="wall replay")
        ctx.eq(f"{device.label} replay revision", frame["revision"], wall["revision"])
        ctx.eq(f"{device.label} replay generation", frame["generation"], wall["generation"])
        ctx.eq(f"{device.label} replay placement", frame["placement"], None)
        ctx.eq(f"{device.label} replay scene", frame["scene"]["content"], {"type": "color"})
        ctx.eq(
            f"{device.label} replay wall size",
            (frame["wall"]["width"], frame["wall"]["height"]),
            (wall["width"], wall["height"]),
        )

    # Each connection must have been announced to the controllers exactly once.
    for index in range(ctx.n):
        ctx.expect_event(controller, "device_online", device_id=ctx.devices[index].device_id, what="device_online")
    ctx.eq(
        "no other controller event arrived",
        controller.frames_within(0.2),
        [],
        detail="only device_online belongs to a first connection",
    )

    # Handshake rejections: the server accepts first, then closes with a
    # documented code so a browser can observe it.
    code = ctx.raw_close_code(f"/ws/device?device_id={deterministic_device_id('nobody')}&protocol=2")
    ctx.eq("an unregistered device is closed with 4404", code, 4404)
    code = ctx.raw_close_code(f"/ws/device?device_id={ctx.devices[0].device_id}&protocol=9")
    ctx.eq("an unsupported protocol is closed with 4426", code, 4426)
    code = ctx.raw_close_code("/ws/device?device_id=not-a-uuid&protocol=2")
    ctx.eq("a malformed device id is closed with 4400", code, 4400)


# ---------------------------------------------------------------------------
# 06 — presence and controllers
# ---------------------------------------------------------------------------


@scenario("06_presence", "Controllers see the fleet online; a v1 controller sees no v2 frames")
def presence(ctx: Ctx) -> None:
    # A controller opened *now* must already know every tablet is online.
    fresh = ctx.harness.open_controller("v2b", protocol=2)
    snapshot = fresh.next_frame(predicate=lambda f: f.get("type") == "snapshot", what="snapshot")
    ctx.eq("snapshot counts the fleet", len(snapshot["devices"]), ctx.n)
    ctx.eq("every tablet is online", {d["online"] for d in snapshot["devices"]}, {True})
    ctx.eq(
        "roster agrees with the controller",
        {rec["online"] for rec in ctx.harness.roster().values()},
        {True},
    )

    # A version-1 controller gets a version-1 snapshot and must never be
    # handed a version-2 wall frame. The v2 controller beside it proves the
    # broadcast really happened during the same window.
    v1 = ctx.harness.open_controller("v1", protocol=None)
    v1_snapshot = v1.next_frame(predicate=lambda f: f.get("type") == "snapshot", what="v1 snapshot")
    ctx.eq("v1 snapshot lists the roster", len(v1_snapshot["devices"]), ctx.n)
    ctx.expect(
        "v1 snapshot carries no wall object",
        "wall" not in v1_snapshot,
        expected="no 'wall' key",
        actual=sorted(v1_snapshot),
    )

    v2 = ctx.controller("v2")
    v1.drain()
    v2.drain()
    current = ctx.wall
    before = current["revision"]
    response = ctx.harness.put(
        "/wall", json={"width": current["width"], "height": current["height"]}
    )
    ctx.eq("the broadcast change is accepted", response.status_code, 200)
    revision = response.json()["revision"]
    ctx.eq("revision advanced by one", revision, before + 1)

    ctx.expect_event(v2, "wall_updated", what="wall_updated on v2")
    stray = v1.frames_within(0.3)
    ctx.eq(
        "v1 controller received nothing while v2 was updated",
        stray,
        [],
        detail="version-1 sockets must not see wall_updated",
    )
    ctx.harness.close_controller("v1")


# ---------------------------------------------------------------------------
# 07 — colour commands
# ---------------------------------------------------------------------------


@scenario("07_colour", "Colour commands reach every socket and are validated")
def colour(ctx: Ctx) -> None:
    controller = ctx.controller("v2")
    controller.drain()
    for device in ctx.devices:
        device.pump.drain()

    response = ctx.harness.post("/devices/color", json={"color": "#FF00AA"})
    ctx.eq("broadcast colour accepted", response.status_code, 200)
    payload = response.json()
    ctx.eq("colour is normalised", payload["color"], "#ff00aa")
    ctx.eq("every roster entry updated", payload["updated"], ctx.n)
    ctx.eq("every socket was delivered to", payload["delivered"], ctx.n)

    for device in ctx.devices:
        frame = device.pump.next_frame(
            predicate=lambda f: f.get("type") == "set_color",
            what="set_color",
        )
        ctx.eq(f"{device.label} colour", frame["color"], "#ff00aa")
    for index in range(ctx.n):
        ctx.expect_event(controller, "device_updated", device_id=ctx.devices[index].device_id)

    single = ctx.harness.post(
        f"/devices/{ctx.devices[0].device_id}/color", json={"color": "00ff00"}
    )
    ctx.eq("single-device colour delivered", single.json()["delivered"], 1)
    frame = ctx.devices[0].pump.next_frame(
        predicate=lambda f: f.get("type") == "set_color", what="set_color"
    )
    ctx.eq("single-device colour value", frame["color"], "#00ff00")

    ctx.eq(
        "an invalid colour is 422",
        ctx.harness.post("/devices/color", json={"color": "zzz"}).status_code,
        422,
    )
    ctx.eq(
        "a colour for an unknown device is 404",
        ctx.harness.post(
            f"/devices/{deterministic_device_id('nobody')}/color", json={"color": "00ff00"}
        ).status_code,
        404,
    )
    ctx.eq(
        "the roster colour really changed",
        ctx.harness.roster()[ctx.devices[0].device_id]["color"],
        "#00ff00",
    )


# ---------------------------------------------------------------------------
# 08 — wall layout
# ---------------------------------------------------------------------------


@scenario("08_wall_layout", "PUT /wall resizes the canvas, broadcasts, and validates")
def wall_layout(ctx: Ctx) -> None:
    before = ctx.wall
    ctx.eq("starting dimensions", (before["width"], before["height"]), (2000, 1000))

    response = ctx.harness.put("/wall", json={"width": WALL_W, "height": WALL_H})
    ctx.eq("resize accepted", response.status_code, 200)
    resized = response.json()
    ctx.eq("revision advanced by one", resized["revision"], before["revision"] + 1)
    ctx.eq("generation unchanged by a layout change", resized["generation"], before["generation"])

    frames = ctx.wall_frames(revision=resized["revision"])
    for device in ctx.devices:
        frame = frames[device.device_id]
        ctx.eq(
            f"{device.label} sees the new canvas",
            (frame["wall"]["width"], frame["wall"]["height"]),
            (WALL_W, WALL_H),
        )

    ctx.eq(
        "zero width is 422",
        ctx.harness.put("/wall", json={"width": 0}).status_code,
        422,
    )
    ctx.eq(
        "negative height is 422",
        ctx.harness.put("/wall", json={"height": -5}).status_code,
        422,
    )
    ctx.eq(
        "an unknown key is 422, not silently ignored",
        ctx.harness.put("/wall", json={"mode": "solid"}).status_code,
        422,
    )
    ctx.eq(
        "the wall is unchanged by rejected bodies",
        (ctx.wall["width"], ctx.wall["height"]),
        (WALL_W, WALL_H),
    )

    only_height = ctx.harness.put("/wall", json={"height": WALL_H})
    ctx.eq("a single-field resize is accepted", only_height.status_code, 200)
    ctx.eq(
        "the untouched dimension survived",
        (only_height.json()["width"], only_height.json()["height"]),
        (WALL_W, WALL_H),
    )


# ---------------------------------------------------------------------------
# 09 — explicit placements
# ---------------------------------------------------------------------------


@scenario("09_placements", "Every tablet is placed by hand; each placement bumps the revision once")
def placements(ctx: Ctx) -> None:
    cells = _band_cells(ctx.n)
    revision = ctx.wall["revision"]
    controller = ctx.controller("v2")
    controller.drain()

    for index, device in enumerate(ctx.devices):
        cell = cells[index]
        response = ctx.harness.put(
            f"/devices/{device.device_id}/placement",
            json={"x": cell["x"], "y": cell["y"], "w": cell["w"], "h": cell["h"], "bezel": cell["bezel"]},
        )
        ctx.eq(f"{device.label} placement accepted", response.status_code, 200)
        revision += 1
        ctx.eq(f"{device.label} bumped the revision once", response.json()["revision"], revision)

    wall = ctx.wall
    ctx.eq("every device has a placement", len(wall["placements"]), ctx.n)
    ctx.expect(
        "placements are stored with their device_id",
        all(key == value["device_id"] for key, value in wall["placements"].items()),
        expected="key == placement.device_id",
        actual={k: v["device_id"] for k, v in wall["placements"].items()},
    )

    # Each tablet's own frame carries its own rect, stripped of device_id.
    frames = ctx.wall_frames(revision=revision)
    for index, device in enumerate(ctx.devices):
        expected = {key: value for key, value in _placement_from(cells[index]).items()}
        ctx.eq(f"{device.label} frame placement", frames[device.device_id]["placement"], expected)
        ctx.eq(f"{device.label} frame has no device_id", "device_id" in (frames[device.device_id]["placement"] or {}), False)

    # The band tiles its own rectangle exactly: no overlaps, no holes, all
    # inside the wall (a partial last row is still a partition of its union).
    metrics = tiling_report(cells, WALL_W, WALL_H)
    ctx.eq("no cell overlaps another", metrics["overlap_area"], 0)
    ctx.eq("no cell sticks out of the wall", metrics["out_of_bounds"], [])
    ctx.eq("no degenerate cell", metrics["degenerate"], [])
    ctx.eq("cells are a partition of their union", metrics["sum_area"], metrics["union_area"])
    if ctx.n % BAND_COLS == 0:
        band_area = WALL_W * ((ctx.n // BAND_COLS) * CELL_H)
        ctx.eq(
            "the band covers its whole rectangle",
            metrics["covered_area"],
            float(band_area),
            detail=f"{ctx.n} cells of {CELL_W}x{CELL_H} in {BAND_COLS} columns",
        )
    ctx.note("band cells", ctx.n)
    ctx.note("band covered area", metrics["covered_area"], "wall units^2")

    controller.drain()


# ---------------------------------------------------------------------------
# 10 — placement validation
# ---------------------------------------------------------------------------


@scenario("10_placement_validation", "Bad placements are 422/404; releasing a slot is idempotent")
def placement_validation(ctx: Ctx) -> None:
    victim = ctx.devices[0]
    cells = _band_cells(ctx.n)

    def put(device_id: str, payload: dict[str, Any]) -> Any:
        return ctx.harness.put(f"/devices/{device_id}/placement", json=payload)

    revision_before = ctx.wall["revision"]
    ctx.eq(
        "an unknown device cannot be placed",
        put(deterministic_device_id("nobody"), {"x": 0, "y": 0, "w": 10, "h": 10}).status_code,
        404,
    )
    ctx.eq(
        "a malformed device id is 404",
        put("not-a-uuid", {"x": 0, "y": 0, "w": 10, "h": 10}).status_code,
        404,
    )
    ctx.eq("zero width is 422", put(victim.device_id, {"x": 0, "y": 0, "w": 0, "h": 10}).status_code, 422)
    ctx.eq("zero height is 422", put(victim.device_id, {"x": 0, "y": 0, "w": 10, "h": 0}).status_code, 422)
    ctx.eq(
        "a bezel that erases the visible rect is 422",
        put(
            victim.device_id,
            {"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"left": 60, "right": 40}},
        ).status_code,
        422,
    )
    ctx.eq(
        "a non-integer bezel is 422",
        put(
            victim.device_id,
            {"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"left": "wide"}},
        ).status_code,
        422,
    )
    ctx.eq(
        "rejected placements changed nothing",
        ctx.wall["revision"],
        revision_before,
        detail="a 422 must not bump the revision",
    )
    ctx.eq(
        "the device kept its placement",
        ctx.wall["placements"][victim.device_id]["w"],
        cells[0]["w"],
    )

    # Releasing: 200 even when there is nothing to release, and the device's
    # own frame follows the release.
    revision = ctx.wall["revision"]
    controller = ctx.controller("v2")
    controller.drain()
    released = ctx.harness.delete(f"/devices/{victim.device_id}/placement")
    ctx.eq("release accepted", released.status_code, 200)
    revision += 1
    ctx.eq("release bumped the revision", released.json()["revision"], revision)
    ctx.expect(
        "the placement is gone",
        victim.device_id not in ctx.wall["placements"],
        expected="absent",
        actual=sorted(ctx.wall["placements"]),
    )
    frame = ctx.wall_frame(victim, revision=revision)
    ctx.eq("the device is told it has no placement", frame["placement"], None)
    ctx.expect_event(controller, "wall_updated", what="wall_updated after release")

    again = ctx.harness.delete(f"/devices/{victim.device_id}/placement")
    ctx.eq("releasing twice still succeeds", again.status_code, 200)
    ctx.eq("releasing twice bumps the revision again", again.json()["revision"], revision + 1)
    ctx.eq(
        "releasing an unknown device is 404",
        ctx.harness.delete(f"/devices/{deterministic_device_id('nobody')}/placement").status_code,
        404,
    )

    # Put it back so the band still tiles for the scenarios that follow.
    restored = put(victim.device_id, _placement_from(cells[0]))
    ctx.eq("restoring the placement succeeds", restored.status_code, 200)
    ctx.eq(
        "the band is whole again",
        len(ctx.wall["placements"]),
        ctx.n,
    )


# ---------------------------------------------------------------------------
# 11 — scene: colour
# ---------------------------------------------------------------------------


@scenario("11_scene_colour", "PUT /scene sets content only, and validates the variant")
def scene_colour(ctx: Ctx) -> None:
    before = ctx.wall
    response = ctx.harness.put("/scene", json={"content": {"type": "color"}})
    ctx.eq("colour scene accepted", response.status_code, 200)
    revision = before["revision"] + 1
    ctx.eq("revision advanced by one", response.json()["revision"], revision)
    ctx.eq(
        "content only — the layout is untouched",
        response.json()["placements"],
        before["placements"],
    )
    ctx.eq("the wire content object is exactly the type", response.json()["scene"]["content"], {"type": "color"})

    frames = ctx.wall_frames(revision=revision)
    for device in ctx.devices:
        ctx.eq(f"{device.label} sees colour", frames[device.device_id]["scene"]["content"], {"type": "color"})

    ctx.eq(
        "an unknown content type is 422",
        ctx.harness.put("/scene", json={"content": {"type": "colour"}}).status_code,
        422,
    )
    ctx.eq(
        "an image without an asset is 422",
        ctx.harness.put("/scene", json={"content": {"type": "image"}}).status_code,
        422,
    )
    ctx.eq(
        "an asset on colour content is 422",
        ctx.harness.put(
            "/scene",
            json={"content": {"type": "color", "asset": "sha256:" + "0" * 64}},
        ).status_code,
        422,
    )
    ctx.eq(
        "an unknown key is 422",
        ctx.harness.put("/scene", json={"mode": "solid"}).status_code,
        422,
    )
    ctx.eq(
        "rejected bodies did not move the revision",
        ctx.wall["revision"],
        revision,
    )


# ---------------------------------------------------------------------------
# 12 — scene: calibration and the capability downgrade
# ---------------------------------------------------------------------------


@scenario("12_scene_calibration_caps", "Calibration reaches capable tablets; others are downgraded")
def scene_calibration_caps(ctx: Ctx) -> None:
    before = ctx.wall
    response = ctx.harness.put("/scene", json={"content": {"type": "calibration"}})
    ctx.eq("calibration scene accepted", response.status_code, 200)
    revision = before["revision"] + 1
    ctx.eq("revision advanced", response.json()["revision"], revision)

    frames = ctx.wall_frames(revision=revision)
    saw_calibration = saw_downgrade = 0
    for device in ctx.devices:
        frame = frames[device.device_id]
        capable = "calibration" in device.caps
        expected = {"type": "calibration"} if capable else {"type": "color"}
        ctx.eq(f"{device.label} content (caps={device.caps})", frame["scene"]["content"], expected)
        ctx.eq(f"{device.label} keeps its generation", frame["generation"], before["generation"])
        stored = before["placements"].get(device.device_id)
        ctx.eq(
            f"{device.label} keeps its placement",
            frame["placement"],
            None if stored is None else {k: v for k, v in stored.items() if k != "device_id"},
        )
        saw_calibration += capable
        saw_downgrade += not capable
    ctx.expect(
        "the fleet exercises both sides of the downgrade",
        saw_calibration > 0 and saw_downgrade > 0,
        expected="at least one capable and one incapable tablet",
        actual={"calibration": saw_calibration, "downgraded": saw_downgrade},
    )
    ctx.eq("the controller sees the real content", ctx.wall["scene"]["content"], {"type": "calibration"})


# ---------------------------------------------------------------------------
# 13 — scene: still image, inventory and bytes
# ---------------------------------------------------------------------------


@scenario("13_scene_image", "Curated asset, image scene, per-device descriptor, and byte re-hashing")
def scene_image(ctx: Ctx) -> None:
    asset_path = ctx.harness.work_dir / "assets" / "Simulator.png"
    png = write_png(asset_path, 160, 120, (30, 60, 120))
    expected_id = "sha256:" + hashlib.sha256(png).hexdigest()

    inventory = ctx.harness.get("/assets")
    ctx.eq("inventory is 200", inventory.status_code, 200)
    ctx.eq("inventory must not be cacheable", inventory.headers.get("cache-control"), "no-store")
    entries = inventory.json()["assets"]
    ctx.eq("one curated file", len(entries), 1)
    entry = entries[0]
    ctx.eq(
        "entry descriptor",
        (
            entry["name"],
            entry["mime"],
            entry["intrinsicWidth"],
            entry["intrinsicHeight"],
            entry["bytes"],
            entry["url"],
        ),
        ("Simulator.png", "image/png", 160, 120, len(png), f"/assets/{expected_id}"),
    )
    ctx.eq("content id is the hash of the bytes", entry["id"], expected_id)

    served = ctx.harness.get(f"/assets/{expected_id}")
    ctx.eq("asset bytes are served", served.status_code, 200)
    ctx.eq("served bytes re-hash to the id", "sha256:" + hashlib.sha256(served.content).hexdigest(), expected_id)
    ctx.eq("served payload is the file", served.content, png)
    ctx.eq("served content type", served.headers.get("content-type"), "image/png")
    ctx.eq("served nosniff", served.headers.get("x-content-type-options"), "nosniff")
    ctx.eq(
        "an unknown asset id is 404",
        ctx.harness.get("/assets/sha256:" + "0" * 64).status_code,
        404,
    )

    before = ctx.wall
    accepted = ctx.harness.put(
        "/scene", json={"content": {"type": "image", "asset": expected_id}}
    )
    ctx.eq("image scene accepted", accepted.status_code, 200)
    revision = before["revision"] + 1
    ctx.eq("revision advanced", accepted.json()["revision"], revision)
    ctx.eq(
        "the wire descriptor carries the composed url and derived size",
        accepted.json()["scene"]["content"],
        {
            "type": "image",
            "asset": expected_id,
            "fit": "cover",
            "intrinsicWidth": 160,
            "intrinsicHeight": 120,
            "url": f"/assets/{expected_id}",
        },
    )

    frames = ctx.wall_frames(revision=revision)
    capable = incapable = 0
    for device in ctx.devices:
        content = frames[device.device_id]["scene"]["content"]
        if "image" in device.caps:
            capable += 1
            ctx.eq(f"{device.label} gets the image descriptor (caps={device.caps})", content.get("type"), "image")
            ctx.eq(f"{device.label} asset url", content.get("url"), f"/assets/{expected_id}")
        else:
            incapable += 1
            ctx.eq(
                f"{device.label} is downgraded to colour (caps={device.caps})",
                content,
                {"type": "color"},
            )
    ctx.expect(
        "the fleet exercises both sides of the image downgrade",
        capable > 0 and incapable > 0,
        expected="at least one image-capable and one incapable tablet",
        actual={"image": capable, "downgraded": incapable},
    )

    unknown = "sha256:" + "1" * 64
    ctx.eq(
        "a well-formed but unknown asset is 422",
        ctx.harness.put("/scene", json={"content": {"type": "image", "asset": unknown}}).status_code,
        422,
    )
    ctx.eq("a rejected asset left the revision alone", ctx.wall["revision"], revision)
    ctx.eq(
        "an unsupported fit is 422",
        ctx.harness.put(
            "/scene", json={"content": {"type": "image", "asset": expected_id, "fit": "stretch"}}
        ).status_code,
        422,
    )
    ctx.eq("the scene is still the accepted one", ctx.wall["scene"]["content"]["asset"], expected_id)

    # The directory is re-scanned on every read: a second file appears at once.
    write_png(ctx.harness.work_dir / "assets" / "Second.png", 64, 64, (200, 40, 40))
    refreshed = ctx.harness.get("/assets").json()["assets"]
    ctx.eq("inventory picks up new files without a restart", len(refreshed), 2)
    # ... and removing it drops it from the inventory at once.
    asset_path.unlink()
    ctx.eq("inventory drops removed files", len(ctx.harness.get("/assets").json()["assets"]), 1)
    ctx.eq(
        "a vanished asset now 404s instead of serving stale bytes",
        ctx.harness.get(f"/assets/{expected_id}").status_code,
        404,
    )

    # Put a working image back so later scenarios have content to save/recall.
    second_id = next(
        item["id"] for item in ctx.harness.get("/assets").json()["assets"]
    )
    restored = ctx.harness.put("/scene", json={"content": {"type": "image", "asset": second_id}})
    ctx.eq("the surviving asset can be shown", restored.status_code, 200)
    ctx.note("active image asset", second_id)


# ---------------------------------------------------------------------------
# 14 — named snapshots: layouts and scenes
# ---------------------------------------------------------------------------


@scenario("14_snapshots", "Saved layouts and scenes recall independently, and saves never bump")
def snapshots(ctx: Ctx) -> None:
    start = ctx.wall
    layout_name = "GridBands"
    scene_name = "Picture"

    # --- save the layout: no revision change, no broadcast ---------------
    saved = ctx.harness.put(f"/layouts/{layout_name}")
    ctx.eq("layout saved", saved.status_code, 200)
    ctx.eq("saving does not bump the revision", ctx.wall["revision"], start["revision"])
    listing = ctx.harness.get("/layouts").json()["layouts"]
    names = [entry["name"] for entry in listing]
    ctx.expect("the layout is listed", layout_name in names, expected=layout_name, actual=names)
    stored = next(entry["layout"] for entry in listing if entry["name"] == layout_name)
    ctx.eq("stored width/height match the wall", (stored["width"], stored["height"]), (WALL_W, WALL_H))
    ctx.eq("stored placements match the wall", stored["placements"], start["placements"])

    ctx.eq(
        "saving twice is 409 without replace",
        ctx.harness.put(f"/layouts/{layout_name}").status_code,
        409,
    )
    ctx.eq(
        "replace=true overwrites",
        ctx.harness.put(f"/layouts/{layout_name}", params={"replace": "true"}).status_code,
        200,
    )
    ctx.eq(
        "a malformed name is 422",
        ctx.harness.put("/layouts/bad!name").status_code,
        422,
    )

    # --- change the wall, then recall the saved arrangement --------------
    revision = ctx.wall["revision"]
    dropped = ctx.harness.delete(f"/devices/{ctx.devices[-1].device_id}/placement")
    ctx.eq("a placement was released", dropped.status_code, 200)
    revision += 1
    ctx.eq("release bumped the revision", ctx.wall["revision"], revision)

    recalled = ctx.harness.post(f"/layouts/{layout_name}/recall")
    ctx.eq("recall accepted", recalled.status_code, 200)
    revision += 1
    ctx.eq("recall bumps the revision", recalled.json()["revision"], revision)
    ctx.eq("recall restores every placement", recalled.json()["placements"], start["placements"])
    ctx.eq("recall leaves the scene alone", recalled.json()["scene"], start["scene"])
    ctx.eq(
        "recalling an unknown layout is 404",
        ctx.harness.post("/layouts/NoSuchLayout/recall").status_code,
        404,
    )

    # --- scenes save and recall their content only -----------------------
    ctx.eq("scene saved", ctx.harness.put(f"/scenes/{scene_name}").status_code, 200)
    ctx.eq("saving a scene does not bump", ctx.wall["revision"], revision)
    scene_listing = ctx.harness.get("/scenes").json()["scenes"]
    scene_names = [entry["name"] for entry in scene_listing]
    ctx.expect("the scene is listed", scene_name in scene_names, expected=scene_name, actual=scene_names)
    stored_scene = next(entry["content"] for entry in scene_listing if entry["name"] == scene_name)
    ctx.expect(
        "the stored content carries no composed url",
        "url" not in stored_scene,
        expected="no 'url' key (the server composes it on the way out)",
        actual=sorted(stored_scene),
    )

    revision += 1
    switched = ctx.harness.put("/scene", json={"content": {"type": "color"}})
    ctx.eq("scene switched to colour", switched.status_code, 200)
    ctx.eq("switching bumps the revision", switched.json()["revision"], revision)
    layout_before_recall = ctx.wall["placements"]

    scene_recalled = ctx.harness.post(f"/scenes/{scene_name}/recall")
    ctx.eq("scene recall accepted", scene_recalled.status_code, 200)
    revision += 1
    ctx.eq("scene recall bumps the revision", scene_recalled.json()["revision"], revision)
    ctx.eq(
        "scene recall restores the content (with its composed url)",
        scene_recalled.json()["scene"]["content"]["type"],
        "image",
    )
    ctx.expect(
        "scene recall leaves the arrangement alone",
        scene_recalled.json()["placements"] == layout_before_recall,
        expected=layout_before_recall,
        actual=scene_recalled.json()["placements"],
    )

    ctx.eq(
        "recalling an unknown scene is 404",
        ctx.harness.post("/scenes/NoSuchScene/recall").status_code,
        404,
    )
    ctx.eq("a 404 recall did not bump", ctx.wall["revision"], revision)

    ctx.eq("layout deleted", ctx.harness.delete(f"/layouts/{layout_name}").status_code, 200)
    ctx.eq("deleting a layout twice is 404", ctx.harness.delete(f"/layouts/{layout_name}").status_code, 404)
    ctx.eq("scene deleted", ctx.harness.delete(f"/scenes/{scene_name}").status_code, 200)
    ctx.eq("deleting a scene twice is 404", ctx.harness.delete(f"/scenes/{scene_name}").status_code, 404)
    ctx.eq(
        "deleting snapshots leaves the active wall alone",
        ctx.wall["revision"],
        revision,
        detail="only recall is a wall change",
    )


# ---------------------------------------------------------------------------
# 15 — auto tiling
# ---------------------------------------------------------------------------


@scenario("15_auto_tiling", "Auto-arrange tiles the wall; the geometry is checked as numbers")
def auto_tiling(ctx: Ctx) -> None:
    controller = ctx.controller("v2")
    controller.drain()
    for device in ctx.devices:
        device.pump.drain()

    n = ctx.n
    wall = ctx.wall
    revision = wall["revision"]

    # --- default columns: a vacancy we can predict exactly ---------------
    response = ctx.harness.post("/wall/auto")
    ctx.eq("auto-arrange accepted", response.status_code, 200)
    revision += 1
    ctx.eq("auto bumped the revision", response.json()["revision"], revision)

    default_columns = max(1, round(math.sqrt(n)))
    default_rows = -(-n // default_columns)
    expected_cells, xs, ys = _expected_grid(n, default_columns, WALL_W, WALL_H)
    assigned = response.json()["placements"]
    ctx.eq("every online tablet got a cell", len(assigned), n)

    vacant = [
        (row, column)
        for row in range(default_rows)
        for column in range(default_columns)
        if (row, column)
        not in {(index // default_columns, index % default_columns) for index in range(n)}
    ]
    vacant_area = sum(
        (xs[column + 1] - xs[column]) * (ys[row + 1] - ys[row]) for row, column in vacant
    )
    metrics = tiling_report(
        {device_id: value for device_id, value in assigned.items()}, WALL_W, WALL_H
    )
    ctx.eq("default grid leaves no overlaps", metrics["overlap_area"], 0)
    ctx.eq("default grid stays inside the wall", metrics["out_of_bounds"], [])
    ctx.eq(
        "default grid leaves exactly the vacant cells uncovered",
        metrics["uncovered_area"],
        float(vacant_area),
        detail=f"columns={default_columns} rows={default_rows} vacant={len(vacant)}",
    )
    ctx.note("auto default columns", default_columns)
    ctx.note("auto default uncovered area", metrics["uncovered_area"], "wall units^2")

    # Each tablet must have been given exactly the cell the rules predict.
    for index, device in enumerate(ctx.devices):
        cell = expected_cells[index]
        got = assigned.get(device.device_id)
        ctx.eq(
            f"{device.label} default cell",
            {key: got[key] for key in ("x", "y", "w", "h")},
            {key: cell[key] for key in ("x", "y", "w", "h")},
        )
    frames = ctx.wall_frames(revision=revision)
    for index, device in enumerate(ctx.devices):
        cell = expected_cells[index]
        ctx.eq(
            f"{device.label} frame carries its cell",
            frames[device.device_id]["placement"],
            _placement_from(cell),
        )

    # --- explicit columns: an exact partition of the whole wall ----------
    columns = _auto_columns(n, WALL_W, WALL_H)
    response = ctx.harness.post("/wall/auto", json={"columns": columns})
    ctx.eq("explicit columns accepted", response.status_code, 200)
    revision += 1
    ctx.eq("second auto bumped the revision", response.json()["revision"], revision)
    cells = response.json()["placements"]
    metrics = tiling_report(cells, WALL_W, WALL_H)
    ctx.eq(
        "the grid is an exact partition of the wall",
        metrics["exact_partition"],
        True,
        detail=(
            f"columns={columns} sum={metrics['sum_area']} union={metrics['union_area']} "
            f"wall={metrics['wall_area']} overlap={metrics['overlap_area']} "
            f"uncovered={metrics['uncovered_area']}"
        ),
    )
    ctx.eq("no overlap", metrics["overlap_area"], 0.0)
    ctx.eq("nothing uncovered", metrics["uncovered_area"], 0.0)
    ctx.eq("nothing outside the wall", metrics["outside_area"], 0.0)
    ctx.note("auto grid columns", columns)
    ctx.note("auto grid cells", metrics["cell_count"])

    expected_cells, _, _ = _expected_grid(n, columns, WALL_W, WALL_H)
    for index, device in enumerate(ctx.devices):
        cell = expected_cells[index]
        got = cells.get(device.device_id)
        ctx.eq(
            f"{device.label} explicit cell",
            {key: got[key] for key in ("x", "y", "w", "h")},
            {key: cell[key] for key in ("x", "y", "w", "h")},
        )

    ctx.eq(
        "zero columns is 422",
        ctx.harness.post("/wall/auto", json={"columns": 0}).status_code,
        422,
    )
    ctx.eq(
        "negative columns is 422",
        ctx.harness.post("/wall/auto", json={"columns": -2}).status_code,
        422,
    )
    ctx.eq("rejected auto did not move the revision", ctx.wall["revision"], revision)

    # --- seam geometry over the auto grid --------------------------------
    # Hand-derived for the default fleet and this exact grid: a 400x400 cell
    # with a 1024x768 (4:3) viewport scales by 1024/400 = 2.56, so the
    # 768-px-tall viewport covers only 300 of the cell's 400 wall units ->
    # 50 units cropped top and bottom, none left/right. The 16:9 kiosk
    # (1920x1080) scales by 4.8 and crops 87.5 vertically; the portrait
    # tablet (768x1024) scales by 2.56 and crops 50 horizontally.
    cell_w = expected_cells[0]["w"]
    cell_h = expected_cells[0]["h"]
    if ctx.n == 18 and (cell_w, cell_h) == (400, 400):
        anchors: dict[int, tuple[float, float]] = {0: (0.0, 87.5), 1: (50.0, 0.0)}
        for index in range(2, ctx.n):
            anchors[index] = (0.0, 50.0)

        by_id = {device.device_id: device for device in ctx.devices}
        index_of = {device.device_id: index for index, device in enumerate(ctx.devices)}
        pairs = adjacent_pairs({key: value for key, value in cells.items()})
        ctx.expect("the grid has seams to measure", len(pairs) > 0, expected=">0", actual=len(pairs))
        worst = 0.0
        for left_id, right_id, axis, _shared in pairs:
            left = by_id[left_id]
            right = by_id[right_id]
            left_rect = visible_rect(cells[left_id])
            right_rect = visible_rect(cells[right_id])
            gap = seam_gap(left_rect, right_rect, left.viewport, right.viewport, axis)
            ox_a, oy_a = anchors[index_of[left_id]]
            ox_b, oy_b = anchors[index_of[right_id]]
            expected = (ox_a + ox_b) if axis == "x" else (oy_a + oy_b)
            ctx.close(
                f"seam {left.label}/{right.label} along {axis}",
                gap["gap"],
                expected,
                detail=f"cell {cell_w}x{cell_h}, viewports {left.viewport} and {right.viewport}",
            )
            worst = max(worst, abs(gap["gap"] - expected))
        ctx.note("seam pairs measured", len(pairs))
        ctx.note("largest deviation from the hand-derived crops", worst, "wall units")
        ctx.note(
            "worst seam gap",
            max(
                seam_gap(
                    visible_rect(cells[a]),
                    visible_rect(cells[b]),
                    by_id[a].viewport,
                    by_id[b].viewport,
                    axis,
                )["gap"]
                for a, b, axis, _ in pairs
            ),
            "wall units",
        )
    else:
        ctx.note(
            "seam anchors skipped",
            "hand-derived crop anchors apply to the default 18-tablet fleet "
            "in 400x400 cells; this run uses a different grid",
        )


# ---------------------------------------------------------------------------
# 16 — aspect-matched placements: the seams disappear
# ---------------------------------------------------------------------------


@scenario("16_seam_matched", "4:3 cells for 4:3 tablets: every seam gap is zero")
def seam_matched(ctx: Ctx) -> None:
    # Slots 0 and 1 are the 16:9 kiosk and the 3:4 portrait tablet; every
    # other slot is a 1024x768 (4:3) tablet, and 400x300 is exactly 4:3, so
    # the cover crops nothing and neighbouring windows must meet exactly.
    matched = [device for device in ctx.devices if device.slot >= 2]
    for device in ctx.devices:
        if device.slot >= 2:
            cell = _band_cells(ctx.n)[device.slot - 2]
            response = ctx.harness.put(
                f"/devices/{device.device_id}/placement",
                json=_placement_from(cell),
            )
            ctx.eq(f"{device.label} matched placement accepted", response.status_code, 200)
        else:
            response = ctx.harness.delete(f"/devices/{device.device_id}/placement")
            ctx.eq(f"{device.label} released (it is not 4:3)", response.status_code, 200)

    wall = ctx.wall
    placed = wall["placements"]
    ctx.eq("only the 4:3 tablets hold a slot", len(placed), len(matched))

    cells = {device_id: value for device_id, value in placed.items()}
    metrics = tiling_report(cells, WALL_W, WALL_H)
    ctx.eq("matched cells never overlap", metrics["overlap_area"], 0.0)
    ctx.eq("matched cells stay in the wall", metrics["out_of_bounds"], [])
    ctx.eq("matched cells partition their union", metrics["sum_area"], metrics["union_area"])

    by_id = {device.device_id: device for device in matched}
    pairs = adjacent_pairs(cells)
    ctx.expect("there are seams to measure", len(pairs) > 0, expected=">0", actual=len(pairs))

    worst_gap = 0.0
    worst_crop = 0.0
    for left_id, right_id, axis, _shared in pairs:
        left, right = by_id[left_id], by_id[right_id]
        rect_a = visible_rect(cells[left_id])
        rect_b = visible_rect(cells[right_id])
        gap = seam_gap(rect_a, rect_b, left.viewport, right.viewport, axis)
        ctx.close(
            f"matched seam {left.label}/{right.label} along {axis}",
            gap["gap"],
            0.0,
            detail=f"visible {rect_a} vs {rect_b}",
        )
        worst_gap = max(worst_gap, abs(gap["gap"]))
        worst_crop = max(worst_crop, abs(gap["crop_a"]), abs(gap["crop_b"]))
        scale, ox, oy = centred_cover(rect_a["w"], rect_a["h"], *left.viewport)
        ctx.close(f"{left.label} cover scale", scale, left.viewport[0] / rect_a["w"])
        ctx.close(f"{left.label} horizontal crop", ox, 0.0)
        ctx.close(f"{left.label} vertical crop", oy, 0.0)

    ctx.note("matched seam pairs", len(pairs))
    ctx.note("largest matched seam gap", worst_gap, "wall units")
    ctx.note("largest matched cover crop", worst_crop, "wall units")

    # The two released tablets must be told they have no placement.
    revision = wall["revision"]
    for device in ctx.devices:
        if device.slot < 2:
            frame = ctx.wall_frame(device, revision=revision, what="unplaced frame")
            ctx.eq(f"{device.label} has no placement", frame["placement"], None)


# ---------------------------------------------------------------------------
# 17 — mismatched aspects and bezels: the gaps are quantified
# ---------------------------------------------------------------------------


@scenario("17_seam_mismatch", "Aspect mismatch and bezel are measured, not hand-waved")
def seam_mismatch(ctx: Ctx) -> None:
    kiosk, portrait, plain = ctx.devices[0], ctx.devices[1], ctx.devices[2]

    for device in ctx.devices:
        released = ctx.harness.delete(f"/devices/{device.device_id}/placement")
        ctx.eq(f"{device.label} released for the mismatch study", released.status_code, 200)

    # Portrait tablet on the left, a 4:3 tablet beside it, the 16:9 kiosk
    # underneath the portrait tablet — all in 400x300 (4:3) cells.
    portrait_rect = {"x": 0, "y": 0, "w": 400, "h": 300, "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0}}
    plain_rect = {"x": 400, "y": 0, "w": 400, "h": 300, "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0}}
    kiosk_rect = {"x": 0, "y": 300, "w": 400, "h": 300, "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0}}
    for device, rect in ((portrait, portrait_rect), (plain, plain_rect), (kiosk, kiosk_rect)):
        response = ctx.harness.put(f"/devices/{device.device_id}/placement", json=rect)
        ctx.eq(f"{device.label} placed", response.status_code, 200)

    # --- the portrait tablet (768x1024, 0.75) in a 4:3 cell -------------
    # scale = max(768/400, 1024/300) = 1024/300 = 3.4133…
    # ox = (400 - 768/scale)/2 = (400 - 225)/2 = 87.5, oy = (300 - 300)/2 = 0
    scale_p, ox_p, oy_p = centred_cover(400, 300, *portrait.viewport)
    ctx.close("portrait cover scale", scale_p, 1024 / 300, tol=1e-12)
    ctx.close("portrait horizontal crop", ox_p, 87.5)
    ctx.close("portrait vertical crop", oy_p, 0.0)

    # --- the 16:9 kiosk (1920x1080) in the same 4:3 cell ----------------
    # scale = max(1920/400, 1080/300) = 4.8
    # ox = (400 - 400)/2 = 0, oy = (300 - 225)/2 = 37.5
    scale_k, ox_k, oy_k = centred_cover(400, 300, *kiosk.viewport)
    ctx.close("kiosk cover scale", scale_k, 4.8, tol=1e-12)
    ctx.close("kiosk horizontal crop", ox_k, 0.0)
    ctx.close("kiosk vertical crop", oy_k, 37.5)

    # --- a 4:3 tablet in a 4:3 cell crops nothing ------------------------
    # scale = max(1024/400, 768/300) = 2.56 (the aspects are equal), so
    # neither axis is cropped at all.
    scale_n, ox_n, oy_n = centred_cover(400, 300, *plain.viewport)
    ctx.close("matched cover scale", scale_n, 1024 / 400, tol=1e-12)
    ctx.close("matched horizontal crop", ox_n, 0.0)
    ctx.close("matched vertical crop", oy_n, 0.0)

    # --- the horizontal seam: only the portrait tablet hides anything ----
    # gap = separation (0) + ox_portrait (87.5) + ox_plain (0)
    gap_x = seam_gap(
        visible_rect(portrait_rect), visible_rect(plain_rect), portrait.viewport, plain.viewport, "x"
    )
    ctx.close("horizontal seam gap", gap_x["gap"], 87.5)
    ctx.close(
        "portrait crop in device pixels",
        gap_x["px_a"],
        87.5 * (1024 / 300),
        tol=1e-6,
        detail="87.5 wall units x its cover scale",
    )
    ctx.close("plain tablet crop in device pixels", gap_x["px_b"], 0.0)

    # --- the horizontal seam: only the kiosk hides anything --------------
    # gap = oy_portrait (0) + oy_kiosk (37.5)
    gap_y = seam_gap(
        visible_rect(portrait_rect), visible_rect(kiosk_rect), portrait.viewport, kiosk.viewport, "y"
    )
    ctx.close("vertical seam gap", gap_y["gap"], 37.5)
    ctx.close("kiosk crop in device pixels", gap_y["px_b"], 37.5 * 4.8, tol=1e-6)

    # --- bezel: hidden frame is added to the gap, edge for edge ----------
    # The plain tablet keeps its 400x300 footprint but gains a 40-unit left
    # bezel, so its visible rect starts at x=440 (and is 360 wide) while the
    # portrait tablet still ends at x=400. gap = (440 - 400) separation +
    # ox_portrait (87.5) + ox_plain (360x300 visible in a 4:3 viewport ->
    # scale 1024/360 -> no horizontal crop) = 127.5.
    bezeled = {"x": 400, "y": 0, "w": 400, "h": 300, "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 40}}
    response = ctx.harness.put(f"/devices/{plain.device_id}/placement", json=bezeled)
    ctx.eq("a bezelled placement is accepted", response.status_code, 200)
    visible = visible_rect(bezeled)
    ctx.eq("visible rect follows the formula", visible, {"x": 440, "y": 0, "w": 360, "h": 300})
    scale_b, ox_b, oy_b = centred_cover(visible["w"], visible["h"], *plain.viewport)
    ctx.close("bezel changes the cover scale", scale_b, 1024 / 360, tol=1e-12)
    ctx.close("bezel leaves no horizontal crop", ox_b, 0.0)
    # 768 px over a 300-unit-tall visible rect at 1024/360 per unit shows
    # 270 units, so (300 - 270)/2 = 15 units are cropped top and bottom.
    ctx.close("bezel forces a vertical crop", oy_b, 15.0)

    gap_bezel = seam_gap(visible_rect(portrait_rect), visible, portrait.viewport, plain.viewport, "x")
    ctx.close("bezel plus cover crop equals the seam gap", gap_bezel["gap"], 127.5)
    ctx.note("seam gap with a 40-unit bezel", gap_bezel["gap"], "wall units")

    # The wire must carry exactly what we asked for, bezel included.
    stored = ctx.wall["placements"][plain.device_id]
    ctx.eq("bezels survive the round trip", stored["bezel"], bezeled["bezel"])
    ctx.eq("visible rect is positive for every placement", all(
        visible_rect(value)["w"] > 0 and visible_rect(value)["h"] > 0
        for value in ctx.wall["placements"].values()
    ), True)


# ---------------------------------------------------------------------------
# 18 — revision and generation
# ---------------------------------------------------------------------------


@scenario("18_revision_generation", "Revisions advance one at a time inside one generation")
def revision_generation(ctx: Ctx) -> None:
    for device in ctx.devices:
        device.pump.drain()
    v2 = ctx.controller("v2")
    v2.drain()
    v2b = ctx.harness.controllers.get("v2b")
    if v2b is not None:
        v2b.drain()

    start = ctx.wall
    revision = start["revision"]
    generation = start["generation"]

    # Saving and deleting a snapshot is not a wall change.
    ctx.harness.put("/layouts/RevisionProbe")
    ctx.eq("saving a layout does not bump", ctx.wall["revision"], revision)
    ctx.harness.delete("/layouts/RevisionProbe")
    ctx.eq("deleting a layout does not bump", ctx.wall["revision"], revision)
    ctx.eq("generation never changed", ctx.wall["generation"], generation)

    operations: list[tuple[str, Callable[[], Any]]] = [
        ("colour scene", lambda: ctx.harness.put("/scene", json={"content": {"type": "color"}})),
        ("canvas size", lambda: ctx.harness.put("/wall", json={"width": WALL_W, "height": WALL_H})),
        (
            "placement",
            lambda: ctx.harness.put(
                f"/devices/{ctx.devices[0].device_id}/placement",
                json=_placement_from(_band_cells(ctx.n)[0]),
            ),
        ),
        ("auto-arrange", lambda: ctx.harness.post("/wall/auto", json={"columns": _auto_columns(ctx.n, WALL_W, WALL_H)})),
        ("calibration scene", lambda: ctx.harness.put("/scene", json={"content": {"type": "calibration"}})),
        ("release a slot", lambda: ctx.harness.delete(f"/devices/{ctx.devices[-1].device_id}/placement")),
    ]

    for label, operation in operations:
        response = operation()
        ctx.eq(f"{label} accepted", response.status_code, 200)
        revision += 1
        ctx.eq(f"{label} bumps to {revision}", response.json()["revision"], revision)
        ctx.eq(f"{label} keeps the generation", response.json()["generation"], generation)

    # Every tablet received exactly those revisions, in order, under one
    # generation; and so did the controllers.
    for device in ctx.devices:
        for expected in range(start["revision"] + 1, revision + 1):
            frame = ctx.wall_frame(device, revision=expected, what=f"revision {expected}")
            ctx.eq(f"{device.label} generation at r{expected}", frame["generation"], generation)
        ctx.eq(
            f"{device.label} has no frame beyond {revision}",
            device.pump.frames_within(0.15),
            [],
            detail="revisions must arrive one at a time",
        )

    for controller in (v2, v2b):
        if controller is None:
            continue
        for expected in range(start["revision"] + 1, revision + 1):
            frame = controller.next_frame(
                predicate=lambda f, expected=expected: f.get("type") == "wall_updated"
                and f["wall"]["revision"] == expected,
                what=f"wall_updated {expected}",
            )
            ctx.eq(f"{controller.label} saw r{expected}", frame["wall"]["generation"], generation)

    ctx.eq("GET /wall agrees with the last frame", ctx.wall["revision"], revision)
    ctx.eq("GET /wall generation is unchanged", ctx.wall["generation"], generation)
    ctx.note("revisions advanced in this scenario", revision - start["revision"])


# ---------------------------------------------------------------------------
# 19 — reconnect
# ---------------------------------------------------------------------------


@scenario("19_reconnect", "A tablet that drops and returns is replayed, not re-created")
def reconnect(ctx: Ctx) -> None:
    device = ctx.devices[5 % ctx.n]
    controller = ctx.controller("v2")
    controller.drain()
    device.pump.drain()

    before = ctx.wall
    seen_before = ctx.harness.get(f"/device/{device.device_id}").json()["last_seen"]
    roster_before = len(ctx.harness.roster())

    closed = device.disconnect()
    ctx.expect(
        "our own close is observed by the reader",
        closed.get(SOCKET_CLOSED) is True,
        expected="socket-closed marker",
        actual=closed,
    )
    ctx.expect_event(controller, "device_offline", device_id=device.device_id, what="device_offline")

    roster = ctx.harness.roster()
    ctx.eq("the roster keeps the device", len(roster), roster_before)
    ctx.eq("the device is offline", roster[device.device_id]["online"], False)
    ctx.eq(
        "a disconnect changes no wall state",
        ctx.wall["placements"],
        before["placements"],
    )

    welcome = device.connect(ctx.harness)
    ctx.eq("welcome on reconnect", welcome["type"], "welcome")
    ctx.eq("still protocol 2", welcome.get("protocol"), 2)

    frame = ctx.wall_frame(device, revision=ctx.wall["revision"], what="replayed wall")
    ctx.eq("replay carries the current revision", frame["revision"], ctx.wall["revision"])
    ctx.eq("replay carries the current generation", frame["generation"], ctx.wall["generation"])
    ctx.eq(
        "replay carries the current placement",
        frame["placement"],
        None if device.device_id not in ctx.wall["placements"] else {
            key: value for key, value in ctx.wall["placements"][device.device_id].items()
            if key != "device_id"
        },
    )

    ctx.expect_event(controller, "device_online", device_id=device.device_id, what="device_online")
    ctx.eq(
        "a reconnect never announces an offline first",
        [
            frame.get("type")
            for frame in controller.frames_within(0.2)
            if frame.get("device_id") == device.device_id
        ],
        [],
    )
    roster = ctx.harness.roster()
    ctx.eq("no duplicate roster entry", len(roster), roster_before)
    ctx.eq("online again", roster[device.device_id]["online"], True)
    ctx.expect(
        "last_seen moved forward",
        roster[device.device_id]["last_seen"] > seen_before,
        expected=f"> {seen_before}",
        actual=roster[device.device_id]["last_seen"],
    )


# ---------------------------------------------------------------------------
# 20 — socket replacement
# ---------------------------------------------------------------------------


@scenario("20_socket_replacement", "A second socket takes the slot over; the first closes with 4409")
def socket_replacement(ctx: Ctx) -> None:
    device = ctx.devices[6 % ctx.n]
    controller = ctx.controller("v2")
    controller.drain()
    device.pump.drain()

    closed = device.replace(ctx.harness)
    ctx.eq("the replaced socket closed with 4409", closed.get("code"), 4409)
    ctx.expect(
        "the replacement is a documented close",
        closed.get(SOCKET_CLOSED) is True,
        expected="socket-closed marker",
        actual=closed,
    )

    welcome = device.pump.next_frame(predicate=lambda f: f.get("type") == "welcome", what="welcome")
    ctx.eq("the new socket is welcomed", welcome["device_id"], device.device_id)
    frame = ctx.wall_frame(device, what="wall replay on the replacement")
    ctx.eq("the new socket gets the wall", frame["type"], "wall")
    ctx.eq("the new socket is at the current revision", frame["revision"], ctx.wall["revision"])

    events = [
        item.get("type")
        for item in controller.frames_within(0.3)
        if frame_device_id(item) == device.device_id
    ]
    ctx.eq(
        "a replacement announces device_online only — never device_offline",
        events.count("device_online") >= 1,
        True,
        detail=f"events seen: {events}",
    )
    ctx.eq("no device_offline for a replaced socket", events.count("device_offline"), 0, detail=f"events seen: {events}")

    roster = ctx.harness.roster()
    ctx.eq("still online", roster[device.device_id]["online"], True)
    ctx.eq("roster unchanged", len(roster), ctx.n)


# ---------------------------------------------------------------------------
# 21 — restart: a new generation over the same database
# ---------------------------------------------------------------------------


@scenario("21_restart", "Restart mints a new generation and keeps the persisted wall")
def restart(ctx: Ctx) -> None:
    before = ctx.wall
    roster_before = len(ctx.harness.roster())

    ctx.harness.restart()
    ctx.expect(
        "the harness came back",
        ctx.harness.client is not None,
        expected="running client",
        actual=ctx.harness.client,
    )

    after = ctx.wall
    ctx.expect(
        "generation is regenerated on every start",
        after["generation"] != before["generation"],
        expected=f"different from {before['generation']}",
        actual=after["generation"],
    )
    ctx.eq("revision continues from the database", after["revision"], before["revision"])
    ctx.eq("placements survive the restart", after["placements"], before["placements"])
    ctx.eq("scene survives the restart", after["scene"], before["scene"])
    ctx.eq("the roster is memory-only", len(ctx.harness.roster()), 0)
    ctx.expect(
        "no socket outlived the server",
        all(not device.connected for device in ctx.devices),
        expected="every device disconnected",
        actual=[device.label for device in ctx.devices if device.connected],
    )

    # Without a roster entry the handshake must fail with a documented code.
    code = ctx.raw_close_code(
        f"/ws/device?device_id={ctx.devices[0].device_id}&protocol=2"
    )
    ctx.eq("a forgotten device is closed with 4404", code, 4404)

    ctx.harness.register_all()
    ctx.eq("the fleet re-registers", len(ctx.harness.roster()), roster_before)
    ctx.eq(
        "the roster really is rebuilt from nothing",
        {record["color"] for record in ctx.harness.roster().values()},
        {None},
        detail="colour and presence live in memory only",
    )

    welcomes = ctx.harness.connect_all()
    ctx.eq("every tablet reconnects", len(welcomes), ctx.n)
    frames = ctx.wall_frames(revision=after["revision"], what="first frame after restart")
    for device in ctx.devices:
        frame = frames[device.device_id]
        ctx.eq(f"{device.label} new generation", frame["generation"], after["generation"])
        ctx.eq(f"{device.label} persisted revision", frame["revision"], after["revision"])

    # A controller opened after the restart sees the rebuilt roster and the
    # new generation, proving the snapshot reads live state.
    fresh = ctx.harness.open_controller("v2", protocol=2)
    snapshot = fresh.next_frame(predicate=lambda f: f.get("type") == "snapshot", what="snapshot")
    ctx.eq("post-restart snapshot lists the fleet", len(snapshot["devices"]), ctx.n)
    ctx.eq("post-restart snapshot generation", snapshot["wall"]["generation"], after["generation"])
    ctx.eq("post-restart snapshot revision", snapshot["wall"]["revision"], after["revision"])


# ---------------------------------------------------------------------------
# 22 — heartbeats and the sweeper
# ---------------------------------------------------------------------------


@scenario("22_sweeper", "Heartbeats keep a socket alive; a silent one is swept with 4408")
def sweeper(ctx: Ctx) -> None:
    import main  # imported here: the harness patches the running app's module

    victim = ctx.devices[3 % ctx.n]
    others = [device for device in ctx.devices if device is not victim]
    controller = ctx.controller("v2")
    controller.drain()

    # --- a heartbeat really moves last_seen ------------------------------
    before = ctx.harness.get(f"/device/{victim.device_id}").json()["last_seen"]
    session = victim.pump.session
    victim.send_heartbeat()
    deadline = time.monotonic() + 2.0
    after = before
    while time.monotonic() < deadline and after <= before:
        time.sleep(0.05)
        after = ctx.harness.get(f"/device/{victim.device_id}").json()["last_seen"]
    ctx.expect(
        "a heartbeat advances last_seen",
        after > before,
        expected=f"> {before}",
        actual=after,
        detail=(
            f"connected={victim.connected} session_open={session is not None} "
            f"close_code={victim.pump.closed_code} error={victim.pump.closed_error!r}"
        ),
    )

    # --- go silent and let the sweeper notice ----------------------------
    # The timing constants are read per pass by the sweeper, so patching the
    # running module is enough. The heartbeat interval is shortened at the
    # same time so every *other* tablet keeps checking in well inside the
    # temporary timeout — only the victim is meant to look dead.
    original_timeout = main.hub.HEARTBEAT_TIMEOUT_S
    original_interval = main.hub.SWEEP_INTERVAL_S
    original_heartbeat = ctx.harness.heartbeat_interval
    main.hub.HEARTBEAT_TIMEOUT_S = 1.0
    main.hub.SWEEP_INTERVAL_S = 0.05
    ctx.harness.heartbeat_interval = 0.05
    victim.heartbeat_enabled = False
    swept_at = time.monotonic()
    try:
        closed = victim.pump.wait_closed(timeout=8.0)
        sweep_latency = time.monotonic() - swept_at
    finally:
        main.hub.HEARTBEAT_TIMEOUT_S = original_timeout
        main.hub.SWEEP_INTERVAL_S = original_interval
        ctx.harness.heartbeat_interval = original_heartbeat
        victim.heartbeat_enabled = True
        victim.pump.drain()

    ctx.eq("the silent socket was closed with 4408", closed.get("code"), 4408)
    ctx.expect_event(controller, "device_offline", device_id=victim.device_id, what="device_offline from the sweeper")
    roster = ctx.harness.roster()
    ctx.eq("the swept tablet reads offline", roster[victim.device_id]["online"], False)
    ctx.eq(
        "the swept tablet is still in the roster",
        victim.device_id in roster,
        True,
        detail="the sweeper closes sockets, it does not forget devices",
    )
    survivors_online = {roster[device.device_id]["online"] for device in others}
    ctx.eq(
        "no other tablet was swept by the temporary timeout",
        survivors_online,
        {True},
        detail=f"seen: {survivors_online}",
    )
    ctx.note("sweep latency", round(sweep_latency, 3), "s")

    # --- and it can come straight back -----------------------------------
    controller.drain()
    welcome = victim.connect(ctx.harness)
    ctx.eq("the swept tablet reconnects", welcome["type"], "welcome")
    ctx.expect_event(controller, "device_online", device_id=victim.device_id, what="device_online after the sweep")
    ctx.eq(
        "it is online again",
        ctx.harness.roster()[victim.device_id]["online"],
        True,
    )
    ctx.eq(
        "the sweeper's temporary timings are gone",
        (main.hub.HEARTBEAT_TIMEOUT_S, main.hub.SWEEP_INTERVAL_S),
        (original_timeout, original_interval),
    )
