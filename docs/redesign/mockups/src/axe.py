import sys, json, pathlib, urllib.request
from playwright.sync_api import sync_playwright
M = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/mockups')
AXE = pathlib.Path('/tmp/axe-4.10.2.min.js')
if not AXE.exists(): AXE.write_bytes(urllib.request.urlopen('https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js').read())
states = ['main','selected','measure','arrange','recovery','firstrun']
summary = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for n in sys.argv[1].split(','):
        for th in ['light','dark']:
            for w,h in [(1440,900),(390,844)]:
                ctx = b.new_context(viewport={'width':w,'height':h}, color_scheme=th); pg = ctx.new_page()
                for s in states:
                    pg.goto(f'file://{M}/{n}.html?state={s}&theme={th}&shot=1'); pg.wait_for_timeout(900)
                    pg.add_script_tag(content=AXE.read_text())
                    r = pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}).then(r=>({v:r.violations.map(x=>({id:x.id,impact:x.impact,n:x.nodes.length,t:x.nodes.slice(0,3).map(y=>y.target.join(' ')+' :: '+(y.failureSummary||'').slice(0,160))})),inc:r.incomplete.filter(x=>x.id=='color-contrast').map(x=>({n:x.nodes.length,t:x.nodes.map(y=>y.target.join(' ')+' :: '+(y.any[0]&&y.any[0].message||'').slice(0,120))})),pass:r.passes.filter(x=>x.id=='color-contrast').map(x=>x.nodes.length)}))")
                    key=f'{n}/{th}/{w}/{s}'; summary[key]={'violations':r['v'],'cc_incomplete':r['inc'],'cc_pass_nodes':r['pass']}
                ctx.close()
    b.close()
json.dump(summary, open(pathlib.Path(__file__).parent.parent.parent/'shots/mockups/axe-results.json','w'), indent=1)
tot=0
for k,v in summary.items():
    if v['violations']:
        for x in v['violations']: tot+=1; print('VIOL',k,x['id'],x['impact'],x['n'],x['t'][:2])
inc=sum(sum(i['n'] for i in v['cc_incomplete']) for v in summary.values())
passn=sum(sum(v['cc_pass_nodes']) for v in summary.values())
print('runs',len(summary),'violation-types',tot,'cc incomplete nodes',inc,'cc pass nodes',passn)
