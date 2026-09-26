"""In-process harness: isolated environment, the real app, virtual tablets.

The simulator drives the **real** FastAPI application through
``fastapi.testclient.TestClient`` — the same app object the test suite uses,
run on a real event loop in a background thread. Two properties make a
15–20 tablet scenario possible on top of that:

* entering ``TestClient`` as a context manager gives the client **one shared
  blocking portal**, so HTTP requests, every device socket, and every
  controller socket all run on the *same* event loop (a socket and a request
  must share a loop or a broadcast could never reach them);
* every socket's outbound stream is unbounded, so a device that is slow to
  read never applies back-pressure to a broadcast — the risk is the opposite
  one (a reader that waits forever), which is why **each socket is drained by
  its own dedicated thread** and every wait in the harness is bounded.

Rules the harness relies on (and that scenarios must keep):

1. the main thread owns the TestClient: it performs all HTTP calls and opens
   or closes every socket — reader threads only ever *receive*;
2. a reader never outlives its socket: closing a session unblocks its reader
   with an exception, which the reader turns into a ``socket-closed`` marker
   frame, and only then may a replacement session be attached;
3. nothing here writes outside ``work_dir``: the database and the asset
   directory are pointed at a temporary directory before the app is imported.
"""

from __future__ import annotations

import os
import queue
import struct
import threading
import time
import zlib
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

# Everything the app is imported for lives at the repository root: ``main``
# mounts ``frontend/client`` and ``frontend/controller`` by relative path, so
# the process has to be *in* the repository root when it is imported.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Marker frame a reader pushes when its socket ends (cleanly or not). Never a
# protocol frame, so scenarios can tell "the server closed this" from "the
# server sent me this".
SOCKET_CLOSED = "__sim-socket-closed__"

DEFAULT_WAIT_S = 5.0


class HarnessError(RuntimeError):
    """A harness invariant failed: timeout, unexpected close, bad state."""


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------


def prepare_environment(work_dir: Path) -> dict[str, str]:
    """Point the app at a temporary database and asset directory.

    Called before ``main`` is imported (the paths are read at call time, but
    setting them first means no code path can ever observe the defaults),
    and it also clears the optional origin fences so a developer's ambient
    ``TABLET_WALL_*_ORIGIN`` cannot change what the simulator exercises.
    The directory defaults (``tablet-wall.db``, ``./assets``) are what the
    repository's own development data uses, so they must never be reachable
    from a run.
    """
    work = Path(work_dir)
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    database = work / "tablet-wall.db"
    env = {
        "TABLET_WALL_DB": str(database),
        "TABLET_WALL_ASSET_DIR": str(assets),
    }
    for key, value in env.items():
        os.environ[key] = value
    os.environ.pop("TABLET_WALL_OPERATOR_ORIGIN", None)
    os.environ.pop("TABLET_WALL_TABLET_ORIGIN", None)
    return env


def deterministic_device_id(seed: str) -> str:
    """A stable UUID4 for one fleet slot, so runs are reproducible.

    Built from a hash of ``seed`` with the version nibble forced to ``4`` and
    the variant bits forced to the RFC 4122 form, because both the request
    model and ``_parse_device_id`` reject anything else.
    """
    import hashlib

    digest = hashlib.sha256(f"tablet-wall-simulator:{seed}".encode()).hexdigest()
    variant = f"{(int(digest[16], 16) & 0x3) | 0x8:x}"
    return f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-{variant}{digest[17:20]}-{digest[20:32]}"


def write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Write a small, valid, dependency-free PNG and return its bytes.

    The asset pipeline validates with Pillow and re-hashes the bytes, so the
    file has to be a real PNG: signature, IHDR, a zlib-compressed IDAT of
    scanlines (filter byte 0 per row), IEND, CRCs on every chunk.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    scanline = b"\x00" + bytes(rgb) * width
    raw = scanline * height
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return data


