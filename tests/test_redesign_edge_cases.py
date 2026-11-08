"""Evidence trust checks for held real traffic, native keys, and honest closure."""

import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("playwright.sync_api")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator/browser"))
import redesign_acceptance as driver  # noqa: E402
from _redesign_edge_cases import HeldResponse, late_mutation, old_paint, task  # noqa: E402
from operator_accessibility import native_tab_to  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from playwright.sync_api import expect  # noqa: E402


def test_partial_or_failed_runs_cannot_close_mandatory_groups():
    external = {"verified": False}
    rows = driver.coverage_report([], external)
    assert len(rows) == len(driver.MANDATORY_OPEN)
    assert not any(row["status"] == "PASS" for row in rows)
    names = driver.SOFTWARE_GROUPS[0]
    reports = [
        {"scenario": name, "pass": True, "artifacts": "/synthetic/" + name}
        for name in names
    ]
    assert driver.coverage_report(reports, external)[0]["status"] == "PASS"
    reports[0]["pass"] = False
    failed = driver.coverage_report(reports, external)[0]
    assert failed["status"] == "ISSUES" and failed["issues"] == [names[0]]
    assert driver.ENVIRONMENT_OPEN


def test_external_proof_rejects_changed_source_or_allowlist(tmp_path):
    source = Path("/tmp/tablet-wall-favicon-ingress-tys6crky/ingress-manifest.json")
    if not source.exists():
        pytest.skip(
            "External root proof is environment-local; no proof is manufactured"
        )
    manifest = json.loads(source.read_text())
    copied = tmp_path / "proof.json"
    copied.write_text(json.dumps(manifest))
    stale_source = json.loads(json.dumps(manifest))
    stale_source["source_sha256"]["main.py"] = "0" * 64
    copied.write_text(json.dumps(stale_source))
    stale = driver.external_ingress_proof(copied)
    assert not stale["verified"] and not stale["source_matches"]["main.py"]
    manifest["allowlist_sha256"] = "0" * 64
    copied.write_text(json.dumps(manifest))
    result = driver.external_ingress_proof(copied)
    assert not result["verified"] and not result["allowlist_matches"]
    assert result["classification"] == "external_root_evidence"


def test_external_proof_parser_accepts_expanded_denial_matrix(tmp_path):
    """Synthetic parser input, never an ingress execution or product acceptance."""
    source = Path("/tmp/tablet-wall-favicon-ingress-tys6crky/ingress-manifest.json")
    if not source.exists():
        pytest.skip("Environment-local proof schema fixture is unavailable")
    manifest = json.loads(source.read_text())
    manifest["source_sha256"] = {
        name: driver.digest(driver.ROOT / name) for name in manifest["source_sha256"]
    }
    manifest["allowlist_sha256"] = driver.digest(
        driver.ROOT / "deploy/tablet-routes.caddy"
    )
    origin = f"http://127.0.0.1:{manifest['tablet_port']}"
    manifest["requests"].extend(
        {"origin": origin, "method": method, "path": path, "status": 403}
        for method, path in (
            ("POST", "/client/favicon.svg"),
            ("HEAD", "/client/favicon.svg/extra"),
            ("HEAD", "/client/client.js"),
        )
    )
    manifest["requests"].append(
        {
            "origin": origin,
            "method": "HEAD",
            "path": "/client/favicon.svg",
            "status": 200,
        }
    )
    proof = tmp_path / "synthetic-parser-fixture.json"
    proof.write_text(json.dumps(manifest))
    result = driver.external_ingress_proof(proof)
    assert result["verified"] and result["exact_favicon_head_proven"]
    assert result["tablet_denials"] == 127


