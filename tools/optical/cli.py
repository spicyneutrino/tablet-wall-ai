"""Command line entry points for fixtures and optical analysis."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence

from tools.validation import evidence

from . import TOOL_NAME, TOOL_VERSION
from .detect import analyze_capture
from .fixtures import generate_suite
from .inputs import load_capture, load_events, load_rois
from .model import AnalysisConfig
from .report import write_outputs


def _config_from_args(args: argparse.Namespace) -> AnalysisConfig:
    return AnalysisConfig(
        baseline_frames=args.baseline_frames,
        min_baseline_frames=args.min_baseline_frames,
        confirm_frames=args.confirm_frames,
    )


def _manifest_evidence_kind(path: Path) -> str | None:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    kind = raw.get("evidence_kind") if isinstance(raw, dict) else None
    return kind if kind in ("synthetic", "operator-hardware") else None


def _error_report(
    out_dir: Path,
    *,
    evidence_kind: str,
    started_at: str,
    error: BaseException,
) -> None:
    report = evidence.build_report(
        tool=TOOL_NAME,
        tool_version=TOOL_VERSION,
        gate="optical-cut-timing",
        evidence_kind=evidence_kind,
        started_at=started_at,
        checks=[evidence.check_row("analysis completed", False, error=str(error))],
        scenarios=[],
        expected_scenarios=[],
        limitations=[
            "The analysis aborted; no event metric is available.",
            "The optical gate remains MISSING; this tool cannot change a hardware gate.",
        ],
        error={
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    )
    evidence.write_report(out_dir / "report.json", report)


def _analyse(
    manifest: Path,
    rois_path: Path,
    events_path: Path,
    out_dir: Path,
    *,
    config: AnalysisConfig,
    decode_video: bool,
    frames_dir: Path | None,
    ocr: bool,
    repo_root: Path | None,
    ffmpeg_cmd: str,
    ffprobe_cmd: str,
    tesseract_cmd: str,
) -> dict[str, Any]:
    started_at = evidence.iso_now()
    capture = load_capture(
        manifest,
        decoded_dir=frames_dir or (out_dir / "decoded-frames"),
        force_video_decode=decode_video,
        ffmpeg_cmd=ffmpeg_cmd,
        ffprobe_cmd=ffprobe_cmd,
    )
    rois = load_rois(rois_path, capture=capture)
    events = load_events(events_path)
    timing_source = (
        "ffprobe"
        if any("ffprobe" in warning for warning in capture.warnings)
        else "manifest"
    )
    analysis = analyze_capture(
        capture,
        rois,
        events,
        config=config,
        ocr=ocr,
        tesseract_cmd=tesseract_cmd,
        timing_source=timing_source,
        started_at=started_at,
    )
    return write_outputs(
        analysis,
        out_dir,
        input_paths=[manifest, rois_path, events_path],
        repo_root=repo_root,
    )


def analyse_case_directory(
    case_dir: Path,
    out_dir: Path,
    **options: Any,
) -> dict[str, Any]:
    return _analyse(
        case_dir / "manifest.json",
        case_dir / "rois.json",
        case_dir / "events.json",
        out_dir,
        **options,
    )


def _command_fixtures(args: argparse.Namespace) -> int:
    suite = generate_suite(Path(args.out))
    print(json.dumps({
        "suite": suite["suite_path"],
        "cases": [case["case_id"] for case in suite["cases"]],
        "note": "Synthetic fixtures validate the analyzer only.",
    }, indent=2, sort_keys=True))
    return 0


def _command_analyze(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config = _config_from_args(args)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    evidence_kind = _manifest_evidence_kind(Path(args.manifest).resolve()) or args.evidence_kind
    try:
        result = _analyse(
            Path(args.manifest).resolve(),
            Path(args.rois).resolve(),
            Path(args.events).resolve(),
            out_dir,
            config=config,
            decode_video=args.decode_video,
            frames_dir=Path(args.frames_dir).resolve() if args.frames_dir else None,
            ocr=args.ocr,
            repo_root=repo_root,
            ffmpeg_cmd=args.ffmpeg,
            ffprobe_cmd=args.ffprobe,
            tesseract_cmd=args.tesseract,
        )
    except Exception as error:  # noqa: BLE001 - a failed run still needs evidence
        _error_report(
            out_dir,
            evidence_kind=evidence_kind,
            started_at=evidence.iso_now(),
            error=error,
        )
        print(f"optical analysis failed: {error}", file=sys.stderr)
        return 2
    report = result["report_data"]
    print(json.dumps({
        "report": result["report"],
        "analysis": result["analysis"],
        "events_csv": result["events_csv"],
        "panels_csv": result["panels_csv"],
        "summary_md": result["summary_md"],
        "checks_passed": report["checks_passed"],
        "checks_total": report["checks_total"],
        "failure_reasons": report["failure_reasons"],
        "hardware_gate_status": report["hardware_gate_status"],
        "completion": report["completion"],
    }, indent=2, sort_keys=True))
    return 0


def _command_analyze_suite(args: argparse.Namespace) -> int:
    suite_root = Path(args.suite).resolve()
    suite_path = suite_root / "suite.json"
    if not suite_path.exists():
        print(f"no suite.json under {suite_root}", file=sys.stderr)
        return 2
    suite = json.loads(suite_path.read_text())
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    config = _config_from_args(args)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    summary: list[dict[str, Any]] = []
    failures = 0
    for case in suite.get("cases", []):
        case_dir = suite_root / "cases" / case["case_id"]
        try:
            result = analyse_case_directory(
                case_dir,
                out_root / case["case_id"],
                config=config,
                decode_video=False,
                frames_dir=None,
                ocr=args.ocr,
                repo_root=repo_root,
                ffmpeg_cmd=args.ffmpeg,
                ffprobe_cmd=args.ffprobe,
                tesseract_cmd=args.tesseract,
            )
            report = result["report_data"]
            summary.append({
                "case_id": case["case_id"],
                "report": result["report"],
                "hardware_gate_status": report["hardware_gate_status"],
                "completion": report["completion"],
                "checks_passed": report["checks_passed"],
                "checks_total": report["checks_total"],
                "failure_reasons": report["failure_reasons"],
            })
        except Exception as error:  # noqa: BLE001 - retain the failing case
            failures += 1
            _error_report(
                out_root / case["case_id"],
                evidence_kind="synthetic",
                started_at=evidence.iso_now(),
                error=error,
            )
            summary.append({
                "case_id": case["case_id"],
                "error": f"{type(error).__name__}: {error}",
            })
    (out_root / "suite-summary.json").write_text(
        json.dumps({"suite": str(suite_path), "cases": summary}, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "suite": str(suite_path),
        "out": str(out_root),
        "cases": len(summary),
        "errors": failures,
        "summary": str(out_root / "suite-summary.json"),
        "note": "Synthetic fixtures validate the analyzer only.",
    }, indent=2, sort_keys=True))
    return 0 if failures == 0 else 1


def _add_common_analysis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-frames", type=int, default=8)
    parser.add_argument("--min-baseline-frames", type=int, default=3)
    parser.add_argument("--confirm-frames", type=int, default=1)
    parser.add_argument("--ocr", action="store_true", help="read the burned-in source-frame ROI")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--tesseract", default="tesseract")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.optical.cli",
        description=(
            "Optical cut analyzer for the tablet wall. Every report keeps the "
            "optical-cut-timing hardware gate MISSING."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixtures = subparsers.add_parser("fixtures", help="write the synthetic fixture suite")
    fixtures.add_argument("--out", required=True)
    fixtures.set_defaults(func=_command_fixtures)

    analyze = subparsers.add_parser("analyze", help="analyse one capture")
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--rois", required=True)
    analyze.add_argument("--events", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--decode-video", action="store_true")
    analyze.add_argument("--frames-dir", default=None)
    analyze.add_argument(
        "--evidence-kind",
        choices=("synthetic", "operator-hardware"),
        default="operator-hardware",
        help="used only if the manifest cannot be loaded",
    )
    _add_common_analysis_options(analyze)
    analyze.set_defaults(func=_command_analyze)

    suite = subparsers.add_parser("analyze-suite", help="analyse every generated fixture case")
    suite.add_argument("--suite", required=True)
    suite.add_argument("--out", required=True)
    _add_common_analysis_options(suite)
    suite.set_defaults(func=_command_analyze_suite)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
