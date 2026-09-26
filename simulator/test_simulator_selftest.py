"""Self-tests for the simulator's own plumbing — no app, no network.

Focused on the invariants that are easy to miss in a green run:

* ``--scenario`` never turns an ambiguous prefix into a silent "run
  everything"; bare numbers map onto their zero-padded ids;
* a scenario begun but never finished can *not* produce a green report;
* ``Harness.close`` survives its own failures, stops device readers,
  controller readers and the heartbeat, and reports stragglers from all
  of them (not only devices);
* the report is opt-in: the CLI default writes no file, and ``--report``
  conflicts with ``--no-report``.

These are deliberately outside ``tests/`` (the production suite) so the
app test suite never collects them by default. Run with::

    uv run pytest simulator/test_simulator_selftest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SIMULATOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIMULATOR_DIR.parent
for _entry in (str(SIMULATOR_DIR), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import pytest  # noqa: E402

import run as simulator_run  # noqa: E402
import scenarios as scenarios_module  # noqa: E402
from harness import Harness, build_specs  # noqa: E402
from report import Recorder  # noqa: E402


# ---------------------------------------------------------------------------
# --scenario matching
# ---------------------------------------------------------------------------


def _ids(*argv: str) -> list[str]:
    parser = simulator_run.build_parser()
    args = parser.parse_args(list(argv))
    return [item.id for item in simulator_run.select_scenarios(args)]


def test_exact_scenario_id_runs_the_prefix_up_to_it() -> None:
    chosen = _ids("--scenario", "15_auto_tiling")
    assert chosen[0] == "01_isolation"
    assert chosen[-1] == "15_auto_tiling"


def test_bare_number_matches_its_zero_padded_id() -> None:
    # "1" must mean scenario 01 — the old prefix matching turned it into
    # "everything starting with 1", i.e. a silent near-full run.
    assert _ids("--scenario", "1") == ["01_isolation"]
    chosen = _ids("--scenario", "15")
    assert chosen[0] == "01_isolation"
    assert chosen[-1] == "15_auto_tiling"


def test_bare_number_two_means_scenario_02_not_a_prefix() -> None:
    # "2" is the scenario number 02 (02_registration); it must not be read
    # as a prefix of 20_/21_/22_ and silently widen to the full run.
    assert _ids("--scenario", "2") == ["01_isolation", "02_registration"]


def test_last_scenario_number_is_the_full_run() -> None:
    assert _ids("--scenario", "22") == [
        item.id for item in scenarios_module.SCENARIOS
    ]


def test_unambiguous_prefix() -> None:
    assert _ids("--scenario", "16_seam")[-1] == "16_seam_matched"


def test_ambiguous_prefix_is_rejected_not_broadened() -> None:
    # Two ids sharing a prefix: picking the last silently would run far
    # more than asked, so it must be an explicit error. (With the current
    # zero-padded ids a non-digit prefix is always unique — the guard is
    # for the future — so synthesise the collision.)
    original = scenarios_module.SCENARIOS
    try:
        scenarios_module.SCENARIOS = original + [
            scenarios_module.Scenario("23_alpha_one", "fake", lambda ctx: None),
            scenarios_module.Scenario("23_alpha_two", "fake", lambda ctx: None),
        ]
        with pytest.raises(ValueError, match="ambiguous"):
            _ids("--scenario", "23_alpha")
    finally:
        scenarios_module.SCENARIOS = original


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        _ids("--scenario", "99")
    with pytest.raises(ValueError, match="unknown"):
        _ids("--scenario", "not_a_scenario")


def test_repeated_ids_pick_the_last() -> None:
    chosen = _ids("--scenario", "3", "--scenario", "15")
    assert chosen[-1] == "15_auto_tiling"


# ---------------------------------------------------------------------------
# report is opt-in
# ---------------------------------------------------------------------------


def test_report_is_opt_in() -> None:
    parser = simulator_run.build_parser()
    args = parser.parse_args([])
    assert args.report is None  # a default run writes no file
    assert not args.no_report
    assert parser.parse_args(["--report", "-"]).report == "-"
    assert parser.parse_args(["--no-report"]).no_report is True


def test_report_and_no_report_conflict() -> None:
    # The conflict is a usage error caught in main() before anything runs.
    with pytest.raises(SystemExit) as excinfo:
        simulator_run.main(["--report", "out.json", "--no-report"])
    assert excinfo.value.code == 2


def test_report_inside_repository_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        simulator_run.main(["--report", str(SIMULATOR_DIR / "report.json")])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# Recorder: a never-finished scenario can not be green
# ---------------------------------------------------------------------------


def test_pending_scenario_fails_the_run() -> None:
    recorder = Recorder()
    recorder.begin("01_x", "x")
    recorder.finish("passed", 0.0)
    recorder.begin("02_y", "y")  # begun, never finished
    assert recorder.ok is False
    assert any(entry["scenario"] == "02_y" for entry in recorder.failures())
    payload = recorder.to_dict({})
    assert payload["summary"]["ok"] is False
    assert payload["exit_code"] == 1


def test_reconcile_pending_records_the_error() -> None:
    recorder = Recorder()
    recorder.begin("01_x", "x")  # begun, never finished
    assert recorder.reconcile_pending() == ["01_x"]
    assert recorder.scenarios[0].status == "error"
    assert recorder.ok is False


def test_clean_recorder_is_green() -> None:
    recorder = Recorder()
    recorder.begin("01_x", "x")
    recorder.eq("two", 2, 2)
    recorder.finish("passed", 0.0)
    assert recorder.ok is True


def test_observe_records_every_check_without_aborting() -> None:
    # The teardown audit must see all of its checks, even after a failure:
    # expect() aborts on the first one, observe() records them all.
    recorder = Recorder()
    recorder.begin("01_x", "x")
    first = recorder.observe("first", False, expected="a", actual="b")
    second = recorder.observe("second", True, expected="v", actual="v")
    assert first.ok is False and first.expected == "a"
    assert second.ok is True
    assert [check.name for check in recorder.scenarios[0].checks] == ["first", "second"]
    assert recorder.ok is False


# ---------------------------------------------------------------------------
# Harness.close: resilient, complete, truthful about stragglers
# ---------------------------------------------------------------------------


class _StuckPump:
    """Pump stand-in whose reader thread never unwinds."""

    def __init__(self, label: str) -> None:
        self.label = label

    @property
    def alive(self) -> bool:
        return True

    def stop(self) -> None:  # simulate a wedged reader: stop() does nothing
        return None


def test_close_survives_its_own_failure(tmp_path: Path) -> None:
    harness = Harness(tmp_path, build_specs(1))
    try:

        def broken_stop_client() -> None:
            raise RuntimeError("boom")

        harness.stop_client = broken_stop_client  # type: ignore[method-assign]
        stragglers = harness.close()  # must not raise
        assert "boom" in harness.close_error
        assert "heartbeat" not in stragglers
        assert not harness._heartbeat.is_alive()
    finally:
        harness.devices[0].pump.stop()


def test_close_reports_stragglers_from_devices_and_controllers(tmp_path: Path) -> None:
    harness = Harness(tmp_path, build_specs(1))
    real_pump = harness.devices[0].pump
    try:
        # A wedged device reader…
        harness.devices[0].pump = _StuckPump(real_pump.label)  # type: ignore[assignment]
        # …and a wedged controller reader the old close() never inspected.
        stuck_controller = _StuckPump("controller-stuck")
        harness.controllers["stuck"] = stuck_controller

        stragglers = harness.close()  # must not raise
        assert stragglers == sorted(["device00", "controller-stuck"])
        assert "heartbeat" not in stragglers
        assert not harness._heartbeat.is_alive()
    finally:
        harness.controllers.pop("stuck", None)
        real_pump.stop()


def test_clean_close_stops_the_whole_fleet(tmp_path: Path) -> None:
    harness = Harness(tmp_path, build_specs(15))
    stragglers = harness.close()
    assert stragglers == []
    assert harness.close_error == ""
    assert not harness._heartbeat.is_alive()
    assert all(not device.pump.alive for device in harness.devices)
