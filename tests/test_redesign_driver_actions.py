"""Count the real reviewed confirmations, including browser-native dialogs."""

import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("playwright.sync_api")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator/browser"))
import redesign_acceptance as driver  # noqa: E402


@pytest.mark.timeout(120)
def test_first_journey_count_includes_real_native_confirmations(tmp_path):
    result = driver.run_scenario(tmp_path / "run", "action-count", driver.first_wall)
    assert not any(
        row["name"] == "scenario interrupted" for row in result["failures"]
    ), result["failures"]
    identity = json.loads((tmp_path / "run/identity.json").read_text())
    initial = identity["first_wall_actions"]
    assert len(initial) == identity["script_fixture_action_count"] == 17
    assert (
        sum(action.startswith("Accept explicit confirmation:") for action in initial)
        == 2
    )
    assert len(identity["operator_actions"]) > len(initial)
    checks = json.loads((tmp_path / "run/results.json").read_text())["checks"]
    count = next(
        row for row in checks if row["name"].startswith("Scripted first journey")
    )
    assert count["pass"] and count["actual"] == initial
    evidence = json.loads((tmp_path / "run/evidence.json").read_text())
    dialogs = [row for row in evidence if row.get("dialog") == "confirm"]
    assert len(dialogs) == 2 and all(row["accepted"] for row in dialogs)
