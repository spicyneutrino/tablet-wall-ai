"""Bounded transport races and native-input acceptance on disposable shipped clients."""

from copy import deepcopy
import json
import time

from playwright.sync_api import expect


def ids(rig):
    return [client["id"] for client in rig.manifest["clients"]]


def task(page, name):
    page.get_by_role("tab", name=name, exact=True).click()


def pick(page, device):
    page.locator(f'.dev-pick[data-device-id="{device}"]').click()


def refreshed(page):
    with page.expect_response("**/api/v3/config"):
        page.locator("#btn-roster-refresh").click()
    expect(page.locator("body")).to_have_attribute("data-connection", "current")


def second_operator(rig):
    context = rig.browser.new_context(viewport={"width": 1440, "height": 900})
    rig.contexts.append(context)
    rig.observe(context, "second-operator")
    page = context.new_page()
    page.set_default_timeout(7000)
    page.goto(rig.base + "/controller/physical.html")
    expect(page.locator("#device-count")).to_contain_text(str(len(ids(rig))))
    return page


def save_name(page, device, name):
    task(page, "Tablets")
    pick(page, device)
    page.locator("#tablet-label").fill(name)
    page.locator("#tablet-label-save").click()
    expect(page.locator("#tablet-action-message")).to_contain_text("Name saved")


class HeldResponse:
    """Keep a real response until an explicit release, without sleeping in callbacks."""

    def __init__(self, rig, page, pattern, label):
        self.rig, self.page, self.pattern, self.label = rig, page, pattern, label
        self.route = self.response = None
        self.record = {"race": label, "released": False}
        rig.events.append(self.record)
        page.route(pattern, self.capture)

    def capture(self, route):
        from redesign_acceptance import request_body

        if self.route is not None:
            route.continue_()
            return
        self.route = route
        self.response = route.fetch(timeout=15000)
        self.record.update(
            url=route.request.url,
            method=route.request.method,
            if_match=route.request.headers.get("if-match"),
            request_body=request_body(route.request),
            status=self.response.status,
            body=self.response.text(),
            captured_at=time.monotonic(),
        )

    def wait(self):
        from redesign_acceptance import wait_until

        wait_until(lambda: self.record.get("captured_at"), self.page.wait_for_timeout)

    def release(self, **response_fields):
        if not self.response:
            raise AssertionError("No captured response: " + self.label)
        self.route.fulfill(response=self.response, **response_fields)
        self.page.unroute(self.pattern, self.capture)
        self.record["response_overrides"] = response_fields
        self.record.update(
            released=True,
            released_at=time.monotonic(),
            authority_at_release=self.rig.config(),
        )


def quick_wall(rig):
    p = rig.page
    task(p, "Arrange")
    p.locator("#grid-1x4").click()
    p.locator("#grid-preview").click()
    expect(p.locator("#grid-message")).to_contain_text("Preview only")
    p.locator("#btn-apply").click()
    expect(p.locator("#stage-mode-label")).to_have_text("Applied configuration")
    rig.check(
        len(rig.config()["layout"]["placements"]) == 4,
        "Real UI applies a relative four-tablet fixture",
    )


def show_supplied(rig):
    task(rig.page, "Images")
    rig.page.get_by_role("button", name="Preview supplied.png", exact=True).click()
    rig.page.locator("#show-image").click()
    expect(rig.page.locator("#wall-health")).to_contain_text(
        "4 of 4 showing", timeout=15000
    )


def measured_wall(rig):
    from redesign_acceptance import first_wall

    first_wall(rig)
    task(rig.page, "Arrange")


def pointer_drag(rig):
    measured_wall(rig)
    p, device = rig.page, ids(rig)[0]
    tile = p.locator(f'#stage-svg .slot[data-device-id="{device}"]')
    tile.click()
    before = rig.config()
    old = float(p.locator("#slot-center-x").input_value())
    body = tile.locator(".operator-body-outline")
    body.scroll_into_view_if_needed()
    box = body.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 3
    scale = body.evaluate("e=>e.getScreenCTM().a")
    p.mouse.move(x, y)
    p.mouse.down()
    p.mouse.move(x + 2, y + 1)
    rig.check(
        p.locator("#btn-apply").is_disabled(),
        "Physical pointer threshold leaves a two-pixel move clean",
    )
    p.mouse.move(x + 31, y + 11, steps=5)
    delta = float(p.locator("#slot-center-x").input_value()) - old
    rig.check(
        abs(delta - 31 / scale) < 0.06 and rig.config()["layout"] == before["layout"],
        "Physical pointer movement agrees with rendered millimetre transform and stays local",
        {"delta_mm": delta, "expected_mm": 31 / scale},
    )
    p.keyboard.press("Escape")
    p.mouse.up()
    rig.check(
        abs(float(p.locator("#slot-center-x").input_value()) - old) < 0.01
        and p.locator("#btn-apply").is_disabled(),
        "Escape cancels captured physical drag without durable changes",
    )
    p.mouse.move(x, y)
    p.mouse.down()
    p.mouse.move(x + 25, y + 9, steps=4)
    p.mouse.up()
    proposed = float(p.locator("#slot-center-x").input_value())
    p.locator("#btn-apply").click()
    expect(p.locator("#stage-mode-label")).to_have_text("Applied configuration")
    current = rig.config()
    rig.check(
        abs(current["layout"]["slots"][device]["center_x_mm"] - proposed) < 0.01
        and all(
            current["layout"]["slots"][key]["profile_revision"]
            == before["layout"]["slots"][key]["profile_revision"]
            and current["layout"]["slots"][key]["calibration_revision"]
            == before["layout"]["slots"][key]["calibration_revision"]
            for key in ids(rig)
        ),
        "Physical drag commits reviewed position with all exact measurement pins",
    )
    task(p, "Settings")
    rig.dialog_accept = False
    count = len(rig.requests)
    rig.open_disclosures(p.locator("#clear-wall"))
    p.locator("#clear-wall").click()
    rig.check(
        rig.config()["layout"] == current["layout"]
        and not any(r["url"].endswith("/layout/clear") for r in rig.requests[count:]),
        "Native Clear cancellation sends no command and preserves the wall",
    )
    rig.dialog_accept = True
    rig.viewport_shots("physical-drag-clear-cancel")


