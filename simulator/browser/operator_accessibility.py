"""Native-markup keyboard and rendered-layout probes on isolated shipped clients."""

import argparse
from pathlib import Path
import sys
from playwright.sync_api import expect

from _redesign_edge_cases import task_tab

CONTRAST = r"""() => {
 const rgba=c=>{const a=c.match(/[\d.]+/g).map(Number);return [...a.slice(0,3),a.length>3?a[3]:1]};
 const over=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3])).concat(1);
 const lum=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 return [...document.querySelectorAll('h1,h2,h3,label,input,select,.btn,.rail-tab,.wall-health span,.chip,.hint,[role=status],.page-error,#readiness-status')].filter(e=>e.checkVisibility()&&(e.textContent.trim()||e.value)&&!e.closest('svg,[aria-hidden=true],:disabled')).map(e=>{
 const chain=[];for(let p=e;p;p=p.parentElement)chain.unshift(p);
 let bg=[255,255,255,1],outer=bg,unsupported=false;
 for(const p of chain){const s=getComputedStyle(p);outer=bg;bg=over(rgba(s.backgroundColor),bg);if(s.backgroundImage!=='none'||Number(s.opacity)!==1)unsupported=true;}
 const s=getComputedStyle(e),fg=over(rgba(s.color),bg),a=lum(fg),b=lum(bg),size=parseFloat(s.fontSize);
 const border=over(rgba(s.borderTopColor),bg),bl=lum(border),ol=lum(outer);
 const boundary=e.matches('input:not([type=checkbox]):not([type=radio]),select')?{ratio:(Math.max(bl,ol)+.05)/(Math.min(bl,ol)+.05),width:parseFloat(s.borderTopWidth),style:s.borderTopStyle}:null;
 return {id:e.id,text:(e.textContent.trim()||e.value).slice(0,140),kind:e.dataset.kind||e.closest('[data-kind]')?.dataset.kind,foreground:fg,background:bg,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),threshold:size>=24||(size>=18.6667&&parseFloat(s.fontWeight)>=700)?3:4.5,boundary,unsupported};
 });
}"""


def focus(page):
    return page.evaluate("""()=>({tag:document.activeElement.tagName,id:document.activeElement.id,
      text:document.activeElement.textContent.slice(0,100),disabled:!!document.activeElement.disabled,
      visible:document.activeElement.getClientRects().length>0})""")


def native_tab_to(page, selector, maximum=120):
    """Use only native sequential Tab; never repair a failed route with focus()."""
    visited = []
    for _ in range(maximum):
        if page.evaluate("s=>!!document.activeElement?.matches(s)", selector):
            return visited
        page.keyboard.press("Tab")
        visited.append(focus(page))
    raise AssertionError(f"Native Tab did not reach {selector}; visited {visited}")


def native_tab_task(page, name):
    native_tab_to(page, "[role=tab][aria-selected=true]")
    names = page.get_by_role("tab").all_text_contents()
    names = [value.strip() for value in names]
    current = names.index(
        page.locator("[role=tab][aria-selected=true]").inner_text().strip()
    )
    target = names.index(name)
    for _ in range(abs(target - current)):
        page.keyboard.press("ArrowRight" if target > current else "ArrowLeft")


