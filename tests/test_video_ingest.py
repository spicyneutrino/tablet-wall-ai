"""Video ingest (R4): the accept and reject matrix, losslessness, and tool safety.

``video.ingest`` is the whole worker minus the process wrapper, so most cases
call it in-process on a temp job directory. One case runs the real
``python -m tabletwall.video`` entry point under the worker's rlimits.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tabletwall import video
from tabletwall.media_worker import Rejected
from video_fixtures import (  # noqa: F401  (make_video and video_dir are fixtures)
    needs_ffmpeg, make_video, packet_md5, probe, video_dir,
)

pytestmark = needs_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def job(tmp_path) -> Path:
    directory = tmp_path / "job"
    directory.mkdir()
    return directory


def ingest(path: Path, job: Path) -> dict:
    return video.ingest(str(path), str(job))


def objects_by_role(result: dict) -> dict[str, dict]:
    return {entry["role"]: entry for entry in result["objects"]}


class TestAccepted:
    def test_baseline_h264_mp4_is_described_for_the_contract_descriptor(self, make_video, job):
        result = ingest(make_video("baseline.mp4"), job)
        assert result["ok"] is True
        assert result["video"] == {
            "intrinsicWidth": 320, "intrinsicHeight": 240, "durationMs": 2000,
            "codec": "avc1.42C01F", "profile": "Constrained Baseline", "level": "3.1",
            "pixelFormat": "yuv420p", "frameRate": 15.0, "bitrate": result["video"]["bitrate"],
            "faststart": True, "audio": True,
        }
        assert result["video"]["bitrate"] > 0
        objects = objects_by_role(result)
        assert objects["video"]["mime"] == "video/mp4"
        assert objects["thumbnail"]["mime"] == "image/jpeg"
        assert (objects["video"]["width"], objects["video"]["height"]) == (320, 240)
        assert max(objects["thumbnail"]["width"], objects["thumbnail"]["height"]) <= 256
        for entry in objects.values():
            assert entry["filename"].startswith(entry["sha256"])
            assert (job / entry["filename"]).is_file()
        assert video.validate_facts(result["video"]) == result["video"]

    def test_a_non_faststart_file_is_remuxed_losslessly_to_faststart(self, make_video, job):
        source = make_video("nonfaststart.mp4")
        assert video.scan_boxes(str(source)) is False
        result = ingest(source, job)
        output = job / objects_by_role(result)["video"]["filename"]
        assert video.scan_boxes(str(output)) is True
        assert result["video"]["faststart"] is True
        assert packet_md5(output) == packet_md5(source)

    def test_an_already_faststart_file_is_still_normalized_and_verified(self, make_video, job):
        source = make_video("baseline.mp4")
        assert video.scan_boxes(str(source)) is True
        result = ingest(source, job)
        output = job / objects_by_role(result)["video"]["filename"]
        assert packet_md5(output) == packet_md5(source)
        assert packet_md5(output, "a:0") == packet_md5(source, "a:0")

    def test_quicktime_h264_is_normalized_to_mp4_and_unsupported_audio_is_dropped(
        self, make_video, job
    ):
        result = ingest(make_video("quicktime.mov"), job)
        output = job / objects_by_role(result)["video"]["filename"]
        assert probe(output)["format"]["format_name"].startswith("mov,mp4")
        assert output.read_bytes()[4:8] == b"ftyp"
        assert b"qt  " not in output.read_bytes()[:32]
        assert result["video"]["audio"] is False
        assert [s["codec_type"] for s in probe(output)["streams"]] == ["video"]

    def test_container_metadata_such_as_gps_is_stripped(self, make_video, job):
        source = make_video("metadata.mp4")
        assert b"SECRETTITLE" in source.read_bytes()
        result = ingest(source, job)
        output = (job / objects_by_role(result)["video"]["filename"]).read_bytes()
        assert b"SECRETTITLE" not in output
        assert b"51.5074" not in output

    def test_rotation_metadata_survives_and_the_intrinsic_size_is_the_displayed_size(
        self, make_video, job
    ):
        result = ingest(make_video("rotated.mp4"), job)
        assert (result["video"]["intrinsicWidth"], result["video"]["intrinsicHeight"]) == (360, 640)
        objects = objects_by_role(result)
        assert (objects["video"]["width"], objects["video"]["height"]) == (360, 640)
        assert objects["thumbnail"]["height"] > objects["thumbnail"]["width"]
        stream = probe(job / objects["video"]["filename"])["streams"][0]
        rotations = [d.get("rotation") for d in stream.get("side_data_list", [])]
        assert 90 in rotations

    def test_portrait_1080x1920_is_accepted_because_the_cap_is_per_edge(self, make_video, job):
        result = ingest(make_video("portrait.mp4"), job)
        assert (result["video"]["intrinsicWidth"], result["video"]["intrinsicHeight"]) == (1080, 1920)

    def test_the_largest_accepted_profile_is_1080p_level_4_1(self, make_video, job):
        result = ingest(make_video("hd.mp4"), job)
        assert result["video"]["level"] == "4.1"
        assert result["video"]["profile"] == "High"
        assert (result["video"]["intrinsicWidth"], result["video"]["intrinsicHeight"]) == (1920, 1080)


class TestRejected:
    @pytest.mark.parametrize(
        ("name", "fragment"),
        [
            ("hevc.mp4", "HEVC"),
            ("vp9.webm", "WebM or Matroska"),
            ("tenbit.mp4", "yuv420p10le"),
            ("oversize.mp4", "2560x1440"),
            ("level51.mp4", "level is 5.1"),
            ("fps120.mp4", "120 fps"),
            ("short.mp4", "shorter than 1 second"),
            ("long.mp4", "minutes"),
            ("audio.m4a", "no video"),
            ("truncated_moov_last.mp4", "truncated"),
            ("truncated_faststart.mp4", "truncated"),
            ("ffconcat.txt", "not an MP4"),
            ("playlist.m3u8", "HLS playlist"),
            ("garbage.bin", "not an MP4"),
        ],
    )
    def test_each_unsupported_file_gets_an_actionable_reason(self, make_video, job, name, fragment):
        with pytest.raises(Rejected) as refusal:
            ingest(make_video(name), job)
        reason = refusal.value.reason
        assert fragment in reason
        assert len(reason) > 40
        assert not list(job.glob("*.mp4")) and not list(job.glob("*.jpg"))

    def test_a_missing_or_symbolic_source_is_refused(self, tmp_path, job):
        with pytest.raises(Rejected):
            ingest(tmp_path / "absent.mp4", job)
        target = tmp_path / "real.bin"
        target.write_bytes(b"x")
        link = tmp_path / "link.mp4"
        link.symlink_to(target)
        with pytest.raises(Rejected, match="regular file"):
            ingest(link, job)

    def test_a_source_over_the_byte_cap_is_refused_before_any_tool_runs(
        self, make_video, job, monkeypatch
    ):
        monkeypatch.setattr(video, "MAX_VIDEO_BYTES", 100)

        def forbidden(*_args, **_kwargs):
            raise AssertionError("a tool ran for an oversize source")

        monkeypatch.setattr(subprocess, "run", forbidden)
        with pytest.raises(Rejected, match="larger than"):
            ingest(make_video("baseline.mp4"), job)

    def test_a_missing_ffmpeg_is_an_operator_facing_refusal(self, make_video, job, monkeypatch):
        monkeypatch.setenv("PATH", str(job))
        assert video.tools_available() is False
        with pytest.raises(Rejected, match="not installed"):
            ingest(make_video("baseline.mp4"), job)


class TestFactValidation:
    def test_the_parent_re_checks_the_worker_facts(self, make_video, job):
        facts = ingest(make_video("baseline.mp4"), job)["video"]
        for field, value in (
            ("durationMs", 600_001), ("durationMs", 999), ("faststart", False),
            ("pixelFormat", "yuv420p10le"), ("profile", "High 10"), ("frameRate", 61),
            ("audio", 1), ("bitrate", True), ("intrinsicWidth", 0),
        ):
            with pytest.raises(ValueError):
                video.validate_facts({**facts, field: value})
        with pytest.raises(ValueError):
            video.validate_facts({**facts, "extra": 1})
        with pytest.raises(ValueError):
            video.validate_facts(None)


class TestToolSafety:
    def test_every_tool_call_is_a_fixed_argv_that_reads_only_a_local_mov(
        self, make_video, job, monkeypatch
    ):
        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(argv, *args, **kwargs):
            calls.append(list(argv))
            assert kwargs.get("shell") in (None, False)
            return real_run(argv, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", spy)
        ingest(make_video("baseline.mp4"), job)

        assert [call[0] for call in calls] == ["ffprobe", "ffmpeg", "ffprobe", "ffmpeg"]
        for call in calls:
            assert call[call.index("-protocol_whitelist") + 1] == "file"
            assert call[call.index("-f") + 1] == "mov"
            inputs = [call[call.index("-i") + 1]] if "-i" in call else [call[-1]]
            assert all(item.startswith("file:/") for item in inputs)

    def test_a_url_or_concat_looking_filename_never_reaches_ffmpeg_as_a_protocol(
        self, make_video, tmp_path, monkeypatch
    ):
        shutil.copyfile(make_video("baseline.mp4"), tmp_path / "baseline.mp4")
        shutil.copyfile(make_video("high.mp4"), tmp_path / "high.mp4")
        hostile = tmp_path / "concat:baseline.mp4|high.mp4"
        shutil.copyfile(make_video("baseline.mp4"), hostile)
        url_like = tmp_path / "http:evil.example:8080-a.mp4"
        shutil.copyfile(make_video("baseline.mp4"), url_like)
        monkeypatch.chdir(tmp_path)

        calls: list[list[str]] = []
        real_run = subprocess.run

        def spy(argv, *args, **kwargs):
            calls.append(list(argv))
            return real_run(argv, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", spy)
        for index, name in enumerate((hostile.name, url_like.name)):
            work = tmp_path / f"job{index}"
            work.mkdir()
            result = video.ingest(name, str(work))  # relative, protocol-looking path
            assert result["ok"] is True

        for call in calls:
            reads = call[call.index("-i") + 1] if "-i" in call else call[-1]
            assert reads.startswith("file:/")
            assert not reads.startswith(("file:concat", "concat:", "http:"))

    def test_a_text_file_that_names_local_files_is_never_parsed_by_a_demuxer(
        self, make_video, job, monkeypatch
    ):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("ffprobe ran on a text file")

        monkeypatch.setattr(subprocess, "run", forbidden)
        for name in ("ffconcat.txt", "playlist.m3u8"):
            with pytest.raises(Rejected):
                ingest(make_video(name), job)


class TestBoxStructure:
    def test_a_trailing_partial_box_is_a_truncated_file(self, make_video, tmp_path):
        data = make_video("baseline.mp4").read_bytes()
        broken = tmp_path / "extra.mp4"
        broken.write_bytes(data + b"\x00\x00\x00\x20free")
        with pytest.raises(Rejected, match="truncated"):
            video.scan_boxes(str(broken))

    def test_an_mp4_with_no_moov_is_refused(self, tmp_path):
        broken = tmp_path / "nomoov.mp4"
        broken.write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
        with pytest.raises(Rejected, match="truncated"):
            video.scan_boxes(str(broken))


class TestWorkerProcess:
    def test_the_real_worker_entry_point_runs_1080p_under_the_rlimits(self, make_video, job):
        source = make_video("hd.mp4")
        result_path = job / "result.json"
        completed = subprocess.run(
            [sys.executable, "-m", "tabletwall.video", str(source), str(job), str(result_path)],
            cwd=ROOT, capture_output=True, timeout=120,
        )
        assert completed.returncode == 0, completed.stderr.decode()
        payload = json.loads(result_path.read_text())
        assert payload["ok"] is True
        assert payload["video"]["intrinsicWidth"] == 1920

    def test_a_refusal_is_a_written_result_with_a_zero_exit(self, make_video, job):
        result_path = job / "result.json"
        completed = subprocess.run(
            [sys.executable, "-m", "tabletwall.video", str(make_video("hevc.mp4")), str(job),
             str(result_path)],
            cwd=ROOT, capture_output=True, timeout=120,
        )
        assert completed.returncode == 0
        payload = json.loads(result_path.read_text())
        assert payload["ok"] is False
        assert "HEVC" in payload["error"]
