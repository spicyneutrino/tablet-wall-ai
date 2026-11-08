"""Trust boundaries for the restoration driver, not application behavior."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator/browser"))
import restoration_acceptance as driver  # noqa: E402


def fake_source(root: Path) -> Path:
    (root / "frontend").mkdir(parents=True)
    (root / "tabletwall").mkdir()
    (root / "deploy").mkdir()
    (root / "main.py").write_text("app = None\n")
    (root / "frontend/app.js").write_text("window.app = 1;\n")
    (root / "tabletwall/module.py").write_text("VALUE = 1\n")
    (root / "deploy/tool.py").write_text("VALUE = 2\n")
    return root


def clean_cleanup() -> dict:
    return {
        "browser_disconnected": True,
        "port_closed": True,
        "private_data_removed": True,
        "server": {"pid": 123, "exit": 0, "alive": False},
        "errors": [],
    }


def test_registry_and_bodies_cover_all_ten_durable_scenarios():
    expected = {
        "gallery-focus",
        "recovery-sheet",
        "library-composer",
        "scene-paint",
        "fit-feedback",
        "geometry-tools",
        "fleet-power",
        "historical-forms",
        "historical-membership",
        "historical-uncertainty",
    }
    assert len(driver.SCENARIOS) == 10
    assert set(driver.SCENARIOS) == expected
    assert set(driver.IMPLEMENTED) == expected
    assert driver.INCOMPLETE == ()
    assert set(driver.SCENARIO_BODIES) == expected
    for name, body in driver.SCENARIO_BODIES.items():
        assert callable(body), name
        assert body.__name__ == name.replace("-", "_"), name
        assert driver.SCENARIOS[name]["status"] == "implemented"
        assert driver.SCENARIOS[name]["owner"] == ("M0-02" if name in {
            "gallery-focus", "recovery-sheet", "library-composer", "scene-paint",
        } else "M6-00")
    assert set(driver.SCENARIO_FIXTURES) == expected
    assert driver.SCENARIO_HOOKS["fit-feedback"]["owner"] == "M5-03"
    assert driver.SCENARIO_HOOKS["fleet-power"]["owner"] == "M6-02"


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakeHookPage:
    def __init__(self, selectors=(), expressions=None):
        self.selectors = set(selectors)
        self.expressions = expressions or {}

    def locator(self, selector):
        return FakeLocator(1 if selector in self.selectors else 0)

    def evaluate(self, expression):
        return self.expressions.get(expression, False)


class FakeHookRig:
    def __init__(self, page):
        self.page = page
        self.results = []

    def check(self, name, ok, actual=None, expected=True, **kwargs):
        self.results.append(
            {
                "name": name,
                "pass": bool(ok),
                "actual": actual,
                "expected": expected,
                **kwargs,
            }
        )
        return bool(ok)


def test_missing_feature_hook_fails_explicitly_with_the_owner_named():
    rig = FakeHookRig(FakeHookPage())
    assert driver.require_hooks(rig, "fit-feedback") is False
    assert len(rig.results) == 1
    row = rig.results[0]
    assert row["pass"] is False
    assert row["classification"] == "missing_required_hook"
    assert row["expected"] == "all registered hooks present"
    assert "M5-03" in row["name"]
    assert {item["selector"] for item in row["actual"]["missing"]} == {
        "#fit-feedback",
        "#fit-summary",
        "#fit-applied",
        "#crop-bars",
    }


def test_present_feature_hook_adds_no_failure_and_missing_js_hook_is_named():
    present = FakeHookRig(
        FakeHookPage(
            selectors={"#fit-feedback", "#fit-summary", "#fit-applied", "#crop-bars"}
        )
    )
    assert driver.require_hooks(present, "fit-feedback") is True
    assert present.results == []

    missing_js = FakeHookRig(
        FakeHookPage(selectors={"#tablet-evidence"}, expressions={})
    )
    assert driver.require_hooks(missing_js, "fleet-power") is False
    assert missing_js.results[0]["classification"] == "missing_required_hook"
    assert "M6-02" in missing_js.results[0]["name"]
    assert any(
        "powerReadiness" in item.get("expression", "")
        for item in missing_js.results[0]["actual"]["missing"]
    )

    present_js = FakeHookRig(
        FakeHookPage(
            selectors={"#tablet-evidence"},
            expressions={
                "() => typeof window.OperatorStage?.powerReadiness === 'function'": True,
                "() => !!document.getElementById('tablet-evidence')": True,
            },
        )
    )
    assert driver.require_hooks(present_js, "fleet-power") is True
    assert present_js.results == []


def test_fit_feedback_missing_hook_does_not_fake_a_pass_or_touch_the_server():
    rig = FakeHookRig(FakeHookPage())
    driver.fit_feedback(rig)
    assert len(rig.results) == 1
    assert rig.results[0]["pass"] is False
    assert rig.results[0]["classification"] == "missing_required_hook"
    assert not hasattr(rig, "new_client")


def test_current_guard_delete_sends_the_exact_config_if_match():
    calls = []

    class GuardRig:
        def config(self):
            return {"etag": "current-etag"}

        def request(self, method, path, body=None, if_match=None):
            calls.append((method, path, body, if_match))
            return 200, {"removed": True}

    status, _ = driver.delete_device_with_current_guard(GuardRig(), "device-1")
    assert status == 200
    assert calls == [("DELETE", "/devices/device-1", None, "current-etag")]


def test_current_guard_delete_refuses_an_unguarded_request():
    class NoGuardRig:
        def config(self):
            return {}

        def request(self, *_args, **_kwargs):
            raise AssertionError("must not send an unguarded DELETE")

    with pytest.raises(RuntimeError, match="refusing an unguarded DELETE"):
        driver.delete_device_with_current_guard(NoGuardRig(), "device-1")


def test_pattern_controls_navigate_to_images_after_the_authorized_move():
    events = []

    class PatternRig:
        def task(self, name):
            events.append(("task", name))

        def click(self, selector):
            events.append(("click", selector))

    driver.show_pattern(PatternRig(), "#show-colours")
    assert events == [("task", "Images"), ("click", "#show-colours")]


def test_artifacts_must_be_new_and_outside_both_repositories(tmp_path):
    source = fake_source(tmp_path / "source")
    created = driver.new_artifacts(tmp_path / "run", source)
    assert created.is_dir()
    with pytest.raises(FileExistsError):
        driver.new_artifacts(created, source)
    with pytest.raises(ValueError):
        driver.new_artifacts(driver.REPO / "inside-repository", source)
    with pytest.raises(ValueError):
        driver.new_artifacts(source / "inside-source", source)


def test_new_artifacts_can_defer_creation_to_the_scenario(tmp_path):
    source = fake_source(tmp_path / "source")
    deferred = driver.new_artifacts(tmp_path / "deferred", source, create=False)
    assert not deferred.exists()
    deferred.mkdir()
    with pytest.raises(FileExistsError):
        driver.new_artifacts(deferred, source, create=False)
    with pytest.raises(FileExistsError):
        driver.new_artifacts(deferred, source)


def test_wait_until_polls_evaluate_and_never_uses_wait_for_function():
    class FakePage:
        def __init__(self, results):
            self.results = list(results)
            self.calls = []

        def evaluate(self, expression, arg=None):
            self.calls.append((expression, arg))
            return self.results.pop(0) if self.results else False

        def wait_for_timeout(self, _milliseconds):
            return None

    page = FakePage([False, True])
    assert driver.wait_until(page, "() => ready", timeout=1, arg="x") is True
    assert len(page.calls) == 2
    assert page.calls[0] == ("() => ready", "x")

    expired = FakePage([])
    with pytest.raises(TimeoutError, match="bounded wait expired"):
        driver.wait_until(expired, "() => never", timeout=0.01)
    assert not hasattr(expired, "wait_for_function")


def test_launch_browser_uses_playwright_default_headless_browser():
    class FakeBrowser:
        version = "test-version"

    class FakeChromium:
        def __init__(self):
            self.kwargs = None

        def launch(self, **kwargs):
            self.kwargs = kwargs
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()

    playwright = FakePlaywright()
    environment = {"PRIVATE": "1"}
    browser = driver.launch_browser(playwright, environment)
    assert browser.version == "test-version"
    assert playwright.chromium.kwargs == {"headless": True, "env": environment}


def test_environment_is_private_complete_and_does_not_mutate_ambient(tmp_path, monkeypatch):
    for key, value in {
        "TABLET_WALL_DB": "/operator/live.db",
        "TABLET_WALL_ASSET_DIR": "/operator/assets",
        "TABLET_WALL_MEDIA_DIR": "/operator/media",
        "TABLET_WALL_BACKUP_DIR": "/operator/backups",
        "TABLET_WALL_OPERATOR_ORIGIN": "https://live.wall.test",
        "TABLET_WALL_TABLET_ORIGIN": "https://tablet.wall.test",
        "TABLET_WALL_AUTH_TOKEN": "must-not-inherit",
        "TABLET_WALL_OPERATOR_CREDENTIAL": "must-not-inherit",
        "TABLET_WALL_UPLOAD_MODE": "proxy",
        "TABLET_WALL_FUTURE_OPTION": "untrusted",
        "TABLET_ORIGIN": "https://legacy.wall.test",
        "AUTH_TOKEN": "must-not-inherit",
        "OPERATOR_CREDENTIAL": "must-not-inherit",
    }.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    data = tmp_path / "data"
    environment = driver.restoration_environment(data, 35719, uploads=True)
    private = {
        key: value for key, value in environment.items() if key.startswith("TABLET_WALL_")
    }
    assert private == {
        "TABLET_WALL_DB": str(data / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(data / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(data / "media"),
        "TABLET_WALL_BACKUP_DIR": str(data / "backups"),
        "TABLET_WALL_UPLOAD_MODE": "loopback",
        "TABLET_WALL_OPERATOR_ORIGIN": "http://127.0.0.1:35719",
        "TABLET_WALL_TABLET_ORIGIN": "http://127.0.0.1:35719",
    }
    assert environment["TMPDIR"] == str(data / "tmp")
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["HOME"] == str(data / "xdg" / "home")
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "run"),
    ):
        assert environment[key] == str(data / "xdg" / name)
        assert (data / "xdg" / name).is_dir()
    for name in ("assets", "media", "backups", "tmp"):
        assert (data / name).is_dir()
    for key in ("TABLET_ORIGIN", "AUTH_TOKEN", "OPERATOR_CREDENTIAL"):
        assert key not in environment
    assert dict(os.environ) == before

    disabled = driver.restoration_environment(tmp_path / "disabled", 35720, uploads=False)
    assert disabled["TABLET_WALL_UPLOAD_MODE"] == "disabled"
    assert disabled["TABLET_WALL_OPERATOR_ORIGIN"] == "http://127.0.0.1:35720"


def test_fixture_groups_are_unique_deterministic_and_cover_required_shapes(tmp_path):
    first = driver.generate_fixtures(tmp_path / "first")
    assert [group["count"] for group in first] == [0, 1, 8, 24]
    assert [len(group["files"]) for group in first] == [0, 1, 8, 24]
    files = [entry for group in first for entry in group["files"]]
    assert len(files) == 33
    assert len({entry["sha256"] for entry in files}) == 33
    assert len({entry["name"] for entry in files}) == 33
    assert {entry["format"] for entry in files} == {"png", "jpeg"}
    assert {(entry["width"], entry["height"]) for entry in files} >= {
        (1600, 1000),
        (1000, 1600),
        (2400, 1000),
    }
    assert max(len(entry["name"]) for entry in files) >= 80
    for entry in files:
        assert Path(entry["path"]).is_file()
        assert Path(entry["path"]).stat().st_size == entry["bytes"]
        assert driver.digest(Path(entry["path"])) == entry["sha256"]

    second = driver.generate_fixtures(tmp_path / "second")
    def manifest(groups):
        return {
            entry["relative_path"]: (entry["sha256"], entry["width"], entry["height"])
            for group in groups
            for entry in group["files"]
        }
    assert manifest(first) == manifest(second)

    assets = driver.prepare_assets(tmp_path / "first", tmp_path / "assets", 8)
    assert len(assets) == 8
    assert {entry["sha256"] for entry in assets} == {
        entry["sha256"] for entry in first[2]["files"]
    }
    assert all(Path(entry["path"]).is_file() for entry in assets)


def test_source_identity_separates_application_from_driver(tmp_path):
    source = fake_source(tmp_path / "source")
    identity = driver.application_identity(source)
    assert identity["source_root"] == str(source.resolve())
    assert identity["head"] is None
    assert identity["git_repository"] is False
    assert identity["file_count"] == 4
    assert len(identity["application_sha256"]) == 64
    assert "simulator/browser/restoration_acceptance.py" not in identity["application_hashes"]
    before = identity["application_sha256"]
    (source / "frontend/app.js").write_text("window.app = 2;\n")
    changed = driver.application_identity(source)
    assert changed["application_sha256"] != before
    assert changed["source_root"] == identity["source_root"]

    driver_identity = driver.driver_identity()
    assert driver_identity["driver_root"] == str(driver.REPO.resolve())
    assert "simulator/browser/restoration_acceptance.py" in driver_identity["driver_hashes"]
    assert "simulator/browser/run.py" in driver_identity["driver_hashes"]
    assert driver_identity["driver_hashes"]["simulator/browser/restoration_acceptance.py"] == driver.digest(
        driver.REPO / "simulator/browser/restoration_acceptance.py"
    )
    assert len(driver_identity["driver_sha256"]) == 64
    assert driver_identity["test_sha256"] == driver.digest(Path(driver.__file__).parents[2] / driver.TEST_PATH)


def test_source_root_must_be_an_application_tree(tmp_path):
    with pytest.raises(ValueError, match="main.py"):
        driver.resolve_source_root(tmp_path)
    source = fake_source(tmp_path / "source")
    assert driver.resolve_source_root(source) == source.resolve()


def test_server_launch_uses_the_selected_source_root_as_cwd(tmp_path, monkeypatch):
    source = fake_source(tmp_path / "selected-source")
    recorded = {}

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        recorded["argv"] = argv
        recorded["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(driver.subprocess, "Popen", fake_popen)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    log_path = tmp_path / "server.log"
    process, log, argv = driver.launch_server(source, {"PRIVATE": "1"}, log_path, listener)
    try:
        assert recorded["argv"] == argv
        assert argv[1:4] == ["-m", "uvicorn", "main:app"]
        assert recorded["kwargs"]["cwd"] == str(source.resolve())
        assert recorded["kwargs"]["env"] == {"PRIVATE": "1"}
        assert recorded["kwargs"]["pass_fds"] == (listener.fileno(),)
        assert recorded["kwargs"]["start_new_session"] is True
        assert process.pid == 4242
        assert log_path.is_file()
    finally:
        log.close()
        listener.close()


def test_an_incomplete_registry_entry_still_writes_explicit_failure_without_a_server(
    tmp_path, monkeypatch
):
    source = fake_source(tmp_path / "source")
    monkeypatch.setitem(
        driver.SCENARIOS,
        "fit-feedback",
        {
            "name": "fit-feedback",
            "status": "incomplete",
            "owner": "M5-03",
            "reason": "Fixture test forces the old incomplete branch.",
            "known_baseline_failure": None,
        },
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("incomplete scenarios must not launch a server or browser")

    monkeypatch.setattr(driver, "launch_server", forbidden)
    out = tmp_path / "evidence"
    code = driver.main(
        [
            "--scenario",
            "fit-feedback",
            "--artifacts",
            str(out),
            "--source-root",
            str(source),
        ]
    )
    assert code == 1
    result = json.loads((out / "results.json").read_text())
    assert result["scenario"] == "fit-feedback"
    assert result["pass"] is False
    assert result["acceptance_complete"] is False
    assert result["software_complete"] is False
    assert result["source"]["application_unchanged"] is True
    assert [row["scenario"] for row in result["incomplete"]] == ["fit-feedback"]
    assert result["incomplete"][0]["failures"][0]["classification"] == "explicitly_incomplete"
    assert result["reports"][0]["status"] == "incomplete"
    assert result["reports"][0]["pass"] is False
    assert result["fixtures"] == []
    assert not (out / "fit-feedback").exists()
    assert list(out.iterdir()) == [out / "results.json"]


def _fake_report(name: str) -> dict:
    return {
        "scenario": name,
        "status": "fail",
        "pass": False,
        "checks": 1,
        "failures": [{"pass": False}],
        "fixtures": [],
        "cleanup": {"errors": []},
    }


def test_single_implemented_scenario_creates_its_own_artifacts_target(tmp_path, monkeypatch):
    source = fake_source(tmp_path / "source")
    calls = []

    def fake_run(out, name, source_root, identity):
        assert not out.exists()
        out.mkdir(parents=True)
        calls.append((out, name, source_root, identity))
        return _fake_report(name)

    monkeypatch.setattr(driver, "run_scenario", fake_run)
    out = tmp_path / "single"
    code = driver.main(
        [
            "--scenario",
            "gallery-focus",
            "--artifacts",
            str(out),
            "--source-root",
            str(source),
        ]
    )
    assert code == 1
    assert [call[0] for call in calls] == [out.resolve()]
    assert calls[0][1] == "gallery-focus"
    assert calls[0][2] == source.resolve()
    result = json.loads((out / "results.json").read_text())
    assert result["scenario"] == "gallery-focus"
    assert result["fixture_coverage"] == {
        "generated_groups": [0, 1, 8, 24],
        "served_by_scenario": dict(driver.SCENARIO_FIXTURES),
        "note": driver.FIXTURE_COVERAGE_NOTE,
    }


def test_all_scenario_uses_new_child_artifact_directories(tmp_path, monkeypatch):
    source = fake_source(tmp_path / "source")
    calls = []

    def fake_run(out, name, source_root, identity):
        assert out.parent.is_dir()
        assert not out.exists()
        out.mkdir()
        calls.append((out, name))
        return _fake_report(name)

    monkeypatch.setattr(driver, "run_scenario", fake_run)
    out = tmp_path / "all"
    code = driver.main(
        [
            "--scenario",
            "all",
            "--artifacts",
            str(out),
            "--source-root",
            str(source),
        ]
    )
    assert code == 1
    assert [call[1] for call in calls] == list(driver.IMPLEMENTED)
    assert [call[0] for call in calls] == [out.resolve() / name for name in driver.IMPLEMENTED]
    assert len(calls) == 10
    result = json.loads((out / "results.json").read_text())
    assert result["incomplete"] == []
    assert [report["scenario"] for report in result["reports"]] == [
        "gallery-focus",
        "recovery-sheet",
        "library-composer",
        "scene-paint",
        "fit-feedback",
        "geometry-tools",
        "fleet-power",
        "historical-forms",
        "historical-membership",
        "historical-uncertainty",
    ]
    assert result["fixture_coverage"]["generated_groups"] == [0, 1, 8, 24]


def test_task_values_include_the_settings_panel():
    assert driver.TASK_VALUES["Settings"] == "system"
    assert driver.TASK_VALUES["Arrange"] == "show"


def test_unknown_or_missing_scenario_is_a_usage_error(tmp_path):
    source = fake_source(tmp_path / "source")
    with pytest.raises(SystemExit) as unknown:
        driver.main(
            [
                "--artifacts",
                str(tmp_path / "unknown"),
                "--scenario",
                "not-a-scenario",
                "--source-root",
                str(source),
            ]
        )
    assert unknown.value.code == 2
    with pytest.raises(SystemExit) as missing:
        driver.main(["--scenario", "gallery-focus", "--source-root", str(source)])
    assert missing.value.code == 2


def test_scenario_pass_requires_assertions_and_complete_cleanup():
    assert driver.scenario_pass([{"pass": True}], clean_cleanup()) is True
    assert driver.scenario_pass([{"pass": True}, {"pass": False}], clean_cleanup()) is False
    assert driver.scenario_pass([], clean_cleanup()) is False
    assert driver.scenario_pass([{"pass": True}], clean_cleanup(), interrupted=True) is False
    alive = clean_cleanup()
    alive["server"]["alive"] = True
    assert driver.scenario_pass([{"pass": True}], alive) is False
    not_closed = clean_cleanup()
    not_closed["port_closed"] = False
    assert driver.scenario_pass([{"pass": True}], not_closed) is False
    not_removed = clean_cleanup()
    not_removed["private_data_removed"] = False
    assert driver.scenario_pass([{"pass": True}], not_removed) is False
    errors = clean_cleanup()
    errors["errors"] = ["cleanup problem"]
    assert driver.scenario_pass([{"pass": True}], errors) is False


def test_help_lists_the_frozen_scenario_interface():
    result = subprocess.run(
        [sys.executable, str(Path(driver.__file__)), "--help"],
        cwd=driver.REPO,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "--artifacts" in result.stdout
    assert "--source-root" in result.stdout
    for name in driver.SCENARIOS:
        assert name in result.stdout
    assert "Explicitly incomplete" in result.stdout