def native_keyboard(rig):
    from _redesign_edge_cases import quick_wall, task

    p = rig.page
    quick_wall(rig)
    p.reload()
    expect(p.locator("body")).to_have_attribute("data-connection", "current")
    walk, first = [], None
    for _ in range(110):
        p.keyboard.press("Tab")
        row = p.evaluate("""()=>{const e=document.activeElement,s=getComputedStyle(e),r=e.getBoundingClientRect();
          const x=(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2,y=(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;
          return {id:e.id,tag:e.tagName,html:e.outerHTML.slice(0,220),disabled:!!e.disabled,
          hidden:!!e.closest('[hidden]'),visible:e.checkVisibility(),index:[...document.querySelectorAll('*')].indexOf(e),
          outline:s.outlineStyle,outlineWidth:parseFloat(s.outlineWidth),boxShadow:s.boxShadow,
          svgFocus:e.matches('.slot')&&getComputedStyle(e.querySelector('.operator-body-outline')).stroke!=='none',
          occluded:r.width>0&&r.height>0&&!e.contains(document.elementFromPoint(x,y))};}""")
        if first is not None and (row["index"] == first or row["tag"] == "BODY"):
            break
        first = row["index"] if first is None else first
        walk.append(row)
    rig.events.append({"native_tab_walk": walk})
    rig.check(
        bool(walk)
        and all(
            row["visible"] and not row["disabled"] and not row["hidden"] for row in walk
        ),
        "Sequential native Tab reaches only visible enabled controls",
        walk,
        fatal=False,
    )
    rig.check(
        all(a["index"] < b["index"] for a, b in zip(walk, walk[1:])),
        "Sequential native Tab follows DOM source order without a desktop panel trap",
        walk,
        fatal=False,
    )
    rig.check(
        all(
            (row["outline"] != "none" and row["outlineWidth"] > 0)
            or row["boxShadow"] != "none"
            or row["svgFocus"]
            for row in walk
            if row["tag"] != "BODY"
        ),
        "Sequential native Tab has a visible focus treatment at every visited control",
        walk,
        fatal=False,
    )
    rig.check(
        not any(row["occluded"] for row in walk if row["tag"] != "BODY"),
        "Sequential native Tab focused controls are not covered by sticky content",
        [row for row in walk if row["occluded"]],
        fatal=False,
    )
    native_tab_task(p, "Saved")
    native_tab_to(p, "#btn-layout-save")
    p.keyboard.press("Enter")
    expect(p.locator("#layout-msg")).to_contain_text("Enter an arrangement name")
    rig.check(
        focus(p)["id"] == "layout-name",
        "Invalid empty arrangement submission focuses its own name field",
        focus(p),
        fatal=False,
    )
    native_tab_to(p, "#scene-save")
    p.keyboard.press("Enter")
    expect(p.locator("#scene-message")).to_contain_text("Enter a scene name")
    rig.check(
        focus(p)["id"] == "scene-name",
        "Invalid empty scene submission focuses its own name field",
        focus(p),
        fatal=False,
    )
    native_tab_task(p, "Arrange")
    rows = p.locator("#grid-order li[data-device-id]")
    second_id = rows.nth(1).get_attribute("data-device-id")
    earlier = f'#grid-order li[data-device-id="{second_id}"] button[aria-label^="Move earlier"]'
    native_tab_to(p, "#arrange-membership > summary")
    p.keyboard.press("Enter")
    native_tab_to(p, earlier)
    p.keyboard.press("Enter")
    rig.check(
        rows.first.get_attribute("data-device-id") == second_id
        and "Move later" in focus(p)["text"]
        and not focus(p)["disabled"],
        "Native reorder at first boundary retains focus on the enabled opposite action",
        focus(p),
        fatal=False,
    )
    later = (
        f'#grid-order li[data-device-id="{second_id}"] button[aria-label^="Move later"]'
    )
    native_tab_to(p, later)
    for _ in range(3):
        p.keyboard.press("Enter")
    rig.check(
        rows.last.get_attribute("data-device-id") == second_id
        and "Move earlier" in focus(p)["text"]
        and not focus(p)["disabled"],
        "Native reorder at final boundary retains focus on the enabled opposite action",
        focus(p),
        fatal=False,
    )
    native_tab_to(p, "#grid-preview")
    p.keyboard.press("Enter")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    native_tab_task(p, "Tablets")
    trigger_id = p.locator("[role=tab][aria-selected=true]").get_attribute("id")
    native_tab_task(p, "Images")
    dialog = p.locator("#draft-resolution")
    expect(dialog).to_be_visible()
    contains = []
    for key in ["Tab"] * 7 + ["Shift+Tab"] * 7:
        p.keyboard.press(key)
        contains.append(
            p.evaluate(
                "()=>({inside:document.querySelector('#draft-resolution').contains(document.activeElement),id:document.activeElement.id,tag:document.activeElement.tagName,documentFocused:document.hasFocus()})"
            )
        )
    rig.check(
        all(row["inside"] or not row["documentFocused"] for row in contains),
        "Native modal dialog contains page focus during forward and reverse Tab; browser chrome remains reachable",
        contains,
        fatal=False,
    )
    p.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    rig.check(
        focus(p)["id"] == trigger_id,
        "Native dialog Escape keeps the draft and returns focus to its trigger",
        focus(p),
        fatal=False,
    )
    rig.viewport_shots("native-keyboard")
    task(p, "Arrange")
    p.locator("#btn-cancel").click()


