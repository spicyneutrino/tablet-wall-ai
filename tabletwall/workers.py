"""One process owns the in-memory device and playback registries."""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tabletwall import persist


@contextmanager
def single_worker() -> Iterator[None]:
    """Hold a stable lock inode for the lifespan, including startup failures."""
    path = Path(persist.db_path()).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path) + ".runtime.lock", os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Tablet Wall requires one worker per database. Another process "
                "owns the runtime lock; run uvicorn with --workers 1."
            ) from error
        yield
    finally:
        os.close(descriptor)