def snap_spacing(rig):
    quick_wall(rig)
    p, device = rig.page, ids(rig)[1]
    tile = p.locator(f'#stage-svg .slot[data-device-id="{device}"]')
    tile.click()
    rig.open_disclosures(p.locator("#logical-snap"))
    p.locator("#logical-snap").fill("10")
    body = tile.locator(".operator-body-outline")
    body.scroll_into_view_if_needed()
    box = body.bounding_box()
    scale = body.evaluate("e=>e.getScreenCTM().a")
    x, y = box["x"] + box["width"] / 3, box["y"] + box["height"] / 3
    before = rig.config()
    p.mouse.move(x, y)
    rig.events.append(
        {
            "pointer_fixture": {
                "box": box,
                "scale": scale,
                "hit": p.evaluate(
                    "([x,y])=>document.elementFromPoint(x,y)?.outerHTML", [x, y]
                ),
            }
        }
    )
    p.mouse.down()
    p.mouse.move(x + 17 * scale, y + 14 * scale)
    p.mouse.up()
    actual = [p.locator("#logical-" + axis).input_value() for axis in ("x", "y")]
    rig.check(
        actual == ["90", "10"] and rig.config()["layout"] == before["layout"],
        "Native logical pointer movement snaps 17 by 14 units to explicit ten-unit spacing",
        actual,
        ["90", "10"],
    )
    p.locator("#btn-undo").click()
    rig.check(
        p.locator("#logical-x").input_value() == "70",
        "Snapped pointer drag is one undoable draft operation",
    )
    p.locator("#btn-redo").click()
    p.locator("#btn-apply").click()
    expect(p.locator("#stage-mode-label")).to_have_text("Applied configuration")
    rig.check(
        rig.config()["layout"]["placements"][device]["x"] == 90,
        "Snapped draft applies through the guarded arrangement action",
    )


def command_variants(rig):
    measured_wall(rig)
    p, device = rig.page, ids(rig)[0]
    task(p, "Tablets")
    pick(p, device)
    before = rig.config()
    p.locator("#tablet-reconnect").click()
    expect(p.locator("#tablet-action-message")).to_contain_text("keeps its identity")
    from redesign_acceptance import wait_until

    wait_until(
        lambda: (
            rig.config()["runtime"]["devices"][device]["render"]["current"]
            and rig.config()["runtime"]["devices"][device]["render"]["accepted_token"][
                "connection_id"
            ]
            != before["runtime"]["devices"][device]["render"]["accepted_token"][
                "connection_id"
            ]
        ),
        p.wait_for_timeout,
        timeout=20,
    )
    rig.check(
        rig.tablets[0].evaluate("localStorage.getItem('tablet-wall-device-id')")
        == device,
        "Explicit online Reconnect obtains a new current token while keeping browser identity",
    )
    rig.tablets[0].close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][device]["online"],
        p.wait_for_timeout,
    )
    expect(p.locator("#tablet-identify")).to_be_disabled()
    expect(p.locator("#tablet-retry-image")).to_be_disabled()
    expect(p.locator("#tablet-reconnect")).to_be_disabled()
    rig.check(
        device in rig.config()["layout"]["slots"]
        and not rig.config()["runtime"]["devices"][device]["render"]["current"],
        "Offline reservation disables Identify Retry and Reconnect and drops current paint evidence",
    )
    task(p, "Arrange")
    row = p.locator(f'#grid-order li[data-device-id="{device}"]')
    rig.open_disclosures(row.locator("input[type=checkbox]"))
    row.locator("input[type=checkbox]").uncheck()
    reopened = rig.tablets[0].context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[0] = reopened
    wait_until(
        lambda: rig.config()["runtime"]["devices"][device]["online"], p.wait_for_timeout
    )
    rig.check(
        not row.locator("input[type=checkbox]").is_checked(),
        "Intentional grid exclusion survives same-storage reconnect",
    )
    rig.viewport_shots("offline-reconnect-commands")


def batch_uncertain(rig):
    p, subjects = rig.page, ids(rig)
    p.locator("#grid-kind").select_option("physical")
    rig.open_disclosures(p.locator("#group-model"))
    p.locator("#group-model").select_option("google-pixel-c")
    rig.open_disclosures(p.locator("#group-hardware"))
    p.locator("#group-hardware").check()

    def committed_abort(route):
        response = route.fetch()
        rig.events.append(
            {
                "race": "second assignment committed before lost response",
                "status": response.status,
                "committed": response.json(),
            }
        )
        route.abort("connectionreset")

    with rig.fault(
        "postcommit assignment response lost", [(r"/tablet-assignments/", ["network"])]
    ):
        p.route("**/api/v3/tablet-assignments/" + subjects[1], committed_abort, times=1)
        rig.open_disclosures(p.locator("#group-confirm"))
        p.locator("#group-confirm").click()
        expect(p.locator("#group-result")).to_contain_text(
            "Completion uncertain", timeout=20000
        )
        requests = [r for r in rig.requests if "/tablet-assignments/" in r["url"]]
        current = rig.config()["tablet_assignments"]
        rig.check(
            len(requests) == 2
            and current[subjects[0]]["mode"]
            == current[subjects[1]]["mode"]
            == "explicit"
            and current[subjects[2]]["mode"] != "explicit",
            "Uncertain batch stops after lost second response and reconciles actual partial commits",
            p.locator("#group-result").inner_text(),
        )
        rig.check(
            not p.locator("#group-hardware").is_checked()
            and "Tablet 2" in p.locator("#group-subjects").inner_text(),
            "Uncertain batch requires a new declaration for captured unresolved subjects",
        )
        rig.open_disclosures(p.locator("#group-hardware"))
        p.locator("#group-hardware").check()
        rig.open_disclosures(p.locator("#group-confirm"))
        p.locator("#group-confirm").click()
        expect(p.locator("#group-result")).to_contain_text(
            "Untouched · none", timeout=20000
        )
        counts = {
            device: sum(
                r["url"].endswith(device)
                for r in rig.requests
                if "/tablet-assignments/" in r["url"]
            )
            for device in subjects
        }
        rig.check(
            list(counts.values()) == [1, 2, 1, 1],
            "Only explicitly reviewed unresolved batch subjects retry",
            counts,
        )