def entry_recovery(rig):
    from _redesign_edge_cases import measured_wall

    measured_wall(rig)
    p = rig.page
    for viewport in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
        for entry in ("/controller/", "/controller/index.html"):
            context = rig.browser.new_context(viewport=viewport)
            rig.contexts.append(context)
            page_label = f"forwarded-entry-{viewport['width']}-{entry}"
            rig.observe(context, page_label)
            page = context.new_page()
            with rig.fault(
                "automatic entry forwarding may cancel its own font request",
                [(r"/controller/fonts/.*\.ttf", ["net::ERR_ABORTED"])],
            ):
                page.goto(rig.base + entry + "?acceptance=preserve%20me&x=2#wall-proof")
            expect(page).to_have_url(
                rig.base
                + "/controller/physical.html?acceptance=preserve%20me&x=2#wall-proof"
            )
            expect(page.locator("#rail-tabs")).to_be_visible()
            expect(page.locator("body")).to_have_attribute("data-connection", "current")
            page.evaluate("document.fonts.ready")
            sockets = [
                row
                for row in rig.events
                if row.get("page") == page_label
                and row.get("direction") == "received"
                and isinstance(row.get("payload"), dict)
                and row["payload"].get("type") == "snapshot"
            ]
            rig.check(
                len(sockets) == 1,
                f"{entry} preserves exact query/hash and opens a working workspace at {viewport['width']}",
                {"url": page.url, "snapshots": len(sockets)},
            )
            rig.shot(page, "forwarded-entry")
            page.close()
    client = rig.tablets[0]
    cdp = client.context.new_cdp_session(client)
    for viewport in ({"width": 900, "height": 1280}, {"width": 1280, "height": 900}):
        client.set_viewport_size(viewport)
        cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        rig.manifest["render_modes"].append(
            {
                "page": "client-recovery",
                "viewport": viewport,
                "page_scale": 2,
                "method": "CDP page scaling emulation; not native browser zoom",
            }
        )
        panel = client.locator("#calibration-recovery")
        expect(panel).to_be_visible(timeout=15000)
        for percent in (100, 200):
            client.evaluate("p=>document.documentElement.style.fontSize=p+'%'", percent)
            panel.evaluate("e=>e.scrollTop=e.scrollHeight")
            metrics = panel.evaluate("""e=>{const copy=e.querySelector('.recovery-copy'),r=copy.getBoundingClientRect(),p=e.getBoundingClientRect();
              return {heading:e.querySelector('h1').textContent,reason:e.querySelector('p').textContent,
              hidden:e.hidden,role:e.getAttribute('role'),font:parseFloat(getComputedStyle(e.querySelector('p')).fontSize),
              overflow:document.documentElement.scrollWidth>innerWidth+1,panelOverflow:e.scrollWidth>e.clientWidth+1,
              copyWidth:r.width,panelWidth:p.width,copyBottom:r.bottom,panelBottom:p.bottom,scrollable:e.scrollHeight>e.clientHeight,
              reasonBottom:e.querySelector('p').getBoundingClientRect().bottom,
              textInSVG:!!e.querySelector('svg text')};}""")
            rig.check(
                not metrics["overflow"]
                and not metrics["panelOverflow"]
                and not metrics["textInSVG"]
                and len(metrics["reason"]) > 20
                and metrics["font"] >= 18
                and metrics["reasonBottom"] <= metrics["panelBottom"] + 1
                and (
                    metrics["copyBottom"] <= metrics["panelBottom"] + 1
                    or metrics["scrollable"]
                ),
                f"Readable DOM client recovery at {viewport['width']}x{viewport['height']} text {percent}%",
                metrics,
                fatal=False,
            )
            rig.shot(client, f"dom-recovery-text-{percent}")
        client.evaluate("document.documentElement.style.fontSize=''")
    client.set_viewport_size({"width": 900, "height": 1280})
    cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
    expect(client.locator("#calibration-recovery")).to_be_hidden(timeout=15000)
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    rig.check(
        True,
        "Restoring calibrated viewport removes DOM recovery and requires fresh current paints",
    )


