"""Actual UI journeys, ported from the source-matched functional handoff."""

import json
import time
import urllib.request
from PIL import Image
from playwright.sync_api import expect

from _redesign_edge_cases import task_tab


def review_forget(rig, page):
    subject = page.locator("#tablet-label-form").get_attribute("data-device-id")
    for attempt in range(3):
        rig.open_disclosures(page.locator("#tablet-forget-preview"))
        page.locator("#tablet-forget-preview").click()
        page.wait_for_function("""() => !document.querySelector('#tablet-forget-preview').disabled
            && (!document.querySelector('#tablet-forget-impact').hidden
                || document.querySelector('#tablet-action-message').textContent.includes('A newer update arrived. Refresh this task.'))""")
        if page.locator("#tablet-forget-impact").is_visible():
            break
        rig.events.append({"operator_read_recovery": "Forget impact refused a newer update; explicitly refresh status before reviewing again", "attempt": attempt + 1})
        sheet = page.locator("#device-sheet")
        modal = sheet.get_attribute("data-modal") == "true"
        if modal:
            page.locator("#device-sheet-close").click()
        with page.expect_response("**/api/v3/config") as response:
            page.locator("#btn-roster-refresh").click()
        response.value.finished()
        page.evaluate("()=>new Promise(requestAnimationFrame)")
        if modal:
            page.locator(f'#device-list .dev-pick[data-device-id="{subject}"]').click()
    expect(page.locator("#tablet-forget-impact")).to_be_visible()


