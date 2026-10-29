"""R4 prerecorded-video ingest, run as a bounded subprocess.

Usage::

    python -m tabletwall.video <source_path> <job_dir> <result_path>

The worker accepts one H.264 MP4 or MOV and nothing else: no transcoding, no
guessing at other containers. It inspects the file with ``ffprobe``, applies
the acceptance rules from ``media_limits``, remuxes it losslessly into a
faststart MP4 holding the video track and at most one AAC or MP3 track, pulls
one frame as a poster, and writes both as content-addressed objects into
``job_dir``. The JSON result is written last, with the same contract as
``media_worker``: ``ok: false`` is a clean refusal, a nonzero exit means no
result could be written.

Every ``ffprobe``/``ffmpeg`` call is a fixed argv with no shell, reads its
input as ``-f mov`` only (so an uploaded HLS or ffconcat text file is never
parsed by a demuxer that follows its own references), and allows the ``file``
protocol only. The child limits come from ``media_worker._apply_limits``;
file-size and wall-clock bounds are added here. The remux always runs, even
for an already-faststart file, because it is also the integrity pass: it
drops GPS and other container metadata, normalizes MOV to MP4, and fails on a
truncated stream under ``-xerror``.
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
from types import ModuleType
from typing import Any

from PIL import Image

from tabletwall.media_limits import (
    MAX_H264_LEVEL,
    MAX_PROBE_BYTES,
    MAX_VIDEO_BYTES,
    MAX_VIDEO_DURATION_MS,
    MAX_VIDEO_FPS,
    MAX_VIDEO_LONG_EDGE,
    MAX_VIDEO_SHORT_EDGE,
    MIN_VIDEO_DURATION_MS,
    RENDITION_EDGES,
    THUMBNAIL_QUALITY,
    VIDEO_PIPELINE_VERSION,
    VIDEO_PROFILES,
    VIDEO_TOOL_TIMEOUT_S,
)
from tabletwall.media_video import VIDEO_MIME
from tabletwall.media_worker import (
    Rejected,
    _apply_limits,
    _check_job_dir,
    _check_result_path,
    _encode_jpeg,
    _fit,
    _fsync_dir,
    _write_result,
)

try:
    import resource as _resource
    resource: ModuleType | None = _resource
except ImportError:  # pragma: no cover - the server runs on POSIX
    resource = None

_MIB = 1024 * 1024
_MAX_TOP_LEVEL_BOXES = 4096
_KEPT_AUDIO = ("aac", "mp3")
_ISO_FIRST_BOXES = (b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot", b"junk")

# ``-show_entries`` keeps the JSON small and bounded: only the fields the
# rules read, never the full tag set.
_PROBE_ENTRIES = (
    "format=duration,bit_rate,size,nb_streams"
    ":stream=index,codec_type,codec_name,profile,level,pix_fmt,width,height,"
    "avg_frame_rate,r_frame_rate,bit_rate,duration,codec_tag_string,"
    "mime_codec_string,field_order"
    ":stream_disposition=attached_pic"
    ":stream_side_data=side_data_type,rotation"
)

_TRUNCATED = (
    "The file looks truncated or damaged (its MP4 structure ends early). "
    "Re-export it and upload it again."
)
_UNREADABLE = (
    "The file could not be read as MP4 or MOV video. "
    "Re-export it as an H.264 MP4 and upload it again."
)
_REENCODE_HINT = (
    "Re-encode it first, for example: ffmpeg -i input -c:v libx264 "
    "-profile:v high -level 4.1 -pix_fmt yuv420p output.mp4"
)

_FOREIGN_CONTAINERS = (
    (b"\x1a\x45\xdf\xa3", "WebM or Matroska"),
    (b"OggS", "Ogg"),
    (b"RIFF", "AVI or another RIFF"),
    (b"\x00\x00\x01\xba", "MPEG program stream"),
    (b"\x00\x00\x01\xb3", "MPEG video"),
    (b"ID3", "MP3 audio"),
    (b"fLaC", "FLAC audio"),
    (b"#EXTM3U", "HLS playlist text"),
)


# ---------------------------------------------------------------------------
# container structure
# ---------------------------------------------------------------------------


def sniff(head: bytes) -> None:
    """Refuse anything that does not start like an ISO base media file."""
    if len(head) >= 8 and head[4:8] in _ISO_FIRST_BOXES:
        return
    for magic, name in _FOREIGN_CONTAINERS:
        if head.startswith(magic):
            raise Rejected(
                f"This is a {name} file. Only H.264 video in an MP4 or MOV "
                "container is accepted. " + _REENCODE_HINT
            )
    if len(head) >= 4 and head[0] == 0x47:
        raise Rejected(
            "This looks like an MPEG transport stream. Only H.264 video in an "
            "MP4 or MOV container is accepted. " + _REENCODE_HINT
        )
    raise Rejected(
        "The file is not an MP4 or MOV video. Only H.264 video in an MP4 or "
        "MOV container is accepted. " + _REENCODE_HINT
    )


def scan_boxes(path: str) -> bool:
    """Walk the top-level boxes; return True when ``moov`` precedes ``mdat``.

    The boxes must tile the file exactly. A box that overruns the end, a
    header that does not fit, or no ``moov`` at all is a truncated upload, and
    this catches it without decoding. The same walk is the faststart check
    for both the source and the remuxed output.
    """
    size = os.path.getsize(path)
    position = 0
    count = 0
    first_moov = first_mdat = None
    with open(path, "rb") as handle:
        while position < size:
            count += 1
            if count > _MAX_TOP_LEVEL_BOXES:
                raise Rejected(_UNREADABLE)
            handle.seek(position)
            header = handle.read(16)
            if len(header) < 8:
                raise Rejected(_TRUNCATED)
            box_size = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            header_size = 8
            if box_size == 1:
                if len(header) < 16:
                    raise Rejected(_TRUNCATED)
                box_size = int.from_bytes(header[8:16], "big")
                header_size = 16
            elif box_size == 0:
                box_size = size - position
            if box_size < header_size or position + box_size > size:
                raise Rejected(_TRUNCATED)
            if kind == b"moov" and first_moov is None:
                first_moov = position
            elif kind == b"mdat" and first_mdat is None:
                first_mdat = position
            position += box_size
    if first_moov is None:
        raise Rejected(_TRUNCATED)
    return first_mdat is None or first_moov < first_mdat


# ---------------------------------------------------------------------------
# subprocess plumbing
# ---------------------------------------------------------------------------


def _tool_env() -> dict[str, str]:
    # One malloc arena keeps the address-space limit meaningful on a many-core
    # host, where glibc otherwise reserves 64 MiB of address space per thread.
    return {"PATH": os.environ.get("PATH", "/usr/bin"), "LC_ALL": "C", "MALLOC_ARENA_MAX": "1"}


def _tail(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 4096))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _run(argv: list[str], job_dir: str, label: str) -> str:
    """Run one tool; return the path of its captured stdout.

    Output goes to files in the job directory so a hostile stream cannot grow
    this process's memory; the caller reads a bounded prefix.
    """
    out_path = os.path.join(job_dir, f"{label}.out")
    err_path = os.path.join(job_dir, f"{label}.err")
    try:
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            completed = subprocess.run(
                argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                env=_tool_env(), timeout=VIDEO_TOOL_TIMEOUT_S, close_fds=True,
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        raise Rejected(
            f"Reading the video took longer than {VIDEO_TOOL_TIMEOUT_S} seconds; "
            "upload a shorter or simpler file."
        ) from error
    except FileNotFoundError as error:
        raise Rejected(
            "ffmpeg is not installed on the server, so video cannot be processed."
        ) from error
    if completed.returncode != 0:
        message = _tail(err_path)
        if "moov atom not found" in message or "Invalid data" in message:
            raise Rejected(_TRUNCATED if label != "probe" else _UNREADABLE)
        if completed.returncode < 0:
            raise Rejected(
                "Processing the video ran past a server resource limit; upload a "
                "smaller or shorter file."
            )
        raise Rejected(_TRUNCATED if label == "remux" else _UNREADABLE)
    return out_path


def _probe(path: str, job_dir: str, label: str = "probe") -> dict[str, Any]:
    argv = [
        "ffprobe", "-v", "error", "-protocol_whitelist", "file", "-f", "mov",
        "-print_format", "json", "-show_entries", _PROBE_ENTRIES, f"file:{path}",
    ]
    out_path = _run(argv, job_dir, label)
    if os.path.getsize(out_path) > MAX_PROBE_BYTES:
        raise Rejected("The file declares too many tracks or too much metadata.")
    try:
        with open(out_path, "rb") as handle:
            document = json.loads(handle.read(MAX_PROBE_BYTES))
    except (OSError, ValueError) as error:
        raise Rejected(_UNREADABLE) from error
    if not isinstance(document, dict):
        raise Rejected(_UNREADABLE)
    return document


# ---------------------------------------------------------------------------
# acceptance rules
# ---------------------------------------------------------------------------


def _rate(value: Any) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    numerator, _, denominator = value.partition("/")
    try:
        top, bottom = int(numerator), int(denominator)
    except ValueError:
        return None
    return top / bottom if top > 0 and bottom > 0 else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def facts_from_probe(document: dict[str, Any]) -> tuple[dict[str, Any], int, int | None]:
    """Apply the acceptance rules; return ``(facts, video index, audio index)``.

    ``facts`` is exactly what the descriptor and the ``media_video`` row carry.
    Size is the display size after rotation metadata. The size cap is applied
    as long edge and short edge so portrait phone video is accepted.
    """
    streams = document.get("streams")
    if not isinstance(streams, list):
        raise Rejected(_UNREADABLE)
    streams = [stream for stream in streams if isinstance(stream, dict)]
    videos = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
        and not (stream.get("disposition") or {}).get("attached_pic")
    ]
    if not videos:
        if any(stream.get("codec_type") == "audio" for stream in streams):
            raise Rejected(
                "The file has audio but no video track. Upload an MP4 with an "
                "H.264 video track."
            )
        raise Rejected("The file has no video track. Upload an MP4 with an H.264 video track.")
    if len(videos) > 1:
        raise Rejected(
            "The file has more than one video track. Export a single-track MP4 "
            "and upload that."
        )
    video = videos[0]

    codec = video.get("codec_name")
    if codec != "h264":
        raise Rejected(
            f"The video codec is {str(codec or 'unknown').upper()}. Only H.264 is "
            "accepted, and the server does not transcode. " + _REENCODE_HINT
        )
    if video.get("codec_tag_string") != "avc1":
        raise Rejected(
            "The H.264 stream keeps its parameter sets in the frames (avc3). "
            "Re-export it as a standard avc1 MP4. " + _REENCODE_HINT
        )
    pixel_format = video.get("pix_fmt")
    if pixel_format != "yuv420p":
        raise Rejected(
            f"The pixel format is {pixel_format or 'unknown'}. Only 8-bit "
            "yuv420p is accepted. " + _REENCODE_HINT
        )
    profile = video.get("profile")
    if profile not in VIDEO_PROFILES:
        raise Rejected(
            f"The H.264 profile is {profile or 'unknown'}. Use Constrained "
            "Baseline, Main or High. " + _REENCODE_HINT
        )
    level = video.get("level")
    if type(level) is not int or level <= 0:
        raise Rejected("The H.264 level is not reported. " + _REENCODE_HINT)
    if level > MAX_H264_LEVEL:
        raise Rejected(
            f"The H.264 level is {level // 10}.{level % 10}. The limit is "
            f"{MAX_H264_LEVEL // 10}.{MAX_H264_LEVEL % 10}. " + _REENCODE_HINT
        )

    width, height = video.get("width"), video.get("height")
    if type(width) is not int or type(height) is not int or width < 2 or height < 2:
        raise Rejected(_UNREADABLE)
    rotation = 0
    for datum in video.get("side_data_list") or []:
        if isinstance(datum, dict) and datum.get("side_data_type") == "Display Matrix":
            reported_rotation = datum.get("rotation")
            rotation = reported_rotation if type(reported_rotation) is int else 0
    if rotation % 180 != 0:
        width, height = height, width
    if max(width, height) > MAX_VIDEO_LONG_EDGE or min(width, height) > MAX_VIDEO_SHORT_EDGE:
        raise Rejected(
            f"The video is {width}x{height}. The limit is {MAX_VIDEO_LONG_EDGE}x"
            f"{MAX_VIDEO_SHORT_EDGE} in either orientation. " + _REENCODE_HINT
        )

    frame_rate = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    if frame_rate is None:
        raise Rejected("The frame rate is not reported. " + _REENCODE_HINT)
    if frame_rate > MAX_VIDEO_FPS + 0.01:
        raise Rejected(
            f"The frame rate is {frame_rate:g} fps. The limit is {MAX_VIDEO_FPS:g}. "
            + _REENCODE_HINT
        )

    container = document.get("format")
    if not isinstance(container, dict):
        container = {}
    seconds = _number(container.get("duration"))
    if seconds is None:
        seconds = _number(video.get("duration"))
    if seconds is None:
        raise Rejected("The video duration is not reported. Re-export the file.")
    duration_ms = round(seconds * 1000)
    if duration_ms < MIN_VIDEO_DURATION_MS:
        raise Rejected("The video is shorter than 1 second; use a longer clip.")
    if duration_ms > MAX_VIDEO_DURATION_MS:
        raise Rejected(
            f"The video is {duration_ms / 60000:.1f} minutes. The limit is "
            f"{MAX_VIDEO_DURATION_MS // 60000} minutes; trim it first."
        )

    codec_string = video.get("mime_codec_string")
    if not isinstance(codec_string, str) or len(codec_string) != 11 or not codec_string.startswith("avc1."):
        raise Rejected("The codec string is not reported. " + _REENCODE_HINT)
    bitrate = _number(container.get("bit_rate"))
    if bitrate is None:
        size = _number(container.get("size"))
        bitrate = size * 8 / seconds if size else None
    if bitrate is None:
        raise Rejected("The video bitrate is not reported. Re-export the file.")

    audio_index = None
    for stream in streams:
        if stream.get("codec_type") == "audio" and stream.get("codec_name") in _KEPT_AUDIO:
            audio_index = stream.get("index")
            break
    video_index = video.get("index")
    if type(video_index) is not int or (audio_index is not None and type(audio_index) is not int):
        raise Rejected(_UNREADABLE)

    facts = {
        "intrinsicWidth": width,
        "intrinsicHeight": height,
        "durationMs": duration_ms,
        "codec": "avc1." + codec_string[5:].upper(),
        "profile": profile,
        "level": f"{level // 10}.{level % 10}",
        "pixelFormat": pixel_format,
        "frameRate": round(frame_rate, 3),
        "bitrate": int(round(bitrate)),
        "faststart": False,
        "audio": audio_index is not None,
    }
    return facts, video_index, audio_index


# ---------------------------------------------------------------------------
# remux, poster, objects
# ---------------------------------------------------------------------------


def _remux(source: str, target: str, video_index: int, audio_index: int | None, job_dir: str) -> None:
    argv = [
        "ffmpeg", "-v", "error", "-nostdin", "-threads", "1",
        "-protocol_whitelist", "file", "-f", "mov", "-i", f"file:{source}",
        "-map", f"0:{video_index}",
    ]
    if audio_index is not None:
        argv += ["-map", f"0:{audio_index}"]
    argv += [
        "-c", "copy", "-map_metadata", "-1", "-map_chapters", "-1", "-xerror",
        "-fflags", "+bitexact", "-movflags", "+faststart", "-f", "mp4", "-y", target,
    ]
    _run(argv, job_dir, "remux")


def _poster_frame(source: str, target: str, duration_ms: int, job_dir: str) -> None:
    # One decoded frame, single-threaded: the address-space limit leaves no
    # room for the default decoder and filter thread pools.
    for position in (min(1.0, duration_ms / 10000), 0.0):
        argv = [
            "ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
            "-protocol_whitelist", "file", "-f", "mov", "-ss", f"{position:.3f}",
            "-i", f"file:{source}", "-threads", "1", "-map", "0:v:0", "-frames:v", "1",
            "-c:v", "png", "-compression_level", "1", "-f", "image2", "-y", target,
        ]
        try:
            _run(argv, job_dir, "poster")
        except Rejected:
            continue
        if os.path.exists(target) and os.path.getsize(target) > 0:
            return
    raise Rejected("A poster frame could not be decoded from the video. " + _REENCODE_HINT)


def _fsync_file(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _adopt(path: str, job_dir: str, suffix: str, limit: int) -> tuple[str, str, int]:
    """Hash a finished file and rename it to its content name in ``job_dir``."""
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            total += len(chunk)
            if total > limit:
                raise Rejected("The processed video is larger than the 250 MiB limit.")
            digest.update(chunk)
    _fsync_file(path)
    name = digest.hexdigest() + suffix
    os.replace(path, os.path.join(job_dir, name))
    _fsync_dir(job_dir)
    return name, digest.hexdigest(), total


def _source_file(path: str) -> str:
    absolute = os.path.abspath(os.fspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as error:
        raise Rejected("The source file is missing or unreadable.") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Rejected("The source is not a regular file; pass the real file path.")
    if info.st_size > MAX_VIDEO_BYTES:
        raise Rejected(
            f"The source is larger than the {MAX_VIDEO_BYTES // _MIB} MiB limit; "
            "upload a smaller video."
        )
    return absolute


def ingest(source_path: str, job_dir: str) -> dict[str, Any]:
    """Inspect, remux and publish-prepare one video; return the success payload."""
    _check_job_dir(job_dir)
    source = _source_file(source_path)
    with open(source, "rb") as handle:
        sniff(handle.read(16))
    scan_boxes(source)
    facts, video_index, audio_index = facts_from_probe(_probe(source, job_dir))

    remuxed = os.path.join(job_dir, "remux.mp4")
    _remux(source, remuxed, video_index, audio_index, job_dir)
    if os.path.getsize(remuxed) > MAX_VIDEO_BYTES:
        raise Rejected("The processed video is larger than the 250 MiB limit.")
    faststart = scan_boxes(remuxed)
    if not faststart:
        raise Rejected(_UNREADABLE)
    final, _, _ = facts_from_probe(_probe(remuxed, job_dir, "final"))
    final["faststart"] = True

    frame = os.path.join(job_dir, "frame.png")
    _poster_frame(remuxed, frame, final["durationMs"], job_dir)
    with Image.open(frame) as picture:
        picture.load()
        rgb = picture.convert("RGB")
    thumb_size = _fit(rgb.size, RENDITION_EDGES[2])
    if thumb_size != rgb.size:
        rgb = rgb.resize(thumb_size, Image.Resampling.LANCZOS)
    poster_path = os.path.join(job_dir, "poster.jpg")
    with open(poster_path, "wb") as handle:
        handle.write(_encode_jpeg(rgb, THUMBNAIL_QUALITY))
    os.unlink(frame)

    video_name, video_digest, video_bytes = _adopt(remuxed, job_dir, ".mp4", MAX_VIDEO_BYTES)
    poster_name, poster_digest, poster_bytes = _adopt(poster_path, job_dir, ".jpg", 10 * _MIB)
    return {
        "ok": True,
        "pipeline_version": VIDEO_PIPELINE_VERSION,
        "objects": [
            {
                "role": "video", "filename": video_name, "sha256": video_digest,
                "bytes": video_bytes, "width": final["intrinsicWidth"],
                "height": final["intrinsicHeight"], "mime": VIDEO_MIME,
            },
            {
                "role": "thumbnail", "filename": poster_name, "sha256": poster_digest,
                "bytes": poster_bytes, "width": rgb.width, "height": rgb.height,
                "mime": "image/jpeg",
            },
        ],
        "video": final,
    }


# ---------------------------------------------------------------------------
# process entry point
# ---------------------------------------------------------------------------


def _apply_video_limits() -> None:
    """Cap any file a child tool can write at the video ceiling plus headroom."""
    if resource is None:
        return
    cap = MAX_VIDEO_BYTES + 16 * _MIB
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print(
            "usage: python -m tabletwall.video <source_path> <job_dir> <result_path>",
            file=sys.stderr,
        )
        return 2
    source_path, job_dir, result_path = args
    try:
        _apply_limits()
        _apply_video_limits()
        _check_result_path(result_path)
    except (OSError, ValueError) as error:
        print(f"video: cannot write a result: {error}", file=sys.stderr)
        return 1
    try:
        payload = ingest(source_path, job_dir)
    except Rejected as rejection:
        payload = {"ok": False, "error": rejection.reason}
    except MemoryError:
        payload = {"ok": False, "error": "The video needs more memory than the worker limit allows."}
    try:
        _write_result(result_path, payload)
    except OSError as error:
        print(f"video: cannot write a result: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
