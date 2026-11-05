"""Separate experience evidence supplement; behavioral acceptance remains authoritative."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from types import SimpleNamespace

from playwright.sync_api import expect, sync_playwright
from redesign_acceptance import Rig, digest, new_artifacts, wait_until
from _redesign_edge_cases import TASK_TABS, HeldResponse, quick_wall, show_supplied

VIEWPORTS = ((1440, 900), (390, 844), (320, 844), (820, 1180))
TARGETS = {
    "Images": ("#image-gallery button", "#show-image"),
    "Tablets": ("#device-list .dev-pick",),
    "Arrange": ("#grid-1x4", "#grid-preview, #btn-apply:not([disabled])"),
}
MEASURE = """selectors => {
 const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=="hidden");
 const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};
 const row=e=>({id:e.id,tag:e.tagName,text:(e.innerText||e.getAttribute("aria-label")||"").slice(0,140),
   ...box(e),disabled:!!e.disabled,tabindex:e.tabIndex});
 const controls=[...document.querySelectorAll("button,a[href],input,select,textarea,summary,[tabindex]")].filter(visible);
 const panel=document.querySelector('[role="tabpanel"]:not([hidden])');
 const targets=selectors.map(selector=>({selector,elements:[...document.querySelectorAll(selector)].filter(visible).map(e=>{
   const r=e.getBoundingClientRect(); const x=Math.max(0,Math.min(innerWidth-1,r.x+r.width/2));
   const y=Math.max(0,Math.min(innerHeight-1,r.y+r.height/2)); const hit=document.elementFromPoint(x,y);
   return {...row(e),inViewport:r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth,
     centerOccluded:!!hit&&!e.contains(hit)&&!hit.contains(e)};
 })}));
 return {url:location.href,title:document.title,task:document.body.dataset.task,scrollY,
   activeTask:panel?row(panel):null,overflow:document.documentElement.scrollWidth>innerWidth+1,
   targets,domControls:controls.map(row),focusOrder:controls.filter(e=>e.tabIndex>=0&&!e.disabled).map(row),
   stageArt:[...document.querySelectorAll('#stage-svg image')].map(box),
   stageLabels:[...document.querySelectorAll('#stage-svg .operator-slot-label')].filter(visible).map(row),
   sticky:controls.filter(e=>["fixed","sticky"].includes(getComputedStyle(e).position)).map(row)};
}"""


def entry_findings(metrics):
    findings = ["horizontal overflow"] if metrics["overflow"] else []
    for target in metrics["targets"]:
        if not any(e["inViewport"] and not e["centerOccluded"] for e in target["elements"]):
            findings.append(target["selector"] + " absent or occluded at entry")
    return findings


class ExperienceRig(Rig):
    def close(self):
        super().close()
        cleanup = self.manifest["cleanup"]
        cleanup["remaining_owned_browser_pids"] = [pid for pid in cleanup.get("remaining_owned_browser_pids", []) if pid != os.getpid()]
        self.write("identity.json", self.manifest)

    def viewport_shots(self, name):
        if name == "empty":
            capture(self, "empty", tasks=("Images", "Tablets", "Arrange"))


def capture(rig, state, tasks=("Images", "Tablets", "Arrange", "Saved", "Settings")):
    p = rig.page
    viewport = p.viewport_size
    selected_task = p.locator("#compact-task-select").input_value()
    for width, height in VIEWPORTS:
        p.set_viewport_size({"width": width, "height": height})
        for task in tasks:
            rig.task(task)
            p.evaluate("window.scrollTo(0,0)")
            p.evaluate("document.fonts.ready")
            metrics = p.evaluate(MEASURE, TARGETS.get(task, ()))
            metrics.update(state=state,viewport=p.viewport_size,screenshot=rig.shot(p, state + "-" + task))
            metrics["entry_findings"] = entry_findings(metrics)
            rig.experience.append(metrics)
    p.set_viewport_size(viewport)
    rig.task(next(name for name, value in TASK_TABS.items() if value == selected_task))


def journey(rig, artwork):
    p = rig.page
    if artwork:
        from PIL import Image
        target = rig.private / "assets" / "supplied.png"
        with Image.open(artwork) as image:
            image.convert("RGB").save(target)
        rig.manifest["experience_artwork"] = {"source":str(artwork.resolve()),"source_sha256":digest(artwork),"served_sha256":digest(target)}
        rig.task("Images")
        rig.click("#refresh-images")
    quick_wall(rig)
    show_supplied(rig)
    capture(rig, "live")
    rig.shot(rig.tablets[0], "actual-client-art")
    rig.task("Tablets")
    rig.click(p.locator("#device-list .dev-pick").first)
    rig.click("#tablet-identify")
    expect(rig.tablets[0].locator("#identify")).to_be_visible()
    rig.task("Images")
    held = HeldResponse(rig,p,"**/api/v3/images","experience inventory pending")
    rig.click("#refresh-images")
    held.wait()
    capture(rig,"inventory-pending",tasks=("Images",))
    held.release()
    expect(p.locator("#refresh-images")).to_be_enabled()
    rig.task("Arrange")
    before = rig.config()
    rig.click("#grid-2x2")
    rig.click("#grid-preview")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    assert rig.config()["revision"] == before["revision"]
    capture(rig, "arrangement-preview", tasks=("Arrange",))
    rig.tablets[0].close()
    device = rig.manifest["clients"][0]["id"]
    wait_until(lambda:not rig.config()["runtime"]["devices"][device]["online"],p.wait_for_timeout)
    capture(rig,"one-offline",tasks=("Tablets",))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts",required=True,type=Path)
    parser.add_argument("--browser",required=True,type=Path)
    parser.add_argument("--artwork",type=Path)
    parser.add_argument("--baseline",action="store_true")
    args=parser.parse_args(argv)
    out=new_artifacts(args.artifacts)
    rig=ExperienceRig(out,"experience")
    rig.experience=[]
    rig.manifest["experience_driver_sha256"]=digest(Path(__file__))
    shutil.copyfile(__file__,out/"experience_acceptance.py")
    rig.manifest["limits"].extend(["Experience evidence requires manual judgment; no automatic experience pass.", "Failed-image and conflict states, enlarged text and physical geometry variants remain outside this bounded supplement.", "Focus order records DOM candidates, not full native keyboard traversal; center-point occlusion is a heuristic."])
    interrupted=None
    with sync_playwright() as pw:
        browser=SimpleNamespace(executable_path=str(args.browser.resolve()),launch=pw.chromium.launch)
        try:
            rig.setup(SimpleNamespace(chromium=browser))
            journey(rig,args.artwork)
        except Exception:
            interrupted=traceback.format_exc()
        finally:
            rig.close()
    findings=[{"state":m["state"],"task":m["task"],"viewport":m["viewport"],"findings":m["entry_findings"]}
              for m in rig.experience if m["entry_findings"]]
    result={"baseline":args.baseline,"interruption":interrupted,"observations":rig.experience,
            "entry_findings":findings,"cleanup":rig.manifest["cleanup"],
            "status":"baseline_evidence" if args.baseline else "manual_review_required",
            "experience_pass":False,"behavioral_gate":"redesign_acceptance.py remains authoritative"}
    rig.write("experience.json",result)
    print(json.dumps({"artifacts":str(out),"status":result["status"],"observations":len(rig.experience),
                      "entry_findings":len(findings),"interruption":interrupted,"cleanup":result["cleanup"]},indent=2))
    cleanup=result["cleanup"]
    unexpected_network = [row for row in rig.network if not row.get("induced")]
    unexpected_console = [row for row in rig.console if not row.get("induced")]
    return int(bool(interrupted or unexpected_network or unexpected_console or rig.errors or cleanup["errors"] or not cleanup.get("port_closed")
                    or cleanup.get("remaining_owned_browser_pids") or any(s.get("remaining_owned_process_group") for s in rig.manifest.get("servers",[]))))


if __name__ == "__main__":
    sys.exit(main())