@pytest.mark.timeout(30)
def test_native_tab_helper_uses_real_tab_and_bounds_an_unreachable_target():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(
                '<button id="a">A</button><button id="b">B</button><button id="off" disabled>Off</button>'
            )
            page.evaluate(
                "window.keys=[];document.addEventListener('keydown',e=>window.keys.push({key:e.key,trusted:e.isTrusted}))"
            )
            path = native_tab_to(page, "#b", maximum=5)
            assert [row["id"] for row in path] == ["a", "b"]
            assert page.evaluate("window.keys.every(e=>e.key==='Tab'&&e.trusted)")
            with pytest.raises(AssertionError, match="Native Tab did not reach #off"):
                native_tab_to(page, "#off", maximum=4)
            assert not page.locator("#off").evaluate("e=>e===document.activeElement")
        finally:
            browser.close()


@pytest.mark.timeout(100)
def test_two_held_real_responses_release_independently(tmp_path):
    def body(rig):
        page = rig.page
        task(page, "Tablets")
        config = HeldResponse(
            rig, page, "**/api/v3/config", "held config alongside image inventory"
        )
        page.locator("#btn-roster-refresh").click()
        config.wait()
        task(page, "Images")
        expect(page.locator("#refresh-images")).to_be_enabled()
        inventory = HeldResponse(
            rig,
            page,
            "**/api/v3/images",
            "inventory must remain held when config releases",
        )
        receipts = []
        page.on(
            "response",
            lambda response: (
                receipts.append(response.url)
                if response.url.endswith("/api/v3/images")
                else None
            ),
        )
        page.locator("#refresh-images").click()
        inventory.wait()
        config.release()
        rig.check(
            not receipts and page.locator("#refresh-images").is_disabled(),
            "Releasing config does not silently release concurrently held inventory",
            receipts,
        )
        inventory.release()
        expect(page.locator("#refresh-images")).to_be_enabled()
        rig.check(
            len(receipts) == 1,
            "Only explicit inventory release completes its actual UI read",
            receipts,
        )

    result = driver.run_scenario(tmp_path / "run", "held-route-trust", body)
    assert result["pass"], result["failures"]


@pytest.mark.timeout(100)
@pytest.mark.parametrize(
    "body", [late_mutation, old_paint], ids=["old-mutation", "old-paint"]
)
def test_real_transport_race_retains_old_payload_and_actual_new_authority(
    tmp_path, body
):
    result = driver.run_scenario(tmp_path / "run", "race-trust", body)
    assert result["pass"], result["failures"]
    events = json.loads((tmp_path / "run/evidence.json").read_text())
    identity = json.loads((tmp_path / "run/identity.json").read_text())
    assert (
        identity["cleanup"]["port_closed"]
        and identity["cleanup"]["private_data_removed"]
    )
    assert not identity["cleanup"]["remaining_owned_browser_pids"]
    if body is late_mutation:
        held = next(
            row
            for row in events
            if row.get("race") == "old mutation success after newer authority"
        )
        assert held["released"] and held["method"] == "PATCH"
        assert json.loads(held["body"])["etag"] != held["authority_at_release"]["etag"]
        assert held["captured_at"] < held["released_at"]
    else:
        acks = [
            row["ack"]
            for row in events
            if row.get("fixture_injection") == "held native displayed acknowledgement"
        ]
        assert len({row["token"]["revision"] for row in acks}) >= 2
        assert all(
            row["type"] == "render_ack" and row["status"] == "displayed" for row in acks
        )


def test_held_response_release_keeps_followup_requests_routable():
    from types import SimpleNamespace

    removed, fulfilled, continued = [], [], []
    held = object.__new__(HeldResponse)
    held.label, held.pattern, held.record = "config", "**/api/v3/config", {}
    held.response = object()
    held.route = SimpleNamespace(fulfill=lambda **kwargs: fulfilled.append(kwargs))
    held.page = SimpleNamespace(unroute=lambda *args: removed.append(args))
    held.rig = SimpleNamespace(config=lambda: {"etag": "current"})
    held.release()
    assert fulfilled and held.record["released"]
    assert removed == []
    held.capture(SimpleNamespace(continue_=lambda: continued.append(True)))
    assert continued == [True]
