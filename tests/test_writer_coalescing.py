"""Causal coalescing: only complete state snapshots collapse, in causal order."""

import asyncio

import pytest

from tabletwall import writer
from tabletwall.protocol import WS_CLOSE_WRITER_OVERFLOW


class FakeWebSocket:
    def __init__(self):
        self.frames = []
        self.closed = None
        self.block = asyncio.Event()

    async def send_json(self, frame):
        await self.block.wait()
        self.frames.append(frame)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


async def drain(socket, count):
    for _ in range(200):
        if len(socket.frames) >= count:
            return
        await asyncio.sleep(.01)


def shape(frames):
    return [(frame["type"], frame.get("n")) for frame in frames]


def test_a_slow_reader_gets_the_latest_snapshot_and_every_causal_frame_in_order():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket)
        connection.start()
        await connection.send({"type": "welcome"})
        await asyncio.sleep(.01)  # welcome is in flight; nothing can drop it
        for frame in (
            {"type": "playback_status", "n": 1},
            {"type": "prepare", "n": 2},
            {"type": "playback_status", "n": 3},
            {"type": "commit", "n": 4},
            {"type": "playback_status", "n": 5},
            {"type": "cancel", "n": 6},
            {"type": "playback_status", "n": 7},
        ):
            await connection.send(frame)
        socket.block.set()
        await drain(socket, 5)
        await asyncio.sleep(.05)
        await connection.stop()
        return socket.frames

    assert shape(asyncio.run(scenario())) == [
        ("welcome", None), ("prepare", 2), ("commit", 4), ("cancel", 6),
        ("playback_status", 7),
    ]


def test_a_snapshot_never_overtakes_a_causal_frame_enqueued_before_it():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket)
        connection.start()
        await connection.send({"type": "welcome"})
        await asyncio.sleep(.01)
        await connection.send({"type": "playback_status", "n": 1})
        await connection.send({"type": "commit", "n": 2})
        await connection.send({"type": "playback_status", "n": 3})
        socket.block.set()
        await drain(socket, 3)
        await asyncio.sleep(.05)
        await connection.stop()
        return socket.frames

    assert shape(asyncio.run(scenario())) == [
        ("welcome", None), ("commit", 2), ("playback_status", 3),
    ]


def test_identical_causal_frames_are_never_collapsed():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket)
        connection.start()
        for _ in range(3):
            await connection.send({"type": "prepare", "n": 1})
            await connection.send({"type": "commit", "n": 1})
        socket.block.set()
        await drain(socket, 6)
        await asyncio.sleep(.05)
        await connection.stop()
        return socket.frames

    assert [frame["type"] for frame in asyncio.run(scenario())] == ["prepare", "commit"] * 3


def test_snapshot_types_coalesce_independently_and_free_the_budget():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket, frame_budget=3)
        connection.start()
        await connection.send({"type": "prepare"})
        await asyncio.sleep(.01)
        for n in range(20):
            await connection.send({"type": "playback_status", "n": n})
            await connection.send({"type": "wall_updated", "n": n})
        assert connection.closed is False
        socket.block.set()
        await drain(socket, 3)
        await asyncio.sleep(.05)
        await connection.stop()
        return socket

    socket = asyncio.run(scenario())
    assert socket.closed is None
    assert shape(socket.frames) == [
        ("prepare", None), ("playback_status", 19), ("wall_updated", 19),
    ]


def test_a_stamped_frame_is_not_coalesced_and_overflow_still_closes():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket, frame_budget=2)
        connection.start()
        await connection.send({"type": "playback_status", "n": 1}, stamp=lambda f: None)
        await connection.send({"type": "playback_status", "n": 2}, stamp=lambda f: None)
        assert len(connection.queue) == 2
        with pytest.raises(ConnectionError):
            await connection.send({"type": "prepare"})
        await connection.stop()
        return socket

    assert asyncio.run(scenario()).closed[0] == WS_CLOSE_WRITER_OVERFLOW


def test_queued_bytes_stay_balanced_after_coalescing():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket)
        connection.start()
        for n in range(10):
            await connection.send({"type": "playback_status", "n": n, "pad": "x" * 50})
        socket.block.set()
        await drain(socket, 1)
        await asyncio.sleep(.05)
        remaining = connection.queued_bytes
        await connection.stop()
        return remaining

    assert asyncio.run(scenario()) == 0
