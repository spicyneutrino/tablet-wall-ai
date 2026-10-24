"""Test-only ASGI entry for the disposable suspend experiment.

It runs the unmodified application with one change in the server clock's
adapter seam: ``ServerClock(sample=...)`` is the injected ``(boottime,
monotonic)`` reader. Here BOOTTIME gets a persistent step read from a file the
runner owns, while MONOTONIC and all scheduling stay real. A step larger than
``clock.SUSPEND_THRESHOLD_MS`` is exactly what a host suspend looks like to
``check_suspend``: BOOTTIME advanced and MONOTONIC did not.

No product file is edited. The runner uses this entry only for its second
disposable server, never for the unmodified-clock run.
"""

import os
from pathlib import Path

from tabletwall import clock

_STEP_FILE = Path(os.environ["SIM_BOOTTIME_STEP_FILE"])


def _step_ms() -> float:
    try:
        return float(_STEP_FILE.read_text() or 0)
    except (OSError, ValueError):
        return 0.0


def _injected_pair() -> tuple[float, float]:
    boot, mono = clock._now_pair()
    return boot + _step_ms(), mono


class InjectedServerClock(clock.ServerClock):
    def __init__(self) -> None:
        super().__init__(sample=_injected_pair)


clock.ServerClock = InjectedServerClock

from main import app  # noqa: E402,F401  (must import after the adapter is in place)
