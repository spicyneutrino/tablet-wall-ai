"""One bounded ordered writer per WebSocket (R2).

Every application frame goes through this queue. A slow reader therefore
delays only its own connection: broadcasts enqueue and return, and the
writer task is the only place a send is awaited. Welcome and the initial
snapshot are enqueued before the socket is published to broadcasts, so a
later state frame cannot overtake them.

Only complete state snapshots coalesce (``COALESCED_TYPES``). A snapshot that
is still queued when a newer one of the same type arrives is dropped and the
newer one is appended, so a slow reader sees the latest state without a
backlog. The queue stays in causal order: prepare, commit, cancel, welcome
and every other frame are never dropped or reordered, and a snapshot never
overtakes a frame that was enqueued before it.
"""

import asyncio
import contextlib
import json
from collections import deque
from typing import Any

from fastapi import WebSocket

from tabletwall.protocol import (
    WS_CLOSE_NORMAL,
    WS_CLOSE_WRITER_OVERFLOW,
)

MAX_QUEUED_FRAMES = 64
MAX_QUEUED_BYTES = 1024 * 1024
SEND_TIMEOUT_S = 5.0
COALESCED_TYPES = frozenset({"playback_status", "wall_updated", "config_updated"})

# ``{websocket: Writer}``. The endpoint owns attach/detach; hub and main only
# look a writer up, so an old endpoint cannot send through a replacement's
# writer.
_writers: dict[Any, "Writer"] = {}


class Writer:
    """A FIFO sender with a frame/byte budget and a send deadline."""

    def __init__(
        self,
        websocket: WebSocket,
        *,
        frame_budget: int = MAX_QUEUED_FRAMES,
        byte_budget: int = MAX_QUEUED_BYTES,
        timeout: float = SEND_TIMEOUT_S,
    ) -> None:
        self.websocket = websocket
        self.frame_budget = frame_budget
        self.byte_budget = byte_budget
        self.timeout = timeout
        self.queue: deque[tuple[dict[str, Any], Any, int]] = deque()
        self._wake = asyncio.Event()
        self.queued_bytes = 0
        self.task: asyncio.Task[None] | None = None
        self.closed = False

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def send(self, frame: dict[str, Any], stamp: Any = None) -> None:
        if self.closed:
            raise ConnectionError("writer is closed")
        size = len(json.dumps(frame, separators=(",", ":")))
        if stamp is None and frame.get("type") in COALESCED_TYPES:
            self._drop_stale_snapshot(frame["type"])
        if len(self.queue) >= self.frame_budget:
            await self._overflow("frame queue is full")
        if self.queued_bytes + size > self.byte_budget:
            await self._overflow("byte budget is exhausted")
        self.queued_bytes += size
        self.queue.append((frame, stamp, size))
        self._wake.set()

    def _drop_stale_snapshot(self, frame_type: str) -> None:
        for entry in self.queue:
            if entry[1] is None and entry[0].get("type") == frame_type:
                self.queue.remove(entry)
                self.queued_bytes = max(0, self.queued_bytes - entry[2])
                return

    async def _overflow(self, reason: str) -> None:
        self.closed = True
        with contextlib.suppress(Exception):
            await self.websocket.close(code=WS_CLOSE_WRITER_OVERFLOW, reason=reason)
        raise ConnectionError(reason)

    async def _run(self) -> None:
        while True:
            while not self.queue:
                self._wake.clear()
                await self._wake.wait()
            frame, stamp, size = self.queue.popleft()
            self.queued_bytes = max(0, self.queued_bytes - size)
            try:
                if stamp is not None:
                    stamp(frame)
                await asyncio.wait_for(self.websocket.send_json(frame), timeout=self.timeout)
            except Exception:
                self.closed = True
                with contextlib.suppress(Exception):
                    await self.websocket.close(code=WS_CLOSE_NORMAL)
                return

    async def stop(self) -> None:
        self.closed = True
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None


def attach(websocket: WebSocket) -> Writer:
    """Create and start the writer for one connection."""
    writer = Writer(websocket)
    writer.start()
    _writers[websocket] = writer
    return writer


def get(websocket: WebSocket) -> Writer | None:
    return _writers.get(websocket)


async def detach(websocket: WebSocket) -> None:
    """Stop and forget this connection's writer, if it is still the owner."""
    writer = _writers.pop(websocket, None)
    if writer is not None:
        await writer.stop()


def clear() -> None:
    """Test reset: forget every writer without awaiting the stopped tasks."""
    for writer in list(_writers.values()):
        writer.closed = True
        if writer.task is not None:
            writer.task.cancel()
    _writers.clear()