def parity(rig):
    page = rig.page
    base = rig.base
    RUN = rig.private
    tablets = rig.tablets
    manifest = rig.manifest
    requests = rig.requests
    errors = rig.errors
    config = rig.config
    check = rig.check
    shot = rig.shot
    ids = sorted(
        config()["runtime"]["devices"],
        key=lambda id: config()["runtime"]["devices"][id]["number"],
    )

    def task(name):
        if page.locator("#device-sheet").get_attribute("data-modal") == "true":
            page.locator("#device-sheet-close").click()
        rig.task(name)

    def pick(id):
        page.locator(f'#device-list .dev-pick[data-device-id="{id}"]').click()

    def wait_config(predicate, description):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = config()
            if predicate(current):
                check(True, description)
                return current
            page.wait_for_timeout(50)
        check(False, description)

    def showing(count=4):
        expect(page.locator("#btn-wall-health")).to_have_attribute(
            "aria-label", f"{count} of {count} tablets showing the current image. Issues.", timeout=10000
        )

    def grid_preview():
        page.locator("#grid-preview").click()
        expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview", timeout=10000)
        expect(page.locator("#stage-svg .slot")).to_have_count(4)

    def apply():
        page.locator("#btn-apply").click()
        expect(page.locator("body")).to_have_attribute("data-stage-mode", "live", timeout=10000)

    def save_arrangement(name):
        task("Saved")
        page.locator("#layout-name").fill(name)
        page.locator("#btn-layout-save").click()
        expect(page.locator("#layout-msg")).to_contain_text("saved", timeout=10000)

    def save_scene(name):
        task("Saved")
        page.locator("#scene-name").fill(name)
        page.locator("#scene-save").click()
        expect(page.locator("#scene-message")).to_contain_text(
            "Content saved", timeout=10000
        )

    def recall(name):
        task("Saved")
        page.get_by_role(
            "button", name=f"Recall arrangement “{name}”", exact=True
        ).click()
        expect(page.locator("#layout-msg")).to_contain_text("recalled", timeout=10000)

    page.locator("#grid-1x4").click()
    grid_preview()
    check(
        len(config()["layout"]["placements"]) == 0,
        "Quick grid preview leaves committed geometry empty",
    )
    check(
        page.locator("#stage-svg .slot[data-preview=true]").count() == 4,
        "Preview tiles carry preview state instead of live paint proof",
    )
    page.locator("#view-toggle").click()
    expect(page.locator("#stage-svg .slot")).to_have_count(0)
    page.locator("#view-toggle").click()
    expect(page.locator("#stage-svg .slot")).to_have_count(4)
    task("Images")
    expect(page.locator("#draft-resolution")).to_be_visible()
    page.locator("#resolve-stay").click()
    expect(task_tab(page, "Arrange")).to_have_attribute(
        "aria-selected", "true"
    )
    task("Images")
    page.locator("#resolve-discard").click()
    expect(task_tab(page, "Images")).to_have_attribute(
        "aria-selected", "true"
    )
    check(
        config()["layout"]["placements"] == {},
        "Stay and Discard resolve a grid without writing geometry or content",
    )
    task("Arrange")
    page.locator("#grid-kind").select_option("physical")
    rig.open_disclosures(page.locator("#group-model"))
    page.locator("#group-model").select_option("google-pixel-c")
    rig.open_disclosures(page.locator("#group-hardware"))
    page.locator("#group-hardware").check()
    rig.open_disclosures(page.locator("#group-confirm"))
    page.locator("#group-confirm").click()
    expect(page.locator("#group-result")).to_contain_text(
        "Untouched · none", timeout=15000
    )
    check(
        all(config()["tablet_assignments"][id]["mode"] == "explicit" for id in ids),
        "Captured group confirms all four hardware identities",
    )
    rig.open_disclosures(page.locator("#grid-common-mount"))
    page.locator("#grid-common-mount").select_option("0")
    page.locator("#grid-1x4").click()
    grid_preview()
    shot(page, "03-measured-preview")
    apply()
    wait_config(
        lambda c: c["layout"]["kind"] == "physical" and len(c["layout"]["slots"]) == 4,
        "Measured arrangement applied once through the grid command",
    )
    check(
        all(
            s["mount_angle"] == 0
            and s["profile_revision"] >= 1
            and s["calibration_revision"] >= 1
            for s in config()["layout"]["slots"].values()
        ),
        "Explicit common mount and exact measurement pins persisted",
    )
    manifest["measured_config"] = config()
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').click()
    task("Arrange")
    pins_before = {
        id: (slot["profile_revision"], slot["calibration_revision"])
        for id, slot in config()["layout"]["slots"].items()
    }
    old_x = config()["layout"]["slots"][ids[-1]]["center_x_mm"]
    rig.open_disclosures(page.locator("#slot-center-x"))
    page.locator("#slot-center-x").fill(str(old_x + 20))
    page.locator("#slot-center-x").press("Tab")
    rig.open_disclosures(page.locator("#slot-angle"))
    page.locator("#slot-angle").fill("180")
    page.locator("#slot-angle").press("Tab")
    rig.open_disclosures(page.locator("#btn-nudge-y-plus"))
    page.locator("#btn-nudge-y-plus").click()
    apply()
    check(
        config()["layout"]["slots"][ids[-1]]["mount_angle"] == 180
        and config()["layout"]["slots"][ids[-1]]["nudge_y_mm"] == 1,
        "Measured position, mounted rotation and nudge apply through one geometry command",
    )
    rig.open_disclosures(page.locator("#bounds-mode"))
    page.locator("#bounds-mode").select_option("fixed")
    rig.open_disclosures(page.locator("#bounds-width"))
    page.locator("#bounds-width").fill(str(config()["layout"]["bounds"]["width"] + 40))
    page.locator("#bounds-width").press("Tab")
    apply()
    check(
        config()["layout"]["sizing"]["mode"] == "fixed",
        "Measured fixed bounds remain manually editable",
    )
    rig.open_disclosures(page.locator("#bounds-mode"))
    page.locator("#bounds-mode").select_option("tablets")
    rig.open_disclosures(page.locator("#pack-columns"))
    page.locator("#pack-columns").fill("4")
    rig.open_disclosures(page.locator("#pack-gap"))
    page.locator("#pack-gap").fill("5")
    rig.open_disclosures(page.locator("#btn-pack-tablets"))
    page.locator("#btn-pack-tablets").click()
    apply()
    check(
        config()["layout"]["sizing"]["mode"] == "tablets",
        "Measured packing and fit bounds are reachable in Arrange",
    )
    task("Tablets")
    pick(ids[-1])
    rig.open_disclosures(page.locator("#tablet-participation"))
    page.locator("#tablet-participation").uncheck()
    task("Arrange")
    apply()
    check(
        config()["layout"]["slots"][ids[-1]]["participating"] is False,
        "Participation is a geometry draft until Apply",
    )
    task("Tablets")
    rig.open_disclosures(page.locator("#tablet-participation"))
    page.locator("#tablet-participation").check()
    task("Arrange")
    apply()
    task("Arrange")
    for angle in ["90", "270"]:
        rig.open_disclosures(page.locator("#grid-common-mount"))
        page.locator("#grid-common-mount").select_option(angle)
        page.locator("#grid-preview").click()
        expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
        submitted = json.loads(
            [r for r in requests if r["url"].endswith("/api/v3/grid/preview")][-1][
                "body"
            ]
        )
        check(
            set(submitted["mount_angles"].values()) == {int(angle)},
            "Explicit common mounted rotation "
            + angle
            + " overrides stored values without guessing",
        )
    page.locator("#btn-cancel").click()
    check(
        page.locator("#grid-common-mount").input_value() == "",
        "Discard clears the common mount declaration and preserves the applied mounting",
    )
    task("Tablets")
    pick(ids[0])
    task("Settings")
    page.locator("#measurement-details").evaluate("details=>details.open=true")
    rig.open_disclosures(page.locator("#profile-active-width"))
    page.locator("#profile-active-width").fill("148.5")
    rig.open_disclosures(page.locator("#btn-profile-save"))
    page.locator("#btn-profile-save").click()
    expect(page.locator("#profile-msg")).to_contain_text("Saved profile")
    check(
        {
            id: (slot["profile_revision"], slot["calibration_revision"])
            for id, slot in config()["layout"]["slots"].items()
        }
        == pins_before,
        "Newly saved measurement history leaves exact current layout pins unchanged",
    )
    save_arrangement("Original measured")
    task("Images")
    page.get_by_role("button", name="Preview supplied.png", exact=True).click()
    page.locator("#image-fit").select_option("contain")
    before = config()
    page.locator("#show-image").click()
    showing()
    check(
        config()["layout"] == before["layout"],
        "Show image changes content and preserves the applied geometry",
    )
    shot(page, "04-image-shown-desktop")
    shot(tablets[0], "04-client-current-slice")
    manifest["image_shown_config"] = config()
    task("Tablets")
    pick(ids[0])
    tablets[0].set_viewport_size({"width": 930, "height": 1280})
    expect(page.locator("#tablet-recovery")).to_contain_text(
        "calibrated", timeout=10000
    )
    expect(page.locator("#open-tablet-measurements")).to_be_visible()
    tablets[0].set_viewport_size({"width": 900, "height": 1280})
    showing()
    check(
        True,
        "Measured viewport mismatch links to screen setup and restoring the recorded viewport obtains fresh current paint",
    )
    task("Images")
    for ext, color in [("png", (34, 145, 90)), ("jpg", (60, 80, 200))]:
        filename = RUN / ("upload-" + ext + "." + ext)
        Image.new("RGB", (640, 480), color).save(filename)
        before = config()
        rig.open_disclosures(page.locator("#upload-file"))
        page.locator("#upload-file").set_input_files(str(filename))
        rig.open_disclosures(page.locator("#upload-submit"))
        page.locator("#upload-submit").click()
        expect(page.locator("#upload-message")).to_contain_text(
            "Image added and selected", timeout=15000
        )
        expect(page.get_by_role("button", name=f"Preview upload-{ext}.{ext}", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#show-image")).to_be_enabled(timeout=10000)
        check(
            config()["scene"] == before["scene"]
            and config()["layout"] == before["layout"],
            f"Actual {ext} upload selects locally and never auto-shows",
        )
        page.locator("#image-fit").select_option("cover" if ext == "png" else "contain")
        selected_asset = page.locator("#selected-image-controls").get_attribute("data-asset-id")
        page.locator("#show-image").click()
        wait_config(lambda c: c["scene"]["content"]["asset"] == selected_asset, "Show commits the exact uploaded asset before the next upload")
        showing()
    save_scene("Landscape")
    task("Tablets")
    pick(ids[0])
    page.locator("#tablet-label").fill("Lobby left")
    pick(ids[1])
    page.locator("#tablet-label").fill("Lobby right pending")
    pick(ids[0])
    expect(page.locator("#tablet-label")).to_have_value("Lobby left")
    page.locator("#tablet-label").focus()
    page.locator("#tablet-label").evaluate("input => input.setSelectionRange(3,6)")
    page.locator("#btn-roster-refresh").dispatch_event("click")
    page.wait_for_timeout(150)
    check(
        page.locator("#tablet-label").evaluate(
            "input => document.activeElement===input && input.selectionStart===3 && input.selectionEnd===6"
        ),
        "Runtime reconciliation preserves focused name input and caret",
    )
    page.locator("#tablet-label-save").click()
    wait_config(
        lambda c: c["device_labels"].get(ids[0]) == "Lobby left",
        "Name saved for its captured tablet identity",
    )
    pick(ids[1])
    expect(page.locator("#tablet-label")).to_have_value("Lobby right pending")
    page.locator("#tablet-label-discard").click()
    pick(ids[0])
    task("Settings")
    page.locator("#measurement-details").evaluate("details => details.open=true")
    rig.open_disclosures(page.locator("#profile-active-width"))
    page.locator("#profile-active-width").fill("148.25")
    rig.open_disclosures(page.locator("#cal-viewport-width"))
    page.locator("#cal-viewport-width").fill("887")
    rig.open_disclosures(page.locator("#tablet-model"))
    page.locator("#tablet-model").select_option("manual")
    task("Tablets")
    pick(ids[1])
    task("Settings")
    check(
        page.locator("#profile-active-width").input_value() != "148.25",
        "Tablet B never inherits tablet A measurement fields",
    )
    task("Tablets")
    pick(ids[0])
    task("Settings")
    expect(page.locator("#profile-active-width")).to_have_value("148.25")
    expect(page.locator("#cal-viewport-width")).to_have_value("887")
    expect(page.locator("#tablet-model")).to_have_value("manual")
    check(
        True,
        "Profile, calibration and model choice retain exact drafts across tablet and task switches",
    )
    for group in ["profile", "calibration", "model"]:
        page.locator("#discard-" + group).click()
    task("Arrange")
    page.locator("#grid-kind").select_option("logical")
    page.locator("#grid-1x4").click()
    grid_preview()
    apply()
    wait_config(
        lambda c: c["layout"]["kind"] == "logical",
        "Cross-kind quick arrangement succeeds with a real safety copy",
    )
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').click()
    rig.open_disclosures(page.locator("#logical-mode"))
    page.locator("#logical-mode").select_option("fixed")
    rig.open_disclosures(page.locator("#logical-width"))
    page.locator("#logical-width").fill("1200")
    page.locator("#logical-width").press("Tab")
    rig.open_disclosures(page.locator("#logical-height"))
    page.locator("#logical-height").fill("800")
    page.locator("#logical-height").press("Tab")
    page.locator("#logical-w").fill("84")
    page.locator("#logical-w").press("Tab")
    page.locator("#logical-bezel-left").fill("2")
    page.locator("#logical-bezel-left").press("Tab")
    page.locator("#btn-undo").click()
    expect(page.locator("#logical-bezel-left")).to_have_value("0")
    page.locator("#btn-redo").click()
    expect(page.locator("#logical-bezel-left")).to_have_value("2")
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').focus()
    page.wait_for_timeout(1200)
    check(
        page.locator("#stage-svg .logical-resize").evaluate(
            "node=>document.activeElement===node.closest('.slot')"
        ),
        "Runtime reconciliation keeps the same resize handle and focused stage tablet",
    )
    w_before = page.locator("#logical-w").input_value()
    handle = page.locator("#stage-svg .logical-resize")
    expect(handle).to_be_visible()
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        box["x"] + box["width"] / 2 + 20, box["y"] + box["height"] / 2 + 10, steps=4
    )
    page.keyboard.press("Escape")
    page.mouse.up()
    expect(page.locator("#logical-w")).to_have_value(w_before)
    expect(handle).to_be_visible()
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        box["x"] + box["width"] / 2 + 20, box["y"] + box["height"] / 2 + 10, steps=4
    )
    page.mouse.up()
    check(
        float(page.locator("#logical-w").input_value()) > float(w_before),
        "Logical pointer resize changes the selected tablet and Escape restores a cancelled resize",
    )
    page.locator("#btn-undo").click()
    x_before = page.locator("#logical-x").input_value()
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').focus()
    page.keyboard.press("Shift+ArrowRight")
    check(
        float(page.locator("#logical-x").input_value()) == float(x_before) + 10,
        "Shift-arrow nudges only the selected stage tablet",
    )
    page.locator("#btn-undo").click()
    rig.open_disclosures(page.locator("#logical-rotate"))
    page.locator("#logical-rotate").click()
    expect(page.locator("#logical-h")).to_have_value(w_before)
    page.locator("#btn-undo").click()
    page.locator(".logical-tiling").evaluate("details=>details.open=true")
    rig.open_disclosures(page.locator("#logical-tile-columns"))
    page.locator("#logical-tile-columns").fill("2")
    rig.open_disclosures(page.locator("#logical-tile-rows"))
    page.locator("#logical-tile-rows").fill("2")
    rig.open_disclosures(page.locator("#logical-tile-gap"))
    page.locator("#logical-tile-gap").fill("10")
    rig.open_disclosures(page.locator("#logical-tile-order"))
    page.locator("#logical-tile-order").select_option("id")
    rig.open_disclosures(page.locator("#logical-pack"))
    page.locator("#logical-pack").click()
    rig.open_disclosures(page.locator("#logical-tile-shape"))
    page.locator("#logical-tile-shape").select_option("keep")
    rig.open_disclosures(page.locator("#logical-tile"))
    page.locator("#logical-tile").click()
    apply()
    logical = config()["layout"]
    check(
        logical["width"] == 1200
        and logical["height"] == 800
        and logical["placements"][ids[-1]]["bezel"]["left"] == 2,
        "Primary custom logical size, bezel, undo/redo, pack, tile and fixed bounds persist",
    )
    save_arrangement("Relative custom")
    check(
        page.locator("#return-point-name").inner_text() != "",
        "Real server-returned cross-kind return point is offered directly",
    )
    relative_saved = config()["layout"]
    content_saved = config()["scene"]
    page.locator("#return-point-recall").click()
    wait_config(
        lambda c: c["layout"]["kind"] == "physical",
        "Direct Recall return point restores the actual server-created arrangement",
    )
    check(
        config()["scene"] == content_saved,
        "Return point recall preserves current content",
    )
    recall("Relative custom")
    check(
        config()["layout"] == relative_saved,
        "Saved custom relative geometry recalls after returning from a measured arrangement",
    )
    page.get_by_role("button", name="Preview content “Landscape”", exact=True).click()
    expect(page.locator("#show-image")).to_have_text("Show saved content")
    before = config()
    page.locator("#show-image").click()
    showing()
    check(
        config()["layout"] == before["layout"],
        "Saved scene Show recalls content while retaining custom logical geometry",
    )
    task("Settings")
    page.locator("#diagnostic-colour").fill("#246344")
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/v3/config") and response.request.method == "GET"
        )
    ):
        page.locator("#diagnostic-colour-one").click()
        expect(page.locator("#diagnostic-colour-message")).to_contain_text(
            "Diagnostic colour set"
        )
    page.locator("#diagnostic-colour-refresh").click()
    expect(page.locator("#diagnostic-colour-message")).to_contain_text("#246344")
    check(
        config()["layout"] == before["layout"],
        "Diagnostic test colour is reachable and does not replace layout authority",
    )
    before_saved = config()
    save_scene("Disposable scene")
    save_scene("Disposable scene")
    page.get_by_role(
        "button", name="Delete content “Disposable scene”", exact=True
    ).click()
    expect(
        page.get_by_role("button", name="Preview content “Disposable scene”", exact=True)
    ).to_have_count(0)
    save_arrangement("Disposable arrangement")
    save_arrangement("Disposable arrangement")
    page.get_by_role(
        "button", name="Delete arrangement “Disposable arrangement”", exact=True
    ).click()
    expect(
        page.get_by_role(
            "button", name="Recall arrangement “Disposable arrangement”", exact=True
        )
    ).to_have_count(0)
    check(
        config()["layout"] == before_saved["layout"]
        and config()["scene"] == before_saved["scene"],
        "Explicit overwrite and delete for both Saved kinds preserve applied geometry and content",
    )
    task("Settings")
    page.locator("#diagnostic-colour").fill("#654321")
    page.locator("#diagnostic-colour-all").click()
    expect(page.locator("#diagnostic-colour-message")).to_contain_text(
        "all currently registered tablets"
    )
    colours = json.load(urllib.request.urlopen(base + "/devices"))
    check(
        all(colours[id]["color"] == "#654321" for id in ids),
        "Explicit all-tablet colour command targets all four registrations",
    )
    before_pattern = config()
    page.get_by_text("Check patterns", exact=True).click()
    rig.open_disclosures(page.locator("#show-colours"))
    page.locator("#show-colours").click()
    wait_config(
        lambda c: c["scene"]["content"]["type"] == "color",
        "Show tablet colours is an explicit content command",
    )
    check(
        config()["layout"] == before_pattern["layout"],
        "Colour display preserves custom logical geometry",
    )
    task("Images")
    rig.open_disclosures(page.locator("#restore-image"))
    page.locator("#restore-image").click()
    showing()
    check(
        config()["scene"]["content"]["asset"]
        == before_pattern["scene"]["content"]["asset"],
        "Restore previous content obtains four fresh current image reports",
    )
    task("Settings")
    page.locator("#experimental-opt-in").check()
    expect(page.locator("#experimental-controls")).to_be_visible()
    check(
        "Experimental playback"
        in page.locator("#experimental-opt-in")
        .locator("xpath=ancestor::section[1]")
        .inner_text(),
        "Existing playlist and playback controls remain reachable and marked Experimental",
    )
    page.locator("#experimental-opt-in").uncheck()
    page.set_viewport_size({"width": 390, "height": 844})
    task("Images")
    phone_image = RUN / "phone-added.png"
    Image.new("RGB", (720, 480), (45, 125, 145)).save(phone_image)
    rig.open_disclosures(page.locator("#upload-file"))
    page.locator("#upload-file").set_input_files(str(phone_image))
    before_phone = config()
    rig.open_disclosures(page.locator("#upload-submit"))
    page.locator("#upload-submit").click()
    expect(page.locator("#upload-message")).to_contain_text("added and selected")
    check(
        config()["scene"] == before_phone["scene"],
        "Admitted phone viewport upload selects without auto-showing",
    )
    page.locator("#show-image").click()
    showing()
    save_scene("Phone scene")
    save_arrangement("Phone custom")
    tablets[3].close()
    wait_config(
        lambda c: not c["runtime"]["devices"][ids[3]]["online"],
        "Phone recovery sees an offline reserved position",
    )
    task("Tablets")
    pick(ids[3])
    expect(page.locator("#tablet-reconnect")).to_be_disabled()
    expect(page.locator("#tablet-recovery")).to_contain_text("power")
    review_forget(rig, page)
    rig.open_disclosures(page.locator("#tablet-forget-cancel"))
    page.locator("#tablet-forget-cancel").click()
    check(
        page.locator("#tablet-forget-preview").evaluate(
            "node=>document.activeElement===node"
        ),
        "Phone Forget cancellation returns focus to its trigger without changing the wall",
    )
    new_client = tablets[3].context.new_page()
    new_client.on("pageerror", lambda e: errors.append("client: " + str(e)))
    new_client.goto(base + "/client/")
    tablets[3] = new_client
    showing()
    check(
        new_client.evaluate("()=>localStorage.getItem('tablet-wall-device-id')")
        == ids[3],
        "Reopened shipped client retains identity and needs a fresh paint report",
    )
    manifest["phone_shown_config"] = config()
    task("Images")
    shot(page, "05-phone-images")
    page.set_viewport_size({"width": 320, "height": 700})
    task("Tablets")
    shot(page, "06-phone-tablets-320")
    page.set_viewport_size({"width": 1440, "height": 900})
    for arrangement in ["Original measured", "Relative custom"]:
        recall(arrangement)
        task("Tablets")
        for id in [ids[1], ids[2], ids[0], ids[3]]:
            pick(id)
            rig.open_disclosures(page.locator("#tablet-remove"))
            page.locator("#tablet-remove").click()
            wait_config(
                lambda c: (
                    id
                    not in (
                        c["layout"].get("slots")
                        if c["layout"]["kind"] == "physical"
                        else c["layout"].get("placements")
                    )
                ),
                "Remove lifecycle succeeds for " + id[:8],
            )
        c = config()
        check(
            not (
                c["layout"].get("slots")
                if c["layout"]["kind"] == "physical"
                else c["layout"].get("placements")
            )
            and len(c["runtime"]["devices"]) == 4,
            "Final removal leaves an empty "
            + c["layout"]["kind"]
            + " wall and retains registrations",
        )
    recall("Original measured")
    task("Settings")
    rig.open_disclosures(page.locator("#clear-wall"))
    page.locator("#clear-wall").click()
    wait_config(
        lambda c: not c["layout"]["slots"],
        "Explicit Clear wall endpoint clears positions and preserves registrations",
    )
    check(
        all(
            r["url"].split(base)[-1].startswith("/api/v3/devices/")
            for r in requests
            if r["url"].endswith("/remove")
        ),
        "Removal requests use the dedicated lifecycle route",
    )
    shot(page, "07-settings-after-clear")
    manifest["final_config"] = config()
    check(
        not errors,
        "No JavaScript page errors in the full rendered journey: " + repr(errors),
    )