def batch_selection(rig):
    p, subjects = rig.page, ids(rig)
    p.locator("#grid-kind").select_option("physical")
    rig.open_disclosures(p.locator("#group-model"))
    p.locator("#group-model").select_option("google-pixel-c")
    rig.open_disclosures(p.locator("#group-hardware"))
    p.locator("#group-hardware").check()
    held = HeldResponse(
        rig,
        p,
        "**/api/v3/tablet-assignments/" + subjects[0],
        "captured batch versus changed selection",
    )
    rig.open_disclosures(p.locator("#group-confirm"))
    p.locator("#group-confirm").click()
    held.wait()
    row = p.locator(
        f'#grid-order li[data-device-id="{subjects[-1]}"] input[type=checkbox]'
    )
    row.uncheck()
    task(p, "Tablets")
    pick(p, subjects[2])
    held.release()
    task(p, "Arrange")
    expect(p.locator("#group-result")).to_contain_text(
        "Untouched · none", timeout=20000
    )
    actual = [
        r["url"].rsplit("/", 1)[-1]
        for r in rig.requests
        if "/tablet-assignments/" in r["url"]
    ]
    rig.check(
        actual == subjects and not row.is_checked(),
        "Delayed model batch keeps original four subjects despite changed grid and inspector selection",
        actual,
        subjects,
    )
    rig.check(
        all(
            rig.config()["tablet_assignments"][device]["mode"] == "explicit"
            for device in subjects
        ),
        "Captured batch outcomes are attached to every original subject",
    )


def mixed_models(rig):
    p, subjects = rig.page, ids(rig)
    task(p, "Tablets")
    pick(p, subjects[0])
    task(p, "Settings")
    p.locator("#measurement-details > summary").click()
    rig.open_disclosures(p.locator("#tablet-model"))
    p.locator("#tablet-model").select_option("ipad-air-2")
    rig.open_disclosures(p.locator("#apply-tablet-model"))
    p.locator("#apply-tablet-model").click()
    from redesign_acceptance import wait_until

    wait_until(
        lambda: (
            rig.config()["tablet_assignments"][subjects[0]].get("model_id")
            == "ipad-air-2"
        ),
        p.wait_for_timeout,
    )
    rig.check(
        rig.config()["tablet_assignments"][subjects[0]]["model_id"] == "ipad-air-2",
        "Actual UI can declare a different hardware model without pretending viewport compatibility",
    )
    task(p, "Arrange")
    p.locator("#grid-kind").select_option("physical")
    assignments = deepcopy(rig.config()["tablet_assignments"])
    rig.check(
        p.locator("#group-model").input_value() == ""
        and not p.locator("#group-hardware").is_checked(),
        "Mixed model group is not automatically declared homogeneous",
    )
    rig.open_disclosures(p.locator("#group-confirm"))
    p.locator("#group-confirm").click()
    expect(p.locator("#group-result")).to_contain_text("checked their hardware")
    rig.check(
        rig.config()["tablet_assignments"] == assignments,
        "Missing hardware declaration never writes an incompatible model batch",
    )
    rig.open_disclosures(p.locator( f'#grid-order li[data-device-id="{subjects[0]}"] input[type=checkbox]' ))
    p.locator(
        f'#grid-order li[data-device-id="{subjects[0]}"] input[type=checkbox]'
    ).uncheck()
    rig.open_disclosures(p.locator("#group-model"))
    p.locator("#group-model").select_option("google-pixel-c")
    rig.open_disclosures(p.locator("#group-hardware"))
    p.locator("#group-hardware").check()
    rig.open_disclosures(p.locator("#group-confirm"))
    p.locator("#group-confirm").click()
    expect(p.locator("#group-result")).to_contain_text(
        "Untouched · none", timeout=15000
    )
    rig.open_disclosures(p.locator( f'#grid-order li[data-device-id="{subjects[0]}"] input[type=checkbox]' ))
    p.locator(
        f'#grid-order li[data-device-id="{subjects[0]}"] input[type=checkbox]'
    ).check()
    rig.open_disclosures(p.locator("#grid-common-mount"))
    p.locator("#grid-common-mount").select_option("0")
    p.locator("#grid-1x4").click()
    p.locator("#grid-preview").click()
    expect(p.locator("#grid-message")).to_contain_text("Preview only")
    p.locator("#btn-apply").click()
    expect(p.locator("#stage-mode-label")).to_have_text("Applied configuration")
    rig.check(
        rig.config()["tablet_assignments"][subjects[0]]["model_id"] == "ipad-air-2"
        and all(
            rig.config()["tablet_assignments"][device]["model_id"] == "google-pixel-c"
            for device in subjects[1:]
        ),
        "Explicit subgroup confirmation preserves mixed hardware assignments",
    )
    task(p, "Images")
    p.get_by_role("button", name="Preview supplied.png", exact=True).click()
    p.locator("#show-image").click()
    expect(p.locator("#wall-health")).to_contain_text("3 of 4 showing", timeout=15000)
    expect(rig.tablets[0].locator("#calibration-recovery")).to_be_visible()
    task(p, "Tablets")
    pick(p, subjects[0])
    rig.check(
        "calibrat" in p.locator("#tablet-recovery").inner_text().lower(),
        "Confirmed incompatible model still reports mapping setup required",
        p.locator("#tablet-recovery").inner_text(),
        fatal=False,
    )
    rig.viewport_shots("mixed-model-mapping-refusal")


def stale_reads(rig):
    from redesign_acceptance import wait_until

    quick_wall(rig)
    show_supplied(rig)
    p, device = rig.page, ids(rig)[0]
    task(p, "Tablets")
    pick(p, device)

    def fallback(route):
        response = route.fetch()
        payload = response.json()
        payload.pop("runtime", None)
        rig.events.append(
            {
                "fixture_injection": "v3 response without runtime invokes real fallback GET",
                "config": payload,
            }
        )
        route.fulfill(response=response, json=payload)

    p.route("**/api/v3/config", fallback, times=1)
    held = HeldResponse(
        rig, p, "**/devices", "fallback roster held across newer runtime"
    )
    p.locator("#btn-roster-refresh").click()
    held.wait()
    rig.tablets[0].close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][device]["online"],
        p.wait_for_timeout,
    )
    expect(p.locator("#tablet-evidence")).to_contain_text("Offline")
    held.release()
    expect(p.locator("#tablet-evidence")).to_contain_text("Offline")
    expect(p.locator("#wall-health")).to_contain_text("3 of 4 showing", timeout=15000)
    rig.check(
        not p.locator("#tablet-reconnect").is_enabled(),
        "Stale fallback roster cannot revive online commands or old paint after newer offline event",
    )
    task(p, "Settings")
    p.locator("#diagnostic-colour").fill("#123456")
    diagnostic = HeldResponse(
        rig, p, "**/devices", "diagnostic GET held across newer v3 runtime"
    )
    p.locator("#diagnostic-colour-refresh").click()
    diagnostic.wait()
    reopened = rig.tablets[0].context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[0] = reopened
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing", timeout=15000)
    diagnostic.release()
    expect(p.locator("#diagnostic-colour-message")).to_contain_text("newer update")
    rig.check(
        p.locator("#diagnostic-colour").input_value() == "#123456"
        and all(
            row["render"]["current"]
            for row in rig.config()["runtime"]["devices"].values()
        ),
        "Stale diagnostic colour GET is refused without overwriting edited colour or current v3 paint",
    )