def visual_states(rig):
    from _redesign_edge_cases import HeldResponse, pick, save_name, task
    from redesign_acceptance import wait_until

    p = rig.page
    device = rig.manifest["clients"][0]["id"]
    label = "Café e\u0301 長い名前 🧱 العربية " * 2
    save_name(p, device, label.strip())
    long_name = "Long filename Café e\u0301 長い名前 wall composition repeated repeated repeated.png"
    from PIL import Image

    Image.new("RGB", (333, 197), (115, 31, 173)).save(
        rig.private / "assets" / long_name
    )
    task(p, "Images")
    p.locator("#refresh-images").click()
    expect(
        p.get_by_role("button", name="Preview " + long_name, exact=True)
    ).to_have_count(1)
    for width, height in ((1440, 900), (390, 844), (320, 640)):
        p.set_viewport_size({"width": width, "height": height})
        for name in ("Tablets", "Images"):
            task(p, name)
            if name == "Tablets":
                pick(p, device)
                expect(p.locator("#tablet-label")).to_have_value(label.strip())
            metrics = p.evaluate(
                "()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,width:innerWidth,scrollWidth:document.documentElement.scrollWidth})"
            )
            rig.check(
                not metrics["overflow"],
                f"Long Unicode tablet and image names retain readable {name} at {width}",
                metrics,
                fatal=False,
            )
            rig.shot(p, "long-names-" + name)
    p.set_viewport_size({"width": 1440, "height": 900})
    task(p, "Images")
    with p.expect_response("**/api/v3/images") as inventory:
        p.locator("#refresh-images").click()
    thumbnails = {row["thumbnail_url"] for row in inventory.value.json()["images"]}
    with rig.fault("missing only thumbnail bytes", [(r"/(assets|media)/", [404])]):

        def thumbnail(route):
            route.fulfill(status=404, body="Synthetic missing thumbnail")

        for path in thumbnails:
            p.route(rig.base + path, thumbnail)
        p.reload()
        task(p, "Images")
        p.locator("#image-gallery").scroll_into_view_if_needed()
        wait_until(
            lambda: (
                p.locator('#image-gallery li[data-thumbnail="unavailable"]').count() > 0
            ),
            p.wait_for_timeout,
        )
        for width, height in ((1440, 900), (390, 844)):
            p.set_viewport_size({"width": width, "height": height})
            button = p.get_by_role("button", name="Preview " + long_name, exact=True)
            rig.check(
                button.is_visible()
                and button.is_enabled()
                and button.inner_text().find(long_name) >= 0,
                f"Missing thumbnail retains full native image name dimensions and selection action at {width}",
                button.inner_text(),
            )
            rig.shot(p, "missing-thumbnail")
        for path in thumbnails:
            p.unroute(rig.base + path, thumbnail)
    p.reload()
    task(p, "Images")
    held = HeldResponse(
        rig,
        p,
        "**/api/v3/images",
        "actual inventory loading state held for desktop and phone inspection",
    )
    p.locator("#refresh-images").click()
    held.wait()
    for width, height in ((1440, 900), (390, 844)):
        p.set_viewport_size({"width": width, "height": height})
        rig.check(
            "Reading" in p.locator("#image-message").inner_text()
            and p.locator("#show-image").is_disabled(),
            f"Canonical image loading state disables unsafe Show at {width}",
        )
        rig.shot(p, "inventory-loading")
    held.release()
    expect(p.locator("#refresh-images")).to_be_enabled()
    with rig.fault(
        "inventory GET temporarily unavailable", [(r"/api/v3/images", [503])]
    ):
        p.route(
            "**/api/v3/images",
            lambda route: route.fulfill(
                status=503, json={"detail": "Synthetic image library failure"}
            ),
            times=1,
        )
        p.locator("#refresh-images").click()
        expect(p.locator("#image-message")).to_contain_text("Image library unavailable")
        for width, height in ((1440, 900), (390, 844)):
            p.set_viewport_size({"width": width, "height": height})
            rig.check(
                p.locator("#refresh-images").is_enabled()
                and "retry" in p.locator("#image-message").inner_text(),
                f"Canonical image error state retains explicit Refresh recovery at {width}",
            )
            rig.shot(p, "inventory-error")
    assets = {
        path: path.read_bytes() for path in (rig.private / "assets").glob("*.png")
    }
    for path in assets:
        path.unlink()
    rig.events.append(
        {
            "fixture_injection": "temporarily remove only private file-backed library to obtain real empty inventory",
            "paths": [str(path) for path in assets],
        }
    )
    p.locator("#refresh-images").click()
    expect(p.locator("#image-message")).to_have_text("No images available.")
    for width, height in ((1440, 900), (390, 844)):
        p.set_viewport_size({"width": width, "height": height})
        rig.check(
            p.locator("#image-gallery li").count() == 0
            and "No images" in p.locator("#image-message").inner_text(),
            f"Canonical empty image inventory retains admitted Add image and Arrange at {width}",
        )
        rig.shot(p, "inventory-empty")
    for path, data in assets.items():
        path.write_bytes(data)
    p.locator("#refresh-images").click()
    expect(
        p.get_by_role("button", name="Preview supplied.png", exact=True)
    ).to_be_visible()


