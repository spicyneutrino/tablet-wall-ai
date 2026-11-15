"""axe-core plus a rendered contrast walk over every state of final.html, both widths and themes.
The walk records every text colour / background pair that is actually painted (composited through
ancestors), plus input borders, selected-tab indicators and focus rings, and fails any pair below
its WCAG minimum. SVG stage text is covered by contrast_final.py (axe marks it incomplete).
Writes shots/final/audit.json."""
import json, pathlib, sys, urllib.request
from playwright.sync_api import sync_playwright
M = pathlib.Path(__file__).resolve().parent.parent
OUT = M.parent / 'shots' / 'final'; OUT.mkdir(parents=True, exist_ok=True)
AXE = pathlib.Path('/tmp/axe-4.10.2.min.js')  # same cached copy axe.py uses
if not AXE.exists():
    AXE.write_bytes(urllib.request.urlopen('https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js').read())
STATES = ['main', 'selected', 'arrange', 'measure-model', 'measure-size', 'measure-ruler', 'measure-review', 'firstrun', 'loading',
          'offline', 'unreachable', 'uncertain', 'conflict', 'server', 'data', 'playback', 'library', 'components']
WALK = r"""(() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (a, b) => [0,1,2].map(i => a[i] * a[3] + b[i] * (1 - a[3])).concat(1);
  const lum = c => { const v = c.slice(0,3).map(x => { x /= 255; return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126*v[0] + 0.7152*v[1] + 0.0722*v[2]; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x,y) + 0.05) / (Math.min(x,y) + 0.05); };
  const hex = c => '#' + c.slice(0,3).map(x => Math.round(x).toString(16).padStart(2,'0')).join('');
  // effective background: composite every translucent layer from the root down; flag images/stage behind
  const bgOf = el => { const chain = []; for (let e = el; e; e = e.parentElement) chain.push(e);
    let col = parse(getComputedStyle(document.documentElement).backgroundColor) || [255,255,255,1]; if (col[3] < 1) col = over(col, [255,255,255,1]);
    let img = false;
    for (const e of chain.reverse()) { const cs = getComputedStyle(e); const c = parse(cs.backgroundColor);
      if (c && c[3] > 0) col = over(c, col);
      if (cs.backgroundImage !== 'none' && !e.matches('select')) img = true; }
    // overlays drawn on the stage (absolutely positioned siblings of the stage well) sit on --stage
    if (el.closest('[data-on-stage]') && col[3] === 1 && !chain.some(e => e.closest('[data-on-stage]') && parse(getComputedStyle(e).backgroundColor)[3] > 0)) {
      const v = getComputedStyle(document.documentElement).getPropertyValue('--stage').trim(); col = [1,3,5].map(i => parseInt(v.slice(i, i + 2), 16)).concat(1); }
    return {col, img}; };
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.opacity !== '0' && !e.closest('.proto,.sr-only,svg,[aria-hidden="true"]'); };
  const inert = e => { const d = document.querySelector('dialog[open]'); return d && !d.contains(e); };
  const pairs = [];
  const add = (kind, fg, bg, min, el) => { const r = ratio(fg, bg); pairs.push({kind, fg: hex(fg), bg: hex(bg), r: Math.round(r*100)/100, min, ok: r >= min - 0.005, where: (el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].slice(0,3).join('.')) + ' "' + (el.textContent || '').trim().slice(0, 30) + '"'}); };
  for (const e of document.querySelectorAll('body *')) {
    if (!vis(e) || inert(e)) continue;
    const cs = getComputedStyle(e);
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const {col, img} = bgOf(e);
    if (own && !img) {
      let fg = parse(cs.color); fg = over(fg, col);
      const px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
      const large = px >= 24 || (px >= 18.66 && bold);
      add(large ? 'text-large' : 'text', fg, col, large ? 3 : 4.5, e);
    }
    if (e.matches('input.input, select.input') && !e.disabled) { const p = bgOf(e.parentElement).col; add('input-border', over(parse(cs.borderTopColor), p), p, 3, e); }
    if (e.matches('input.switch')) { const p = bgOf(e.parentElement).col; add('switch-track', over(parse(cs.backgroundColor), p), p, 3, e); }
    if (e.matches('.tab[aria-selected="true"]')) { const a = getComputedStyle(e, '::after'); add('tab-indicator', parse(a.backgroundColor), col, 3, e); }
    if (e.matches('.src[aria-pressed="true"]')) { add('thumb-ring', parse(getComputedStyle(document.documentElement).getPropertyValue('--primary').trim().replace(/^#(..)(..)(..)$/, (m,a,b,c)=>`rgb(${parseInt(a,16)}, ${parseInt(b,16)}, ${parseInt(c,16)})`)), col, 3, e); }
    if (e.matches('.btn[aria-pressed="true"]')) { const p = bgOf(e.parentElement).col; add('pressed-ring', parse(getComputedStyle(document.documentElement).getPropertyValue('--primary').trim().replace(/^#(..)(..)(..)$/, (m,a,b,c)=>`rgb(${parseInt(a,16)}, ${parseInt(b,16)}, ${parseInt(c,16)})`)), p, 3, e); }
    if (e.matches('.num.is-current, .row[aria-current="true"] .num')) add('current-badge', over(parse(cs.backgroundColor), col), bgOf(e.parentElement).col, 3, e);
    if (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2) { const p = bgOf(e.parentElement).col; add('focus-ring', parse(cs.outlineColor), p, 3, e); }
  }
  return pairs;
})()"""
summary, allpairs = {}, {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for th in ['light', 'dark']:
        for w, h in [(1440, 900), (390, 844)]:
            phone = w < 600
            ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=th, has_touch=phone, is_mobile=phone, reduced_motion='reduce')
            pg = ctx.new_page()
            for s in STATES:
                pg.goto(f'file://{M}/final.html?state={s}&theme={th}&shot=1')
                pg.wait_for_function('document.fonts.status === "loaded"'); pg.wait_for_timeout(200)
                pg.add_script_tag(content=AXE.read_text())
                r = pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']}}).then(r=>({v:r.violations.map(x=>({id:x.id,impact:x.impact,n:x.nodes.length,t:x.nodes.slice(0,3).map(y=>y.target.join(' ')+' :: '+(y.failureSummary||'').slice(0,200))})),inc:r.incomplete.filter(x=>x.id=='color-contrast').reduce((a,x)=>a+x.nodes.length,0),pass:r.passes.filter(x=>x.id=='color-contrast').reduce((a,x)=>a+x.nodes.length,0)}))")
                pairs = pg.evaluate(WALK)
                key = f'{th}/{w}/{s}'
                summary[key] = {'violations': r['v'], 'cc_incomplete': r['inc'], 'cc_pass_nodes': r['pass'], 'walk_fails': [x for x in pairs if not x['ok']]}
                for x in pairs:
                    k = (th, x['kind'], x['fg'], x['bg'])
                    if k not in allpairs or x['r'] < allpairs[k]['r']:
                        allpairs[k] = {**x, 'theme': th, 'example': key}
            ctx.close()
    b.close()
