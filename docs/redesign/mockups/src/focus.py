import pathlib
from playwright.sync_api import sync_playwright
M = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/mockups')
OUT = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/shots/mockups')
cases = [('a', 'main', '#m-show'), ('b', 'arrange', '.choice[aria-checked="true"]'), ('c', 'main', '.src[aria-pressed="true"]')]
with sync_playwright() as p:
    b = p.chromium.launch()
    for th in ['light', 'dark']:
        pg = b.new_page(viewport={'width': 1440, 'height': 900}, color_scheme=th)
        for n, s, sel in cases:
            pg.goto(f'file://{M}/{n}.html?state={s}&theme={th}&shot=1'); pg.wait_for_timeout(800)
            for i in range(60):
                pg.keyboard.press('Tab')
                if pg.evaluate(f"document.activeElement && document.activeElement.matches('{sel}')"): break
            ok = pg.evaluate(f"document.activeElement.matches('{sel}') && document.activeElement.matches(':focus-visible')")
            ring = pg.evaluate("(()=>{const cs=getComputedStyle(document.activeElement);return cs.outlineStyle+' '+cs.outlineWidth+' '+cs.outlineColor})()")
            r = pg.evaluate("(()=>{const r=document.activeElement.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()")
            pg.screenshot(path=str(OUT / f'focus-{n}-{th}.png'), clip={'x': max(0, r[0]-24), 'y': max(0, r[1]-24), 'width': r[2]+48, 'height': r[3]+48})
            print(n, th, 'tabs', i+1, 'focus-visible', ok, ring)
        pg.close()
    b.close()
