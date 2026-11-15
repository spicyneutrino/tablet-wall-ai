"""Drive setup using its filled actions and record the four honest wall states."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port-range", default="44220-44229")
    args = parser.parse_args()
    os.environ["TABLET_WALL_RENEWAL_PORT_RANGE"] = args.port_range
    from playwright.sync_api import expect, sync_playwright
    from simulator.browser import renewal_acceptance as ra

    args.out.mkdir(parents=True)
    rig = ra.RenewalRig(args.out, "images-workbench", ra.REPO, {})
    records, presses = [], []

    def primary(expected):
        buttons = rig.page.locator(".btn-primary:visible")
        expect(buttons).to_have_count(1)
        expect(buttons).to_have_attribute("id", expected)
        expect(buttons).to_be_enabled()
        presses.append(expected)
        buttons.click()

    def capture(state, expected):
        page = rig.page
        for width, height in [(1440, 900), (390, 844)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(200)
            expect(page.locator(".btn-primary:visible")).to_have_count(0 if state == "S3" else 1)
            if state != "S3":
                expect(page.locator(".btn-primary:visible")).to_have_attribute("id", expected)
            assert page.locator("body").get_attribute("data-test-live") == "false"
            records.append({"state": state, "viewport": [width, height],
                            "primary": expected, "tally": page.locator(".stage-tally").inner_text(),
                            "commit": page.locator("#draft-state").inner_text()})
            page.screenshot(path=str(args.out / f"{state}-{width}x{height}.png"))
        page.set_viewport_size({"width": 1440, "height": 900})

    with sync_playwright() as pw:
        try:
            rig.setup(pw)
            page = rig.page
            capture("S0", "first-wall-join-action")
            primary("first-wall-join-action")
            expect(page.locator("#copy-tablet-url")).to_be_focused()
            clients = [rig.new_client(ra.CLIENT_SPECS[0], i) for i in range(6)]
            expect(page.locator("#empty-title")).to_have_text("6 tablets waiting to be arranged")
            expect(page.locator("#join-strip")).to_be_hidden()
            capture("S1", "first-wall-arrange-action")
            primary("first-wall-arrange-action")
            expect(page.locator("#grid-preview")).to_be_focused()
            primary("grid-preview")
            expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
            primary("btn-apply")
            expect(page.locator("body")).to_have_attribute("data-stage-mode", "live")
            config = rig.config()
            layout = config["layout"]
            assert len(layout["placements"]) == len(clients) == 6
            assert len({slot["x"] for slot in layout["placements"].values()}) == 3
            assert len({slot["y"] for slot in layout["placements"].values()}) == 2
            expect(page.locator("#draft-state")).to_have_text("No image yet · tablet colours")
            capture("S2", "first-wall-image-action")
            primary("first-wall-image-action")
            assert page.evaluate("!!document.activeElement.closest('#image-gallery') || document.activeElement.id === 'image-search'")
            page.locator("#image-gallery .image-choice-button").first.click()
            primary("show-image")
            expect(page.locator("#setup-strip")).to_be_hidden()
            expect(page.locator("#wall-health")).to_contain_text("6 of 6")
            capture("S3", None)
            assert rig.config()["scene"]["content"]["type"] == "image"
            assert not rig.page_errors, rig.page_errors
        except Exception:
            if rig.page and not rig.page.is_closed():
                rig.page.screenshot(path=str(args.out / "failure.png"))
                (args.out / "failure.txt").write_text(rig.page.locator("body").inner_text())
            raise
        finally:
            cleanup = rig.close()
            result = {"states": records, "filled_action_presses": presses,
                      "page_errors": rig.page_errors, "console": rig.console,
                      "network": rig.network, "cleanup": cleanup}
            (args.out / "first-run.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"PASS: {len(records)} state/viewport checks; {len(presses)} filled-action presses; no page errors")


if __name__ == "__main__":
    main()
