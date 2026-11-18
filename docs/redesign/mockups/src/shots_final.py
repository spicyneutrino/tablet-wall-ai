"""Screenshots of final.html. Usage: shots_final.py <out-dir> [states,...|all] [themes] [widths]
Waits for fonts and the stage labels; 390 runs with touch emulation (pointer: coarse).
Also prints the preview stage box per state (G1: it must not move between states)."""
import sys, json, pathlib
from playwright.sync_api import sync_playwright
M = pathlib.Path(__file__).resolve().parent.parent
ALL = ['main', 'selected', 'arrange', 'measure-model', 'measure-size', 'measure-ruler', 'measure-review', 'firstrun', 'loading',
       'offline', 'unreachable', 'uncertain', 'conflict', 'server', 'data', 'playback', 'library', 'components']
OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
states = ALL if len(sys.argv) < 3 or sys.argv[2] == 'all' else sys.argv[2].split(',')
themes = sys.argv[3].split(',') if len(sys.argv) > 3 else ['light', 'dark']
widths = [int(w) for w in sys.argv[4].split(',')] if len(sys.argv) > 4 else [1440, 390]
SIZE = {1440: (1440, 900), 390: (390, 844)}
boxes = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for th in themes:
        for w in widths:
            phone = w < 600
            ctx = b.new_context(viewport={'width': SIZE[w][0], 'height': SIZE[w][1]}, color_scheme=th, has_touch=phone, is_mobile=phone,
                                device_scale_factor=1, reduced_motion='reduce')
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            for s in states:
                pg.goto(f'file://{M}/final.html?state={s}&theme={th}&shot=1')
                pg.evaluate('document.fonts.ready')
                pg.wait_for_function('document.fonts.status === "loaded"')
                pg.wait_for_timeout(250)
                if phone and s == states[0]:
                    print(th, w, 'pointer coarse:', pg.evaluate("matchMedia('(pointer: coarse)').matches"))
                boxes[f'{th}/{w}/{s}'] = pg.evaluate("(()=>{const e=document.getElementById('stage');if(!e)return null;const r=e.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]})()")
                pg.screenshot(path=str(OUT / f'{s}-{w}-{th}.png'))
            if errs:
                print(th, w, 'PAGE ERRORS', errs[:3])
            ctx.close()
    b.close()
json.dump(boxes, open(OUT / 'stage-boxes.json', 'w'), indent=0)
for w in widths:
    for th in themes:
        vals = {k.split('/')[2]: v for k, v in boxes.items() if k.startswith(f'{th}/{w}/') and v}
        uniq = {tuple(v) for s, v in vals.items() if s != 'components'}
        print(f'stage box {th} {w}: {len(uniq)} distinct {sorted(uniq)}')
