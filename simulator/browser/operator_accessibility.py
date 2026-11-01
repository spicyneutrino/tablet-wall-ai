"""Bounded TWR-14 actual-app probes. Run with --artifacts NEW_DIRECTORY."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CONTRAST = r"""() => {
 const rgba=c=>{const a=c.match(/[\d.]+/g).map(Number);return [...a.slice(0,3),a.length>3?a[3]:1]};
 const over=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3])).concat(1);
 const lum=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 return [...document.querySelectorAll('.btn-primary:not(:disabled),.wall-health span,.chip,.hint,[role=status],.page-error,#readiness-status')].filter(e=>e.checkVisibility()&&e.textContent.trim()&&!e.closest('svg,[aria-hidden=true],:disabled')).map(e=>{
 const chain=[];for(let p=e;p;p=p.parentElement)chain.unshift(p);
 let bg=[255,255,255,1],unsupported=false;
 for(const p of chain){const s=getComputedStyle(p);bg=over(rgba(s.backgroundColor),bg);if(s.backgroundImage!=='none'||Number(s.opacity)!==1)unsupported=true;}
 const s=getComputedStyle(e),fg=over(rgba(s.color),bg),a=lum(fg),b=lum(bg),size=parseFloat(s.fontSize);
 return {id:e.id,text:e.textContent.trim().slice(0,140),kind:e.dataset.kind||e.closest('[data-kind]')?.dataset.kind,foreground:fg,background:bg,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),threshold:size>=24||(size>=18.6667&&parseFloat(s.fontWeight)>=700)?3:4.5,unsupported};
 });
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', required=True, type=Path)
    out = parser.parse_args().artifacts.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'checks': [], 'failures': [], 'contrast': [], 'console': [], 'network': [],
              'app_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'command': [sys.executable, *sys.argv], 'root': str(ROOT)}

    def check(ok, name, detail=None):
        report['checks'].append({'name': name, 'pass': bool(ok), 'detail': detail})
        if not ok:
            report['failures'].append(name)
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)

    def wait(predicate):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.15)
        try:
            report['timeout_ui'] = page.locator('#grid-message,#calibration-msg,#tablet-action-message').all_text_contents()
            page.screenshot(path=str(out / 'timeout.png'), full_page=True)
        except UnboundLocalError:
            pass
        raise AssertionError('bounded state wait expired')

    def keyboard(locator):
        locator.focus()
        locator.press('Enter')

    def focus(page):
        return page.evaluate("() => ({tag:document.activeElement.tagName,id:document.activeElement.id,text:document.activeElement.textContent.slice(0,100),disabled:!!document.activeElement.disabled})")

    def contrast(page, state):
        rows = page.evaluate(CONTRAST)
        report['contrast'].append({'state': state, 'rows': rows})
        bad = [r for r in rows if r['unsupported'] or r['ratio'] < r['threshold']]
        check(bool(rows) and not bad, 'contrast ' + state, bad)

    server = None

    def stop_server():
        nonlocal server
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server = None

    try:
        with tempfile.TemporaryDirectory(prefix='wall-accessibility-') as private, open(out / 'server.log', 'w') as log, ExitStack() as cleanup:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            base = f'http://127.0.0.1:{port}'
            env = {k: v for k, v in os.environ.items() if not k.startswith(('TABLET_WALL', 'WALL'))}
            for key, value in {'DB': 'wall.db', 'ASSET_DIR': 'assets', 'MEDIA_DIR': 'media', 'BACKUP_DIR': 'backups'}.items():
                path = Path(private) / value
                if key != 'DB':
                    path.mkdir()
                env['TABLET_WALL_' + key] = str(path)
            env.update(TABLET_WALL_TABLET_ORIGIN=base, TABLET_WALL_OPERATOR_ORIGIN=base, TABLET_WALL_UPLOAD_MODE='disabled')
            report['private_data'] = private
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            cleanup.callback(stop_server)

            def healthy():
                if server.poll() is not None:
                    raise RuntimeError('server exited')
                try:
                    with urllib.request.urlopen(base + '/healthz', timeout=1) as response:
                        return response.status == 200
                except OSError:
                    return False
            wait(healthy)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    tablet_ids = []
                    for _ in range(4):
                        context = browser.new_context(viewport={'width': 1024, 'height': 768}, device_scale_factor=2)
                        client = context.new_page()
                        client.goto(base + '/client/')
                        wait(lambda: client.evaluate("localStorage.getItem('tablet-wall-device-id')"))
                        tablet_ids.append(client.evaluate("localStorage.getItem('tablet-wall-device-id')"))
                    page = browser.new_page(viewport={'width': 1600, 'height': 1000}, reduced_motion='reduce')
                    page.set_default_timeout(5000)
                    page.on('pageerror', lambda error: report['console'].append(str(error)))
                    page.on('console', lambda msg: report['console'].append(msg.text) if msg.type in ('warning', 'error') else None)
                    page.on('requestfailed', lambda req: report['network'].append({'url': req.url, 'failure': req.failure}))
                    page.on('response', lambda res: report['network'].append({'url': res.url, 'status': res.status}) if res.status >= 400 else None)
                    page.goto(base + '/controller/physical.html')
                    wait(lambda: '4 online' in page.locator('#device-count').inner_text())
                    wall = page.get_by_role('tab', name='Wall', exact=True)
                    keyboard(wall)
                    for index, direction in [(1, 'earlier'), (2, 'later')]:
                        keyboard(page.locator('#grid-order li').nth(index).get_by_role('button', name=re.compile('^Move ' + direction)))
                        active = focus(page)
                        check(active['tag'] == 'BUTTON' and not active['disabled'] and active['text'].startswith('Move'), 'reorder boundary ' + direction, active)
                    page.locator('#grid-kind').select_option('logical')
                    keyboard(page.locator('#grid-2x2'))
                    keyboard(page.locator('#grid-preview'))
                    wait(lambda: page.locator('#grid-cancel').is_enabled())
                    contrast(page, 'enabled Apply preview')
                    page.screenshot(path=str(out / '1600-enabled-apply.png'), full_page=True)
                    page.set_viewport_size({'width': 390, 'height': 844})
                    contrast(page, 'phone enabled Apply preview')
                    page.screenshot(path=str(out / '390-enabled-apply.png'), full_page=True)
                    page.set_viewport_size({'width': 1600, 'height': 1000})
                    keyboard(page.locator('#grid-cancel'))
                    check(page.locator('#btn-apply').is_disabled(), 'keyboard preview cancel')
                    keyboard(page.locator('#grid-preview'))
                    wait(lambda: page.locator('#btn-apply').is_enabled())
                    dialogs = []

                    def accept(dialog):
                        dialogs.append(dialog.message)
                        dialog.accept()
                    page.on('dialog', accept)
                    keyboard(page.locator('#btn-apply'))
                    wait(lambda: 'Arrangement applied once' in page.locator('#grid-message').inner_text())
                    check(page.locator('#btn-apply').is_disabled(), 'Apply via Enter committed logical layout')
                    tablet_tab = page.get_by_role('tab', name='Tablets', exact=True)
                    keyboard(tablet_tab)
                    keyboard(page.locator('.dev-pick').first)
                    label = ('長い名前 Café 🧱 العربية ' * 3).strip()
                    page.locator('#tablet-label').fill(label)
                    keyboard(page.locator('#tablet-label-save'))
                    wait(lambda: label.strip() in page.locator('#tablet-action-name').inner_text())
                    check(True, 'long Unicode label persisted')
                    page.locator('#tablet-label').focus()
                    before = focus(page)
                    page.wait_for_timeout(16000)
                    check(focus(page) == before, 'focus after 15-second reconcile', focus(page))
                    extra = browser.new_context()
                    extra_page = extra.new_page()
                    extra_page.goto(base + '/client/')
                    extra_id = extra_page.evaluate("localStorage.getItem('tablet-wall-device-id')")
                    wait(lambda: '5 online' in page.locator('#device-count').inner_text())
                    check(focus(page) == before, 'focus after roster join', focus(page))
                    extra.close()
                    keyboard(page.locator(f'.dev-pick[data-device-id="{extra_id}"]'))
                    wait(lambda: page.locator('#tablet-forget-preview').is_enabled())
                    keyboard(page.locator('#tablet-forget-preview'))
                    wait(lambda: page.locator('#tablet-forget-confirm').is_visible())
                    keyboard(page.locator('#tablet-forget-confirm'))
                    wait(lambda: page.locator(f'.dev-pick[data-device-id="{extra_id}"]').count() == 0)
                    keyboard(page.locator(f'.dev-pick[data-device-id="{tablet_ids[0]}"]'))
                    keyboard(tablet_tab)
                    keyboard(page.locator('#tablet-remove'))
                    wait(lambda: 'Removed active slot' in page.locator('#tablet-action-message').inner_text())
                    check(focus(page)['tag'] != 'BODY', 'focus after remove', focus(page))
                    page.screenshot(path=str(out / 'remove-focus.png'), full_page=True)
                    check(bool(dialogs), 'native Remove confirmation accepted', dialogs)
                    keyboard(wall)
                    page.locator('#layout-name').fill('Accessibility snapshot')
                    keyboard(page.locator('#btn-layout-save'))
                    saved = page.locator('#saved-layouts li').filter(has_text='Accessibility snapshot')
                    wait(lambda: saved.count() == 1)
                    keyboard(saved.get_by_role('button', name='Delete', exact=True))
                    wait(lambda: saved.count() == 0)
                    check(focus(page)['tag'] != 'BODY', 'focus after snapshot delete', focus(page))
                    page.screenshot(path=str(out / 'delete-focus.png'), full_page=True)
                    for width, height in [(1600, 1000), (390, 844)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        for mode in ['normal', 'zoom', 'text']:
                            page.evaluate("mode => {document.documentElement.style.zoom=mode==='zoom'?'2':'1';document.documentElement.style.fontSize=mode==='text'?'200%':''}", mode)
                            for tab in ['Wall', 'Tablets', 'System']:
                                keyboard(page.get_by_role('tab', name=tab, exact=True))
                                if tab == 'System':
                                    wait(lambda: 'Readiness reported' in page.locator('#readiness-status').inner_text())
                                metrics = page.evaluate("""() => ({overflow:document.documentElement.scrollWidth>innerWidth+1,targets:['#btn-apply','#btn-wall-health','#tablet-action-name'].filter(s=>document.querySelector(s).checkVisibility()).map(s=>{const e=document.querySelector(s),r=e.getBoundingClientRect();return {s,width:r.width,height:r.height,clipped:e.scrollWidth>e.clientWidth+1}})})""")
                                check(not metrics['overflow'] and all(t['width']>0 and t['height']>0 and not t['clipped'] for t in metrics['targets']), f'{width} {mode} {tab} layout', metrics)
                                contrast(page, f'{width} {mode} {tab}')
                                unnamed = page.locator('button:visible,input:visible,select:visible,a[href]:visible,[role=button]:visible,[role=tab]:visible').evaluate_all("""es=>es.filter(e=>!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.textContent.trim()&&![...(e.labels||[])].some(l=>l.textContent.trim())&&!(e.tagName==='INPUT'&&['submit','button'].includes(e.type)&&e.value)).map(e=>e.outerHTML)""")
                                check(not unnamed, f'names {width} {mode} {tab}', unnamed)
                                page.screenshot(path=str(out / f'{width}-{mode}-{tab}.png'), full_page=True)
                    page.evaluate("() => {document.documentElement.style.zoom='1';document.documentElement.style.fontSize=''}")
                    page.set_viewport_size({'width': 1600, 'height': 1000})
                    def config():
                        return page.evaluate("fetch('/api/v3/config').then(r=>r.json())")

                    for device_id in tablet_ids:
                        keyboard(tablet_tab)
                        keyboard(page.locator(f'.dev-pick[data-device-id="{device_id}"]'))
                        keyboard(page.get_by_role('tab', name='System', exact=True))
                        page.locator('#measurement-details').evaluate('e => e.open=true')
                        page.locator('#tablet-model').select_option('google-pixel-c')
                        keyboard(page.locator('#apply-tablet-model'))
                        wait(lambda: config()['tablet_assignments'].get(device_id, {}).get('mode') == 'explicit')
                        keyboard(page.locator('#cal-use-viewport'))
                        keyboard(page.locator('#btn-calibration-save'))
                        wait(lambda: any(c['device_id'] == device_id for c in config()['calibrations']))
                    keyboard(wall)
                    page.locator('#grid-kind').select_option('physical')
                    page.locator('#grid-orientation').select_option('landscape')
                    for choice in page.locator('#grid-order .check-label input').all():
                        choice.check()
                    keyboard(page.locator('#grid-2x2'))
                    keyboard(page.locator('#grid-preview'))
                    wait(lambda: page.locator('#btn-apply').is_enabled())
                    keyboard(page.locator('#btn-apply'))
                    wait(lambda: 'Arrangement applied once' in page.locator('#grid-message').inner_text())
                    check(any('Replace the' in text for text in dialogs), 'cross-kind Apply confirmation accepted')
                    slot = page.locator('#stage-svg .slot').first
                    keyboard(slot)
                    slot.press('ArrowRight')
                    check(page.locator('#btn-apply').is_enabled(), 'keyboard nudge creates draft')
                    keyboard(page.locator('#btn-cancel'))
                    check(page.locator('#btn-apply').is_disabled(), 'keyboard cancel nudge')
                    keyboard(wall)
                    wall.press('ArrowRight')
                    check(page.get_by_role('tab', name='Tablets', exact=True).get_attribute('aria-selected') == 'true', 'arrow tab navigation')
                    keyboard(wall)
                    page.locator('#grid-rows').fill('0')
                    keyboard(page.locator('#grid-preview'))
                    wait(lambda: 'Cannot preview' in page.locator('#grid-message').inner_text())
                    check(page.locator('#grid-message').get_attribute('aria-live') == 'polite', 'real invalid-input error in live region', page.locator('#grid-message').inner_text())
                    contrast(page, 'real preview error')
                    page.screenshot(path=str(out / 'desktop-error-focused.png'), full_page=True)
                    keyboard(page.get_by_role('tab', name='System', exact=True))
                    assets = Path(private) / 'assets'
                    assets.rename(Path(private) / 'assets-away')
                    keyboard(page.locator('#btn-readiness-refresh'))
                    wait(lambda: page.locator('#btn-readiness-refresh').inner_text() == 'Refresh readiness')
                    contrast(page, 'readiness missing private asset directory')
                    report['readiness_missing_assets'] = page.locator('#readiness-status').inner_text()
                    (Path(private) / 'assets-away').rename(assets)
                    page.locator('#cal-viewport-width').fill('0')
                    keyboard(page.locator('#btn-calibration-save'))
                    wait(lambda: page.locator('#calibration-msg').get_attribute('data-kind') == 'err')
                    check(page.locator('#calibration-msg').get_attribute('aria-live') == 'polite', 'actual calibration error live region', page.locator('#calibration-msg').inner_text())
                    for width, height in [(1600, 1000), (390, 844)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        contrast(page, f'{width} actual calibration error')
                        page.screenshot(path=str(out / f'{width}-calibration-error.png'), full_page=True)
                    for tab in page.get_by_role('tab').all():
                        keyboard(tab)
                        unnamed = page.locator('button:visible,input:visible,select:visible,a[href]:visible,[role=button]:visible,[role=tab]:visible').evaluate_all("""es=>es.filter(e=>!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.textContent.trim()&&![...(e.labels||[])].some(l=>l.textContent.trim())).map(e=>e.outerHTML)""")
                        check(not unnamed, 'visible names final ' + tab.inner_text(), unnamed)
                    check(page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"), 'reduced motion preference active')
                    check(not report['console'] and not report['network'], 'no unexpected console or network failures')
                finally:
                    browser.close()
    except Exception as error:
        report['failures'].append(repr(error))
        raise
    finally:
        stop_server()
        report['private_data_removed'] = not Path(report.get('private_data', '')).exists()
        (out / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
