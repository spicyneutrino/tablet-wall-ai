"""Contracts for the standalone device probe and its desktop smoke report."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image
import pytest

from simulator.browser import decode_probe
from tools.validation import evidence

REQUIRED_FIELDS = {
    "page.instance_id",
    "page.sequence",
    "page.previous_instance_id",
    "page.navigation",
    "environment.user_agent",
    "environment.platform",
    "environment.viewport",
    "environment.device_pixel_ratio",
    "environment.orientation",
    "environment.display_mode",
    "environment.codec_support",
    "environment.api_support",
    "environment.wake_lock",
    "environment.fullscreen",
    "source.name",
    "source.size",
    "source.sha256",
    "play.attempts",
    "media_events",
    "samples",
    "frame_callbacks",
    "lifecycle",
    "actions",
    "markers",
    "lineage",
    "persistence",
    "unavailable",
}

REQUIRED_MEDIA_EVENTS = {
    "loadstart",
    "loadedmetadata",
    "canplay",
    "playing",
    "waiting",
    "stalled",
    "ended",
    "error",
}

CONTROL_IDS = {
    "video",
    "play",
    "pause",
    "loop",
    "seek",
    "mute",
    "download",
    "reset",
    "mark-button",
    "wake-lock",
    "fullscreen",
}


def test_probe_contract_has_required_fields_controls_and_bounded_persistence():
    contract = decode_probe.probe_contract()
    assert contract["schema"] == "tablet-wall-device-probe/1"
    assert REQUIRED_FIELDS <= set(contract["required_payload_fields"])
    assert REQUIRED_MEDIA_EVENTS <= set(contract["required_media_events"])
    assert contract["required_frame_metadata"] == [
        "mediaTime", "presentedFrames", "expectedDisplayTime", "width", "height",
    ]

    html = decode_probe.PROBE_INDEX.read_text()
    js = decode_probe.PROBE_JS.read_text()
    for element_id in CONTROL_IDS:
        assert f'id="{element_id}"' in html
    assert "Download JSON" in html
    assert "Reset stored evidence" in html

    for token in (
        "sessionStorage",
        "localStorage",
        'window.addEventListener("pagehide"',
        "saveSession(\"pagehide\")",
        'document.addEventListener("visibilitychange"',
        "requestVideoFrameCallback",
        "getVideoPlaybackQuality",
        "wakeLock",
        "fullscreen",
        "navigator.userAgent",
        "devicePixelRatio",
        "screen.orientation",
        "unexplained_gaps",
        "cause: null",
    ):
        assert token in js

    limits = contract["limits"]
    expected_bounds = {
        "events": 2000,
        "samples": 5000,
        "frame_callbacks": 3000,
        "markers": 500,
        "gaps": 500,
        "lifecycle": 500,
        "actions": 500,
        "play_attempts": 100,
        "ledger_sessions": 100,
    }
    for key, upper in expected_bounds.items():
        assert 0 < limits[key] <= upper
        assert f"LIMITS.{key}" in js or (key == "events" and "LIMITS.events" in js)
    assert "function pushBounded" in js
    assert "trimmed" in js


def test_payload_problems_expose_missing_contract_fields_and_core_events():
    problems = decode_probe.payload_problems({})
    assert any("page.instance_id" in problem for problem in problems)
    assert any("core media event not observed: playing" in problem for problem in problems)
    assert len(problems) > len(REQUIRED_FIELDS)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required to generate the probe fixture",
)
def test_generated_clip_is_h264_ten_seconds_with_a_changing_frame_counter(tmp_path: Path):
    path = tmp_path / "decode-probe-10s.mp4"
    clip = decode_probe.build_clip(path)

    assert path.exists()
    assert clip["codec"] == "h264"
    assert clip["width"] == decode_probe.CLIP_WIDTH
    assert clip["height"] == decode_probe.CLIP_HEIGHT
    assert clip["fps"] == decode_probe.CLIP_FPS
    assert clip["frames"] == decode_probe.CLIP_FRAMES
    assert 9.9 <= clip["duration"] <= 10.1
    assert clip["bytes"] > 100_000
    assert clip["sha256"] == evidence.file_sha256(path)

    overlay = (24, 22, 330, 150)
    frames = []
    for stamp in ("0.2", "5.2"):
        output = tmp_path / f"frame-{stamp}.png"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-ss", stamp, "-i", str(path), "-frames:v", "1", "-y", str(output),
            ],
            check=True, timeout=60,
        )
        with Image.open(output) as image:
            frames.append(list(image.crop(overlay).convert("RGB").getdata()))
    changed = sum(
        1 for left, right in zip(frames[0], frames[1], strict=True)
        if sum(abs(a - b) for a, b in zip(left, right, strict=True)) > 40
    )
    assert changed > len(frames[0]) // 50


def _engine(
    status: str, checks: list[dict[str, object]] | None = None,
    detail: str | None = None,
) -> dict[str, object]:
    return {"status": status, "checks": checks or [], "detail": detail}


def test_report_keeps_the_gate_missing_and_webkit_absence_is_unsupported():
    report = decode_probe.assemble_report(
        started_at="2026-10-25T00:00:00Z",
        engines={
            "chromium": _engine("passed", [
                evidence.check_row("chromium: payload contract", True),
                evidence.check_row("chromium: fresh play", True),
            ]),
            "webkit": _engine(
                "unsupported",
                [evidence.check_row("webkit: must not count", False)],
                detail="Executable doesn't exist",
            ),
        },
        artifacts={},
        tools={"playwright": "1.57.0"},
        repository={"head": "abc", "branch": "b", "dirty": False},
    )

    assert report["schema"] == evidence.SCHEMA
    assert report["gate"] == "physical-decode-suspend"
    assert report["evidence_kind"] == "desktop-browser"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["checks_total"] == 2
    assert report["checks_passed"] == 2
    assert report["failure_reasons"] == []
    assert report["scenarios_total"] == 3
    assert report["scenarios_passed"] == 1
    assert report["cohort"] == ["desktop-chromium", "desktop-webkit"]
    scenarios = {row["id"]: row for row in report["scenarios"]}
    assert scenarios["desktop-chromium"]["status"] == "passed"
    assert scenarios["desktop-webkit"]["status"] == "unsupported"
    assert scenarios["desktop-webkit"]["detail"] == "Executable doesn't exist"
    assert scenarios["ios-safari"]["status"] == "unsupported"
    assert report["completion"] == "incomplete"
    assert any("iOS Safari" in limitation for limitation in report["limitations"])
    assert "iOS Safari" in report["unobserved"]
    assert "app switch / home-screen round trip" in report["unobserved"]


def test_a_failed_chromium_run_blocks_completion_and_unsupported_stays_clean():
    report = decode_probe.assemble_report(
        started_at="2026-10-25T00:00:00Z",
        engines={
            "chromium": _engine("failed", [
                evidence.check_row("chromium: payload contract", False),
            ], detail="fresh play timed out"),
            "webkit": _engine("unsupported", detail="not installed"),
        },
        artifacts={},
        tools={},
    )
    assert report["completion"] == "incomplete"
    assert "desktop-chromium" in report["failure_reasons"]
    assert "chromium: payload contract" in report["failure_reasons"]
    assert "desktop-webkit" not in report["failure_reasons"]


def test_missing_engine_rows_stay_incomplete_rather_than_silently_disappearing():
    report = decode_probe.assemble_report(
        started_at="2026-10-25T00:00:00Z",
        engines={},
        artifacts={},
        tools={},
    )
    scenarios = {row["id"]: row for row in report["scenarios"]}
    assert scenarios["desktop-chromium"]["status"] == "incomplete"
    assert scenarios["desktop-webkit"]["status"] == "incomplete"
    assert scenarios["ios-safari"]["status"] == "unsupported"
    assert report["completion"] == "incomplete"
