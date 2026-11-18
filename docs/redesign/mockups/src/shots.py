import sys, json, pathlib
from playwright.sync_api import sync_playwright
M = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/mockups')
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
names = sys.argv[1].split(',')
states = sys.argv[3].split(',') if len(sys.argv) > 3 else ['main','selected','measure','arrange','recovery','firstrun']
themes = sys.argv[4].split(',') if len(sys.argv) > 4 else ['light']
metrics = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for n in names:
        for th in themes:
            for w, h in [(1440, 900), (390, 844)]:
                ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=th)
                pg = ctx.new_page()
                errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
                for s in states:
                    pg.goto(f'file://{M}/{n}.html?state={s}&theme={th}&shot=1'); pg.wait_for_timeout(900)
                    box = pg.evaluate("(()=>{const e=document.getElementById('stage');if(!e)return null;const r=e.getBoundingClientRect();const w=e.querySelector('svg > rect');const q=w?w.getBoundingClientRect():{width:0,height:0};return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height),Math.round(q.width),Math.round(q.height)]})()")
                    metrics[f'{n}/{th}/{w}/{s}'] = box
                    pg.screenshot(path=str(OUT / f'{n}-{s}-{w}-{th}.png'))
                if errs: print(n, w, 'ERRORS', errs[:3])
                ctx.close()
    b.close()
print(json.dumps(metrics))
