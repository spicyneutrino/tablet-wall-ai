"""Real-browser video transition evidence on a disposable server.

    .venv/bin/python -m simulator.browser.video_transitions_run --artifacts /tmp/...

Scenarios:
  T1  two distinct videos back to back; the first survives to its boundary
  T2  one video with loop=true; the second loop occurrence is visible
  T3  a routine next prepare does not interrupt the active picture
  T4  a manual server-path video_fault at position 0 recovers at 0
  T5  the real following cut after that recovery is visible on every client

T4/T5 use a valid ``video_fault`` sent over a live client socket. That
exercises the server's recovery path; it is not the tablet's natural fault
detector. This is software evidence on one host clock, not optical evidence.
Every original client must show a concrete visible, ready, advancing video
element, and no unexpected page or request error is accepted.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

from simulator.browser.run import (
    CUT_COLOURS,
    ClientSpec,
    Observation,
    Rig,
    calibrate_cohort,
    child_environment,
    descendants,
    open_cohort,
)
from simulator.browser.video_run import (
    audit_browser_issues,
    build_clip,
    check_no_horizontal_clipping,
    probe_advancing_video,
    probe_details,
    read_status,
    repo_metadata,
    video_state,
    wait_advancing,
    wait_advancing_under,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER = "video_transitions_run"
RUNNER_VERSION = 1
EVIDENCE_KIND = "software browser; not optical or physical"
LONG_SECONDS = 20
SHORT_SECONDS = 8
CLIENTS = (
    (ClientSpec("transition-a", 240, 160, 1), 0),
    (ClientSpec("transition-b", 200, 150, 1.25), 180),
)
SCENARIO_ORDER = ("T1", "T2", "T3", "T4", "T5")
SCENARIO_TITLES = {
    "T1": "two distinct videos back to back",
    "T2": "one video with loop=true",
    "T3": "routine next prepare while a video is active",
    "T4": "recovery at position zero from a manual server-path fault",
    "T5": "recovery followed by the real next cut",
}


def upload(http: httpx.Client, path: Path, name: str) -> dict[str, Any]:
    response = http.post(
        f"/uploads?name={name}", content=path.read_bytes(),
        headers={"Content-Type": "video/mp4"},
    )
    if response.status_code != 201:
        raise RuntimeError(f"upload {name} failed: {response.status_code} {response.text[-500:]}")
    return response.json()["asset"]


def save_playlist(http: httpx.Client, items: list[dict[str, Any]], loop: bool) -> dict[str, Any]:
    etag = http.get("/api/v3/playlist").json()["etag"]
    response = http.put(
        "/api/v3/playlist", json={"items": items, "loop": loop},
        headers={"If-Match": etag},
    )
    if response.status_code != 200:
        raise RuntimeError(f"playlist save failed: {response.status_code} {response.text[-500:]}")
    return response.json()["playlist"]


def start_playback(http: httpx.Client) -> dict[str, Any]:
    response = http.post("/api/v3/playback/start")
    if response.status_code != 200:
        raise RuntimeError(f"playback start failed: {response.status_code} {response.text[-500:]}")
    return response.json()


def stop_playback(http: httpx.Client) -> None:
    status = read_status(http)
    if status.get("state") == "stopped":
        return
    response = http.post(
        "/api/v3/playback/stop",
        headers={"If-Match": str(status["version"])},
    )
    if response.status_code not in (200, 204, 409):
        raise RuntimeError(f"playback stop failed: {response.status_code} {response.text[-500:]}")


def active_status(status: dict[str, Any], index: int | None = None,
                  loop: int | None = None, settle_ms: int = 200) -> bool:
    current = status.get("current")
    if not isinstance(current, dict) or status.get("state") not in ("playing", "final"):
        return False
    if status.get("displayed") != current:
        return False
    effective = status.get("current_effective_ms")
    if effective is None or status.get("now_ms", 0) < effective + settle_ms:
        return False
    if index is not None and current.get("item_index") != index:
        return False
    if loop is not None and current.get("loop") != loop:
        return False
    return True


def cohort_complete(status: dict[str, Any], pages: list[tuple[Any, Observation]]) -> bool:
    expected = {observation.device_id for _, observation in pages}
    cohort = set(status.get("cohort") or [])
    return cohort == expected and len(cohort) == len(pages)


def prepare_frames(observation: Observation, since: float,
                   item_index: int | None = None,
                   recovery: bool | None = None) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for event in observation.events:
        if event["kind"] != "ws_received" or event["time"] < since:
            continue
        frame = event.get("frame")
        if not isinstance(frame, dict) or frame.get("type") != "prepare":
            continue
        occurrence = frame.get("occurrence")
        if item_index is not None and (
            not isinstance(occurrence, dict) or occurrence.get("item_index") != item_index
        ):
            continue
        marker = frame.get("recovery_id")
        if recovery is True and not (isinstance(marker, str) and marker):
            continue
        if recovery is False and marker is not None:
            continue
        frames.append(frame)
    return frames


async def wait_for(predicate, timeout: float, message: str) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(.05)
    raise RuntimeError(message)


async def wait_active(http: httpx.Client, index: int, timeout: float = 20,
                      loop: int | None = None) -> dict[str, Any]:
    return await wait_for(
        lambda: _active_or_none(http, index, loop),
        timeout, f"item {index} never became the displayed active occurrence",
    )


async def wait_clients_stopped(pages: list[tuple[Any, Observation]], timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        states = [await video_state(page) for page, _ in pages]
        if all(not state["videos"] for state in states):
            return
        await asyncio.sleep(.05)
    raise RuntimeError("a client kept a video element after playback stopped")


async def ping_open_socket(page: Any) -> dict[str, Any]:
    return await page.evaluate("""() => {
        const open = (window.__fleetSockets || []).filter(ws => ws.readyState === 1);
        return {count: open.length, readyStates: (window.__fleetSockets || []).map(ws => ws.readyState)};
    }""")


async def inject_fault(page: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return await page.evaluate("""payload => {
        const open = (window.__fleetSockets || []).filter(ws => ws.readyState === 1);
        if (open.length !== 1) return {ok: false, open: open.length};
        open[0].send(JSON.stringify(payload));
        return {ok: true, open: open.length};
    }""", payload)


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-transitions-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {
        "runner": RUNNER,
        "runner_version": RUNNER_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "state": "incomplete",
        "scenario_order": list(SCENARIO_ORDER),
        "scenarios": {
            scenario: {
                "id": scenario,
                "title": SCENARIO_TITLES[scenario],
                "status": "incomplete",
                "started": False,
                "finished": False,
                "checks": [],
            }
            for scenario in SCENARIO_ORDER
        },
        "environment": {"checks": []},
        "checks": [],
        "artifacts": str(artifacts),
        "root": str(root),
        "injections": {
            "T4": "valid manual video_fault sent over the live client socket; "
                  "server recovery path, not the natural tablet fault detector",
        },
        **repo_metadata(),
    }
    checks: list[dict[str, Any]] = report["checks"]

    def check(scenario: str, name: str, ok: bool, **detail: Any) -> bool:
        entry = {"scenario": scenario, "name": name, "passed": bool(ok), **detail}
        report["scenarios"][scenario]["checks"].append(entry)
        checks.append(entry)
        return bool(ok)

    def environment_check(name: str, ok: bool, **detail: Any) -> bool:
        entry = {"scenario": "environment", "name": name, "passed": bool(ok), **detail}
        report["environment"]["checks"].append(entry)
        checks.append(entry)
        return bool(ok)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = child_environment(root)
    env.update({"TABLET_WALL_UPLOAD_MODE": "loopback", "TABLET_WALL_OPERATOR_ORIGIN": base})
    log = (artifacts / "server.log").open("x")
    process = None
    resources: list[Any] = []
    owned: dict[int, str] = {}
    observations: list[Observation] = []
    playwright = None
    http = None
    error: str | None = None
    finalized = False

    def finalize() -> None:
        nonlocal finalized
        if finalized:
            return
        finalized = True
        audit_browser_issues(environment_check, observations)
        for scenario in SCENARIO_ORDER:
            entry = report["scenarios"][scenario]
            failed = [item for item in entry["checks"] if not item["passed"]]
            if not entry["started"]:
                entry["status"] = "skipped"
            elif not entry["finished"]:
                entry["status"] = "incomplete"
            elif failed:
                entry["status"] = "failed"
            else:
                entry["status"] = "passed"
            entry["checks_passed"] = sum(1 for item in entry["checks"] if item["passed"])
            entry["checks_total"] = len(entry["checks"])
        passed = sum(1 for entry in checks if entry["passed"])
        report["checks_passed"] = passed
        report["checks_failed"] = len(checks) - passed
        report["checks_total"] = len(checks)
        report["error"] = error
        report["state"] = "incomplete" if error else (
            "passed" if passed == len(checks) and all(
                report["scenarios"][scenario]["finished"] for scenario in SCENARIO_ORDER
            ) else "failed"
        )
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"],
            cwd=REPO, env=env, pass_fds=(listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        listener.close()
        listener = None
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=30)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code in (200, 409):
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("transitions server did not become ready; see server.log")
            await asyncio.sleep(.1)
        report["origin"] = base

        long_path = root / "long.mp4"
        short_path = root / "short.mp4"
        report["fixtures"] = {
            "long": build_clip(long_path, LONG_SECONDS, "testsrc2"),
            "short": build_clip(short_path, SHORT_SECONDS, "smptebars"),
        }
        long_video = upload(http, long_path, "long.mp4")
        short_video = upload(http, short_path, "short.mp4")
        report["descriptors"] = {"long": long_video, "short": short_video}
        if long_video["kind"] != "video" or short_video["kind"] != "video":
            raise RuntimeError("fixtures were not accepted as videos")
        if long_video["durationMs"] < 19_000 or short_video["durationMs"] < 7_000:
            raise RuntimeError("fixture durations are shorter than requested")

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(env={**os.environ, "TMPDIR": str(root / "tmp")})
        resources.append(browser)
        report["browser_version"] = browser.version
        owned.update(descendants(os.getpid()))
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=observations, captured_pages=[],
                  resources=resources, owned=owned, check=environment_check)
        pages = await open_cohort(rig, CLIENTS, "transitions")
        names = [observation.spec.name for _, observation in pages]
        await calibrate_cohort(rig, pages, [mount for _, mount in CLIENTS],
                               CUT_COLOURS, "transitions")
        expected_cohort = {observation.device_id for _, observation in pages}
        report["cohort"] = sorted(expected_cohort)

        # ---- T3 and T1 share one two-video session -----------------------
        report["scenarios"]["T3"]["started"] = True
        report["scenarios"]["T1"]["started"] = True
        t3_start = time.monotonic()
        save_playlist(http, [
            {"asset": long_video["id"], "dwell_ms": 1000},
            {"asset": short_video["id"], "dwell_ms": 1000},
        ], loop=False)
        start_playback(http)
        status = await wait_active(http, 0)
        await pages[0][0].screenshot(path=str(artifacts / "t3-first-active.png"))
        check("T3", "the session starts on the first video",
              (status.get("live") or {}).get("current", {}).get("asset") == long_video["id"],
              current=status.get("current"), live=status.get("live"))
        check("T3", "the original cohort is complete",
              cohort_complete(status, pages), cohort=status.get("cohort"),
              expected=sorted(expected_cohort))
        check("T3", "live status carries the frozen current video metadata",
              (status.get("live") or {}).get("current", {}).get("asset") == long_video["id"]
              and (status.get("live") or {}).get("current", {}).get("kind") == "video",
              live=status.get("live"))

        prepare_status = await wait_for(
            lambda: _pending_and_seen(http, pages, t3_start, 1),
            20, "the routine next prepare never reached every client while video was active",
        )
        check("T3", "a routine prepare for the next video reached every client",
              all(prepare_frames(observation, t3_start, item_index=1, recovery=False)
                  for _, observation in pages),
              frames={
                  observation.spec.name: len(prepare_frames(
                      observation, t3_start, item_index=1, recovery=False
                  )) for _, observation in pages
              })
        check("T3", "the routine prepare is ordinary and has no recovery marker",
              all(
                  frame.get("recovery_id") is None
                  for _, observation in pages
                  for frame in prepare_frames(observation, t3_start, item_index=1)
              ),
              frames={
                  observation.spec.name: [
                      {"recovery_id": frame.get("recovery_id"),
                       "start_media_ms": frame.get("start_media_ms")}
                      for frame in prepare_frames(observation, t3_start, item_index=1)
                  ] for _, observation in pages
              })
        check("T3", "the server still displays the first video with the next prepare pending",
              active_status(prepare_status, 0),
              current=prepare_status.get("current"),
              displayed=prepare_status.get("displayed"),
              pending=prepare_status.get("pending"))
        pending_effective = prepare_status["pending"]["effective_server_ms"]
        t3_probes: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await probe_advancing_video(page, interval=0.5, minimum_after=0.2)
            t3_probes[name] = probe
            check("T3", name + " advances across the routine prepare window",
                  probe["ok"], **probe_details(probe))
            check("T3", name + " samples both fall before the pending cut",
                  read_status(http).get("now_ms", 0) + 100 < pending_effective,
                  now_ms=read_status(http).get("now_ms"),
                  pending_effective=pending_effective)
        after_t3 = read_status(http)
        check("T3", "the routine prepare did not change the current occurrence",
              after_t3.get("current") == prepare_status.get("current")
              and after_t3.get("pending", {}).get("occurrence", {}).get("item_index") == 1,
              current=after_t3.get("current"), pending=after_t3.get("pending"))
        report["T3"] = {
            "status": prepare_status, "probes": t3_probes,
            "pending_effective_ms": pending_effective,
        }
        report["scenarios"]["T3"]["finished"] = True

        boundary_status = None
        # Wait for the last safe window before the first video's boundary. If
        # a premature cut arrives, the predicate below never matches and the
        # check fails rather than silently accepting the wrong occurrence.
        deadline = time.monotonic() + 30
        premature = None
        while time.monotonic() < deadline:
            candidate = read_status(http)
            if candidate.get("current", {}).get("item_index") == 1:
                premature = candidate
                break
            pending = candidate.get("pending") or {}
            effective = pending.get("effective_server_ms")
            if (
                candidate.get("current", {}).get("item_index") == 0
                and effective is not None
                and candidate.get("now_ms", 0) >= effective - 1500
            ):
                boundary_status = candidate
                break
            await asyncio.sleep(.05)
        check("T1", "the first video is still current inside the last 1.5 s before its boundary",
              boundary_status is not None, status=boundary_status or premature)
        if boundary_status is not None:
            t1_before: dict[str, dict[str, Any]] = {}
            for (page, _), name in zip(pages, names, strict=True):
                probe = await probe_advancing_video(page, interval=0.5, minimum_after=2.0)
                t1_before[name] = probe
                check("T1", name + " keeps the first video visible and advancing before its boundary",
                      probe["ok"], **probe_details(probe))
            report["T1"] = {"before_boundary": t1_before}
            await pages[0][0].screenshot(path=str(artifacts / "t1-first-before-boundary.png"))

        second = await wait_for(
            lambda: _active_or_none(http, 1, settle_ms=200),
            15, "the second video never became the displayed active occurrence",
        )
        check("T1", "the second occurrence commits as a new video",
              (second.get("live") or {}).get("current", {}).get("asset") == short_video["id"]
              and (second.get("live") or {}).get("current", {}).get("kind") == "video",
              current=second.get("current"), live=second.get("live"))
        check("T1", "the original cohort is complete after the second commit",
              cohort_complete(second, pages), cohort=second.get("cohort"),
              expected=sorted(expected_cohort))
        t1_after: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(
                page, timeout=15, minimum_after=0.2,
                expected_duration=short_video["durationMs"] / 1000,
            )
            t1_after[name] = probe
            check("T1", name + " shows the second video visible and advancing",
                  probe["ok"], **probe_details(probe))
        report["T1"] = {**report.get("T1", {}), "after_boundary": t1_after, "status": second}
        check("T1", "every original client showed the second video",
              all(probe["ok"] for probe in t1_after.values()), clients=t1_after)
        for (page, observation) in pages:
            await check_no_horizontal_clipping(
                environment_check,
                page, observation.spec.name + " has no horizontal clipping with video visible",
            )
        await pages[0][0].screenshot(path=str(artifacts / "t1-second-active.png"))
        report["scenarios"]["T1"]["finished"] = True
        stop_playback(http)
        await wait_clients_stopped(pages)

        # ---- T2: one video with loop=true -------------------------------
        report["scenarios"]["T2"]["started"] = True
        save_playlist(http, [{"asset": short_video["id"], "dwell_ms": 1000}], loop=True)
        start_playback(http)
        t2_first = await wait_active(http, 0, loop=0)
        check("T2", "the single video starts on loop 0",
              t2_first.get("current", {}).get("loop") == 0,
              current=t2_first.get("current"))
        check("T2", "the original cohort is complete",
              cohort_complete(t2_first, pages), cohort=t2_first.get("cohort"),
              expected=sorted(expected_cohort))
        first_probes: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(page, timeout=15, minimum_after=0.5)
            first_probes[name] = probe
            check("T2", name + " plays the first loop occurrence", probe["ok"], **probe_details(probe))
        report["T2"] = {"first": first_probes}

        t2_loop = await wait_for(
            lambda: _active_or_none(http, 0, loop=1, settle_ms=200),
            30, "the second loop occurrence never reached the displayed state",
        )
        check("T2", "the second loop occurrence committed on the server",
              t2_loop.get("current", {}).get("loop") == 1
              and (t2_loop.get("live") or {}).get("current", {}).get("occurrence")
              == t2_loop.get("current"),
              current=t2_loop.get("current"), live=t2_loop.get("live"))
        loop_probes: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing_under(page, 3.0, timeout=15)
            loop_probes[name] = probe
            check("T2", name + " shows the second loop occurrence visible and advancing",
                  probe["ok"], **probe_details(probe))
            check("T2", name + " does not use the native loop attribute",
                  probe["after"]["loop"] is False, loop=probe["after"]["loop"])
        check("T2", "every original client showed the second loop occurrence",
              all(probe["ok"] for probe in loop_probes.values()), clients=loop_probes)
        report["T2"] = {**report["T2"], "second_loop": loop_probes, "status": t2_loop}
        await pages[0][0].screenshot(path=str(artifacts / "t2-second-loop.png"))
        report["scenarios"]["T2"]["finished"] = True
        stop_playback(http)
        await wait_clients_stopped(pages)

        # ---- T4 and T5: recovery at zero, then the real following cut ----
        report["scenarios"]["T4"]["started"] = True
        report["scenarios"]["T5"]["started"] = True
        save_playlist(http, [
            {"asset": long_video["id"], "dwell_ms": 1000},
            {"asset": short_video["id"], "dwell_ms": 1000},
        ], loop=False)
        start_playback(http)
        t4_before = await wait_active(http, 0)
        await wait_for(
            lambda: read_status(http).get("now_ms", 0)
            >= (t4_before.get("current_effective_ms") or 0) + 1500,
            10, "the first video did not reach a playable position before the fault",
        )
        check("T4", "the original cohort is complete before the fault",
              cohort_complete(read_status(http), pages), cohort=read_status(http).get("cohort"),
              expected=sorted(expected_cohort))
        fault_status = read_status(http)
        occurrence = fault_status.get("current") or {}
        pre_fault_times: dict[str, float | None] = {}
        for (page, _), name in zip(pages, names, strict=True):
            state = await video_state(page)
            visible = [video for video in state["videos"] if video["visible"]]
            pre_fault_times[name] = visible[0]["currentTime"] if len(visible) == 1 else None
        check("T4", "both clients show the first video before the fault",
              all(value is not None and value >= 1.0 for value in pre_fault_times.values()),
              current_times=pre_fault_times)
        payload = {
            "type": "video_fault",
            "session_id": fault_status["session_id"],
            "version": fault_status["version"],
            "occurrence": occurrence,
            "reason": "stalled",
            "position_ms": 0,
        }
        socket_state = await ping_open_socket(pages[0][0])
        t4_start = time.monotonic()
        injection = await inject_fault(pages[0][0], payload)
        check("T4", "the manual server-path fault was sent on one live client socket",
              injection.get("ok") is True and socket_state.get("count") == 1,
              injection=injection, sockets=socket_state, payload=payload)
        recovery = await wait_for(
            lambda: _recovery_at_zero(http),
            20, "the server never started the position-zero recovery",
        )
        check("T4", "the server starts a recovery at position zero",
              recovery.get("position_ms") == 0
              and recovery.get("occurrence") == occurrence
              and recovery.get("state") in ("preparing", "playing"),
              recovery=recovery, injection=report["injections"]["T4"])
        seen = await wait_for(
            lambda: True if all(prepare_frames(o, t4_start, item_index=0, recovery=True)
                                for _, o in pages) else None,
            20, "the recovery prepare did not reach every client",
        )
        check("T4", "the recovery prepare reached every original client", bool(seen),
              frames={
                  observation.spec.name: [
                      {"recovery_id": frame.get("recovery_id"),
                       "start_media_ms": frame.get("start_media_ms")}
                      for frame in prepare_frames(observation, t4_start, item_index=0,
                                                  recovery=True)
                  ] for _, observation in pages
              })
        check("T4", "every recovery prepare carries a non-empty marker and position zero",
              all(
                  isinstance(frame.get("recovery_id"), str) and frame["recovery_id"]
                  and frame.get("start_media_ms") == 0
                  for _, observation in pages
                  for frame in prepare_frames(observation, t4_start, item_index=0,
                                              recovery=True)
              ),
              frames={
                  observation.spec.name: [
                      {"recovery_id": frame.get("recovery_id"),
                       "start_media_ms": frame.get("start_media_ms")}
                      for frame in prepare_frames(observation, t4_start, item_index=0,
                                                  recovery=True)
                  ] for _, observation in pages
              })
        recovered = await wait_for(
            lambda: _recovered_at_zero(http),
            20, "the recovery commit never reached the displayed state",
        )
        check("T4", "the recovery commit returns the first video at zero",
              recovered.get("recovery", {}).get("state") == "playing"
              and recovered.get("recovery", {}).get("position_ms") == 0
              and recovered.get("current", {}).get("item_index") == 0,
              recovery=recovered.get("recovery"), current=recovered.get("current"))
        t4_probes: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(page, timeout=15, minimum_after=0.0)
            t4_probes[name] = probe
            check("T4", name + " shows the recovered video visible and advancing at zero",
                  probe["ok"]
                  and pre_fault_times[name] is not None
                  and probe["after"]["currentTime"] < pre_fault_times[name] + 1.0,
                  **probe_details(probe), pre_fault_time=pre_fault_times[name])
        check("T4", "every original client recovered and advanced",
              all(probe["ok"] for probe in t4_probes.values()), clients=t4_probes)
        report["T4"] = {"status": recovered, "probes": t4_probes,
                        "recovery": recovered.get("recovery")}
        await pages[0][0].screenshot(path=str(artifacts / "t4-recovered-at-zero.png"))
        report["scenarios"]["T4"]["finished"] = True

        following = await wait_for(
            lambda: _active_or_none(http, 1, settle_ms=250),
            35, "the real following cut never reached the displayed state",
        )
        check("T5", "the real following video cut committed",
              (following.get("live") or {}).get("current", {}).get("asset") == short_video["id"]
              and (following.get("live") or {}).get("current", {}).get("kind") == "video"
              and following.get("recovery") is None,
              current=following.get("current"), recovery=following.get("recovery"),
              live=following.get("live"))
        check("T5", "the original cohort is complete after the following cut",
              cohort_complete(following, pages), cohort=following.get("cohort"),
              expected=sorted(expected_cohort))
        t5_probes: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(
                page, timeout=15, minimum_after=0.2,
                expected_duration=short_video["durationMs"] / 1000,
            )
            t5_probes[name] = probe
            check("T5", name + " shows the following video visible and advancing",
                  probe["ok"], **probe_details(probe))
        check("T5", "every original client showed the following cut",
              all(probe["ok"] for probe in t5_probes.values()), clients=t5_probes)
        report["T5"] = {"status": following, "probes": t5_probes}
        await pages[0][0].screenshot(path=str(artifacts / "t5-following-cut.png"))
        report["scenarios"]["T5"]["finished"] = True
        stop_playback(http)
        await wait_clients_stopped(pages)

        for (page, observation) in pages:
            await check_no_horizontal_clipping(
                environment_check,
                page, observation.spec.name + " has no horizontal clipping after stop",
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        with contextlib.suppress(Exception):
            if http is not None:
                http.close()
        with contextlib.suppress(Exception):
            if playwright is not None:
                await playwright.stop()
        with contextlib.suppress(Exception):
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        with contextlib.suppress(Exception):
            if listener is not None:
                listener.close()
        with contextlib.suppress(Exception):
            log.close()
        shutil.rmtree(root, ignore_errors=True)
        finalize()

    if report["state"] == "incomplete":
        return 2
    return 0 if report["checks_failed"] == 0 else 1


def _pending_and_seen(http: httpx.Client, pages: list[tuple[Any, Observation]],
                      since: float, item_index: int) -> dict[str, Any] | None:
    status = read_status(http)
    pending = status.get("pending") or {}
    occurrence = pending.get("occurrence") or {}
    if (
        status.get("current", {}).get("item_index") != 0
        or occurrence.get("item_index") != item_index
        or pending.get("effective_server_ms") is None
    ):
        return None
    if not all(prepare_frames(observation, since, item_index=item_index, recovery=False)
               for _, observation in pages):
        return None
    return status


def _active_or_none(http: httpx.Client, index: int, loop: int | None = None,
                    settle_ms: int = 200) -> dict[str, Any] | None:
    status = read_status(http)
    return status if active_status(status, index, loop, settle_ms) else None


def _recovery_at_zero(http: httpx.Client) -> dict[str, Any] | None:
    status = read_status(http)
    recovery = status.get("recovery")
    if (
        isinstance(recovery, dict)
        and recovery.get("position_ms") == 0
        and recovery.get("state") in ("preparing", "playing")
    ):
        return recovery
    return None


def _recovered_at_zero(http: httpx.Client) -> dict[str, Any] | None:
    status = read_status(http)
    recovery = status.get("recovery")
    if (
        isinstance(recovery, dict)
        and recovery.get("state") == "playing"
        and recovery.get("position_ms") == 0
        and active_status(status, 0)
    ):
        return status
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
