"""Simulator entry point: ``uv run python simulator/run.py``.

Runs the numbered scenarios in :mod:`scenarios` against the real FastAPI
app (in-process via ``TestClient``), optionally writes a JSON report (only
when ``--report`` is given, so a default run leaves no file behind), and
exits non-zero if any check failed.

The process does three things before anything else:

1. moves to the repository root — ``main`` mounts ``frontend/*`` by relative
   path, so it can only be imported from there;
2. points ``TABLET_WALL_DB`` and ``TABLET_WALL_ASSET_DIR`` at a fresh
   temporary directory — the defaults (``./tablet-wall.db``, ``./assets``)
   are the operator's real data and must stay unreachable;
3. fingerprints every file in the repository so the run can prove afterwards
   that it changed nothing (only an explicit ``--report`` path inside the
   repository is excluded from that proof).

Everything else — the app, the fleet, the sockets — lives under ``simulator/``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMULATOR_DIR = Path(__file__).resolve().parent

# Repository state that is legitimately volatile (caches, the virtualenv, the
# git directory): excluding them keeps "nothing changed" about *content*.
SNAPSHOT_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}

# What this simulator is not, reported with every run so a green report is
# never mistaken for browser-level proof.
LIMITATIONS = [
    "No real browser: nothing executes frontend/client/client.js, so canvas "
    "pixels, image decode, layout, and device-pixel-ratio behaviour are not "
    "observed — only the frames and geometry a browser would be given.",
    "TestClient runs the app in-process on one event loop (no TCP, no "
    "uvicorn, no proxy): socket framing, TLS, reverse-proxy timeouts and "
    "origin enforcement in front of the app are outside the run.",
    "Client rendering is modelled in simulator/geometry.py from PROTOCOL.md, "
    "not executed; seam numbers are arithmetic, not screenshots.",
    "Heartbeat timeouts are exercised by patching the sweeper's timing "
    "constants in-process for one scenario; the real 15 s timeout is not "
    "waited for.",
    "No operator-origin (CSRF fence) coverage, no multi-controller "
    "concurrency stress, and no asset validation-failure matrix (corrupt, "
    "oversized, rotated, symlinked files) — those live in the pytest suite.",
]


# ---------------------------------------------------------------------------
# repository fingerprint
# ---------------------------------------------------------------------------


def snapshot_repo(exclude: Path | None = None) -> dict[str, tuple[int, int]]:
    """``{relative path: (size, mtime_ns)}`` for every tracked-ish file.

    Read-only, and deliberately wide: any write anywhere in the repository
    (including somewhere the simulator should never touch, like ``./assets``
    or ``tablet-wall.db``) shows up as a difference.
    """
    exclude = exclude.resolve() if exclude is not None else None
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        parts = set(path.relative_to(REPO_ROOT).parts)
        if parts & SNAPSHOT_SKIP_DIRS:
            continue
        if path.suffix == ".pyc":
            continue
        if exclude is not None and path.resolve() == exclude:
            continue
        stat = path.stat()
        snapshot[str(path.relative_to(REPO_ROOT))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def diff_snapshots(
    before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]
) -> dict[str, list[str]]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(
        path for path in set(before) & set(after) if before[path] != after[path]
    )
    return {"added": added, "removed": removed, "changed": changed}


def git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    from harness import DEFAULT_DEVICE_COUNT, MAX_DEVICES, MIN_DEVICES

    parser = argparse.ArgumentParser(
        prog="simulator/run.py",
        description=(
            "Run the bounded virtual-tablet scenario against the real FastAPI "
            "app using an isolated temporary database and asset directory."
        ),
    )
    parser.add_argument(
        "--devices",
        type=int,
        default=DEFAULT_DEVICE_COUNT,
        metavar="N",
        help=(
            f"virtual tablets to simulate ({MIN_DEVICES}–{MAX_DEVICES}; "
            f"default {DEFAULT_DEVICE_COUNT})"
        ),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "run the sequence up to and including this scenario id "
            "(repeatable; see --list). Accepts an exact id, a longer "
            "unambiguous prefix ('15_auto'), or a bare number ('15'); a "
            "prefix that matches several ids is rejected instead of being "
            "silently broadened. Scenarios build on each other, so a "
            "focused run always starts from the beginning."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list scenario ids and exit",
    )
    parser.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help=(
            "where to write the JSON report ('-' for stdout). Nothing is "
            "written unless this is given: generated output must not land "
            "in the repository by default"
        ),
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="do not write the JSON report file (the default; kept for scripts)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="how long to wait for any single frame (default 5)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop at the first scenario that fails",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="keep the temporary database/asset directory for inspection",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print the summary",
    )
    return parser


def select_scenarios(args: argparse.Namespace) -> list[Any]:
    """The scenarios to run.

    They are a *sequence*, not a set: later ones assume the roster, the
    wall, and the sockets earlier ones built. ``--scenario ID`` therefore
    means "run the sequence up to and including this id" — with several
    ids given, up to the last of them — so a focused run always starts from
    a clean app instead of failing on a premise it never established.

    Matching is deliberate about ambiguity: an exact id wins
    ("05_placement_validation"); a bare number matches its zero-padded id
    ("15" means "15_…"); otherwise the argument is an id prefix
    ("15_auto"). A prefix matching several ids is an error, never a silent
    "run everything up to the last match" ("2" must not become "22_sweeper").
    """
    from scenarios import SCENARIOS

    known = [item.id for item in SCENARIOS]
    if not args.scenario:
        return list(SCENARIOS)
    # Scenario ids are zero-padded ("01_…"); a bare number widens to that
    # width so "3" means "03_…" and can never collide with "30_…" style ids.
    width = max(2, len(str(len(SCENARIOS))))
    last_index = -1
    for wanted in args.scenario:
        if wanted in known:
            last_index = max(last_index, known.index(wanted))
            continue
        if wanted.isdigit():
            padded = f"{int(wanted):0{width}d}"
            matches = [
                index for index, item in enumerate(SCENARIOS)
                if item.id.startswith(padded)
            ]
            if not matches:
                raise ValueError(
                    f"unknown scenario number {wanted!r}; "
                    f"known ids: {', '.join(known)}"
                )
        else:
            matches = [
                index for index, item in enumerate(SCENARIOS)
                if item.id.startswith(wanted)
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"ambiguous scenario prefix {wanted!r}: matches "
                    f"{', '.join(SCENARIOS[index].id for index in matches)}; "
                    "give a longer prefix"
                )
            if not matches:
                raise ValueError(
                    f"unknown scenario {wanted!r}; known ids: {', '.join(known)}"
                )
        last_index = max(last_index, matches[-1])
    return list(SCENARIOS[: last_index + 1])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def prepare_runtime() -> None:
    """Move to the repository root and put it on ``sys.path``."""
    os.chdir(REPO_ROOT)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def residual_stop(harness: Any) -> list[str]:
    """Best-effort shutdown, used only if ``Harness.close`` itself failed.

    Tries the normal stop path once more (closing the sockets is what
    unblocks the readers), signals every pump, joins everything against a
    shared deadline, and returns whatever is still alive so the teardown
    checks still get a truthful straggler list.
    """
    stop_event = getattr(harness, "_heartbeat_stop", None)
    if stop_event is not None:
        stop_event.set()
    try:
        harness.stop_client()
    except Exception:  # noqa: BLE001 - best effort only
        pass
    pumps: list[Any] = [
        device.pump for device in getattr(harness, "devices", [])
    ]
    pumps += list(getattr(harness, "controllers", {}).values())
    for pump in pumps:
        try:
            pump.stop(timeout=0.0)  # signal only; joining happens below
        except Exception:  # noqa: BLE001 - best effort only
            pass
    deadline = time.monotonic() + 5.0  # harness.DEFAULT_WAIT_S, without importing
    stragglers: list[str] = []
    heartbeat = getattr(harness, "_heartbeat", None)
    if heartbeat is not None:
        heartbeat.join(timeout=max(0.0, deadline - time.monotonic()))
        if heartbeat.is_alive():
            stragglers.append("heartbeat")
    for pump in pumps:
        try:
            pump.stop(timeout=max(0.0, deadline - time.monotonic()))
        except Exception:  # noqa: BLE001 - best effort only
            pass
        if pump.alive:
            stragglers.append(pump.label)
    return sorted(stragglers)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from harness import MAX_DEVICES, MIN_DEVICES

    if args.list:
        from scenarios import SCENARIOS

        for item in SCENARIOS:
            print(f"{item.id:28} {item.title}")
        return 0
    if not MIN_DEVICES <= args.devices <= MAX_DEVICES:
        parser.error(f"--devices must be between {MIN_DEVICES} and {MAX_DEVICES}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.report is not None and args.no_report:
        parser.error("--report and --no-report cannot be used together")
    # Resolve relative to the caller, not to the repository directory that
    # prepare_runtime() switches into. Reports inside the source tree would
    # invalidate the repository-unchanged audit by excluding their own path.
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report and args.report != "-" and not args.no_report
        else None
    )
    if report_path is not None and report_path.is_relative_to(REPO_ROOT):
        parser.error("--report must point outside the repository")

    prepare_runtime()

    from harness import Harness, HarnessError, build_specs, fleet_rows
    from report import Recorder, ScenarioAbort
    from scenarios import Ctx

    try:
        selected = select_scenarios(args)
    except ValueError as exc:
        parser.error(str(exc))
    started_at = datetime.now(timezone.utc)
    clock_start = time.monotonic()
    before_files = snapshot_repo(exclude=report_path)

    specs = build_specs(args.devices)
    work_dir = Path(tempfile.mkdtemp(prefix="tablet-wall-sim-"))
    try:
        recorder = Recorder()
        harness = Harness(work_dir, specs)
        ctx = Ctx(harness, recorder, timeout=args.timeout)
    except BaseException:
        # Nothing may outlive a setup failure — not even an empty temp dir.
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    # With --report - the JSON is the product on stdout; every human line
    # goes to stderr so the stream stays machine-readable (print(file=None)
    # is plain stdout, keeping the default behaviour untouched).
    out = sys.stderr if args.report == "-" else None

    print(
        f"tablet-wall simulator: {len(selected)} scenarios, "
        f"{args.devices} virtual tablets, work dir {work_dir}",
        file=out,
    )

    stopped_early = False
    interrupted_run = False
    stragglers: list[str] = []
    try:
        boot_error: str = ""
        try:
            harness.start()
        except KeyboardInterrupt:
            boot_error, interrupted_run = "interrupted", True
        except Exception:  # noqa: BLE001 - boot failures belong in the report
            boot_error = traceback.format_exc()
        if boot_error:
            recorder.begin("00_boot", "The app starts against the temporary environment")
            recorder.finish("error", 0.0, boot_error)
        else:
            for item in selected:
                scenario_start = time.monotonic()
                status, error = "passed", ""
                interrupted = False
                try:
                    # begin..finish is one bracket: anything that raises in
                    # between (a drain failure, Ctrl-C between checks) has to
                    # land in a finished scenario, never a silent "pending".
                    recorder.begin(item.id, item.title)
                    harness.drain_all()
                    time.sleep(0.05)
                    item.run(ctx)
                except ScenarioAbort as exc:
                    status, error = "failed", str(exc)
                except HarnessError as exc:
                    status, error = "failed", str(exc)
                except KeyboardInterrupt:
                    status, error, interrupted = "error", "interrupted", True
                    interrupted_run = True
                except Exception:  # noqa: BLE001 - never hide a crash
                    status, error = "error", traceback.format_exc()
                recorder.finish(status, time.monotonic() - scenario_start, error)
                if not args.quiet and recorder.scenarios and recorder.scenarios[-1].id == item.id:
                    result = recorder.scenarios[-1]
                    passed = sum(1 for check in result.checks if check.ok)
                    marker = "ok  " if status == "passed" else status.upper()
                    print(
                        f"  {marker} {item.id:28} "
                        f"{passed}/{len(result.checks)} checks  "
                        f"{time.monotonic() - scenario_start:5.2f}s",
                        file=out,
                    )
                if interrupted:
                    stopped_early = True
                    break
                if status != "passed" and args.fail_fast:
                    stopped_early = True
                    break
    finally:
        try:
            stragglers = harness.close()
        except BaseException:  # noqa: BLE001 - a close failure must not erase the run
            harness.note_close_problem(f"close raised: {traceback.format_exc()}")
            stragglers = residual_stop(harness)

    # A scenario begun but never finished (an interruption between begin and
    # finish) must never read as green; name it before the summary is built.
    unreached = recorder.reconcile_pending()
    if unreached:
        print(
            f"warning: {', '.join(unreached)} never finished; counted as errors",
            file=out,
        )

    # ---- teardown checks (after the app is gone, before the report) ------
    # This is an audit, not a scenario: every step runs and every check is
    # recorded even when an earlier one fails, because the checks guard the
    # steps (temp-dir removal, the fingerprint) that must not be skipped.
    teardown_start = time.monotonic()
    recorder.begin("23_teardown", "Threads stopped, temp data removed, repository untouched")
    teardown_problems: list[str] = []
    try:
        close_problems = harness.close_error
        if close_problems:
            teardown_problems.append(f"close failed: {close_problems}")
        if stragglers:
            teardown_problems.append(f"readers still running: {', '.join(stragglers)}")

        if args.keep_work_dir:
            recorder.note("work dir kept", str(work_dir))
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
            if work_dir.exists():
                teardown_problems.append(f"temporary data survived at {work_dir}")

        try:
            diff = diff_snapshots(before_files, snapshot_repo(exclude=report_path))
        except Exception:  # noqa: BLE001 - a broken fingerprint check is a finding
            diff = {"added": [], "removed": [], "changed": []}
            teardown_problems.append(f"fingerprint check failed: {traceback.format_exc()}")
        if diff["added"] or diff["removed"] or diff["changed"]:
            teardown_problems.append(f"repository changed: {diff}")

        recorder.observe(
            "teardown closed the app cleanly",
            not close_problems,
            expected="",
            actual=close_problems,
            detail="a close that failed part-way is itself a risk, not noise",
        )
        recorder.observe(
            "every reader thread stopped",
            not stragglers,
            expected="[]",
            actual=stragglers,
            detail="a reader left running would hold the app's portal",
        )
        if not args.keep_work_dir:
            recorder.observe(
                "temporary database and assets removed",
                not work_dir.exists(),
                expected=f"{work_dir} gone",
                actual=str(work_dir) if work_dir.exists() else "gone",
            )
        recorder.observe(
            "no repository file was created, removed or modified",
            not (diff["added"] or diff["removed"] or diff["changed"]),
            expected="no differences",
            actual=diff,
            detail="the run must never touch ./assets, tablet-wall.db, or any source",
        )
        recorder.note("repository files fingerprinted", len(before_files))
        if stopped_early:
            recorder.note("run stopped early", True)
    except Exception:  # noqa: BLE001 - a teardown crash must still produce a report
        teardown_problems.append(traceback.format_exc())
    teardown_status = "failed" if teardown_problems else "passed"
    teardown_error = "; ".join(teardown_problems)
    recorder.finish(teardown_status, time.monotonic() - teardown_start, teardown_error)

    # ---- report ----------------------------------------------------------
    finished_at = datetime.now(timezone.utc)
    meta: dict[str, Any] = {
        "tool": "tablet-wall virtual device simulator",
        "mode": "testclient-in-process",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": round(time.monotonic() - clock_start, 3),
        "python": sys.version.split()[0],
        "git_head": git_head(),
        "repository": str(REPO_ROOT),
        "environment": dict(harness.env),
        "work_dir": str(work_dir),
        "devices": fleet_rows(specs),
        "device_count": args.devices,
        "scenarios_requested": [item.id for item in selected],
        "frame_timeout_s": args.timeout,
        "limitations": LIMITATIONS,
    }

    if not args.no_report:
        if args.report == "-":
            print(json.dumps(recorder.to_dict(meta), indent=2))
        elif report_path is not None:
            try:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(recorder.to_dict(meta), indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                # A failed report write must not hide the summary/exit code.
                print(f"warning: could not write the report to {report_path}: {exc}")

    # ---- summary ---------------------------------------------------------
    counts = recorder.check_counts
    statuses = recorder.scenario_counts
    ok = recorder.ok
    print(
        f"scenarios: {statuses.get('passed', 0)} passed, "
        f"{statuses.get('failed', 0)} failed, {statuses.get('error', 0)} errored "
        f"of {len(recorder.scenarios)}",
        file=out,
    )
    print(
        f"checks:    {counts['passed']} passed, {counts['failed']} failed of {counts['total']}",
        file=out,
    )
    for failure in recorder.failures():
        print(f"  FAIL {failure['scenario']}: {failure['error']}", file=out)
        for check in failure["failed_checks"]:
            print(
                f"        - {check['name']}: expected {check['expected']!r}, got {check['actual']!r}",
                file=out,
            )
    if report_path is not None:
        print(f"report:    {report_path}")
    print(f"duration:  {time.monotonic() - clock_start:.2f}s", file=out)
    print(
        "note:      no browser/canvas execution — see the limitations in the report",
        file=out,
    )
    # An interrupted run is never a green run, even when every finished
    # scenario passed: a Ctrl-C between checks must not look like success.
    return 0 if ok and not interrupted_run else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise SystemExit(130) from None