uniq = sorted(allpairs.values(), key=lambda x: (x['theme'], x['kind'], x['r']))
json.dump({'runs': summary, 'pairs': uniq}, open(OUT / 'audit.json', 'w'), indent=1)
viol = [(k, v) for k, s in summary.items() for v in s['violations']]
for k, v in viol:
    print('AXE', k, v['id'], v['impact'], v['n'], v['t'][:2])
wf = [(k, f) for k, s in summary.items() for f in s['walk_fails']]
for k, f in wf[:40]:
    print('CONTRAST', k, f)
print(f"runs {len(summary)}  axe violations {len(viol)}  cc pass nodes {sum(s['cc_pass_nodes'] for s in summary.values())}  cc incomplete {sum(s['cc_incomplete'] for s in summary.values())}")
print(f"rendered pairs {len(uniq)}  below minimum {sum(not x['ok'] for x in uniq)}  lowest text {min((x['r'] for x in uniq if x['kind']=='text'), default=0)}  lowest UI {min((x['r'] for x in uniq if x['kind'] not in ('text','text-large')), default=0)}")
if '--md' in sys.argv:
    print('| Theme | Kind | Foreground | Background | Ratio | Min | Example |')
    print('|---|---|---|---|---:|---|---|')
    for x in uniq:
        print(f"| {x['theme']} | {x['kind']} | {x['fg']} | {x['bg']} | {x['r']}:1 | {x['min']} | {x['example']} {x['where'][:40]} |")