# ---------------------------------------------------------------------------
# socket readers
# ---------------------------------------------------------------------------


class SocketPump:
    """Drains one test-client socket on its own thread into a queue.

    The reader blocks in ``receive_json()`` until the server says something,
    then parks the frame on an unbounded queue for the main thread to
    consume with a deadline. When the socket ends — clean close, replaced
    socket (4409), heartbeat sweep (4408), or shutdown — the reader records
    the close code, publishes a ``socket-closed`` marker frame, drops the
    handle and idles until a new session is attached or it is stopped.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.closed_code: int | None = None
        self.closed_error: str = ""
        self._session: Any = None
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"pump-{label}", daemon=True
        )
        self._thread.start()

    # -- session handling (main thread only) -------------------------------
    @property
    def session(self) -> Any:
        with self._lock:
            return self._session

    def attach(self, session: Any) -> None:
        """Hand a freshly opened session to the reader."""
        with self._lock:
            self._session = session
        self._closed.clear()

    def detach(self) -> Any:
        with self._lock:
            session, self._session = self._session, None
        return session

    def wait_closed(self, timeout: float = DEFAULT_WAIT_S) -> dict[str, Any]:
        """Block until the reader has seen its socket end; raise on timeout.

        The returned marker frame carries the close code when the server
        closed the socket (4409, 4408, 4404, …) and ``None`` when we closed
        it ourselves.
        """
        if not self._closed.wait(timeout):
            raise HarnessError(
                f"{self.label}: socket did not end within {timeout:.1f}s"
            )
        return {
            SOCKET_CLOSED: True,
            "code": self.closed_code,
            "error": self.closed_error,
        }

    def stop(self, timeout: float = DEFAULT_WAIT_S) -> None:
        """Signal the reader to end and join it (bounded; never raises)."""
        self._stop.set()
        self._thread.join(timeout=timeout)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    # -- frame consumption (main thread only) ------------------------------
    def drain(self) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        while True:
            try:
                frames.append(self.queue.get_nowait())
            except queue.Empty:
                return frames

    def next_frame(
        self,
        timeout: float = DEFAULT_WAIT_S,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        what: str = "frame",
    ) -> dict[str, Any]:
        """Next frame satisfying ``predicate``, or raise a HarnessError.

        Non-matching frames are consumed and discarded: every wait is about
        one specific thing, and the queue is unbounded, so nothing that later
        scenarios need is lost (they drain at their own start anyway).
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessError(
                    f"{self.label}: no {what} within {timeout:.1f}s"
                )
            try:
                frame = self.queue.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if predicate is None or predicate(frame):
                return frame

    def frames_within(self, seconds: float = 0.3) -> list[dict[str, Any]]:
        """Whatever arrives in the next ``seconds`` (used for "must not")."""
        frames: list[dict[str, Any]] = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                frames.append(self.queue.get(timeout=0.05))
            except queue.Empty:
                continue
        return frames

    # -- the reader --------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                session = self._session
            if session is None:
                self._stop.wait(0.01)
                continue
            try:
                frame = session.receive_json()
            except Exception as exc:  # noqa: BLE001 - every exit shape counts
                code = getattr(exc, "code", None)
                self.closed_code = code if isinstance(code, int) else None
                self.closed_error = f"{type(exc).__name__}: {exc}"
                with self._lock:
                    if self._session is session:
                        self._session = None
                self.queue.put(
                    {
                        SOCKET_CLOSED: True,
                        "code": self.closed_code,
                        "error": self.closed_error,
                    }
                )
                self._closed.set()
                continue
            self.queue.put(frame)


# ---------------------------------------------------------------------------
# devices
# ---------------------------------------------------------------------------


@dataclass
class DeviceSpec:
    """One fleet member as it will be *registered* (PROTOCOL.md)."""

    width: int
    height: int
    device_type: str
    caps: tuple[str, ...]
    slot: int

    @property
    def device_id(self) -> str:
        return deterministic_device_id(f"device-{self.slot}")