def edges(rig):
    page = rig.page
    browser = rig.browser
    base = rig.base
    RUN = rig.private
    contexts = rig.contexts
    tablets = rig.tablets
    manifest = rig.manifest
    errors = rig.errors
    config = rig.config
    check = rig.check
    shot = rig.shot
    ids = [
        p.evaluate("() => localStorage.getItem('tablet-wall-device-id')")
        for p in tablets
    ]

    def task(name):
        if page.locator("#device-sheet").get_attribute("data-modal") == "true":
            page.locator("#device-sheet-close").click()
        rig.task(name)

    def pick(id):
        page.locator(f'#device-list .dev-pick[data-device-id="{id}"]').click()

    def wait_config(predicate, description):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            c = config()
            if predicate(c):
                check(True, description)
                return c
            page.wait_for_timeout(50)
        check(False, description)

    def preview():
        page.locator("#grid-preview").click()
        expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")

    def apply():
        page.locator("#btn-apply").click()
        expect(page.locator("body")).to_have_attribute("data-stage-mode", "live", timeout=10000)

    def row(id):
        return page.locator(f'#grid-order li[data-device-id="{id}"]')

    rig.open_disclosures(row(ids[1]).locator("input[type=checkbox]"))
    row(ids[1]).locator("input[type=checkbox]").uncheck()
    row(ids[0]).locator("summary").click()
    rig.open_disclosures(row(ids[0]).locator("input[data-field=w]"))
    row(ids[0]).locator("input[data-field=w]").fill("77")
    tablets[1].reload()
    wait_config(
        lambda c: c["runtime"]["devices"][ids[1]]["online"],
        "Excluded tablet reconnects through its shipped client",
    )
    expect(row(ids[1]).locator("input[type=checkbox]")).not_to_be_checked()
    expect(row(ids[0]).locator("input[data-field=w]")).to_have_value("77")
    check(True, "Intentional exclusion and manually entered size survive reconnect")
    rig.open_disclosures(row(ids[1]).get_by_role("button", name="Include Tablet 2", exact=True))
    row(ids[1]).get_by_role("button", name="Include Tablet 2", exact=True).click()
    fifth_context = browser.new_context(
        viewport={"width": 900, "height": 1280},
        screen={"width": 900, "height": 1280},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    contexts.append(fifth_context)
    rig.observe(fifth_context, "fifth-tablet")
    fifth_context.add_init_script(
        "Object.defineProperty(screen.orientation,'angle',{get:()=>270,configurable:true})"
    )
    fifth = fifth_context.new_page()
    fifth.goto(base + "/client/")
    fifth_id = fifth.evaluate("() => localStorage.getItem('tablet-wall-device-id')")
    manifest["clients"].append(
        {
            "id": fifth_id,
            "context": "fifth-tablet",
            "viewport": fifth.viewport_size,
            "DPR": 2,
            "orientation_override": 270,
            "synthetic_signature": True,
        }
    )
    expect(row(fifth_id).locator("input[type=checkbox]")).not_to_be_checked()
    expect(row(fifth_id).get_by_role("button", name="Include Tablet 5", exact=True)).to_be_visible()
    check(
        row(fifth_id)
        .get_by_role("button", name="Include Tablet 5", exact=True)
        .is_visible(),
        "New join after an edit is explicitly available through Include",
    )
    page.locator("#grid-1x4").click()
    page.locator("#grid-rebuild").click()
    expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    other_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    contexts.append(other_ctx)
    rig.observe(other_ctx, "second-operator")
    other = other_ctx.new_page()
    other.on("dialog", lambda d: d.accept())
    other.goto(base + "/controller/physical.html")
    task_tab(other, "Tablets").click()
    other.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]').click()
    other.locator("#tablet-label").fill("Other operator")
    other.locator("#tablet-label-save").click()
    expect(page.locator("#conflict-panel")).to_be_visible()
    expect(page.locator("#btn-apply")).to_be_disabled()
    expect(page.locator("#stage-svg .slot")).to_have_count(4)
    check(
        config()["layout"]["placements"] == {},
        "Second operator conflict keeps the original preview and blocks apply",
    )
    page.locator("#grid-rebuild").click()
    expect(page.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    apply()
    task("Tablets")
    pick(ids[0])
    page.locator("#tablet-label").fill("Submitted A")

    def hold_name(route):
        response = route.fetch()
        page.locator("#tablet-label").fill("Newer A retained")
        pick(ids[1])
        page.locator("#tablet-label").fill("Pending B retained")
        route.fulfill(response=response)

    page.route("**/api/v3/devices/" + ids[0], hold_name, times=1)
    page.locator("#tablet-label-save").click()
    expect(page.locator("#tablet-label")).to_have_value("Pending B retained")
    page.wait_for_timeout(150)
    check(
        config()["device_labels"][ids[0]] == "Submitted A"
        and page.locator("#tablet-label-form").get_attribute("data-dirty") == "true",
        "Delayed A save preserves the currently selected B edit",
    )
    pick(ids[0])
    expect(page.locator("#tablet-label")).to_have_value("Newer A retained")
    check(
        page.locator("#tablet-label-form").get_attribute("data-dirty") == "true",
        "Delayed save cannot mark a newer edit on A clean",
    )
    page.locator("#tablet-label-discard").click()
    pick(ids[1])
    page.locator("#tablet-label-discard").click()
    pick(ids[0])
    page.locator("#tablet-label").fill("My reviewed name")
    other.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]').click()
    other.locator("#tablet-label").fill("Remote name")
    other.locator("#tablet-label-save").click()
    expect(page.locator("#tablet-action-message")).to_contain_text("changed elsewhere")
    page.locator("#tablet-label-review").click()
    expect(page.locator("#tablet-name-comparison")).to_contain_text("Remote name")
    page.locator("#tablet-name-keep").click()
    page.locator("#tablet-label-save").click()
    wait_config(
        lambda c: c["device_labels"][ids[0]] == "My reviewed name",
        "Explicit comparison retains my name and guards a separate Save against reviewed authority",
    )
    task("Arrange")
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').click()
    page.locator("#logical-x").fill("230")
    page.locator("#logical-x").press("Tab")
    task_tab(other, "Tablets").click()
    other.locator(f'#device-list .dev-pick[data-device-id="{ids[2]}"]').click()
    other.locator("#tablet-label").fill("Manual conflict source")
    other.locator("#tablet-label-save").click()
    expect(page.locator("#btn-apply")).to_be_disabled()
    page.locator("#btn-review-arrangement").click()
    expect(page.locator("#manual-arrangement-review")).to_be_visible()
    page.locator("#manual-review-keep").click()
    expect(page.locator("#btn-apply")).to_be_enabled()
    apply()
    check(
        config()["layout"]["placements"][ids[-1]]["x"] == 230,
        "Manual conflict requires an explicit comparison and keeps the exact proposed geometry",
    )
    task("Arrange")
    page.locator(f'#stage-svg .slot[data-device-id="{ids[-1]}"]').click()
    page.locator("#logical-x").fill("240")
    page.locator("#logical-x").press("Tab")
    scene_before = config()["scene"]
    task("Images")
    page.locator("#resolve-commit").click()
    expect(task_tab(page, "Images")).to_have_attribute(
        "aria-selected", "true"
    )
    check(
        config()["scene"] == scene_before,
        "Resolve Apply arrangement writes geometry without a hidden content commit",
    )
    page.get_by_role("button", name="Preview supplied.png", exact=True).click()
    layout_before = config()["layout"]
    task("Arrange")
    expect(page.locator("#resolve-commit")).to_have_text("Show image")
    page.locator("#resolve-commit").click()
    expect(task_tab(page, "Arrange")).to_have_attribute(
        "aria-selected", "true"
    )
    check(
        config()["layout"] == layout_before,
        "Resolve Show image writes content without a hidden geometry commit",
    )
    task("Saved")
    page.locator("#scene-name").fill("Missing source")
    page.locator("#scene-save").click()
    expect(page.locator("#scene-message")).to_contain_text("Content saved")
    missing_asset = config()["scene"]["content"]["asset"]
    (RUN / "assets" / "supplied.png").unlink()
    task("Images")
    page.locator("#refresh-images").click()
    expect(page.locator("#stage-mode-label")).to_contain_text("Unavailable")
    expect(page.locator("#show-image")).to_be_disabled()
    check(
        config()["layout"] == layout_before
        and config()["scene"]["content"]["asset"] == missing_asset,
        "Missing applied image retains geometry and unavailable content identity",
    )
    replacement = RUN / "replacement.png"
    Image.new("RGB", (700, 400), (210, 130, 30)).save(replacement)
    rig.open_disclosures(page.locator("#upload-file"))
    page.locator("#upload-file").set_input_files(str(replacement))
    rig.open_disclosures(page.locator("#upload-submit"))
    page.locator("#upload-submit").click()
    expect(page.locator("#upload-message")).to_contain_text("added and selected")
    page.locator("#show-image").click()
    expect(page.locator("#wall-health")).to_contain_text(
        "4 of 4 showing the current image", timeout=10000
    )
    check(True, "Missing image recovers through actual Add image, preview and Show")
    task("Saved")
    page.locator("#layout-name").fill("Before swap")
    page.locator("#btn-layout-save").click()
    expect(page.locator("#layout-msg")).to_contain_text("saved")
    tablets[1].close()
    wait_config(
        lambda c: not c["runtime"]["devices"][ids[1]]["online"],
        "Old tablet is offline before replacement review",
    )
    task("Tablets")
    pick(fifth_id)
    rig.open_disclosures("#replacement-offer")
    expect(page.locator("#replacement-offer")).to_be_visible()
    page.locator("#replacement-old").select_option(ids[1])
    page.locator("#replacement-open").click()
    expect(page.locator("#replace-target")).to_have_value(fifth_id)
    rig.open_disclosures(page.locator("#replace-hardware"))
    page.locator("#replace-hardware").select_option("same_hardware")
    rig.open_disclosures(page.locator("#replace-preview"))
    page.locator("#replace-preview").click()
    expect(page.locator("#replace-apply")).to_be_enabled()
    shot(page, "edge-replacement-review")
    rig.open_disclosures(page.locator("#replace-apply"))
    page.locator("#replace-apply").click()
    wait_config(
        lambda c: (
            fifth_id in c["layout"]["placements"]
            and ids[1] not in c["layout"]["placements"]
        ),
        "Contextual same-hardware replacement updates the captured old/new identities",
    )
    task("Saved")
    page.get_by_role(
        "button", name="Recall arrangement “Before swap”", exact=True
    ).click()
    expect(page.locator("#layout-msg")).to_contain_text("recalled")
    check(
        fifth_id in config()["layout"]["placements"],
        "Exactly selected saved arrangement recalls the replacement registration",
    )
    tablets[2].close()
    wait_config(
        lambda c: not c["runtime"]["devices"][ids[2]]["online"],
        "Forget subject is offline",
    )
    task("Tablets")
    pick(ids[2])
    rig.open_disclosures(page.locator("#tablet-forget-preview"))
    review_forget(rig, page)
    rig.open_disclosures(page.locator("#tablet-forget-confirm"))
    page.locator("#tablet-forget-confirm").click()
    expect(page.locator("#tablet-action-message")).to_contain_text("acknowledge")
    rig.open_disclosures(page.locator("#tablet-forget-active"))
    page.locator("#tablet-forget-active").check()
    rig.open_disclosures(page.locator("#tablet-forget-confirm"))
    page.locator("#tablet-forget-confirm").click()
    wait_config(
        lambda c: (
            ids[2] not in c["runtime"]["devices"]
            and ids[2] not in c["layout"]["placements"]
        ),
        "Explicit offline Forget removes registration and active slot after impact acknowledgement",
    )
    check(
        any(
            ids[2] in item["layout"]["placements"]
            for item in json.load(
                urllib.request.urlopen(base + "/api/v3/logical-layouts")
            )["layouts"]
            if item["name"] == "Before swap"
        ),
        "Forget keeps saved reservations",
    )
    shot(page, "edge-after-forget")
    manifest["edge_final_config"] = config()
    check(
        not errors,
        "No JavaScript page errors in rendered conflict and recovery checks: "
        + repr(errors),
    )


