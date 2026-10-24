"""Generate small video fixtures with the installed ffmpeg, once per session.

Nothing here is checked in: every case is built into a temp directory the
first time a test asks for it. A missing ffmpeg skips the dependent tests.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe are not installed")

_H264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]


def _source(size: str = "320x240", rate: int = 15) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}"]


def _sine() -> list[str]:
    return ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]


def _run(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-y", *args],
        check=True, capture_output=True, timeout=120,
    )


def _build(name: str, directory: Path) -> Path:
    target = directory / name
    if name == "baseline.mp4":
        _run(*_source(), *_sine(), "-t", "2", *_H264, "-profile:v", "baseline", "-level", "3.1",
             "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(target))
    elif name == "nonfaststart.mp4":
        _run(*_source(), "-t", "2", *_H264, "-profile:v", "main", str(target))
    elif name == "high.mp4":
        _run(*_source("640x360"), "-t", "2", *_H264, "-profile:v", "high", str(target))
    elif name == "hd.mp4":
        _run(*_source("1920x1080", 30), "-t", "2", *_H264, "-profile:v", "high", "-level", "4.1",
             str(target))
    elif name == "portrait.mp4":
        _run(*_source("1080x1920", 5), "-t", "2", *_H264, "-profile:v", "high", "-level", "4.1",
             str(target))
    elif name == "quicktime.mov":
        _run(*_source(), *_sine(), "-t", "2", *_H264, "-profile:v", "main", "-c:a", "pcm_s16le",
             "-shortest", "-f", "mov", str(target))
    elif name == "metadata.mp4":
        _run(*_source(), "-t", "2", *_H264, "-profile:v", "main",
             "-metadata", "title=SECRETTITLE", "-metadata", "location=+51.5074-000.1278/",
             str(target))
    elif name == "rotated.mp4":
        plain = _ensure("high.mp4", directory)
        _run("-display_rotation", "90", "-i", str(plain), "-c", "copy", str(target))
    elif name == "hevc.mp4":
        _run(*_source(), "-t", "2", "-c:v", "libx265", "-pix_fmt", "yuv420p", "-x265-params",
             "log-level=none", str(target))
    elif name == "vp9.webm":
        _run(*_source(), "-t", "2", "-c:v", "libvpx-vp9", str(target))
    elif name == "tenbit.mp4":
        _run(*_source(), "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p10le",
             "-profile:v", "high10", str(target))
    elif name == "oversize.mp4":
        _run(*_source("2560x1440", 5), "-t", "2", *_H264, "-profile:v", "high",
             "-x264-params", "level=4.1", str(target))
    elif name == "level51.mp4":
        _run(*_source(), "-t", "2", *_H264, "-profile:v", "high", "-level", "5.1", str(target))
    elif name == "fps120.mp4":
        _run(*_source("320x240", 120), "-t", "2", *_H264, "-profile:v", "main", str(target))
    elif name == "short.mp4":
        _run(*_source(), "-t", "0.5", *_H264, "-profile:v", "main", str(target))
    elif name == "long.mp4":
        _run("-f", "lavfi", "-i", "color=c=black:size=64x64:rate=1", "-t", "601", *_H264,
             "-profile:v", "main", "-g", "30", str(target))
    elif name == "audio.m4a":
        _run(*_sine(), "-t", "2", "-c:a", "aac", str(target))
    elif name == "truncated_moov_last.mp4":
        data = _ensure("nonfaststart.mp4", directory).read_bytes()
        target.write_bytes(data[: len(data) // 2])
    elif name == "truncated_faststart.mp4":
        data = _ensure("high.mp4", directory)
        remuxed = directory / "high-faststart.mp4"
        _run("-i", str(data), "-c", "copy", "-movflags", "+faststart", str(remuxed))
        body = remuxed.read_bytes()
        target.write_bytes(body[: int(len(body) * 0.6)])
    elif name == "ffconcat.txt":
        target.write_text("ffconcat version 1.0\nfile '/etc/hostname'\n")
    elif name == "playlist.m3u8":
        target.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile:///etc/hostname\n#EXT-X-ENDLIST\n")
    elif name == "garbage.bin":
        target.write_bytes(os.urandom(4096))
    else:  # pragma: no cover - a typo in a test
        raise KeyError(name)
    return target




def _ensure(name: str, directory: Path) -> Path:
    path = directory / name
    if not path.exists():
        _build(name, directory)
    return path


@pytest.fixture(scope="session")
def video_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("video-fixtures")


@pytest.fixture
def make_video(video_dir):
    """``make_video("baseline.mp4")`` returns the cached fixture path."""

    def make(name: str) -> Path:
        return _ensure(name, video_dir)

    return make


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, timeout=60,
    )
    return json.loads(out.stdout)


def packet_md5(path: Path, stream: str = "v:0") -> str:
    """MD5 over the copied packet payloads of one stream: equal iff lossless."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{stream}",
         "-c", "copy", "-f", "md5", "-"],
        check=True, capture_output=True, timeout=60,
    )
    return out.stdout.decode().strip()


def fabricate_video(size: int = 12 * 1024 * 1024, name: str = "big.mp4") -> dict:
    """Publish a stand-in video object of ``size`` bytes through the real store.

    The bytes are not decodable; only the byte-serving, quota, backup and
    restore paths see them, which is exactly what a 250 MiB file exercises
    without spending minutes in the encoder. Needs the per-test env that
    ``conftest`` sets for the database and media directory.
    """
    from io import BytesIO

    from PIL import Image

    from tabletwall import media

    payload = os.urandom(size)
    digest = hashlib.sha256(payload).hexdigest()
    job = media.new_job()
    Path(job.directory, f"{digest}.mp4").write_bytes(payload)
    buffer = BytesIO()
    Image.new("RGB", (64, 36), (int(digest[0], 16) * 15, 90, 160)).save(buffer, format="JPEG")
    poster = buffer.getvalue()
    poster_digest = hashlib.sha256(poster).hexdigest()
    Path(job.directory, f"{poster_digest}.jpg").write_bytes(poster)
    result = {
        "ok": True,
        "objects": [
            {"role": "video", "filename": f"{digest}.mp4", "sha256": digest, "bytes": size,
             "width": 640, "height": 360, "mime": "video/mp4"},
            {"role": "thumbnail", "filename": f"{poster_digest}.jpg", "sha256": poster_digest,
             "bytes": len(poster), "width": 64, "height": 36, "mime": "image/jpeg"},
        ],
        "video": {
            "intrinsicWidth": 640, "intrinsicHeight": 360, "durationMs": 60_000,
            "codec": "avc1.64001E", "profile": "High", "level": "3.0",
            "pixelFormat": "yuv420p", "frameRate": 30.0, "bitrate": 1_000_000,
            "faststart": True, "audio": False,
        },
    }
    return media.publish_video(job, result, name)