def late_mutation(rig):
    p, subjects = rig.page, ids(rig)
    other = second_operator(rig)
    task(p, "Tablets")
    pick(p, subjects[0])
    p.locator("#tablet-label").fill("Committed older response A")
    held = HeldResponse(
        rig,
        p,
        "**/api/v3/devices/" + subjects[0],
        "old mutation success after newer authority",
    )
    p.locator("#tablet-label-save").click()
    held.wait()
    save_name(other, subjects[1], "Newer authority B")
    expect(p.locator("#device-list")).to_contain_text("Newer authority B")
    pick(p, subjects[2])
    p.locator("#tablet-label").fill("New unsaved C while A waits")
    newer = rig.config()
    held.release()
    expect(p.locator("#device-list")).to_contain_text("Newer authority B")
    expect(p.locator("#tablet-label")).to_have_value("New unsaved C while A waits")
    rig.check(
        json.loads(held.record["body"])["etag"] != newer["etag"]
        and p.locator("#tablet-label-form").get_attribute("data-dirty") == "true"
        and rig.config()["device_labels"][subjects[0]] == "Committed older response A",
        "Late real mutation success preserves newer authority and another subject's newer dirty input",
        {
            "old_etag": json.loads(held.record["body"])["etag"],
            "new_etag": newer["etag"],
            "field": p.locator("#tablet-label").input_value(),
        },
    )


def old_paint(rig):
    from redesign_acceptance import wait_until

    quick_wall(rig)
    show_supplied(rig)
    p, device, client = rig.page, ids(rig)[0], rig.tablets[0]
    client.close()
    held, bridges = [], []

    def bridge(ws):
        server = ws.connect_to_server()
        bridges.append(server)

        def receive(raw):
            value = json.loads(raw)
            if value.get("type") == "render_ack" and value.get("status") == "displayed":
                held.append((raw, value))
                rig.events.append(
                    {
                        "fixture_injection": "held native displayed acknowledgement",
                        "ack": value,
                    }
                )
            else:
                server.send(raw)

        ws.on_message(receive)

    client.context.route_web_socket("**/ws/*", bridge)
    reopened = client.context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[0] = reopened
    wait_until(lambda: held, p.wait_for_timeout)
    old = held[0]
    task(p, "Images")
    p.get_by_role("button", name="Preview supplied.png", exact=True).click()
    p.locator("#image-fit").select_option("contain")
    p.locator("#show-image").click()
    wait_until(
        lambda: any(
            row[1]["token"]["revision"] == rig.config()["revision"] for row in held
        ),
        p.wait_for_timeout,
    )
    before = rig.config()
    bridges[-1].send(old[0])
    with p.expect_response("**/api/v3/config"):
        task(p, "Tablets")
        p.locator("#btn-roster-refresh").click()
    latest = rig.config()
    rig.check(
        not latest["runtime"]["devices"][device]["render"]["current"]
        and old[1]["token"]
        != latest["runtime"]["devices"][device]["render"]["expected_token"]
        and sum(
            row["render"]["current"] for row in latest["runtime"]["devices"].values()
        )
        == 3,
        "Released old actual-client paint acknowledgement cannot confirm a newer scene or connection",
        {
            "old_ack": old[1],
            "new_runtime": latest["runtime"]["devices"][device],
            "before": before["revision"],
        },
    )
    newest = next(
        row
        for row in reversed(held)
        if row[1]["token"]["revision"] == latest["revision"]
    )
    bridges[-1].send(newest[0])
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing", timeout=15000)
    rig.check(
        rig.config()["runtime"]["devices"][device]["render"]["current"],
        "Only fresh exact native paint acknowledgement restores four current reports",
    )


def upload_timeout(rig):
    from redesign_acceptance import wait_until

    quick_wall(rig)
    p = rig.page
    task(p, "Images")
    from PIL import Image

    path = rig.private / "native-timeout.png"
    Image.new("RGB", (321, 197), (110, 30, 180)).save(path)
    source = path.read_bytes()
    held = HeldResponse(
        rig,
        p,
        "**/uploads?*",
        "real upload publication response held until native 120-second XHR timeout",
    )
    rig.open_disclosures(p.locator("#upload-file"))
    p.locator("#upload-file").set_input_files(
        {"name": "native-timeout.png", "mimeType": "image/png", "buffer": source}
    )
    before, started = rig.config(), time.monotonic()
    rig.open_disclosures(p.locator("#upload-submit"))
    p.locator("#upload-submit").click()
    held.wait()
    rig.check(
        held.response.status == 201,
        "Native timeout fixture sent bytes and real upload published before response loss",
        held.record,
    )
    with rig.fault(
        "native XHR timeout after actual publication", [(r"/uploads", ["network"])]
    ):
        wait_until(
            lambda: "uncertain" in p.locator("#upload-message").inner_text(),
            p.wait_for_timeout,
            timeout=126,
        )
        elapsed = time.monotonic() - started
        rig.check(
            118 <= elapsed <= 129
            and p.locator("#upload-submit").is_disabled()
            and rig.config()["scene"] == before["scene"],
            "Native unmodified 120-second XHR timeout locks retry and never shows content",
            {
                "elapsed_seconds": elapsed,
                "message": p.locator("#upload-message").inner_text(),
            },
        )
        held.release()
        p.locator("#refresh-images").click()
        expect(p.locator("#upload-submit")).to_be_enabled()
        rig.check(
            p.get_by_role(
                "button", name="Preview native-timeout.png", exact=True
            ).count()
            == 1,
            "Explicit inventory reconciliation discovers timed-out real publication without automatic duplicate upload",
        )