def batch(rig):
    page = rig.page
    browser = rig.browser
    base = rig.base
    contexts = rig.contexts
    tablets = rig.tablets
    manifest = rig.manifest
    requests = rig.requests
    responses = rig.responses
    errors = rig.errors
    config = rig.config
    check = rig.check
    shot = rig.shot
    ids = [
        client.evaluate("()=>localStorage.getItem('tablet-wall-device-id')")
        for client in tablets
    ]
    other_context = browser.new_context(viewport={"width": 1440, "height": 900})
    contexts.append(other_context)
    rig.observe(other_context, "second-operator")
    other = other_context.new_page()
    other.goto(base + "/controller/physical.html")
    expect(other.locator("#device-list .dev-pick")).to_have_count(4)

    def conflict_before_third(route):
        task_tab(other, "Tablets").click()
        other.locator("#btn-roster-refresh").click()
        other.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]').click()
        other.locator("#tablet-label").fill("Concurrent batch edit")
        other.locator("#tablet-label-save").click()
        expect(other.locator("#tablet-action-message")).to_contain_text("Name saved")
        route.continue_()

    page.route("**/api/v3/tablet-assignments/" + ids[2], conflict_before_third, times=1)
    page.locator("#grid-kind").select_option("physical")
    rig.open_disclosures(page.locator("#group-model"))
    page.locator("#group-model").select_option("google-pixel-c")
    rig.open_disclosures(page.locator("#group-hardware"))
    page.locator("#group-hardware").check()
    rig.open_disclosures(page.locator("#group-confirm"))
    page.locator("#group-confirm").click()
    expect(page.locator("#group-result")).to_contain_text(
        "Failed / conflict · Tablet 3", timeout=15000
    )
    expect(page.locator("#group-result")).to_contain_text("Untouched · Tablet 4")
    expect(page.locator("#group-subjects")).to_have_text(
        "Unresolved hardware confirmation · Tablet 3 · Tablet 4"
    )
    expect(page.locator("#group-hardware")).not_to_be_checked()
    check(
        len([r for r in requests if "/tablet-assignments/" in r["url"]]) == 3,
        "Real external durable change refuses the third model assignment and leaves tablet four untouched",
    )
    check(
        responses[1]["if_match"] == responses[0]["returned_etag"]
        and responses[2]["if_match"] == responses[1]["returned_etag"],
        "Actual sequential model requests use the preceding returned ETag",
    )
    shot(page, "batch-partial-review")
    rig.open_disclosures(page.locator("#group-hardware"))
    page.locator("#group-hardware").check()
    rig.open_disclosures(page.locator("#group-confirm"))
    page.locator("#group-confirm").click()
    expect(page.locator("#group-result")).to_contain_text(
        "Untouched · none", timeout=10000
    )
    assignments = [r for r in requests if "/tablet-assignments/" in r["url"]]
    counts = {id: sum(r["url"].endswith(id) for r in assignments) for id in ids}
    check(
        counts == dict(zip(ids, [1, 1, 2, 1])),
        "Explicit retry reviews and writes only unresolved subjects, never the completed first two",
    )
    check(
        all(config()["tablet_assignments"][id]["mode"] == "explicit" for id in ids),
        "Partial model batch recovers to all four confirmed assignments",
    )
    manifest["batch_result"] = counts
    check(not errors, "No JavaScript errors in the actual partial model batch journey")
