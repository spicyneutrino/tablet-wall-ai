"""Size-bounded, rotating output for the hotspot launcher's child processes.

``backend.log`` and ``caddy.log`` are piped through one reader thread each and
appended in fixed-size pieces to a rotating file. A chatty or wedged process
cannot fill the disk: the active file never passes ``max_bytes`` and only
``backups`` older files are kept. A single output line with no newline cannot
grow launcher memory either, because the reader never buffers more than one
chunk.

Rotation renames the active file to ``.1`` and shifts older archives, so the
log paths the operator already opens do not change. This is runtime rotation
inside the launcher, not an installed logrotate unit.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import IO

DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_BACKUPS = 2
READ_CHUNK = 8192


class RotatingLog:
    """One append-only file capped at ``max_bytes`` with ``backups`` archives."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backups: int = DEFAULT_BACKUPS,
    ):
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        if backups < 1:
            raise ValueError("backups must be at least 1")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backups = backups
        self._size = 0
        self._handle: IO[bytes] | None = None

    def _archive(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("ab")
        self._size = self.path.stat().st_size

    def open(self) -> None:
        self._open()
        if self._size >= self.max_bytes:
            self._rotate()

    def _rotate(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        for index in range(self.backups, 1, -1):
            source = self._archive(index - 1)
            if source.exists():
                os.replace(source, self._archive(index))
        if self.path.exists():
            os.replace(self.path, self._archive(1))
        self._open()

    def write(self, data: bytes) -> None:
        """Append ``data``, rotating between pieces so no file exceeds the cap."""
        if self._handle is None:
            raise ValueError("log is not open")
        view = memoryview(data)
        while view:
            room = self.max_bytes - self._size
            if room <= 0:
                self._rotate()
                continue
            piece = view[:room]
            self._handle.write(piece)
            self._size += len(piece)
            view = view[room:]

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


class LogPump:
    """Attach one child pipe to a ``RotatingLog`` until the pipe reaches EOF."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backups: int = DEFAULT_BACKUPS,
    ):
        self.log = RotatingLog(path, max_bytes=max_bytes, backups=backups)
        self._stream: IO[bytes] | None = None
        self._thread: threading.Thread | None = None
        self.error: OSError | ValueError | None = None

    def __enter__(self) -> LogPump:
        self.log.open()
        return self

    def attach(self, stream: IO[bytes]) -> None:
        if self._thread is not None:
            raise RuntimeError("this log already has a reader")
        self._stream = stream
        self._thread = threading.Thread(
            target=self._pump, name=f"log-{self.log.path.name}", daemon=True
        )
        self._thread.start()

    def _pump(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            while True:
                # ``read1`` returns what one pipe read has available; plain
                # ``read`` would wait for a full chunk and delay live logs.
                read = getattr(stream, "read1", stream.read)
                chunk = read(READ_CHUNK)
                if not chunk:
                    break
                self.log.write(chunk)
        except (OSError, ValueError) as error:
            self.error = error

    def check(self) -> None:
        if self.error is not None:
            raise RuntimeError(
                f"Child logging failed for {self.log.path}. "
                "Check free disk space and directory permissions before restarting."
            ) from self.error

    def __exit__(self, *_exc: object) -> None:
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive() and self._stream is not None:
                try:
                    self._stream.close()
                except OSError:
                    pass
                self._thread.join(timeout=5)
        try:
            self.log.close()
        except (OSError, ValueError) as error:
            self.error = self.error or error
        if not _exc or _exc[0] is None:
            self.check()
