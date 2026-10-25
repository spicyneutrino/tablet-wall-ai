"""Optional ffmpeg/ffprobe video alignment and burned-in frame OCR.

A video is never timed from its nominal frame rate. ``ffprobe`` supplies the
decoded presentation timestamps and ``ffmpeg`` extracts one image per decoded
frame. Numbered source-frame tracking exists only when a burned-in frame ROI
can be read; a cut detector alone is not video synchronization.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .model import Frame

TOOL_TIMEOUT_S = 120


class ToolUnavailable(RuntimeError):
    """The optional external tool is not installed or cannot run."""


def _run(args: list[str], *, timeout: int = TOOL_TIMEOUT_S, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            args,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ToolUnavailable(f"{args[0]} is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise ToolUnavailable(f"{args[0]} timed out") from error
    except OSError as error:
        raise ToolUnavailable(f"cannot run {args[0]}: {error}") from error


def _version_line(command: str, args: list[str]) -> str | None:
    try:
        done = _run([command, *args], timeout=20)
    except ToolUnavailable:
        return None
    text = (done.stdout or b"").decode("utf-8", "replace").strip()
    return text.splitlines()[0] if text else None


def tool_versions(
    ffmpeg_cmd: str = "ffmpeg",
    ffprobe_cmd: str = "ffprobe",
    tesseract_cmd: str = "tesseract",
) -> dict[str, Any]:
    return {
        "ffmpeg": _version_line(ffmpeg_cmd, ["-version"]),
        "ffprobe": _version_line(ffprobe_cmd, ["-version"]),
        "tesseract": _version_line(tesseract_cmd, ["--version"]),
    }


def probe_frame_timestamps(video_path: Path | str, ffprobe_cmd: str = "ffprobe") -> list[float]:
    if shutil.which(ffprobe_cmd) is None:
        raise ToolUnavailable("ffprobe is not installed")
    done = _run([
        ffprobe_cmd,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time,pts_time",
        "-of", "json",
        str(video_path),
    ])
    if done.returncode != 0:
        message = (done.stderr or b"").decode("utf-8", "replace").strip()
        raise ValueError(f"ffprobe failed: {message}")
    try:
        import json

        payload = json.loads(done.stdout or b"{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"ffprobe returned invalid JSON: {error}") from error
    rows = payload.get("frames") or []
    timestamps: list[float] = []
    for row in rows:
        value = row.get("best_effort_timestamp_time")
        if value in (None, "N/A"):
            value = row.get("pts_time")
        if value in (None, "N/A"):
            continue
        timestamps.append(float(value))
    if not timestamps:
        raise ValueError("ffprobe found no video frame timestamps")
    for earlier, later in zip(timestamps, timestamps[1:]):
        if later < earlier:
            raise ValueError("ffprobe frame timestamps run backwards")
    return timestamps


def probe_stream_metadata(video_path: Path | str, ffprobe_cmd: str = "ffprobe") -> dict[str, Any]:
    if shutil.which(ffprobe_cmd) is None:
        raise ToolUnavailable("ffprobe is not installed")
    done = _run([
        ffprobe_cmd,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,r_frame_rate",
        "-of", "json",
        str(video_path),
    ])
    if done.returncode != 0:
        return {}
    try:
        import json

        payload = json.loads(done.stdout or b"{}")
    except json.JSONDecodeError:
        return {}
    streams = payload.get("streams") or []
    if not streams:
        return {}
    row = streams[0]
    return {
        "codec_name": row.get("codec_name"),
        "width": row.get("width"),
        "height": row.get("height"),
        "avg_frame_rate": row.get("avg_frame_rate"),
        "r_frame_rate": row.get("r_frame_rate"),
    }


def decode_video(
    video_path: Path | str,
    output_dir: Path | str,
    *,
    ffmpeg_cmd: str = "ffmpeg",
    ffprobe_cmd: str = "ffprobe",
) -> tuple[Frame, ...]:
    """Extract every decoded frame and pair it with its ffprobe timestamp."""
    source = Path(video_path)
    if not source.exists():
        raise ValueError(f"video does not exist: {source}")
    timestamps = probe_frame_timestamps(source, ffprobe_cmd=ffprobe_cmd)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for existing in destination.iterdir():
        if existing.is_file() and re.fullmatch(r"\d{6}\.png", existing.name):
            existing.unlink()

    prefix = [
        ffmpeg_cmd, "-v", "error", "-i", str(source), "-map", "0:v:0",
    ]
    suffix = ["-start_number", "0", str(destination / "%06d.png")]
    done = _run([*prefix, "-fps_mode", "passthrough", *suffix])
    if done.returncode != 0:
        # Older ffmpeg releases use -vsync instead of -fps_mode.
        done = _run([*prefix, "-vsync", "0", *suffix])
    if done.returncode != 0:
        message = (done.stderr or b"").decode("utf-8", "replace").strip()
        raise ValueError(f"ffmpeg frame extraction failed: {message}")

    extracted = sorted(
        path for path in destination.glob("*.png")
        if re.fullmatch(r"\d{6}\.png", path.name)
    )
    if len(extracted) != len(timestamps):
        raise ValueError(
            f"ffmpeg extracted {len(extracted)} frames but ffprobe reported "
            f"{len(timestamps)} timestamps; frame alignment is not trustworthy"
        )
    return tuple(
        Frame(index=index, path=path, timestamp_s=timestamp)
        for index, (path, timestamp) in enumerate(zip(extracted, timestamps))
    )


def parse_source_frame_text(text: str, digits: int) -> int | None:
    sequences = re.findall(r"\d+", text)
    if not sequences:
        return None
    joined = "".join(sequences)
    if len(joined) < digits:
        return None
    return int(joined[-digits:])


def read_source_frame(
    image_path: Path | str,
    roi: tuple[int, int, int, int],
    digits: int = 6,
    *,
    tesseract_cmd: str = "tesseract",
) -> int | None:
    """Read a burned-in frame number from ``roi`` with tesseract.

    Raises :class:`ToolUnavailable` when tesseract is missing or cannot run.
    Returns ``None`` when the crop is readable but no digits are recognised.
    """
    if shutil.which(tesseract_cmd) is None:
        raise ToolUnavailable("tesseract is not installed")
    x, y, width, height = roi
    try:
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
                return None
            crop = image.crop((x, y, x + width, y + height))
            crop = ImageOps.autocontrast(crop.convert("L"))
            scale = max(1, min(8, 400 // max(crop.height, 1)))
            if scale > 1:
                crop = crop.resize(
                    (crop.width * scale, crop.height * scale),
                    Image.Resampling.LANCZOS,
                )
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
    except OSError:
        return None

    done = _run([
        tesseract_cmd,
        "stdin", "stdout",
        "--psm", "7",
        "-c", "tessedit_char_whitelist=0123456789",
    ], input_bytes=buffer.getvalue(), timeout=15)
    if done.returncode != 0:
        raise ToolUnavailable(
            (done.stderr or b"").decode("utf-8", "replace").strip() or "tesseract failed"
        )
    text = (done.stdout or b"").decode("utf-8", "replace")
    return parse_source_frame_text(text, digits)
