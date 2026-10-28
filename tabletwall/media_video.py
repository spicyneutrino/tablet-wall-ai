"""What the server process needs to know about video without loading the decoder.

``tabletwall.video`` is the worker: it imports Pillow and its warning policy.
The server only needs the MIME type, whether the tools exist, and a trust
boundary check on the facts a worker reports, so those live here.
"""

import shutil
from typing import Any

from tabletwall.media_limits import (
    MAX_VIDEO_DURATION_MS,
    MAX_VIDEO_FPS,
    MIN_VIDEO_DURATION_MS,
    VIDEO_PROFILES,
)

VIDEO_MIME = "video/mp4"


def tools_available() -> bool:
    return bool(shutil.which("ffprobe") and shutil.which("ffmpeg"))


def validate_facts(facts: Any) -> dict[str, Any]:
    """Re-check a worker-reported fact set at the trust boundary."""
    if not isinstance(facts, dict):
        raise ValueError("video facts are not an object")
    expected: dict[str, type | tuple[type, ...]] = {
        "intrinsicWidth": int, "intrinsicHeight": int, "durationMs": int, "codec": str,
        "profile": str, "level": str, "pixelFormat": str, "frameRate": (int, float),
        "bitrate": int, "faststart": bool, "audio": bool,
    }
    if set(facts) != set(expected):
        raise ValueError("video facts have unexpected fields")
    for key, kind in expected.items():
        value = facts[key]
        if isinstance(value, bool) != (kind is bool) or not isinstance(value, kind):
            raise ValueError(f"video fact {key} has the wrong type")
    if not MIN_VIDEO_DURATION_MS <= facts["durationMs"] <= MAX_VIDEO_DURATION_MS:
        raise ValueError("video duration is outside the accepted range")
    if facts["pixelFormat"] != "yuv420p" or facts["profile"] not in VIDEO_PROFILES:
        raise ValueError("video format is outside the accepted set")
    if not facts["faststart"]:
        raise ValueError("video is not faststart")
    if facts["intrinsicWidth"] <= 0 or facts["intrinsicHeight"] <= 0 or facts["bitrate"] < 0:
        raise ValueError("video dimensions or bitrate are invalid")
    if not 0 < facts["frameRate"] <= MAX_VIDEO_FPS + 0.01:
        raise ValueError("video frame rate is outside the accepted range")
    return facts
