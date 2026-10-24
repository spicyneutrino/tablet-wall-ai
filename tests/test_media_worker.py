"""R1 image normalization worker (``tabletwall.media_worker``).

Every test drives the real subprocess with the CLI contract the server uses,
so resource limits, exit status, and the on-disk result file are all part of
the evidence rather than being mocked.
"""

import hashlib
import io
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from tabletwall.media_limits import (
    MAX_MASTER_EDGE,
    MAX_MASTER_PIXELS,
    MAX_OBJECT_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_PIXELS,
    PIPELINE_VERSION,
    RENDITION_EDGES,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ORIENTATION_TAG = 0x0112


def encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def run_worker(
    tmp_path: Path,
    source: Path,
    *,
    job_dir: Path | None = None,
    result_path: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict, Path]:
    if job_dir is None:
        job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    if result_path is None:
        result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tabletwall.media_worker",
            str(source),
            str(job_dir),
            str(result_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert completed.stdout == ""
    payload = json.loads(result_path.read_text())
    return completed, payload, job_dir


def write_source(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def objects_by_role(payload: dict) -> dict[str, dict]:
    return {entry["role"]: entry for entry in payload["objects"]}


def png_header_only(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")


def animated_png() -> bytes:
    frames = [Image.new("RGB", (16, 12), color) for color in ("red", "green", "blue")]
    return encode(frames[0], "PNG", save_all=True, append_images=frames[1:])


def animated_gif() -> bytes:
    frames = [Image.new("RGB", (16, 12), color) for color in ("red", "green")]
    return encode(frames[0], "GIF", save_all=True, append_images=frames[1:])


class TestSuccess:
    def test_exif_orientation_is_baked_in_and_metadata_is_stripped(self, tmp_path):
        stored = Image.new("RGB", (48, 32))
        stored.paste("red", (0, 0, 24, 16))
        stored.paste("blue", (24, 0, 48, 16))
        stored.paste("green", (0, 16, 24, 32))
        stored.paste("yellow", (24, 16, 48, 32))
        exif = Image.Exif()
        exif[ORIENTATION_TAG] = 6
        exif[0x010F] = "SecretCameraMake"
        source = write_source(
            tmp_path, "phone.jpg", encode(stored, "JPEG", quality=95, exif=exif)
        )

        completed, payload, job_dir = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is True
        assert payload["pipeline_version"] == PIPELINE_VERSION
        source_info = payload["source"]
        assert source_info["format"] == "JPEG"
        assert (source_info["width"], source_info["height"]) == (32, 48)
        assert source_info["orientation_applied"] is True
        assert source_info["alpha_flattened"] is False
        assert source_info["icc_converted"] is False

        objects = objects_by_role(payload)
        assert set(objects) == {"master", "display", "fallback", "thumbnail"}
        master = objects["master"]
        assert (master["width"], master["height"]) == (32, 48)
        for entry in objects.values():
            path = job_dir / entry["filename"]
            data = path.read_bytes()
            assert path.is_file()
            assert len(data) == entry["bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            assert entry["mime"] == "image/jpeg"
            assert entry["filename"] == entry["sha256"] + ".jpg"
            assert b"SecretCameraMake" not in data
            with Image.open(path) as image:
                assert image.format == "JPEG"
                assert image.mode == "RGB"
                assert not image.getexif()
                assert "icc_profile" not in image.info
                assert "exif" not in image.info

        with Image.open(source) as original:
            expected = ImageOps.exif_transpose(original).convert("RGB")
        with Image.open(job_dir / master["filename"]) as output:
            assert output.size == expected.size
            for point in ((0, 0), (31, 0), (0, 47), (31, 47), (16, 24)):
                assert output.getpixel(point) == pytest.approx(
                    expected.getpixel(point), abs=30
                )

    def test_identical_source_bytes_produce_identical_hashes(self, tmp_path):
        source = write_source(
            tmp_path, "photo.jpg", encode(Image.new("RGB", (64, 40), "orange"), "JPEG")
        )

        _, first, _ = run_worker(tmp_path, source, job_dir=tmp_path / "first")
        _, second, _ = run_worker(tmp_path, source, job_dir=tmp_path / "second")

        def shape(payload: dict) -> list[tuple]:
            return [
                (entry["role"], entry["sha256"], entry["bytes"], entry["width"], entry["height"])
                for entry in payload["objects"]
            ]

        assert shape(first) == shape(second)

    def test_existing_objects_are_reused_not_rewritten(self, tmp_path):
        source = write_source(
            tmp_path, "photo.jpg", encode(Image.new("RGB", (30, 20), "purple"), "JPEG")
        )
        job_dir = tmp_path / "job"

        _, first, _ = run_worker(tmp_path, source, job_dir=job_dir)
        before = {path.name: path.stat().st_mtime_ns for path in job_dir.iterdir()}
        _, second, _ = run_worker(tmp_path, source, job_dir=job_dir)

        assert [entry["filename"] for entry in first["objects"]] == [
            entry["filename"] for entry in second["objects"]
        ]
        assert {path.name: path.stat().st_mtime_ns for path in job_dir.iterdir()} == before
        assert len({entry["filename"] for entry in first["objects"]}) == len(
            list(job_dir.iterdir())
        )

    def test_rgba_png_is_flattened_onto_white(self, tmp_path):
        image = Image.new("RGBA", (40, 20), (255, 0, 0, 0))
        image.paste((0, 255, 0, 255), (20, 0, 40, 20))
        source = write_source(tmp_path, "alpha.png", encode(image, "PNG"))

        completed, payload, job_dir = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is True
        assert payload["source"]["alpha_flattened"] is True
        assert payload["source"]["format"] == "PNG"
        for entry in payload["objects"]:
            with Image.open(job_dir / entry["filename"]) as output:
                assert output.format == "JPEG"
                assert output.mode == "RGB"
                if entry["role"] == "master":
                    assert output.getpixel((0, 0)) == pytest.approx((255, 255, 255), abs=2)
                    red, green, blue = output.getpixel((39, 0))
                    assert green > 240 and red < 15 and blue < 15

    def test_cmyk_jpeg_converts_through_rgb(self, tmp_path):
        image = Image.new("CMYK", (32, 24), (0, 0, 0, 0))
        image.paste((200, 30, 30, 10), (16, 0, 32, 24))
        source = write_source(tmp_path, "print.jpg", encode(image, "JPEG", quality=95))

        completed, payload, job_dir = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is True, payload
        assert payload["source"]["format"] == "JPEG"
        assert payload["source"]["icc_converted"] is False
        for entry in payload["objects"]:
            with Image.open(job_dir / entry["filename"]) as output:
                assert output.format == "JPEG"
                assert output.mode == "RGB"

    def test_renditions_never_upscale(self, tmp_path):
        source = write_source(
            tmp_path, "tiny.jpg", encode(Image.new("RGB", (64, 40), "navy"), "JPEG")
        )

        _, payload, _ = run_worker(tmp_path, source)

        for entry in payload["objects"]:
            assert (entry["width"], entry["height"]) == (64, 40)


class TestMasterCeilings:
    @pytest.mark.parametrize(
        ("size", "expected_master"),
        [
            ((6000, 1000), (MAX_MASTER_EDGE, 682)),
            ((3000, 3000), (3000, 3000)),
        ],
    )
    def test_master_long_edge_and_pixel_ceilings(self, tmp_path, size, expected_master):
        source = write_source(
            tmp_path, "large.jpg", encode(Image.new("RGB", size, "teal"), "JPEG", quality=95)
        )
        job_dir = tmp_path / "job"

        completed, payload, _ = run_worker(tmp_path, source, job_dir=job_dir)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is True, payload
        master = objects_by_role(payload)["master"]
        assert max(master["width"], master["height"]) <= MAX_MASTER_EDGE
        assert master["width"] * master["height"] <= MAX_MASTER_PIXELS
        assert master["bytes"] <= MAX_OBJECT_BYTES
        assert (master["width"], master["height"]) == expected_master
        with Image.open(job_dir / master["filename"]) as output:
            assert output.size == expected_master

    def test_pixel_ceiling_binds_below_the_edge_ceiling(self, tmp_path):
        source = write_source(
            tmp_path, "square.jpg", encode(Image.new("RGB", (4096, 4096), "olive"), "JPEG")
        )

        completed, payload, job_dir = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is True, payload
        master = objects_by_role(payload)["master"]
        assert max(master["width"], master["height"]) <= MAX_MASTER_EDGE
        assert master["width"] * master["height"] <= MAX_MASTER_PIXELS
        with Image.open(job_dir / master["filename"]) as output:
            assert output.size == (master["width"], master["height"])

    def test_rendition_edges_are_enforced(self, tmp_path):
        source = write_source(
            tmp_path, "wide.jpg", encode(Image.new("RGB", (6000, 1000), "maroon"), "JPEG")
        )

        _, payload, _ = run_worker(tmp_path, source)

        objects = objects_by_role(payload)
        for role, edge in zip(("display", "fallback", "thumbnail"), RENDITION_EDGES):
            entry = objects[role]
            assert max(entry["width"], entry["height"]) == edge
            assert entry["bytes"] <= MAX_OBJECT_BYTES
        assert payload["source"]["width"] * payload["source"]["height"] <= MAX_SOURCE_PIXELS


class TestCleanRejections:
    def test_animated_png_is_rejected(self, tmp_path):
        source = write_source(tmp_path, "animated.png", animated_png())

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "animated" in payload["error"]
        assert set(payload) == {"ok", "error"}

    def test_animated_gif_is_rejected(self, tmp_path):
        source = write_source(tmp_path, "animated.gif", animated_gif())

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "GIF" in payload["error"]

    @pytest.mark.parametrize(
        "data",
        [
            b"this is not an image",
            b"\x89PNG\r\n\x1a\nnot really a png",
            b"\xff\xd8\xff\xe0truncated jpeg",
        ],
    )
    def test_malformed_bytes_are_rejected_without_a_traceback(self, tmp_path, data):
        source = write_source(tmp_path, "bad.bin", data)

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert payload["error"].endswith(".")
        assert "decoded" in payload["error"]
        assert "Traceback" not in completed.stderr

    def test_header_over_the_pixel_limit_is_rejected_before_decoding(self, tmp_path):
        source = write_source(tmp_path, "huge.png", png_header_only(8000, 8000))
        assert 8000 * 8000 > MAX_SOURCE_PIXELS

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "megapixel" in payload["error"]

    def test_source_over_the_byte_limit_is_rejected(self, tmp_path):
        source = tmp_path / "oversized.jpg"
        with source.open("wb") as handle:
            handle.truncate(MAX_SOURCE_BYTES + 1)

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "larger than" in payload["error"]

    def test_symlinked_source_is_rejected(self, tmp_path):
        real = write_source(
            tmp_path, "real.jpg", encode(Image.new("RGB", (16, 16), "red"), "JPEG")
        )
        link = tmp_path / "linked.jpg"
        link.symlink_to(real)

        completed, payload, _ = run_worker(tmp_path, link)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "symbolic link" in payload["error"]

    def test_symlinked_job_dir_is_rejected(self, tmp_path):
        source = write_source(
            tmp_path, "photo.jpg", encode(Image.new("RGB", (16, 16), "red"), "JPEG")
        )
        real_job = tmp_path / "real-job"
        real_job.mkdir()
        link = tmp_path / "job"
        link.symlink_to(real_job)

        completed, payload, _ = run_worker(tmp_path, source, job_dir=link)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "job directory" in payload["error"]
        assert list(real_job.iterdir()) == []

    def test_corrupt_icc_profile_is_rejected_actionably(self, tmp_path):
        source = write_source(
            tmp_path,
            "profile.png",
            encode(Image.new("RGB", (24, 24), "green"), "PNG", icc_profile=b"not an ICC profile"),
        )

        completed, payload, _ = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert "ICC" in payload["error"]
        assert "sRGB" in payload["error"]


class TestResultAndPaths:
    def test_result_json_shape_and_filenames_match_files(self, tmp_path):
        source = write_source(
            tmp_path, "photo.jpg", encode(Image.new("RGB", (20, 10), "silver"), "JPEG")
        )
        result_path = tmp_path / "nested" / "result.json"
        result_path.parent.mkdir()

        completed, payload, job_dir = run_worker(
            tmp_path, source, result_path=result_path
        )

        assert completed.returncode == 0, completed.stderr
        assert set(payload) == {"ok", "pipeline_version", "source", "objects"}
        assert set(payload["source"]) == {
            "format",
            "width",
            "height",
            "orientation_applied",
            "icc_converted",
            "alpha_flattened",
        }
        assert [entry["role"] for entry in payload["objects"]] == [
            "master",
            "display",
            "fallback",
            "thumbnail",
        ]
        for entry in payload["objects"]:
            assert set(entry) == {
                "role",
                "filename",
                "sha256",
                "bytes",
                "width",
                "height",
                "mime",
            }
            assert (job_dir / entry["filename"]).is_file()
        assert sorted(path.name for path in job_dir.iterdir()) == sorted(
            {item["filename"] for item in payload["objects"]}
        )

    def test_rejection_also_writes_result_json(self, tmp_path):
        source = write_source(tmp_path, "bad.jpg", b"nope")

        completed, payload, job_dir = run_worker(tmp_path, source)

        assert completed.returncode == 0, completed.stderr
        assert payload["ok"] is False
        assert set(payload) == {"ok", "error"}
        assert list(job_dir.iterdir()) == []

    def test_symlinked_result_path_fails_without_a_result(self, tmp_path):
        source = write_source(
            tmp_path, "photo.jpg", encode(Image.new("RGB", (16, 16), "red"), "JPEG")
        )
        target = tmp_path / "elsewhere.json"
        target.write_text("untouched")
        result_path = tmp_path / "result.json"
        result_path.symlink_to(target)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tabletwall.media_worker",
                str(source),
                str(job_dir),
                str(result_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=25,
        )

        assert completed.returncode != 0
        assert completed.stdout == ""
        assert "result" in completed.stderr
        assert target.read_text() == "untouched"