def inventory_order(rig):
    from redesign_acceptance import wait_until

    p = rig.page
    task(p, "Images")
    held = HeldResponse(
        rig,
        p,
        "**/api/v3/images",
        "old inventory held across actual successful upload and new inventory",
    )
    p.locator("#refresh-images").click()
    held.wait()
    from PIL import Image

    path = rig.private / "inventory-new.png"
    Image.new("RGB", (317, 193), (90, 30, 170)).save(path)
    rig.open_disclosures(p.locator("#upload-file"))
    p.locator("#upload-file").set_input_files(str(path))
    before = rig.config()
    rig.open_disclosures(p.locator("#upload-submit"))
    p.locator("#upload-submit").click()
    expect(p.locator("#upload-message")).to_contain_text(
        "added and selected", timeout=15000
    )
    expect(
        p.get_by_role("button", name="Preview inventory-new.png", exact=True)
    ).to_be_visible()
    selected = p.locator("#image-select").input_value()
    held.release()
    wait_until(
        lambda: not p.locator("#refresh-images").is_disabled(), p.wait_for_timeout
    )
    rig.check(
        p.locator("#image-select").input_value() == selected
        and p.get_by_role(
            "button", name="Preview inventory-new.png", exact=True
        ).get_attribute("aria-pressed")
        == "true"
        and rig.config()["scene"] == before["scene"],
        "Older real inventory response cannot remove a later upload or its selected asset identity",
        {"selected": selected, "old_inventory": json.loads(held.record["body"])},
    )


def upload_ambiguous(rig, malformed=False):
    from PIL import Image

    p = rig.page
    task(p, "Images")
    expect(
        p.get_by_role("button", name="Preview supplied.png", exact=True)
    ).to_be_visible()
    expect(p.locator("#refresh-images")).to_be_enabled()
    path = rig.private / "ambiguous.png"
    Image.new("RGB", (353, 211), (23, 144, 109)).save(path)
    source = path.read_bytes()
    rig.open_disclosures(p.locator("#upload-file"))
    p.locator("#upload-file").set_input_files(
        {"name": "ambiguous.png", "mimeType": "image/png", "buffer": source}
    )
    before = rig.config()
    with rig.fault("postpublication upload ambiguity", [(r"/uploads", [503])]):
        publication = HeldResponse(
            rig, p, "**/uploads?*", "actual publication held before ambiguous response"
        )
        rig.open_disclosures(p.locator("#upload-submit"))
        p.locator("#upload-submit").click()
        publication.wait()
        receipt = {
            "status": publication.response.status,
            "body": publication.response.json(),
        }
        old = HeldResponse(
            rig,
            p,
            "**/api/v3/images",
            "inventory started before ambiguous upload response must never unlock retry",
        )
        p.locator("#refresh-images").click()
        old.wait()
        rig.events.append(
            {
                "fixture_injection": "actual upstream publication then unreadable201"
                if malformed
                else "actual upstream publication then503",
                **receipt,
            }
        )
        if malformed:
            publication.release(
                status=201,
                content_type="application/json",
                body="{unreadable successful upload",
            )
        else:
            publication.release(
                status=503, json={"detail": "Synthetic postpublication failure"}
            )
        from redesign_acceptance import wait_until

        wait_until(
            lambda: (
                "refused" in p.locator("#upload-message").inner_text()
                or "uncertain" in p.locator("#upload-message").inner_text()
            ),
            p.wait_for_timeout,
        )
        at_response = {
            "message": p.locator("#upload-message").inner_text(),
            "retry_disabled": p.locator("#upload-submit").is_disabled(),
        }
        old.release()
        wait_until(
            lambda: not p.locator("#refresh-images").is_disabled(), p.wait_for_timeout
        )
        after_old = {"retry_disabled": p.locator("#upload-submit").is_disabled()}
        rig.check(
            receipt["status"] == 201 and bool(receipt["body"].get("asset")),
            "Ambiguous upload fixture proves actual publication before altered response",
            receipt,
        )
        rig.check(
            at_response["retry_disabled"] and "uncertain" in at_response["message"],
            "Unreadable successful upload locks retry as uncertain"
            if malformed
            else "Postpublication upload503 locks retry as uncertain",
            at_response,
            fatal=False,
        )
        rig.check(
            after_old["retry_disabled"],
            "Older in-flight inventory cannot unlock ambiguous upload retry",
            after_old,
            fatal=False,
        )
        with rig.fault(
            "explicit inventory refresh fails after uncertain upload",
            [(r"/api/v3/images", [503])],
        ):
            p.route(
                "**/api/v3/images",
                lambda route: route.fulfill(
                    status=503, json={"detail": "Synthetic reconciliation failure"}
                ),
                times=1,
            )
            p.locator("#refresh-images").click()
            expect(p.locator("#image-message")).to_contain_text("unavailable")
            rig.check(
                p.locator("#upload-submit").is_disabled(),
                "Failed explicit inventory refresh cannot unlock uncertain upload",
                fatal=False,
            )
        p.locator("#refresh-images").click()
        expect(p.locator("#image-message")).to_contain_text("images available")
        expect(p.locator("#upload-submit")).to_be_enabled()
        rig.check(
            rig.config()["scene"] == before["scene"]
            and rig.config()["layout"] == before["layout"]
            and sum(
                row["url"].split("?")[0].endswith("/uploads") for row in rig.requests
            )
            == 1,
            "Successful later explicit inventory refresh unlocks without automatic retry or Show",
        )
        rig.viewport_shots("ambiguous-upload-reconciled")


def upload_unreadable(rig):
    upload_ambiguous(rig, malformed=True)


def stale_scene(rig):
    quick_wall(rig)
    show_supplied(rig)
    p, other = rig.page, second_operator(rig)
    task(p, "Saved")
    p.locator("#scene-name").fill("Guarded scene")
    p.locator("#scene-save").click()
    expect(p.locator("#scene-message")).to_contain_text("Scene saved")
    p.get_by_role("button", name="Preview scene “Guarded scene”", exact=True).click()
    old_guard = rig.config()["etag"]
    task(other, "Settings")
    other.get_by_text("Check patterns", exact=True).click()
    rig.open_disclosures(other.locator("#show-colours"))
    other.locator("#show-colours").click()
    expect(other.locator("#active-image")).to_contain_text("Tablet colours")
    task(other, "Saved")
    other.locator("#scene-name").fill("Guarded scene")
    other.locator("#scene-save").click()
    expect(other.locator("#scene-message")).to_contain_text("Scene saved")
    before = rig.config()
    with rig.fault(
        "saved scene changed after real preview", [(r"/scenes/.*/recall", [412])]
    ):
        p.locator("#show-image").click()
        expect(p.locator("#image-message")).to_contain_text("Could not show")
        sent = [
            r
            for r in rig.requests
            if r["url"].endswith("/scenes/Guarded%20scene/recall")
        ]
        rig.check(
            bool(sent)
            and sent[-1]["if_match"] == old_guard
            and rig.config()["scene"] == before["scene"]
            and rig.config()["layout"] == before["layout"],
            "Saved scene Show retains original preview guard and refuses changed snapshot without substituting content",
            sent,
        )


