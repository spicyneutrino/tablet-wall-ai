"""Computed-style walk (type sizes, spacing values), phone scroll stability, visible controls, tool-column height."""
import json, pathlib, sys
from playwright.sync_api import sync_playwright
M = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/mockups')
WALK = r"""(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !e.closest('[hidden],.proto-bar,.sr-only'); };
  const fonts = {}, space = {};
  const add = (o, v, where) => { v = Math.round(parseFloat(v) * 100) / 100; if (!v) return; (o[v] = o[v] || []).length < 3 && o[v].push(where); };
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e) || e.closest('svg')) continue;
    const cs = getComputedStyle(e);
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const tag = e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ').slice(0, 2).join('.') : '');
    if (own) add(fonts, cs.fontSize, tag);
    for (const p of ['marginTop','marginRight','marginBottom','marginLeft','paddingTop','paddingRight','paddingBottom','paddingLeft','rowGap','columnGap']) {
      const v = cs[p]; if (v && v !== 'normal' && v !== 'auto') add(space, Math.abs(parseFloat(v)), tag + ' ' + p);
    }
  }
  for (const t of document.querySelectorAll('svg text')) { const r = t.getBoundingClientRect(); if (r.height && !t.closest('[hidden]')) { const m = t.getScreenCTM(); add(fonts, parseFloat(t.getAttribute('font-size')) * (m ? m.a : 1), 'svg text'); } }
  return {fonts, space};
})()"""
CTRLS = r"""(() => { const vw = innerWidth, vh = innerHeight; let n = 0;
  for (const e of document.querySelectorAll('button,a[href],input,select,textarea,summary,[role=tab],[role=radio],[role=option],[tabindex="0"]')) {
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if (r.width && r.height && r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw && cs.visibility !== 'hidden' && !e.closest('[hidden],.proto-bar') && !e.disabled) n++; }
  return n; })()"""
SCROLL = r"""(async () => { const st = document.getElementById('stage') || document.querySelector('.wall-stage svg');
  const scrollers = [...document.querySelectorAll('*')].filter(e => { const cs = getComputedStyle(e); return /(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 4; });
  window.scrollTo(0, 1e6); scrollers.forEach(e => e.scrollTop = 1e6); await new Promise(r => setTimeout(r, 200));
  const r = st.getBoundingClientRect(); return {top: Math.round(r.top), bottom: Math.round(r.bottom), visible: r.top >= 0 && r.bottom <= innerHeight, scrolled: scrollers.length + (document.scrollingElement.scrollTop > 0 ? 1 : 0)}; })()"""
COL = {'a': '#inspector', 'b': '#tasks', 'c': 'aside'}
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for n in 'abc':
        for w, h in [(1440, 900), (390, 844)]:
            pg = b.new_page(viewport={'width': w, 'height': h})
            for s in ['main', 'selected', 'measure', 'arrange', 'recovery', 'firstrun']:
                pg.goto(f'file://{M}/{n}.html?state={s}&shot=1'); pg.wait_for_timeout(900)
                k = f'{n}/{w}/{s}'
                out[k] = {'walk': pg.evaluate(WALK), 'controls': pg.evaluate(CTRLS)}
                if w == 1440:
                    out[k]['col_scroll_h'] = pg.evaluate(f"(()=>{{const e=[...document.querySelectorAll('{COL[n]}')].find(x=>x.getBoundingClientRect().width>0);return e?[e.scrollHeight,e.clientHeight]:null}})()")
                else:
                    out[k]['scroll'] = pg.evaluate(SCROLL)
            pg.close()
    # today's console
    for w, h in [(1440, 900), (390, 844)]:
        pg = b.new_page(viewport={'width': w, 'height': h}); pg.goto('http://127.0.0.1:8012/controller/physical.html'); pg.wait_for_timeout(2500)
        out[f'today/{w}/main'] = {'controls': pg.evaluate(CTRLS)}
        if w == 390: out[f'today/{w}/main']['scroll'] = pg.evaluate(SCROLL)
        pg.close()
    b.close()
json.dump(out, open(pathlib.Path(__file__).parent.parent.parent / 'shots/mockups/audit-results.json', 'w'), indent=1)
FS = {13, 14, 16, 18, 22}; SP = {1, 2, 4, 8, 12, 16, 24, 32, 48}
for n in 'abc':
    fonts, space = {}, {}
    for k, v in out.items():
        if k.startswith(n + '/'):
            for f, wh in v['walk']['fonts'].items(): fonts.setdefault(float(f), set()).update(wh)
            for f, wh in v['walk']['space'].items(): space.setdefault(float(f), set()).update(wh)
    print(n, 'font sizes', sorted(fonts), 'off-scale', {f: sorted(fonts[f])[:3] for f in fonts if round(f) not in FS})
    print(n, 'spacing', sorted(space), 'off-scale', {f: sorted(space[f])[:3] for f in space if f not in SP})
for k, v in out.items():
    if 'scroll' in v or 'col_scroll_h' in v or k.endswith('/main'):
        print(k, 'controls', v['controls'], v.get('scroll', ''), v.get('col_scroll_h', ''))