class VirtualDevice:
    """A virtual tablet: its registration record plus one reader thread."""

    def __init__(self, spec: DeviceSpec) -> None:
        self.spec = spec
        self.device_id = spec.device_id
        self.width = spec.width
        self.height = spec.height
        self.device_type = spec.device_type
        self.caps = list(spec.caps)
        self.slot = spec.slot
        self.label = f"device{spec.slot:02d}"
        # Heartbeats are what keep a socket alive past HEARTBEAT_TIMEOUT_S
        # (15 s); a scenario that wants the sweeper to notice a *silent*
        # tablet flips this off for just that tablet.
        self.heartbeat_enabled = True
        self.pump = SocketPump(self.label)
        self._stack: ExitStack | None = None

    # -- identity ----------------------------------------------------------
    @property
    def viewport(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def aspect(self) -> float:
        return self.width / self.height

    def registration(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "width": self.width,
            "height": self.height,
            "device_type": self.device_type,
        }

    def ws_url(self, protocol: int = 2) -> str:
        url = f"/ws/device?device_id={self.device_id}&protocol={protocol}"
        if self.caps:
            url += "&caps=" + ",".join(self.caps)
        return url

    # -- sessions (main thread only) ---------------------------------------
    @property
    def connected(self) -> bool:
        return self.pump.session is not None

    def connect(self, harness: "Harness", timeout: float = DEFAULT_WAIT_S) -> dict[str, Any]:
        """Open this device's socket, attach it, return its ``welcome`` frame.

        The handshake returns as soon as the server accepts; waiting for the
        welcome here means no caller ever races the first frame.
        """
        if self.connected:
            raise HarnessError(f"{self.label}: already connected")
        if self._stack is not None:
            # A session that ended without us closing it — swept by the
            # heartbeat timeout, or replaced — still owns portal callbacks;
            # unwind it before opening another or the old task lingers.
            try:
                self._stack.close()
            except Exception:  # noqa: BLE001 - the socket is already gone
                pass
            self._stack = None
        stack = ExitStack()
        try:
            session = stack.enter_context(
                harness.client.websocket_connect(self.ws_url())
            )
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        self.pump.attach(session)
        return self.pump.next_frame(
            timeout, predicate=lambda f: f.get("type") == "welcome", what="welcome"
        )

    def disconnect(self, timeout: float = DEFAULT_WAIT_S) -> dict[str, Any]:
        """Close our side of the socket and wait for the reader to notice."""
        stack = self._stack
        if stack is None:
            raise HarnessError(f"{self.label}: not connected")
        self._stack = None
        stack.close()
        return self.pump.wait_closed(timeout)

    def replace(self, harness: "Harness", timeout: float = DEFAULT_WAIT_S) -> dict[str, Any]:
        """Open a second socket while the first is still open.

        The server must close the old one with 4409 (PROTOCOL.md "One socket
        per device"); we wait for exactly that before handing the reader its
        new session, so the close code cannot be observed by anything other
        than this device's own reader.
        """
        old_stack = self._stack
        if old_stack is None:
            raise HarnessError(f"{self.label}: not connected")
        stack = ExitStack()
        try:
            session = stack.enter_context(
                harness.client.websocket_connect(self.ws_url())
            )
        except BaseException:
            stack.close()
            raise
        try:
            closed = self.pump.wait_closed(timeout)
        except BaseException:
            # The old socket never yielded: do not leave the new session open.
            stack.close()
            raise
        old_stack.close()
        self._stack = stack
        self.pump.attach(session)
        return closed

    def send_heartbeat(self) -> None:
        session = self.pump.session
        if session is None:
            return
        try:
            session.send_json({"type": "heartbeat"})
        except Exception:  # noqa: BLE001 - racing our own close is normal
            pass


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


class Harness:
    """Owns the app process-in-miniature: client, fleet, controllers, timers.

    Lifecycle: :meth:`start` enters ``TestClient`` (which runs the app's
    lifespan: load the wall from the temporary database, mint a generation,
    start the sweeper), scenarios drive it, :meth:`restart` cycles it to
    simulate a server restart over the same database, :meth:`close` tears
    everything down.
    """

    def __init__(self, work_dir: Path, specs: Iterable[DeviceSpec]) -> None:
        self.work_dir = Path(work_dir)
        self.env = prepare_environment(self.work_dir)
        self.client: Any = None
        self._client_stack = ExitStack()
        self.devices = [VirtualDevice(spec) for spec in specs]
        self.controllers: dict[str, SocketPump] = {}
        self._controller_stacks: dict[str, ExitStack] = {}
        # Failures while closing (a wedged disconnect, a lifespan exit that
        # raises) are collected instead of raised, so a partial teardown can
        # never skip the remaining pumps — run.py reports them as a failed
        # teardown check.
        self._close_problems: list[str] = []
        self._heartbeat_interval = 2.5
        self._heartbeat_stop = threading.Event()
        self._heartbeat = threading.Thread(
            target=self._heartbeat_loop, name="heartbeat", daemon=True
        )
        self._heartbeat.start()

    # -- app lifecycle -----------------------------------------------------
    @property
    def close_error(self) -> str:
        """Every problem recorded while closing, joined; empty when clean."""
        return "; ".join(self._close_problems)

    def note_close_problem(self, message: str) -> None:
        """Record a teardown failure for run.py's teardown check."""
        self._close_problems.append(message)

    def start(self) -> None:
        if self.client is not None:
            raise HarnessError("harness already started")
        # Imported here: this runs *after* the temporary paths are in the
        # environment and after run.py has moved the process to the repo root.
        from fastapi.testclient import TestClient

        import main

        self.client = self._client_stack.enter_context(TestClient(main.app))

    def stop_client(self) -> None:
        """Close every socket, then leave the app's lifespan.

        Individual closing failures are recorded via
        :meth:`note_close_problem` instead of raised: a teardown that gives
        up halfway would strand the sockets it never reached. Whatever is
        left behind shows up either as a close problem or as a straggler in
        :meth:`close`.
        """
        problems: list[str] = []
        if self.client is None:
            return
        for device in self.devices:
            if device._stack is not None:  # noqa: SLF001 - same module
                try:
                    device.disconnect()
                except HarnessError:
                    # Expected on a wedged socket: the reader never saw a
                    # clean end within the deadline.
                    device._stack = None  # noqa: SLF001
                    device.pump.detach()
                except Exception as exc:  # noqa: BLE001 - escalate anything else
                    problems.append(
                        f"{device.label} disconnect: {type(exc).__name__}: {exc}"
                    )
                    device._stack = None  # noqa: SLF001
                    device.pump.detach()
        for label, stack in list(self._controller_stacks.items()):
            try:
                stack.close()
            except Exception as exc:  # noqa: BLE001 - keep closing the rest
                problems.append(
                    f"controller {label} close: {type(exc).__name__}: {exc}"
                )
            self._controller_stacks.pop(label, None)
            pump = self.controllers.pop(label, None)
            if pump is not None:
                pump.stop()
        try:
            self._client_stack.close()
        except Exception as exc:  # noqa: BLE001 - keep closing the rest
            problems.append(f"client stack close: {type(exc).__name__}: {exc}")
        self.client = None
        for problem in problems:
            self.note_close_problem(problem)

    def restart(self) -> None:
        """Simulate a server restart over the same database.

        ``TestClient`` restarts the *lifespan*, not the process: the wall is
        reloaded from SQLite and a fresh generation is minted by the app
        itself, but the in-memory roster and socket registries would survive
        the restart — which a real process restart would not, because that
        memory dies with the process. Clearing them here is the emulation of
        process death (and mirrors what the test suite's fixtures do when
        they reset module state); the wall is deliberately left alone so the
        app's own persistence rules are what the scenarios observe.
        """
        self.stop_client()
        self._forget_runtime_state()
        self.start()

    def _forget_runtime_state(self) -> None:
        try:
            import main
        except ImportError:  # the app never booted: nothing to forget
            return
        main.devices.clear()
        main.device_sockets.clear()
        main.controller_sockets.clear()
        main.controller_protocols.clear()

    def close(self) -> list[str]:
        """Full teardown; returns the labels of threads that would not end.

        Readers are joined *first* and only then inspected: a reader is
        alive by design until it is stopped, so anything still alive after
        ``stop()`` is a thread that failed to unwind and belongs in the
        report as a risk rather than in the log as noise.

        Device readers, controller readers, and the heartbeat thread are
        *all* inspected — a close that reports only devices would call a
        leaked controller reader "clean". Close itself does not raise:
        every step is attempted and anything that goes wrong is recorded
        on :attr:`close_error`, so a broken teardown can never skip the
        fingerprint, temporary-directory, or report steps that follow it.
        """
        self._heartbeat_stop.set()
        try:
            self.stop_client()
        except Exception as exc:  # noqa: BLE001 - close must finish its sweep
            self.note_close_problem(f"stop_client: {type(exc).__name__}: {exc}")
        self._heartbeat.join(timeout=DEFAULT_WAIT_S)
        stragglers: list[str] = []
        if self._heartbeat.is_alive():
            stragglers.append("heartbeat")
        for device in self.devices:
            try:
                device.pump.stop()
            except Exception as exc:  # noqa: BLE001 - keep closing the rest
                self.note_close_problem(
                    f"{device.label} pump stop: {type(exc).__name__}: {exc}"
                )
            if device.pump.alive:
                stragglers.append(device.label)
        for label, pump in list(self.controllers.items()):
            try:
                pump.stop()
            except Exception as exc:  # noqa: BLE001 - keep closing the rest
                self.note_close_problem(
                    f"controller {label} pump stop: {type(exc).__name__}: {exc}"
                )
            if pump.alive:
                stragglers.append(pump.label)
        return sorted(stragglers)

    # -- heartbeat ---------------------------------------------------------
    @property
    def heartbeat_interval(self) -> float:
        return self._heartbeat_interval

    @heartbeat_interval.setter
    def heartbeat_interval(self, value: float) -> None:
        self._heartbeat_interval = value

    def _heartbeat_loop(self) -> None:
        """Send every connected tablet a heartbeat on a short, live interval.

        The wait is a fine-grained poll rather than one sleep per interval so
        a scenario that shortens the interval (the sweeper scenario, below)
        takes effect immediately instead of after the *previous* interval has
        elapsed — otherwise every tablet would go quiet exactly when the
        shortened timeout starts counting.
        """
        last_sent = 0.0
        while not self._heartbeat_stop.is_set():
            now = time.monotonic()
            if now - last_sent >= self._heartbeat_interval:
                for device in self.devices:
                    if device.heartbeat_enabled:
                        device.send_heartbeat()
                last_sent = now
            self._heartbeat_stop.wait(0.02)

    # -- HTTP (main thread only) ------------------------------------------
    def get(self, path: str, **kwargs: Any) -> Any:
        return self.client.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.client.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.client.put(path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.client.delete(path, **kwargs)

    def wall(self) -> dict[str, Any]:
        response = self.get("/wall")
        if response.status_code != 200:
            raise HarnessError(f"GET /wall -> {response.status_code}")
        return response.json()

    def register(self, device: VirtualDevice) -> Any:
        return self.post("/devices/register", json=device.registration())

    def register_all(self) -> None:
        for device in self.devices:
            response = self.register(device)
            if response.status_code != 200:
                raise HarnessError(
                    f"{device.label}: register -> {response.status_code}"
                )

    def roster(self) -> dict[str, Any]:
        response = self.get("/devices")
        if response.status_code != 200:
            raise HarnessError(f"GET /devices -> {response.status_code}")
        return response.json()

    def connect_all(self, timeout: float = DEFAULT_WAIT_S) -> list[tuple["VirtualDevice", dict[str, Any]]]:
        """Connect every device that is not connected; return their welcomes."""
        welcomes: list[tuple[VirtualDevice, dict[str, Any]]] = []
        for device in self.devices:
            if not device.connected:
                welcomes.append((device, device.connect(self, timeout=timeout)))
        return welcomes

    def drain_all(self) -> None:
        """Discard queued frames everywhere (scenarios start from silence)."""
        for device in self.devices:
            device.pump.drain()
        for pump in self.controllers.values():
            pump.drain()

    # -- controllers -------------------------------------------------------
    def open_controller(self, label: str, protocol: int | None = 2) -> SocketPump:
        if label in self.controllers:
            raise HarnessError(f"controller {label!r} already open")
        url = "/ws/controller" if protocol is None else f"/ws/controller?protocol={protocol}"
        stack = ExitStack()
        pump = SocketPump(f"controller-{label}")
        try:
            session = stack.enter_context(self.client.websocket_connect(url))
        except BaseException:
            stack.close()
            pump.stop()
            raise
        pump.attach(session)
        self._controller_stacks[label] = stack
        self.controllers[label] = pump
        return pump

    def close_controller(self, label: str) -> None:
        stack = self._controller_stacks.pop(label, None)
        if stack is not None:
            stack.close()
        pump = self.controllers.pop(label, None)
        if pump is not None:
            pump.stop()

    # -- ephemeral sockets (never attached to a reader) --------------------
    def raw_connect(self, url: str) -> Any:
        """Open a socket the main thread reads itself (negative tests)."""
        return self.client.websocket_connect(url)


# ---------------------------------------------------------------------------
# fleet
# ---------------------------------------------------------------------------

# Composition of the default fleet, in slot order. The first six slots
# deliberately cover every capability shape a wall can meet — a legacy
# version-2 client with no caps, one that only knows calibration, one that
# only knows images, and two full ones (one of them a 16:9 kiosk, one a
# 3:4 portrait tablet) — so any fleet size still contains one of each and
# the downgrade matrix is always testable. The rest are plain 4:3 tablets
# with both caps.
FLEET_TEMPLATE: tuple[tuple[int, int, str, tuple[str, ...]], ...] = (
    (1920, 1080, "kiosk", ("calibration", "image")),
    (768, 1024, "android", ("calibration", "image")),
    (1024, 768, "ipad", ()),
    (1024, 768, "ipad", ("calibration",)),
    (1024, 768, "ipad", ("image",)),
    (1024, 768, "ipad", ("calibration", "image")),
    *((1024, 768, "ipad", ("calibration", "image")) for _ in range(14)),
)

# The default fleet size: inside the required 15–20 device band.
DEFAULT_DEVICE_COUNT = 18
MIN_DEVICES = 15
MAX_DEVICES = len(FLEET_TEMPLATE)  # 20


def build_specs(count: int) -> list[DeviceSpec]:
    """The first ``count`` fleet slots, each with a stable UUID4."""
    if count < 1 or count > len(FLEET_TEMPLATE):
        raise HarnessError(
            f"fleet size must be 1..{len(FLEET_TEMPLATE)}, got {count}"
        )
    return [
        DeviceSpec(width=w, height=h, device_type=kind, caps=caps, slot=slot)
        for slot, (w, h, kind, caps) in enumerate(FLEET_TEMPLATE[:count])
    ]


def fleet_rows(specs: Iterable[DeviceSpec]) -> list[dict[str, Any]]:
    """Serialisable fleet description for the report."""
    return [
        {
            "device_id": spec.device_id,
            "slot": spec.slot,
            "viewport": [spec.width, spec.height],
            "device_type": spec.device_type,
            "caps": list(spec.caps),
        }
        for spec in specs
    ]
