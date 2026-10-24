"""R1 image normalization worker, run as a bounded subprocess.

Usage::

    python -m tabletwall.media_worker <source_path> <job_dir> <result_path>

The worker reads one JPEG or PNG, bakes in EXIF orientation, converts to
opaque sRGB, strips every source metadata field, and writes four content-
addressed JPEG objects (master, display, fallback, thumbnail) into
``job_dir``. It then writes a JSON result last, so a result implies the
objects it names are present and fsynced. A clean rejection is still a
written result with ``ok: false`` and exit status 0; a nonzero status means
the worker could not write a result at all.

Source dimensions in the result are upright dimensions: the size after EXIF
orientation has been applied.
"""

import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import warnings
from io import BytesIO

from PIL import Image, ImageCms, ImageOps

from tabletwall.media_limits import (
    JPEG_QUALITY,
    MAX_MASTER_EDGE,
    MAX_MASTER_PIXELS,
    MAX_OBJECT_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_PIXELS,
    PIPELINE_VERSION,
    RENDITION_EDGES,
    THUMBNAIL_QUALITY,
    WORKER_CPU_SECONDS,
    WORKER_MEMORY_BYTES,
)

try:
    import resource
except ImportError:  # pragma: no cover - the server runs on POSIX
    resource = None

warnings.simplefilter("error", Image.DecompressionBombWarning)

_FORMATS = ("JPEG", "PNG")
_EXIF_ORIENTATION = 0x0112
_ROTATING_ORIENTATIONS = (2, 3, 4, 5, 6, 7, 8)
_READ_CHUNK = 1 << 20
_RESAMPLE = Image.Resampling.LANCZOS
_MASTER_QUALITIES = tuple(range(JPEG_QUALITY, 0, -5))[:7]
_TEMP_PREFIX = ".media-worker-"
_MIB = 1024 * 1024

_SOURCE_UNREADABLE = (
    "The source file is missing or unreadable; check that it still exists."
)
_SOURCE_TOO_LARGE = (
    f"The source is larger than the {MAX_SOURCE_BYTES // _MIB} MiB limit; "
    "upload a smaller image."
)
_DECODE_FAILED = (
    "The image could not be decoded; re-export it as a valid JPEG or PNG."
)


