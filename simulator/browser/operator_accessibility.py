"""Native-markup keyboard and rendered-layout probes on isolated shipped clients."""

import argparse
from pathlib import Path
import sys
from playwright.sync_api import expect

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
    tab = p.get_by_role("tab", name="Arrange", exact=True)
    tab.focus()
    tab.press("ArrowRight")
    rig.check(
        p.get_by_role("tab", name="Images", exact=True).get_attribute("aria-selected")
        == "true",
        "Task tabs support ArrowRight roving navigation",
        focus(p),
        fatal=False,
    )
    p.get_by_role("tab", name="Images", exact=True).press("Home")
    rig.check(
        p.get_by_role("tab", name="Tablets", exact=True).get_attribute("aria-selected")
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
    expect(p.locator("#scene-message")).to_contain_text("Scene saved")
    rig.click(p.get_by_role("button", name="Delete scene “Keyboard scene”", exact=True))
    expect(
        p.get_by_role("button", name="Preview scene “Keyboard scene”", exact=True)
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
    rig.click("#tablet-label-discard")
    rig.tablets[3].close()
    from redesign_acceptance import wait_until

    wait_until(
        lambda: not rig.config()["runtime"]["devices"][ids[3]]["online"],
        p.wait_for_timeout,
    )
    rig.click(f'.dev-pick[data-device-id="{ids[3]}"]')
    rig.click("#tablet-forget-preview")
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
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing", timeout=15000)
    rig.check(
        reopened.evaluate("localStorage.getItem('tablet-wall-device-id')") == ids[3],
        "Keyboard recovery retains tablet storage identity",
    )
    rig.manifest["limits"].extend(
        [
            "Keyboard actions use focus plus Enter/Space/native arrows; full sequential Tab-order and screen-reader review remain manual.",
            "Composition events are synthetic; operating-system IME input remains unrun.",
            "Native browser zoom and 400% zoom remain unrun. The 200% zoom matrix explicitly uses CSS zoom emulation.",
            "Modal containment, invalid-submit field focus, reorder boundaries and full non-text contrast need further probes.",
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
        "Accepted initial 68rem/1088px boundary; final stylesheet boundary must be reconciled after styling."
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
        [(r"\.woff", ["network"])],
    ):
        font_requests = []

        def block_font(route):
            font_requests.append(route.request.url)
            route.abort()

        p.route("**/*.woff*", block_font)
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
        p.unroute("**/*.woff*")


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