def missing_live(rig):
    quick_wall(rig)
    show_supplied(rig)
    p = rig.page
    before = rig.config()
    rig.events.append(
        {
            "fixture_injection": "remove only private supplied image bytes",
            "asset": before["scene"]["content"]["asset"],
        }
    )
    (rig.private / "assets/supplied.png").unlink()
    with rig.fault(
        "private live image bytes missing",
        [(r"/(assets|media)/", [404, "network"])],
        [(r"/client/client\.js", r"\[tablet-wall\] image scene failed: .*")],
    ):
        task(p, "Tablets")
        pick(p, ids(rig)[0])
        rig.tablets[0].route("**/assets/**", lambda route: route.continue_())
        rig.tablets[0].reload()
        expect(p.locator("#wall-health")).to_contain_text(
            "3 of 4 showing", timeout=15000
        )
        task(p, "Images")
        p.locator("#refresh-images").click()
        expect(p.locator("#active-image")).to_contain_text("Unavailable")
        rig.check(
            rig.config()["scene"]["content"]["asset"]
            == before["scene"]["content"]["asset"]
            and not rig.config()["runtime"]["devices"][ids(rig)[0]]["render"][
                "current"
            ],
            "Missing actual live image preserves scene identity and marks failed client evidence",
        )
        rig.viewport_shots("missing-live-image")
        from PIL import Image

        path = rig.private / "live-replacement.png"
        Image.new("RGB", (377, 199), (20, 130, 100)).save(path)
        rig.open_disclosures(p.locator("#upload-file"))
        p.locator("#upload-file").set_input_files(str(path))
        rig.open_disclosures(p.locator("#upload-submit"))
        p.locator("#upload-submit").click()
        expect(p.locator("#upload-message")).to_contain_text(
            "added and selected", timeout=15000
        )
        p.locator("#show-image").click()
        expect(p.locator("#wall-health")).to_contain_text(
            "4 of 4 showing", timeout=15000
        )
        rig.check(
            rig.config()["layout"] == before["layout"]
            and rig.config()["scene"]["content"]["asset"]
            != before["scene"]["content"]["asset"],
            "Same Images upload preview Show path replaces missing live bytes with four fresh actual paints",
        )


def save_arrangement(page, name):
    task(page, "Saved")
    page.locator("#layout-name").fill(name)
    page.locator("#btn-layout-save").click()
    expect(page.locator("#layout-msg")).to_contain_text("saved")


def replacement_fixture(rig):
    from redesign_acceptance import wait_until

    measured_wall(rig)
    p, old = rig.page, ids(rig)[0]
    save_arrangement(p, "Exact reservation")
    rig.tablets[0].close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][old]["online"],
        p.wait_for_timeout,
    )
    fresh = rig.new_tablet(4)
    target = fresh.evaluate("localStorage.getItem('tablet-wall-device-id')")
    task(p, "Tablets")
    pick(p, old)
    rig.open_disclosures(p.locator("#replace-target"))
    p.locator("#replace-target").select_option(target)
    rig.open_disclosures(p.locator("#replace-hardware"))
    p.locator("#replace-hardware").select_option("same_hardware")
    selected = p.locator('#replace-saved input[data-name="Exact reservation"]')
    expect(selected).to_be_checked()
    return old, target, fresh


def different_hardware(rig):
    old, target, _ = replacement_fixture(rig)
    p = rig.page
    task(p, "Tablets")
    pick(p, target)
    task(p, "Settings")
    p.locator("#measurement-details > summary").click()
    rig.open_disclosures(p.locator("#tablet-model"))
    p.locator("#tablet-model").select_option("ipad-air-2")
    rig.open_disclosures(p.locator("#apply-tablet-model"))
    p.locator("#apply-tablet-model").click()
    from redesign_acceptance import wait_until

    wait_until(
        lambda: (
            rig.config()["tablet_assignments"][target].get("model_id") == "ipad-air-2"
        ),
        p.wait_for_timeout,
    )
    task(p, "Tablets")
    pick(p, old)
    rig.open_disclosures(p.locator("#replace-target"))
    p.locator("#replace-target").select_option(target)
    before = rig.config()
    rig.open_disclosures(p.locator("#replace-hardware"))
    p.locator("#replace-hardware").select_option("different_hardware")
    rig.open_disclosures(p.locator("#replace-preview"))
    p.locator("#replace-preview").click()
    expect(p.locator("#tablet-action-message")).to_contain_text(
        "physical_rebuild_required"
    )
    rig.check(
        p.locator("#replace-apply").is_disabled()
        and rig.config()["layout"] == before["layout"]
        and [row for row in rig.config()["calibrations"] if row["device_id"] == target]
        == [row for row in before["calibrations"] if row["device_id"] == target],
        "Different hardware replacement refuses inherited physical calibration and preserves exact old reservations",
        {
            "old": old,
            "target": target,
            "message": p.locator("#tablet-action-message").inner_text(),
        },
    )
    rig.viewport_shots("different-hardware-refusal")
    rig.open_disclosures(p.locator("#replace-active"))
    p.locator("#replace-active").uncheck()
    rig.open_disclosures(p.locator('#replace-saved input[data-name="Exact reservation"]'))
    p.locator('#replace-saved input[data-name="Exact reservation"]').uncheck()
    rig.open_disclosures(p.locator("#replace-preview"))
    p.locator("#replace-preview").click()
    expect(p.locator("#replace-apply")).to_be_enabled()
    rig.check(
        "Different hardware; physical measurements are not inherited"
        in p.locator("#replace-summary").inner_text(),
        "Different hardware identity-only review explicitly excludes physical measurement inheritance",
    )
    rig.open_disclosures(p.locator("#replace-cancel"))
    p.locator("#replace-cancel").click()


