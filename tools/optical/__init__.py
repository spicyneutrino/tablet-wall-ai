"""Optical cut-timing analyzer for the tablet wall.

The analyzer measures visible onset in an already recorded high-speed capture.
It never closes the ``optical-cut-timing`` hardware gate: every report is built
through :mod:`tools.validation.evidence` and keeps ``hardware_gate_status`` at
``MISSING``. Synthetic fixtures validate the analyzer only.
"""

from __future__ import annotations

TOOL_NAME = "optical-cut-analyzer"
TOOL_VERSION = "1"

__all__ = ["TOOL_NAME", "TOOL_VERSION"]
