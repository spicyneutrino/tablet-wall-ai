"""Bounded ordered writer: ordering, budgets, timeout, ownership."""

import asyncio

import pytest

from tabletwall import writer
from tabletwall.protocol import WS_CLOSE_WRITER_OVERFLOW


class FakeWebSocket:
    def __init__(self, block: asyncio.Event | None = None):
        self.frames = []
        self.closed = None
        self.block = block

    async def send_json(self, frame):
        if self.block is not None:
            await self.block.wait()
        self.frames.append(frame)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


def test_frames_arrive_in_enqueue_order():
    async def scenario():
        socket = FakeWebSocket()
        connection = writer.Writer(socket)
        connection.start()
        for index in range(5):
            await connection.send({"index": index})
        for _ in range(50):
            if len(socket.frames) == 5:
                break
            await asyncio.sleep(.01)
        await connection.stop()
        return socket.frames

    assert [frame["index"] for frame in asyncio.run(scenario())] == [0, 1, 2, 3, 4]


def test_frame_budget_overflow_closes_with_4429():
    async def scenario():
        socket = FakeWebSocket(block=asyncio.Event())
        connection = writer.Writer(socket, frame_budget=2)
        connection.start()
        await connection.send({"n": 0})
        await connection.send({"n": 1})
        with pytest.raises(ConnectionError):
            await connection.send({"n": 2})
        await connection.stop()
        return socket

    socket = asyncio.run(scenario())
    assert socket.closed[0] == WS_CLOSE_WRITER_OVERFLOW


def test_byte_budget_overflow_closes():
    async def scenario():
        socket = FakeWebSocket(block=asyncio.Event())
        connection = writer.Writer(socket, byte_budget=20)
        connection.start()
        with pytest.raises(ConnectionError):
            await connection.send({"payload": "x" * 40})
        await connection.stop()
        return socket

    assert asyncio.run(scenario()).closed[0] == WS_CLOSE_WRITER_OVERFLOW


def test_a_slow_send_times_out_and_closes_the_socket():
    async def scenario():
        socket = FakeWebSocket(block=asyncio.Event())
        connection = writer.Writer(socket, timeout=.05)
        connection.start()
        await connection.send({"n": 1})
        await asyncio.sleep(.15)
        return socket, connection.closed

    socket, closed = asyncio.run(scenario())
    assert closed is True
    assert socket.closed[0] == 1000


def test_attach_and_detach_are_owned_by_one_connection():
    async def scenario():
        first, second = FakeWebSocket(), FakeWebSocket()
        writer.attach(first)
        writer.attach(second)
        assert writer.get(first) is not None
        await writer.detach(first)
        assert writer.get(first) is None
        assert writer.get(second) is not None
        await writer.detach(second)
        assert writer.get(second) is None

    asyncio.run(scenario())
    writer.clear()