def replacement_connection(rig):
    from redesign_acceptance import wait_until

    old, target, fresh = replacement_fixture(rig)
    p = rig.page
    rig.open_disclosures(p.locator("#replace-preview"))
    p.locator("#replace-preview").click()
    expect(p.locator("#replace-apply")).to_be_enabled()
    plan = json.loads(p.locator("#replace-technical").text_content())
    before = rig.config()
    fresh.close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][target]["online"],
        p.wait_for_timeout,
    )
    replacement = fresh.context.new_page()
    replacement.goto(rig.base + "/client/")
    rig.tablets[-1] = replacement
    wait_until(
        lambda: rig.config()["runtime"]["devices"][target]["online"], p.wait_for_timeout
    )
    wait_until(
        lambda: any(
            row.get("page") == "tablet-5"
            and isinstance(row.get("payload"), dict)
            and row["payload"].get("type") == "welcome"
            and row["payload"].get("connection_id") != plan["new_connection_id"]
            for row in rig.events
        ),
        p.wait_for_timeout,
    )
    new_connection = next(
        row["payload"]["connection_id"]
        for row in reversed(rig.events)
        if row.get("page") == "tablet-5"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("type") == "welcome"
    )
    expect(p.locator("#replace-apply")).to_be_disabled()
    current = rig.config()
    rig.check(
        plan["new_connection_id"] != new_connection
        and before["etag"] == current["etag"]
        and current["layout"] == before["layout"]
        and old in current["runtime"]["devices"],
        "Exact replacement connection guard invalidates review on same-storage reconnect without durable ETag change",
        {
            "plan": plan,
            "new_connection": new_connection,
            "summary": p.locator("#replace-summary").inner_text(),
        },
    )
    rig.check(
        not any(r["url"].endswith("/rebind") for r in rig.requests),
        "Stale replacement connection plan never reaches commit transport",
    )


def replacement_digest(rig):
    old, target, _ = replacement_fixture(rig)
    p, other = rig.page, second_operator(rig)
    rig.open_disclosures(p.locator("#replace-preview"))
    p.locator("#replace-preview").click()
    expect(p.locator("#replace-apply")).to_be_enabled()
    old_saved = next(
        row
        for row in rig.config()["snapshots"]["layouts"]
        if row["name"] == "Exact reservation"
    )
    captured = {}

    def change_digest(route):
        captured["original_request"] = json.loads(route.request.post_data)
        task(other, "Arrange")
        other.locator(f'#stage-svg .slot[data-device-id="{ids(rig)[1]}"]').focus()
        other.keyboard.press("ArrowRight")
        other.locator("#btn-apply").click()
        expect(other.locator("#stage-mode-label")).to_have_text("Applied configuration")
        save_arrangement(other, "Exact reservation")
        latest = rig.config()
        captured.update(
            after_external=latest,
            original_if_match=route.request.headers.get("if-match"),
            adversarial_if_match=latest["etag"],
        )
        response = route.fetch(
            headers={**route.request.headers, "if-match": latest["etag"]}
        )
        captured.update(status=response.status, response=response.json())
        rig.events.append(
            {
                "fixture_injection": "adversarially advance only global guard to isolate exact saved-digest validation",
                **captured,
            }
        )
        route.fulfill(response=response)

    with rig.fault(
        "changed exact saved digest reaches real rebind validation",
        [(r"/rebind$", [412])],
    ):
        p.route("**/api/v3/devices/" + target + "/rebind", change_digest, times=1)
        rig.open_disclosures(p.locator("#replace-apply"))
        p.locator("#replace-apply").click()
        expect(p.locator("#tablet-action-message")).to_contain_text("failed")
        actual = rig.config()
        new_saved = next(
            row
            for row in actual["snapshots"]["layouts"]
            if row["name"] == "Exact reservation"
        )
        rig.check(
            captured["status"] == 412
            and "snapshot_changed" in json.dumps(captured["response"])
            and old_saved["etag"] != new_saved["etag"]
            and captured["original_request"]["saved_layouts"]
            == [{"name": "Exact reservation", "etag": old_saved["etag"]}]
            and actual["layout"] == captured["after_external"]["layout"]
            and old in actual["runtime"]["devices"],
            "Exact selected saved digest rejects rebind even with fresh global authority and performs no partial replacement",
            captured,
        )


def forget_reconnect(rig):
    from redesign_acceptance import wait_until

    quick_wall(rig)
    p, device, client = rig.page, ids(rig)[0], rig.tablets[0]
    task(p, "Tablets")
    pick(p, device)
    client.close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][device]["online"],
        p.wait_for_timeout,
    )
    expect(p.locator("#tablet-forget-preview")).to_be_enabled()
    rig.open_disclosures(p.locator("#tablet-forget-preview"))
    p.locator("#tablet-forget-preview").click()
    expect(p.locator("#tablet-forget-impact")).to_be_visible()
    rig.open_disclosures(p.locator("#tablet-forget-active"))
    p.locator("#tablet-forget-active").check()
    before = rig.config()
    reopened = client.context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[0] = reopened
    wait_until(
        lambda: rig.config()["runtime"]["devices"][device]["online"], p.wait_for_timeout
    )
    expect(p.locator("#tablet-forget-confirm")).to_be_disabled()
    rig.check(
        rig.config()["layout"] == before["layout"]
        and device in rig.config()["runtime"]["devices"]
        and "reconnected" in p.locator("#tablet-forget-text").inner_text(),
        "Real client reconnect after Forget review refuses confirmation and keeps registration and position",
    )
    rig.check(
        not any(
            r["method"] == "DELETE" and r["url"].endswith(device) for r in rig.requests
        ),
        "Stale Forget review sends no destructive command",
    )


def durable_uncertainty(rig):
    p, device = rig.page, ids(rig)[0]
    task(p, "Tablets")
    pick(p, device)
    p.locator("#tablet-label").fill("Durably committed before synthetic 500")

    def postcommit500(route):
        response = route.fetch()
        rig.events.append(
            {
                "fixture_injection": "real name commit then durable HTTP500 response",
                "committed": response.json(),
                "status": response.status,
            }
        )
        route.fulfill(status=500, json={"detail": "Synthetic lost postcommit response"})

    with rig.fault(
        "real durable write followed by HTTP500", [(r"/api/v3/devices/", [500])]
    ):
        p.route("**/api/v3/devices/" + device, postcommit500, times=1)
        p.locator("#tablet-label-save").click()
        from redesign_acceptance import wait_until

        wait_until(
            lambda: any(row.get("status") == 500 for row in rig.network),
            p.wait_for_timeout,
        )
        rig.check(
            rig.config()["device_labels"][device]
            == "Durably committed before synthetic 500",
            "46a9f24 regression fixture really committed before returning durable500",
        )
        pick(p, ids(rig)[1])
        p.locator("#tablet-label").fill("Second write must await explicit refresh")
        count = len(rig.requests)
        p.locator("#tablet-label-save").click()
        expect(p.locator("#tablet-action-message")).to_contain_text(
            "may have completed"
        )
        rig.check(
            len(rig.requests) == count
            and rig.config()["device_labels"].get(ids(rig)[1])
            != "Second write must await explicit refresh",
            "46a9f24 durable500 uncertainty blocks subsequent writes before transport despite automatic reconciliation",
        )
        refreshed(p)
        p.locator("#tablet-label-discard").click()
        p.locator("#tablet-label").fill("Second write must await explicit refresh")
        p.locator("#tablet-label-save").click()
        expect(p.locator("#tablet-action-message")).to_contain_text("Name saved")
        rig.check(
            rig.config()["device_labels"][ids(rig)[1]]
            == "Second write must await explicit refresh",
            "46a9f24 explicit status refresh and renewed field review unlock retry after durable500",
        )