def loading_workspace(rig):
    from _redesign_edge_cases import HeldResponse

    context = rig.browser.new_context(viewport={"width": 1440, "height": 900})
    rig.contexts.append(context)
    rig.observe(context, "loading-workspace")
    context.route_web_socket("**/ws/controller?*", lambda ws: None)
    page = context.new_page()
    held = HeldResponse(
        rig,
        page,
        "**/api/v3/config",
        "first actual config withheld and socket snapshot withheld to inspect unknown state",
    )
    page.goto(rig.base + "/controller/physical.html", wait_until="domcontentloaded")
    held.wait()
    for width, height in ((1440, 900), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        metrics = page.evaluate(
            "()=>({connection:document.body.dataset.connection,emptyVisible:document.querySelector('#wall-empty').checkVisibility(),overflow:document.documentElement.scrollWidth>innerWidth+1,applyDisabled:document.querySelector('#btn-apply').disabled,connectionText:document.querySelector('#roster-status').textContent})"
        )
        rig.check(
            metrics["connection"] == "loading"
            and not metrics["emptyVisible"]
            and metrics["applyDisabled"]
            and not metrics["overflow"],
            f"First authoritative load remains unknown instead of falsely empty at {width}",
            metrics,
            fatal=False,
        )
        rig.shot(page, "workspace-first-loading")
    held.release()
    expect(page.locator("body")).to_have_attribute("data-connection", "current")
    page.close()


STATE_CONTRAST = r"""() => {
 const rgb=c=>{const el=document.createElement('canvas').getContext('2d');el.fillStyle=c;el.fillRect(0,0,1,1);return [...el.getImageData(0,0,1,1).data].slice(0,3)};
 const lum=c=>rgb(c).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>{a=lum(a);b=lum(b);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
 const backdrop=e=>{for(let p=e;p;p=p.parentElement){const c=getComputedStyle(p).backgroundColor;if(c!=='rgba(0, 0, 0, 0)')return c}return '#fff'};
 return [...document.querySelectorAll('#stage-identities li,#stage-svg .operator-body-outline,#stage-svg .logical-resize,:focus-visible')].filter(e=>e.checkVisibility()).map(e=>{
  const s=getComputedStyle(e),svg=e.closest('svg');
  if(e.matches('#stage-identities li')){const bg=backdrop(e);return {kind:'svg-text',text:e.textContent,foreground:s.color,background:bg,ratio:ratio(s.color,bg),threshold:4.5};}
  if(e.matches('.operator-body-outline,.logical-resize'))return {kind:'svg-nontext',id:e.closest('.slot').dataset.deviceId,foreground:e.matches('.logical-resize')?s.fill:s.stroke,background:'#22252a',ratio:ratio(e.matches('.logical-resize')?s.fill:s.stroke,'#22252a'),threshold:3};
  if(e.matches('.slot')){const b=getComputedStyle(e.querySelector('.operator-body-outline'));return {kind:'svg-focus',foreground:b.stroke,background:backdrop(e),width:parseFloat(b.strokeWidth),ratio:ratio(b.stroke,backdrop(e)),threshold:3};}
  const outer=backdrop(e.parentElement);return {kind:'focus-ring',id:e.id,foreground:s.outlineColor,background:outer,width:parseFloat(s.outlineWidth),style:s.outlineStyle,ratio:ratio(s.outlineColor,outer),threshold:3};
 });
}"""


def interaction_contrast(rig):
    from _redesign_edge_cases import quick_wall, task

    p = rig.page
    quick_wall(rig)
    task(p, "Tablets")
    for width, height in ((1440, 900), (390, 844)):
        p.set_viewport_size({"width": width, "height": height})
        p.evaluate("()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
        for mode in ("hover", "focus"):
            target = p.locator("#tablet-label-save")
            if not target.is_visible():
                p.locator(".dev-pick").first.click()
            if mode == "hover":
                target.hover()
            else:
                native_tab_to(p, "#tablet-label-save")
            text = [
                row
                for row in p.evaluate(CONTRAST)
                if row["id"]
                in ("tablet-label-save", "tablet-action-message", "tablet-recovery")
            ]
            rings = p.evaluate(STATE_CONTRAST)
            rig.events.append(
                {
                    "state_contrast": mode,
                    "viewport": p.viewport_size,
                    "text": text,
                    "nontext": rings,
                }
            )
            rig.check(
                bool(text)
                and all(
                    row["ratio"] >= row["threshold"] and not row["unsupported"]
                    for row in text
                ),
                f"Actual {mode} action text contrast at {width}",
                text,
                fatal=False,
            )
            if mode == "focus":
                rig.check(
                    bool(rings)
                    and all(
                        row["ratio"] >= row["threshold"] and (row.get("width", 1) > 0)
                        for row in rings
                    ),
                    f"Actual keyboard focus-ring contrast at {width}",
                    rings,
                    fatal=False,
                )
            rig.shot(p, "interaction-" + mode)
        if p.locator("#device-sheet-close").is_visible():
            p.locator("#device-sheet-close").click()
        task(p, "Arrange")
        tile = p.locator("#stage-svg .slot").first
        if not p.locator("#stage-identities").is_visible():
            p.locator(".stage-technical-toggle:visible").click()
        rig.open_disclosures("#stage-identities li")
        native_tab_to(p, "#stage-svg .slot")
        tile.hover()
        rows = p.evaluate(STATE_CONTRAST)
        rig.events.append(
            {
                "svg_contrast": rows,
                "viewport": p.viewport_size,
                "adjacency": "No-image stage; solid text backing and body boundary against dark active panel. Arbitrary image pixels are not claimed.",
            }
        )
        rig.check(
            any(row["kind"] == "svg-text" for row in rows)
            and any(row["kind"] == "svg-nontext" for row in rows)
            and all(row["ratio"] >= row["threshold"] for row in rows),
            f"Selected hovered focused SVG labels and essential outlines contrast at {width}",
            rows,
            fatal=False,
        )
        rig.shot(p, "svg-interaction-contrast")
        task(p, "Tablets")
    rig.manifest["limits"].append(
        "Contrast samples cover rendered text, field boundaries, default/hover/focus actions and selected SVG on solid backing; gradients, arbitrary photo-edge pixels, browser-native checkbox internals and AT rendering are outside automated sampling."
    )


def native_capabilities(rig):
    import shutil

    context = rig.browser.new_context(viewport={"width": 1280, "height": 900})
    rig.contexts.append(context)
    rig.observe(context, "native-capability-probe")
    page = context.new_page()
    page.goto(rig.base + "/controller/physical.html")
    metrics = "()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visualScale:visualViewport.scale,rootFont:getComputedStyle(document.documentElement).fontSize,cssZoom:getComputedStyle(document.documentElement).zoom})"
    before = page.evaluate(metrics)
    for _ in range(4):
        page.keyboard.press("Control+=")
    after = page.evaluate(metrics)
    page.keyboard.press("Control+0")
    native = (
        before["dpr"] != after["dpr"]
        and after["width"] < before["width"]
        and after["cssZoom"] == "1"
    )
    capabilities = {
        "native_zoom_changed": native,
        "before": before,
        "after": after,
        "tools": {
            name: shutil.which(name) for name in ("orca", "ibus", "fcitx5", "xdotool")
        },
    }
    rig.manifest["native_capabilities"] = capabilities
    rig.events.append({"environment_capability_probe": capabilities})
    rig.manifest["limits"].extend(
        [
            "Native browser 200%/400% zoom unavailable in this private headless context: real browser shortcut did not change effective viewport/DPR. CSS zoom and root text enlargement remain separate emulations.",
            "No native screen-reader or operating-system IME session was driven. Tool discovery alone does not establish usable AT. Synthetic composition is not native IME.",
        ]
    )
    rig.check(
        True,
        "Disposable native capability probe records effective metrics and unavailable zoom IME AT honestly",
        capabilities,
    )
    page.close()


def responsive(rig):
    from redesign_acceptance import first_wall

    p = rig.page
    first_wall(rig)
    rig.task("Tablets")
    ids = [row["id"] for row in rig.manifest["clients"]]
    rig.click(f'.dev-pick[data-device-id="{ids[0]}"]')
    label = ("Café e\u0301 長い名前 🧱 العربية " * 3).strip()
    p.locator("#tablet-label").focus()
    p.keyboard.insert_text(label)
    p.locator("#tablet-label").evaluate("e=>e.setSelectionRange(3,6)")
    before = focus(p)
    p.locator("#btn-roster-refresh").dispatch_event("click")
    expect(p.locator("#device-count")).to_contain_text("4")
    retained = p.locator("#tablet-label").evaluate(
        "e=>({value:e.value,start:e.selectionStart,end:e.selectionEnd})"
    )
    rig.check(
        focus(p) == before and retained == {"value": label, "start": 3, "end": 6},
        "Runtime refresh preserves exact Unicode name, focus and caret",
        retained,
    )
    p.locator("#tablet-label").dispatch_event("compositionstart", {"data": "あ"})
    p.locator("#btn-roster-refresh").dispatch_event("click")
    p.locator("#tablet-label").dispatch_event("compositionend", {"data": "あ"})
    rig.check(
        p.locator("#tablet-label").input_value() == label,
        "Synthetic composition events retain input; native IME remains unrun",
    )
    rig.click("#tablet-label-save")
    expect(p.locator("#tablet-action-message")).to_contain_text("Name saved")
    rig.task("Arrange")
    tab = task_tab(p, "Arrange")
    tab.focus()
    tab.press("ArrowRight")
    rig.check(
        task_tab(p, "Saved").get_attribute("aria-selected")
        == "true",
        "Task tabs support ArrowRight roving navigation",
        focus(p),
        fatal=False,
    )
    task_tab(p, "Saved").press("Home")
    rig.check(
        task_tab(p, "Images").get_attribute("aria-selected")
        == "true",
        "Task tabs support Home navigation",
        focus(p),
        fatal=False,
    )
    rig.task("Saved")
    p.locator("#layout-name").focus()
    p.keyboard.insert_text("Keyboard arrangement")
    rig.click("#btn-layout-save")
    expect(p.locator("#layout-msg")).to_contain_text("saved")
    p.locator("#scene-name").focus()
    p.keyboard.insert_text("Keyboard scene")
    rig.click("#scene-save")
    expect(p.locator("#scene-message")).to_contain_text("Content saved")
    rig.click(p.get_by_role("button", name="Delete content “Keyboard scene”", exact=True))
    expect(
        p.get_by_role("button", name="Preview content “Keyboard scene”", exact=True)
    ).to_have_count(0)
    rig.check(
        focus(p)["tag"] != "BODY" and focus(p)["visible"],
        "Scene delete leaves useful focus",
        focus(p),
        fatal=False,
    )
    rig.task("Tablets")
    rig.click(f'.dev-pick[data-device-id="{ids[1]}"]')
    rig.click("#tablet-remove")
    rig.check(
        ids[1] not in rig.config()["layout"]["slots"],
        "Keyboard removal targets selected middle tablet",
    )
    rig.check(
        focus(p)["tag"] != "BODY" and focus(p)["visible"],
        "Removal leaves useful focus",
        focus(p),
        fatal=False,
    )
    rig.task("Saved")
    rig.click(
        p.get_by_role(
            "button", name="Recall arrangement “Keyboard arrangement”", exact=True
        )
    )
    expect(p.locator("#layout-msg")).to_contain_text("recalled")
    rig.task("Arrange")
    slot = p.locator(f'#stage-svg .slot[data-device-id="{ids[0]}"]')
    slot.focus()
    slot.press("ArrowRight")
    rig.check(
        p.locator("#btn-apply").is_enabled(),
        "Stage-only keyboard nudge creates geometry preview",
    )
    rig.click("#btn-cancel")
    rig.task("Tablets")
    rig.click(f'.dev-pick[data-device-id="{ids[0]}"]')
    field = p.locator("#tablet-label")
    field.focus()
    field.press("End")
    p.keyboard.insert_text("X")
    field.press("Control+z")
    rig.check(
        field.input_value() == label and p.locator("#btn-apply").is_disabled(),
        "Text undo stays native and text arrows never nudge geometry",
        field.input_value(),
        fatal=False,
    )
    field.press("End")
    p.keyboard.insert_text("X")
    rig.click("#tablet-label-discard")
    expect(field).to_have_value(label)
    rig.tablets[3].close()
    from redesign_acceptance import wait_until

    wait_until(
        lambda: not rig.config()["runtime"]["devices"][ids[3]]["online"],
        p.wait_for_timeout,
    )
    rig.click(f'.dev-pick[data-device-id="{ids[3]}"]')
    for attempt in range(3):
        with p.expect_response(f"**/api/v3/devices/{ids[3]}/impact"):
            rig.click("#tablet-forget-preview")
        expect(p.locator("#tablet-forget-preview")).to_be_enabled()
        if p.locator("#tablet-forget-impact").is_visible():
            break
        message = p.locator("#tablet-action-message").inner_text()
        if "A newer update arrived" not in message:
            raise AssertionError("Forget impact did not open: " + message)
        rig.events.append(
            {
                "safe_read_retry": "Forget impact was fenced by newer runtime",
                "attempt": attempt + 1,
                "message": message,
            }
        )
        with p.expect_response("**/api/v3/config"):
            rig.click("#btn-roster-refresh")
    expect(p.locator("#tablet-forget-impact")).to_be_visible()
    rig.shot(p, "keyboard-forget-review")
    rig.click("#tablet-forget-cancel")
    rig.check(
        focus(p)["id"] == "tablet-forget-preview",
        "Keyboard recovery cancel returns trigger focus",
        focus(p),
    )
    reopened = rig.tablets[3].context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[3] = reopened
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    rig.check(
        reopened.evaluate("localStorage.getItem('tablet-wall-device-id')") == ids[3],
        "Keyboard recovery retains tablet storage identity",
    )
    rig.manifest["limits"].extend(
        [
            "This journey uses explicit focus plus native keys. The native-keyboard scenario separately traverses Tab order, dialogs, invalid submissions and reorder boundaries.",
            "Composition events are synthetic; operating-system IME input remains unrun.",
            "Native browser zoom and 400% zoom remain unrun. The 200% zoom matrix explicitly uses CSS zoom emulation.",
            "Interaction contrast and missing-thumbnail/loading/error states run in separate bounded edge cases. Browser-native AT remains unverified.",
        ]
    )
    inspect_layout(rig)


def inspect_layout(rig):
    p = rig.page
    viewports = [
        (1440, 900),
        (1600, 1000),
        (390, 844),
        (320, 640),
        (1087, 900),
        (1089, 900),
    ]
    rig.manifest["breakpoint_probe"] = (
        "Actual integrated workspace/stage styles use 68rem/1088px and 36rem/576px boundaries. This matrix probes 68rem ±1 and both phone widths; text enlargement is recorded separately."
    )
    for width, height in viewports:
        p.set_viewport_size({"width": width, "height": height})
        modes = (
            ("normal", "text-200", "css-zoom-200")
            if width in (1600, 320)
            else ("normal",)
        )
        for mode in modes:
            p.evaluate(
                "mode=>{document.documentElement.style.zoom=mode==='css-zoom-200'?'2':'1';document.documentElement.style.fontSize=mode==='text-200'?'200%':''}",
                mode,
            )
            rig.manifest["render_modes"].append(
                {
                    "viewport": p.viewport_size,
                    "DPR": p.evaluate("devicePixelRatio"),
                    "text": 200 if mode == "text-200" else 100,
                    "zoom": 200 if mode == "css-zoom-200" else 100,
                    "zoom_method": "CSS emulation"
                    if mode == "css-zoom-200"
                    else "default",
                    "reduced_motion": "reduce",
                }
            )
            for task in ("Tablets", "Arrange", "Images", "Saved", "Settings"):
                rig.task(task)
                metrics = p.evaluate("""()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,
                  viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                  navBeforeTask:!!(document.getElementById('rail-tabs').compareDocumentPosition(document.querySelector('.task-panel:not([hidden])'))&Node.DOCUMENT_POSITION_FOLLOWING),
                  clippedTabs:[...document.querySelectorAll('[role=tab]')].filter(e=>{const r=document.createRange();r.selectNodeContents(e);const a=r.getBoundingClientRect(),b=e.getBoundingClientRect();return a.left<b.left-1||a.right>b.right+1||a.top<b.top-1||a.bottom>b.bottom+1}).map(e=>e.textContent),
                  unnamed:[...document.querySelectorAll('button,input:not([type=hidden]),select,a[href]')].filter(e=>e.checkVisibility()&&!e.closest('[hidden]')&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.textContent.trim()&&![...(e.labels||[])].some(l=>l.textContent.trim())).map(e=>e.outerHTML),
                  smallText:[...document.querySelectorAll('.hint,.task-title,.btn,.field label')].filter(e=>e.checkVisibility()&&parseFloat(getComputedStyle(e).fontSize)<14).map(e=>({id:e.id,size:getComputedStyle(e).fontSize})),
                  motion:matchMedia('(prefers-reduced-motion: reduce)').matches})""")
                artifact = rig.shot(p, f"{mode}-{task}")
                rig.check(
                    not metrics["overflow"],
                    f"{width} {mode} {task} no horizontal document overflow",
                    metrics,
                    fatal=False,
                )
                rig.check(
                    metrics["navBeforeTask"] and not metrics["unnamed"],
                    f"{width} {mode} {task} navigation source order and native names",
                    metrics,
                    fatal=False,
                )
                rig.check(
                    not metrics["clippedTabs"],
                    f"{width} {mode} {task} task labels fit native controls",
                    metrics["clippedTabs"],
                    [],
                    fatal=False,
                )
                rows = p.evaluate(CONTRAST)
                bad = [
                    r for r in rows if r["unsupported"] or r["ratio"] < r["threshold"]
                ]
                rig.events.append(
                    {
                        "contrast": rows,
                        "mode": mode,
                        "viewport": p.viewport_size,
                        "task": task,
                        "artifact": artifact,
                    }
                )
                rig.check(
                    bool(rows) and not bad,
                    f"{width} {mode} {task} composited text contrast",
                    bad,
                    "4.5 normal/3 large; unsupported samples fail",
                    fatal=False,
                )
                boundaries = [
                    r
                    for r in rows
                    if r["boundary"]
                    and (
                        r["boundary"]["ratio"] < 3
                        or r["boundary"]["width"] <= 0
                        or r["boundary"]["style"] == "none"
                    )
                ]
                rig.check(
                    not boundaries,
                    f"{width} {mode} {task} essential field boundaries",
                    boundaries,
                    "3:1 composited adjacent backgrounds",
                    fatal=False,
                )
    p.evaluate(
        "()=>{document.documentElement.style.zoom='1';document.documentElement.style.fontSize=''}"
    )
    p.set_viewport_size({"width": 390, "height": 844})
    with rig.fault(
        "blocked local font assets to inspect system fallback",
        [(r"/controller/fonts/.*\.(?:woff2?|ttf)(?:\?|$)", ["network"])],
    ):
        font_requests = []

        def block_font(route):
            font_requests.append(route.request.url)
            route.abort()

        p.route("**/fonts/*", block_font)
        p.reload()
        p.evaluate("document.fonts.ready")
        rig.shot(p, "fonts-blocked-fallback")
        rig.check(
            p.locator("h1").is_visible(),
            "Blocked fonts preserve rendered application heading",
        )
        rig.check(
            bool(font_requests),
            "Font-failure variant actually intercepted a font request",
            font_requests,
            "At least one local font request; no request leaves this variant unproven",
            fatal=False,
        )
        p.unroute("**/fonts/*", block_font)


def main(argv=None):
    from redesign_acceptance import new_artifacts, run_scenario

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args(argv)
    out = new_artifacts(args.artifacts)
    result = run_scenario(out / "responsive", "responsive", responsive, keyboard=True)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