class Rejected(Exception):
    """A clean, actionable refusal: the source or job directory is unusable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _limit_bytes(value: int) -> str:
    return f"{value // _MIB} MiB"


def _apply_limits() -> None:
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (WORKER_CPU_SECONDS, WORKER_CPU_SECONDS))


def _read_source(path: str) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Rejected(_SOURCE_UNREADABLE) from error
    if stat.S_ISLNK(info.st_mode):
        raise Rejected("The source is a symbolic link; pass the real file path instead.")
    if not stat.S_ISREG(info.st_mode):
        raise Rejected("The source is not a regular file; supply a JPEG or PNG file.")
    if info.st_size > MAX_SOURCE_BYTES:
        raise Rejected(_SOURCE_TOO_LARGE)

    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise Rejected(_SOURCE_UNREADABLE) from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Rejected("The source is not a regular file; supply a JPEG or PNG file.")
        if info.st_size > MAX_SOURCE_BYTES:
            raise Rejected(_SOURCE_TOO_LARGE)
        chunks: list[bytes] = []
        remaining = MAX_SOURCE_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(_READ_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    except OSError as error:
        raise Rejected(_SOURCE_UNREADABLE) from error
    finally:
        os.close(fd)

    if len(data) > MAX_SOURCE_BYTES:
        raise Rejected(_SOURCE_TOO_LARGE)
    return data


def _check_job_dir(job_dir: str) -> None:
    try:
        info = os.lstat(job_dir)
    except OSError as error:
        raise Rejected(
            "The job directory does not exist; create it before starting the worker."
        ) from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise Rejected(
            "The job directory is not a real directory; check the worker configuration."
        )


def _check_result_path(result_path: str) -> None:
    if os.path.lexists(result_path):
        info = os.lstat(result_path)
        if stat.S_ISLNK(info.st_mode):
            raise OSError("result path is a symbolic link")
        if not stat.S_ISREG(info.st_mode):
            raise OSError("result path is not a regular file")
    parent = os.path.dirname(os.path.abspath(result_path))
    info = os.lstat(parent)
    if not stat.S_ISDIR(info.st_mode):
        raise OSError("result path parent is not a real directory")


def _inspect(data: bytes) -> tuple[str, int, int, int | None]:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            animated = bool(getattr(image, "is_animated", False))
    except Exception as error:
        raise Rejected(_DECODE_FAILED) from error

    if image_format not in _FORMATS:
        raise Rejected(
            f"The image format is {image_format or 'unrecognised'}; "
            "only still JPEG and PNG images are accepted."
        )
    if animated:
        raise Rejected("The image is animated; supply a single-frame JPEG or PNG.")
    if width < 1 or height < 1:
        raise Rejected(
            "The image has no usable dimensions; re-export it as a valid JPEG or PNG."
        )
    if width * height > MAX_SOURCE_PIXELS:
        raise Rejected(
            f"The image exceeds the {MAX_SOURCE_PIXELS // 1_000_000} megapixel limit; "
            "downscale it and try again."
        )

    try:
        with Image.open(BytesIO(data)) as image:
            orientation = image.getexif().get(_EXIF_ORIENTATION)
    except Exception as error:
        raise Rejected(
            "The image metadata could not be read; re-export it as a valid JPEG or PNG."
        ) from error
    return image_format, width, height, orientation


def _flatten_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _has_transparency(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA", "PA", "RGBa", "La") or "transparency" in image.info


def _to_srgb(image: Image.Image) -> tuple[Image.Image, bool]:
    profile = image.info.get("icc_profile")
    if not profile:
        if image.mode == "RGB":
            return image, False
        return image.convert("RGB"), False
    try:
        source = ImageCms.ImageCmsProfile(BytesIO(profile))
        target = ImageCms.createProfile("sRGB")
        converted = ImageCms.profileToProfile(
            image, source, target, outputMode="RGB", renderingIntent=0
        )
    except Exception as error:
        raise Rejected(
            "The image's ICC profile could not be converted to sRGB; "
            "re-export it in sRGB or without a profile."
        ) from error
    return converted, True


def _normalize(image: Image.Image) -> tuple[Image.Image, bool, bool]:
    ImageOps.exif_transpose(image, in_place=True)
    alpha_flattened = _has_transparency(image)
    working = _flatten_alpha(image) if alpha_flattened else image
    if working.mode not in ("RGB", "CMYK", "L"):
        working = working.convert("RGB")
    rgb, icc_converted = _to_srgb(working)
    rgb.info.clear()
    return rgb, icc_converted, alpha_flattened


def _fit(size: tuple[int, int], edge: int) -> tuple[int, int]:
    width, height = size
    longest = max(width, height)
    if longest <= edge:
        return width, height
    scale = edge / longest
    return max(1, int(width * scale)), max(1, int(height * scale))


def _master_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = _fit(size, MAX_MASTER_EDGE)
    pixels = width * height
    if pixels <= MAX_MASTER_PIXELS:
        return width, height
    scale = math.sqrt(MAX_MASTER_PIXELS / pixels)
    return max(1, int(width * scale)), max(1, int(height * scale))


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=quality,
        optimize=True,
        exif=b"",
        icc_profile=None,
        comment=None,
        xmp=None,
    )
    return buffer.getvalue()


def _encode_master(image: Image.Image) -> bytes:
    for quality in _MASTER_QUALITIES:
        data = _encode_jpeg(image, quality)
        if len(data) <= MAX_OBJECT_BYTES:
            return data
    raise Rejected(
        f"The master still exceeds the {_limit_bytes(MAX_OBJECT_BYTES)} object limit "
        "at the lowest quality; downscale the source."
    )


def _encode_objects(clean: Image.Image) -> list[tuple[str, int, int, bytes]]:
    master_size = _master_size(clean.size)
    master = clean if master_size == clean.size else clean.resize(master_size, _RESAMPLE)
    encoded = [("master", master.width, master.height, _encode_master(master))]

    for role, edge in zip(("display", "fallback", "thumbnail"), RENDITION_EDGES):
        size = _fit(clean.size, edge)
        rendition = clean if size == clean.size else clean.resize(size, _RESAMPLE)
        quality = THUMBNAIL_QUALITY if role == "thumbnail" else JPEG_QUALITY
        data = _encode_jpeg(rendition, quality)
        if len(data) > MAX_OBJECT_BYTES:
            raise Rejected(
                f"The {role} rendition exceeds the "
                f"{_limit_bytes(MAX_OBJECT_BYTES)} object limit; downscale the source."
            )
        encoded.append((role, rendition.width, rendition.height, data))
    return encoded


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _store(job_dir: str, data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    filename = digest + ".jpg"
    final_path = os.path.join(job_dir, filename)

    try:
        info = os.lstat(final_path)
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise Rejected(
                "A file in the job directory does not match its hash name; "
                "use a clean job directory."
            )
        try:
            with open(final_path, "rb") as handle:
                existing = handle.read(len(data) + 1)
        except OSError as error:
            raise Rejected(
                "An existing object in the job directory could not be read; "
                "use a clean job directory."
            ) from error
        if existing != data:
            raise Rejected(
                "A file in the job directory does not match its hash name; "
                "use a clean job directory."
            )
        return filename, digest

    fd, temporary = tempfile.mkstemp(dir=job_dir, prefix=_TEMP_PREFIX, suffix=".jpg")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    _fsync_dir(job_dir)
    return filename, digest


def process(source_path: str, job_dir: str) -> dict:
    """Normalize one source into new objects and return the success payload."""
    _check_job_dir(job_dir)
    data = _read_source(source_path)
    image_format, _, _, orientation = _inspect(data)

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            clean, icc_converted, alpha_flattened = _normalize(image)
            objects = _encode_objects(clean)
            source_width, source_height = clean.size
    except Rejected:
        raise
    except MemoryError as error:
        raise Rejected(
            "The image needs more memory than the worker limit allows; downscale it and try again."
        ) from error
    except Exception as error:
        raise Rejected(_DECODE_FAILED) from error

    records = []
    for role, width, height, object_data in objects:
        filename, digest = _store(job_dir, object_data)
        records.append(
            {
                "role": role,
                "filename": filename,
                "sha256": digest,
                "bytes": len(object_data),
                "width": width,
                "height": height,
                "mime": "image/jpeg",
            }
        )

    return {
        "ok": True,
        "pipeline_version": PIPELINE_VERSION,
        "source": {
            "format": image_format,
            "width": source_width,
            "height": source_height,
            "orientation_applied": orientation in _ROTATING_ORIENTATIONS,
            "icc_converted": icc_converted,
            "alpha_flattened": alpha_flattened,
        },
        "objects": records,
    }


def _write_result(result_path: str, payload: dict) -> None:
    parent = os.path.dirname(os.path.abspath(result_path))
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(dir=parent, prefix=_TEMP_PREFIX, suffix=".json")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, result_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    _fsync_dir(parent)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print(
            "usage: python -m tabletwall.media_worker <source_path> <job_dir> <result_path>",
            file=sys.stderr,
        )
        return 2
    source_path, job_dir, result_path = args

    try:
        _apply_limits()
        _check_result_path(result_path)
    except (OSError, ValueError) as error:
        print(f"media_worker: cannot write a result: {error}", file=sys.stderr)
        return 1

    try:
        payload = process(source_path, job_dir)
    except Rejected as rejection:
        payload = {"ok": False, "error": rejection.reason}

    try:
        _write_result(result_path, payload)
    except OSError as error:
        print(f"media_worker: cannot write a result: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