def history_ownership(rig):
    quick_wall(rig)
    show_supplied(rig)
    p, device = rig.page, ids(rig)[1]
    task(p, "Arrange")
    tile = p.locator(f'#stage-svg .slot[data-device-id="{device}"]')
    tile.focus()
    tile.press("ArrowRight")
    task(p, "Settings")
    rig.open_disclosures(p.locator("#clear-wall"))
    p.locator("#clear-wall").click()
    expect(p.locator("#draft-resolution")).to_be_visible()
    expect(p.locator("#resolve-commit")).to_have_text("Apply arrangement")
    p.locator("#resolve-stay").click()
    rig.check(
        p.locator("body").get_attribute("data-output-dirty") == "true",
        "46a9f24 immediate command resolves arrangement intent and Stay retains it",
    )
    task(p, "Arrange")
    p.locator("#btn-undo").click()
    expect(p.locator("#btn-redo")).to_be_enabled()
    rig.check(
        p.locator("#btn-apply").is_disabled(),
        "46a9f24 history fixture has a real redo entry with no active arrangement draft",
    )
    task(p, "Images")
    p.get_by_role("button", name="Preview supplied.png", exact=True).click()
    p.locator("#image-fit").select_option("contain")
    before = rig.config()
    for panel in ("Images", "Tablets"):
        task(p, panel)
        for key in ("Control+z", "Control+y", "Control+Shift+z"):
            p.locator("#task-" + panel.lower()).focus()
            p.keyboard.press(key)
            rig.check(
                p.locator("body").get_attribute("data-stage-mode") == "image-preview"
                and rig.config()["layout"] == before["layout"]
                and rig.config()["scene"] == before["scene"],
                "46a9f24 image draft owns output across "
                + panel
                + " history shortcut "
                + key,
            )
    task(p, "Arrange")
    expect(p.locator("#draft-resolution")).to_be_visible()
    expect(p.locator("#resolve-commit")).to_have_text("Show image")
    p.locator("#resolve-stay").click()
    task(p, "Settings")
    rig.open_disclosures(p.locator("#clear-wall"))
    p.locator("#clear-wall").click()
    expect(p.locator("#draft-resolution")).to_be_visible()
    expect(p.locator("#resolve-commit")).to_have_text("Show image")
    p.locator("#resolve-discard").click()
    expect(p.locator("#draft-resolution")).to_be_hidden()
    from redesign_acceptance import wait_until

    wait_until(lambda: not rig.config()["layout"]["placements"], p.wait_for_timeout)
    rig.check(
        rig.config()["scene"] == before["scene"]
        and not p.locator("body").get_attribute("data-output-dirty") == "true",
        "46a9f24 immediate command resolves every reachable incompatible output intent before proceeding",
    )
    rig.manifest["limits"].append(
        "The public UI enforces one output draft. A simultaneous illegal manual+image internal state is not injected; its private resolver-loop unit coverage is root-owned."
    )


def refused_grid(rig):
    quick_wall(rig)
    p, device = rig.page, ids(rig)[1]
    before = rig.config()
    tile = p.locator(f'#stage-svg .slot[data-device-id="{device}"]')
    tile.click()
    p.locator("#logical-w").fill("85")
    p.locator("#logical-w").press("Tab")
    p.locator("#grid-preview").click()
    expect(p.locator("#grid-message")).to_contain_text(
        "Apply or cancel the manual draft"
    )
    p.locator("#logical-w").fill("95")
    p.locator("#logical-w").press("Tab")
    rendered = float(tile.locator(".operator-body-outline").get_attribute("width"))
    rig.check(
        rendered == 95
        and p.locator("#btn-apply").is_enabled()
        and rig.config()["layout"] == before["layout"],
        "46a9f24 refused grid preview leaves later manual edits stage and Apply usable",
        {"field": p.locator("#logical-w").input_value(), "stage_width": rendered},
    )
    p.locator("#btn-apply").click()
    expect(p.locator("#stage-mode-label")).to_have_text("Applied configuration")
    rig.check(
        rig.config()["layout"]["placements"][device]["w"] == 95,
        "46a9f24 manual stage and committed geometry agree after refused grid preview",
    )


from operator_accessibility import (  # noqa: E402
    entry_recovery,
    interaction_contrast,
    loading_workspace,
    native_capabilities,
    native_keyboard,
    visual_states,
)


EDGE_CASES = {
    "physical-pointer": pointer_drag,
    "snap-spacing": snap_spacing,
    "command-variants": command_variants,
    "batch-uncertain": batch_uncertain,
    "batch-selection": batch_selection,
    "mixed-models": mixed_models,
    "stale-reads": stale_reads,
    "late-mutation": late_mutation,
    "old-paint": old_paint,
    "upload-timeout": upload_timeout,
    "inventory-order": inventory_order,
    "upload-postpublication": upload_ambiguous,
    "upload-unreadable": upload_unreadable,
    "stale-scene": stale_scene,
    "missing-live": missing_live,
    "different-hardware": different_hardware,
    "replacement-connection": replacement_connection,
    "replacement-digest": replacement_digest,
    "forget-reconnect": forget_reconnect,
    "durable-uncertainty": durable_uncertainty,
    "history-ownership": history_ownership,
    "refused-grid": refused_grid,
    "native-keyboard": native_keyboard,
    "visual-states": visual_states,
    "loading-workspace": loading_workspace,
    "interaction-contrast": interaction_contrast,
    "entry-recovery": entry_recovery,
    "native-capabilities": native_capabilities,
}
