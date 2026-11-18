"""Token contrast for the final design. Reads tokens.css (the single source), resolves the light
and dark blocks, and checks every foreground/background pair the final mockup uses.
Usage: python contrast_final.py [--md]"""
import re, sys, pathlib

CSS = (pathlib.Path(__file__).parent / 'tokens.css').read_text()


def block(selector):
    i = CSS.index(selector)
    body = CSS[CSS.index('{', i) + 1:]
    depth, out = 1, ''
    for ch in body:
        depth += ch == '{'
        depth -= ch == '}'
        if depth == 0:
            break
        out += ch
    return dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})', out))


light = block(':root {')
dark = {**light, **block(':root[data-theme="dark"] {')}
THEMES = {'light': light, 'dark': dark}


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# (foreground, background, minimum, where it is used)
TEXT = 4.5
UI = 3.0
PAIRS = [
    ('text', 'bg', TEXT, 'Body text on the page'),
    ('text', 'surface', TEXT, 'Body text in the side column and sheets'),
    ('text', 'overlay', TEXT, 'Text in dialogs, popovers, canvas toolbar'),
    ('text', 'tonal', TEXT, 'Secondary (tonal) button label'),
    ('text', 'tonal-hover', TEXT, 'Tonal button label, hover; row hover'),
    ('text', 'well', TEXT, 'Text on a sunken well (library tile caption, meter)'),
    ('text', 'field', TEXT, 'Text-input value'),
    ('text-muted', 'field', TEXT, 'Input unit suffix and placeholder'),
    ('control', 'field', UI, 'Text-input border against its own fill'),
    ('text-muted', 'bg', TEXT, 'Muted text on the page'),
    ('text-muted', 'surface', TEXT, 'Muted text in the side column'),
    ('text-muted', 'overlay', TEXT, 'Muted text in dialogs'),
    ('text-muted', 'tonal', TEXT, 'Muted text on a hovered row'),
    ('text-muted', 'well', TEXT, 'Muted text on a well'),
    ('on-primary', 'primary', TEXT, 'Primary button label'),
    ('on-primary', 'primary-hover', TEXT, 'Primary button label, hover'),
    ('primary', 'surface', TEXT, 'Link and primary text in the side column'),
    ('primary', 'bg', TEXT, 'Link and primary text on the page'),
    ('primary', 'overlay', TEXT, 'Link text in dialogs'),
    ('sel-text', 'sel-bg', TEXT, 'Selected row / pressed tool label'),
    ('tally-preview', 'bg', TEXT, 'Preview tally label'),
    ('tally-live', 'surface', TEXT, 'On wall tally label (side column)'),
    ('tally-live', 'bg', TEXT, 'On wall tally label (phone, on the page)'),
    ('ok', 'surface', TEXT, 'Showing status'),
    ('ok', 'ok-bg', TEXT, 'Healthy summary chip'),
    ('ok', 'bg', TEXT, 'Healthy summary chip text on the page header'),
    ('warn', 'warn-bg', TEXT, 'Warning chip and Next step title'),
    ('text', 'warn-bg', TEXT, 'Body text inside the warning Next step block'),
    ('warn', 'surface', TEXT, 'Warning text in the side column'),
    ('err', 'err-bg', TEXT, 'Error chip and block title, danger tonal button'),
    ('text', 'err-bg', TEXT, 'Body text inside an error block'),
    ('err', 'surface', TEXT, 'Error text in the side column'),
    ('err', 'overlay', TEXT, 'Danger text in a sheet'),
    ('on-primary', 'err', TEXT, 'Filled danger button label (confirmation step)'),
    ('on-primary', 'err-hover', TEXT, 'Filled danger button label, hover'),
    ('text', 'sel-bg', TEXT, 'Body text inside a selected/info block'),
    ('disabled', 'disabled-bg', TEXT, 'Disabled button label'),
    ('disabled', 'surface', TEXT, 'Disabled ghost button label'),
    ('control', 'surface', UI, 'Text input border, switch track off'),
    ('control', 'overlay', UI, 'Text input border in dialogs'),
    ('control', 'bg', UI, 'Text input border on the page'),
    ('focus', 'bg', UI, 'Focus ring on the page'),
    ('focus', 'surface', UI, 'Focus ring in the side column'),
    ('focus', 'overlay', UI, 'Focus ring in dialogs'),
    ('primary', 'bg', UI, 'Selected tab indicator, selected thumbnail ring (page)'),
    ('primary', 'surface', UI, 'Selected tab indicator, current-row bar (side column)'),
    ('primary', 'well', UI, 'Upload progress bar on its track'),
    ('primary', 'tonal', UI, 'Pressed tool indicator on tonal'),
    ('warn', 'surface', UI, 'Drop-target / warning icon'),
    ('primary', 'sel-bg', UI, 'Drop zone border while dragging over'),
]
STAGE = [
    ('stage-text', 'stage', TEXT, 'Tablet label on the stage'),
    ('stage-text', 'stage-pill', TEXT, 'Tablet name in its label pill'),
    ('stage-text', 'stage-body', TEXT, 'Text on a tablet body'),
    ('stage-text', 'stage-hatch', TEXT, 'Text over the offline hatch'),
    ('stage-warn', 'stage-pill', TEXT, '"Offline" in its pill'),
    ('stage-sel', 'stage-screen', TEXT, 'Measure dimensions on a blanked screen'),
    ('stage-sel', 'stage', TEXT, 'Dimension readout on the stage'),
    ('stage-text', 'stage-screen', TEXT, 'Ruler numbers on a blanked screen'),
    ('stage-pill', 'stage-sel', TEXT, 'Edit readout (x, y, turn) on its indigo tag'),
    ('stage-line', 'stage', UI, 'Tablet outline'),
    ('stage-line', 'stage-body', UI, 'Screen outline on the body'),
    ('stage-sel', 'stage', UI, 'Selection ring, handles, preview outline'),
    ('stage-sel', 'stage-body', UI, 'Selection ring over a body'),
    ('stage-handle', 'stage', UI, 'Resize handle fill on the stage'),
    ('stage-handle', 'stage-sel', None, 'Handle fill inside its ring (shape cue only)'),
    ('stage-warn', 'stage', UI, 'Offline outline'),
]


def run(md=False):
    rows, bad = [], 0
    for th, t in THEMES.items():
        for f, b, m, use in PAIRS:
            r = ratio(t[f], t[b])
            ok = r >= m
            bad += not ok
            rows.append((th, f, b, t[f], t[b], r, m, use, ok))
    for th in ('light', 'dark'):
        t = THEMES[th]
        for f, b, m, use in STAGE:
            r = ratio(t[f], t[b])
            ok = m is None or r >= m
            bad += not ok
            rows.append(('stage-' + th, f, b, t[f], t[b], r, m, use, ok))
    if md:
        print('| Theme | Pair | Colours | Ratio | Min | Used for | Result |')
        print('|---|---|---|---:|---|---|---|')
    for th, f, b, cf, cb, r, m, use, ok in rows:
        if md:
            print(f"| {th} | `{f}` on `{b}` | {cf} / {cb} | {r:.2f}:1 | {m if m else 'n/a'} | {use} | {'pass' if ok else 'FAIL'} |")
        elif not ok or '--all' in sys.argv:
            print(f"{'FAIL' if not ok else 'ok  '} {th:12} {f:14} on {b:14} {r:5.2f} (min {m})  {use}")
    print(f"\npairs {len(rows)}  fails {bad}")
    return bad


if __name__ == '__main__':
    sys.exit(1 if run('--md' in sys.argv) else 0)
