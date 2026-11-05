#!/usr/bin/env python3
"""Generate the field-guide SVGs from one drawing system.

Run from this directory:

    ../../.venv/bin/python make_figures.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)

FONT = "Cantarell, ui-sans-serif, system-ui, sans-serif"
MONO = "'Source Code Pro', ui-monospace, SFMono-Regular, monospace"


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def text(
    x: float,
    y: float,
    value: str,
    cls: str = "t",
    anchor: str = "start",
    extra: str = "",
) -> str:
    return (
        f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}" {extra}>'
        f"{esc(value)}</text>"
    )


def rect(x: float, y: float, w: float, h: float, cls: str = "surface", rx: float = 3) -> str:
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def line(x1: float, y1: float, x2: float, y2: float, cls: str = "line", extra: str = "") -> str:
    return f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {extra}/>'


def path(d: str, cls: str = "line", extra: str = "") -> str:
    return f'<path class="{cls}" d="{d}" {extra}/>'


def arrow(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    prefix: str,
    cls: str = "arrow",
    dashed: bool = False,
) -> str:
    dash = ' stroke-dasharray="5 5"' if dashed else ""
    return (
        f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
        f'{dash} marker-end="url(#{prefix}-arrow)"/>'
    )


def dot(x: float, y: float, r: float = 4, cls: str = "dot") -> str:
    return f'<circle class="{cls}" cx="{x}" cy="{y}" r="{r}"/>'


def label_box(x: float, y: float, w: float, h: float, title: str, sub: str = "", cls: str = "surface") -> str:
    parts = [rect(x, y, w, h, cls)]
    if sub:
        parts.append(text(x + 14, y + 24, title, "label-strong"))
        parts.append(text(x + 14, y + 44, sub, "small"))
    else:
        parts.append(text(x + 14, y + h / 2 + 5, title, "label"))
    return "".join(parts)


def scope_css(css: str) -> str:
    def replace(match: re.Match[str]) -> str:
        selector = match.group(1)
        if selector == "text":
            selector = "svg text"
        elif selector.startswith("."):
            selector = "svg " + selector
        return f"{selector} {{"

    return re.sub(r"(?m)^\s*(\.?[a-zA-Z][a-zA-Z0-9_-]*)\s*\{", replace, css)

def base_style(prefix: str) -> str:
    css = f"""
<style>
  .bg {{ fill: var(--fig-bg, #f6f8f4); }}
  .surface {{ fill: var(--fig-surface, #ffffff); stroke: var(--fig-line, #ccd8d0); stroke-width: 1.2; }}
  .surface-2 {{ fill: var(--fig-surface-2, #eef3ef); stroke: var(--fig-line, #ccd8d0); stroke-width: 1.2; }}
  .surface-accent {{ fill: var(--fig-accent-soft, #dff1ec); stroke: var(--fig-accent, #0b6b63); stroke-width: 1.4; }}
  .surface-warn {{ fill: var(--fig-warn-soft, #f6ead8); stroke: var(--fig-warn, #985a00); stroke-width: 1.2; }}
  .surface-bad {{ fill: var(--fig-bad-soft, #f6e1df); stroke: var(--fig-bad, #a43a31); stroke-width: 1.2; }}
  .wall {{ fill: var(--fig-wall, #101b17); stroke: var(--fig-wall-line, #2b3b34); stroke-width: 1.2; }}
  .line {{ stroke: var(--fig-line, #ccd8d0); stroke-width: 1.2; }}
  .line-strong {{ stroke: var(--fig-line-strong, #9fb0a6); stroke-width: 1.6; }}
  .arrow {{ stroke: var(--fig-muted, #56655d); stroke-width: 1.5; fill: none; }}
  .arrow-accent {{ stroke: var(--fig-accent, #0b6b63); stroke-width: 1.8; fill: none; }}
  .arrow-warn {{ stroke: var(--fig-warn, #985a00); stroke-width: 1.6; fill: none; }}
  .dot {{ fill: var(--fig-accent, #0b6b63); }}
  .dot-warn {{ fill: var(--fig-warn, #985a00); }}
  .dot-bad {{ fill: var(--fig-bad, #a43a31); }}
  .dot-muted {{ fill: var(--fig-muted, #56655d); }}
  text {{ font-family: {FONT}; fill: var(--fig-ink, #15211b); }}
  .t {{ font-size: 14px; }}
  .small {{ font-size: 12.5px; fill: var(--fig-muted, #56655d); }}
  .tiny {{ font-size: 11.5px; fill: var(--fig-muted, #56655d); letter-spacing: .02em; }}
  .label {{ font-size: 14.5px; }}
  .label-strong {{ font-size: 14px; font-weight: 700; }}
  .title {{ font-size: 18px; font-weight: 700; letter-spacing: -.01em; }}
  .display {{ font-size: 34px; font-weight: 700; letter-spacing: -.03em; }}
  .num {{ font-family: {MONO}; font-size: 11.5px; fill: var(--fig-accent, #0b6b63); letter-spacing: .04em; }}
  .mono {{ font-family: {MONO}; font-size: 12.5px; }}
  .mono-strong {{ font-family: {MONO}; font-size: 12.5px; font-weight: 600; }}
  .accent {{ fill: var(--fig-accent, #0b6b63); }}
  .warn {{ fill: var(--fig-warn, #985a00); }}
  .bad {{ fill: var(--fig-bad, #a43a31); }}
  .muted {{ fill: var(--fig-muted, #56655d); }}
  .ink {{ fill: var(--fig-ink, #15211b); }}
  .panel-label {{ font-size: 12px; font-weight: 700; fill: var(--fig-wall-ink, #e6efe9); }}
  .panel-small {{ font-family: {MONO}; font-size: 9.5px; fill: var(--fig-wall-muted, #93a69c); }}
</style>
"""
    return scope_css(css)


def svg_doc(prefix: str, title: str, body: str, w: int = 960, h: int = 560) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{prefix}-title {prefix}-desc">
<title id="{prefix}-title">{esc(title)}</title>
<desc id="{prefix}-desc">{esc(title)}</desc>
<defs>
  <marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--fig-muted, #56655d)"/>
  </marker>
  <pattern id="{prefix}-dots" width="22" height="22" patternUnits="userSpaceOnUse">
    <circle cx="1" cy="1" r="1" fill="var(--fig-dot, #d6e0d9)"/>
  </pattern>
</defs>
{base_style(prefix)}
<rect class="bg" width="{w}" height="{h}"/>
<rect width="{w}" height="{h}" fill="url(#{prefix}-dots)" opacity=".55"/>
{body}
</svg>
"""


def write(name: str, prefix: str, title: str, body: str, w: int = 960, h: int = 560) -> None:
    (OUT / name).write_text(svg_doc(prefix, title, body, w, h).rstrip() + "\n")


def hero_wall() -> None:
    body = []
    # calibration ticks
    for i in range(0, 9):
        x = 64 + i * 92
        body.append(line(x, 44, x, 54, "line"))
        body.append(text(x, 36, f"{i * 250}", "tiny", "middle"))
    body.append(text(64, 22, "WALL ELEVATION / 2000 × 1000", "mono"))
    body.append(text(896, 22, "AUDIENCE VIEW", "tiny", "end"))
    # 3x2 panels
    panels = [
        (120, 92, 230, 154, "#1"),
        (360, 92, 230, 154, "#2"),
        (600, 92, 230, 154, "#3"),
        (120, 264, 230, 154, "#4"),
        (360, 264, 230, 154, "#5"),
        (600, 264, 230, 154, "#6"),
    ]
    for x, y, w, h, name in panels:
        body.append(rect(x, y, w, h, "wall", 4))
        body.append(rect(x + 10, y + 10, w - 20, h - 20, "wall", 2))
        body.append(text(x + 24, y + 34, name, "num"))
        body.append(dot(x + w - 24, y + 28, 3.5, "dot"))
        body.append(line(x + 24, y + h - 28, x + w - 24, y + h - 28, "line"))
    # signal path and commit line
    body.append(path("M 78 350 C 82 180, 92 160, 112 160", "arrow-accent"))
    body.append(dot(78, 350, 5, "dot"))
    body.append(line(820, 70, 820, 472, "line-strong", 'stroke-dasharray="3 5"'))
    body.append(path("M 812 70 L 828 70 L 820 84 Z", "accent"))
    body.append(text(836, 88, "cut", "mono-strong"))
    body.append(text(836, 104, "t + 1000 ms", "small"))
    body.append(text(64, 500, "ONE SOURCE IMAGE", "mono-strong"))
    body.append(text(64, 518, "Each tablet draws only its slice of the same wall.", "small"))
    body.append(text(896, 500, "6 PANELS", "mono-strong", "end"))
    body.append(text(896, 518, "geometry, not six copies", "small", "end"))
    write("hero-wall.svg", "hero", "A six-panel wall elevation with one source image and a future commit line.", "".join(body), 960, 560)


def system_map() -> None:
    b = []
    b.append(text(52, 38, "RUNTIME TOPOLOGY", "mono"))
    b.append(text(908, 38, "one host · one process · one database", "small", "end"))
    # tablets
    b.append(rect(44, 84, 190, 330, "surface-2", 6))
    b.append(text(58, 110, "Tablets", "label-strong"))
    b.append(text(58, 128, "browser clients", "small"))
    for i, y in enumerate((150, 226, 302)):
        b.append(rect(58, y, 162, 58, "wall", 3))
        b.append(text(72, y + 23, f"#{i + 1}", "num"))
        b.append(text(104, y + 23, "client.js", "panel-label"))
        b.append(text(104, y + 40, "canvas / video", "panel-small"))
        b.append(dot(202, y + 14, 3, "dot"))
    b.append(text(58, 394, "WebSocket v3", "mono"))
    b.append(text(58, 410, "HTTP assets", "small"))
    # server
    b.append(rect(322, 72, 320, 384, "surface", 8))
    b.append(text(340, 98, "FastAPI process", "label-strong"))
    b.append(text(340, 116, "main.py", "mono"))
    modules = [
        ("state.py", "roster · sockets · wall"),
        ("playback.py", "leases · commits"),
        ("geometry.py", "N → P plans"),
        ("media.py", "admit · publish"),
        ("persist.py", "SQLite docs"),
        ("writer.py / hub.py", "queues · broadcast"),
    ]
    for i, (name, sub) in enumerate(modules):
        x = 340 + (i % 2) * 146
        y = 140 + (i // 2) * 76
        b.append(rect(x, y, 132, 58, "surface-2", 3))
        b.append(text(x + 10, y + 22, name, "mono-strong"))
        b.append(text(x + 10, y + 40, sub, "tiny"))
    b.append(text(340, 390, "one event loop", "small"))
    b.append(text(340, 408, "server clock · 100 ms playback tick", "tiny"))
    b.append(text(340, 428, "loopback :8000", "mono"))
    # operators
    b.append(rect(724, 84, 190, 144, "surface-2", 6))
    b.append(text(738, 110, "Physical console", "label-strong"))
    b.append(text(738, 128, "physical.html", "mono"))
    b.append(text(738, 156, "HTTP poll 1 s", "small"))
    b.append(text(738, 174, "no controller socket", "small"))
    b.append(text(738, 200, "stage + tabs", "tiny"))
    b.append(rect(724, 252, 190, 128, "surface-2", 6))
    b.append(text(738, 278, "Legacy console", "label-strong"))
    b.append(text(738, 296, "index.html", "mono"))
    b.append(text(738, 324, "WS v2 listener", "small"))
    b.append(text(738, 342, "upload + logical wall", "small"))
    b.append(text(738, 368, "phase 3 retirement", "tiny"))
    # stores
    b.append(rect(322, 484, 152, 48, "surface-accent", 4))
    b.append(text(338, 504, "wall_state", "mono-strong"))
    b.append(text(338, 520, "SQLite schema 3", "tiny"))
    b.append(rect(490, 484, 152, 48, "surface-accent", 4))
    b.append(text(506, 504, "objects/", "mono-strong"))
    b.append(text(506, 520, "content-addressed", "tiny"))
    # arrows
    b.append(arrow(234, 250, 312, 250, "sys", "arrow-accent"))
    b.append(arrow(312, 300, 234, 300, "sys", "arrow"))
    b.append(arrow(724, 156, 650, 156, "sys", "arrow"))
    b.append(arrow(724, 316, 650, 316, "sys", "arrow"))
    b.append(arrow(410, 456, 398, 476, "sys"))
    b.append(arrow(560, 456, 566, 476, "sys"))
    b.append(text(244, 240, "WS", "mono"))
    b.append(text(244, 320, "frames", "tiny"))
    b.append(text(670, 146, "HTTP", "mono", "end"))
    b.append(text(670, 340, "WS", "mono", "end"))
    b.append(text(480, 468, "commit before broadcast", "small", "middle"))
    write("system-map.svg", "sys", "One FastAPI process, tablet sockets, two operator pages, and two stores.", "".join(b))


def commit_path() -> None:
    b = []
    b.append(text(52, 38, "COMMIT PATH", "mono"))
    b.append(text(908, 38, "write-ahead, then broadcast", "small", "end"))
    steps = [
        ("1", "Controller PUT", "If-Match: current ETag"),
        ("2", "Copy + revision", "draft is applied to a copy"),
        ("3", "SQLite commit", "save_state() returns"),
        ("4", "Reapply to live wall", "same change, same revision"),
        ("5", "Broadcast", "snapshots and render frames"),
    ]
    for i, (n, title, sub) in enumerate(steps):
        y = 88 + i * 82
        b.append(rect(70, y, 330, 58, "surface", 4))
        b.append(text(88, y + 23, n, "num"))
        b.append(text(116, y + 23, title, "label-strong"))
        b.append(text(116, y + 42, sub, "small"))
        if i < 4:
            b.append(arrow(235, y + 58, 235, y + 80, "commit"))
    # side rail
    b.append(rect(470, 88, 196, 140, "surface-2", 4))
    b.append(text(486, 112, "On success", "label-strong"))
    b.append(text(486, 134, "revision +1", "mono"))
    b.append(text(486, 152, "new ETag", "mono"))
    b.append(text(486, 170, "memory == disk", "small"))
    b.append(rect(470, 252, 196, 140, "surface-warn", 4))
    b.append(text(486, 276, "Write fails", "label-strong"))
    b.append(text(486, 298, "no memory change", "small"))
    b.append(text(486, 316, "no broadcast", "small"))
    b.append(text(486, 334, "old state stays true", "small"))
    b.append(rect(470, 416, 196, 74, "surface-accent", 4))
    b.append(text(486, 440, "Broadcast fails", "label-strong"))
    b.append(text(486, 460, "committed state still wins", "small"))
    b.append(text(486, 478, "client retries with ETag", "small"))
    # DB and clients
    b.append(rect(724, 88, 170, 96, "surface", 4))
    b.append(text(740, 112, "SQLite", "label-strong"))
    b.append(text(740, 132, "wall_state row", "mono"))
    b.append(text(740, 150, "transactional", "small"))
    b.append(text(740, 168, "one file", "small"))
    b.append(rect(724, 212, 170, 96, "surface", 4))
    b.append(text(740, 236, "Tablets", "label-strong"))
    b.append(text(740, 256, "render frames", "mono"))
    b.append(text(740, 274, "complete state", "small"))
    b.append(text(740, 292, "generation + revision", "small"))
    b.append(arrow(400, 117, 460, 117, "commit"))
    b.append(arrow(666, 117, 714, 117, "commit"))
    b.append(arrow(666, 260, 714, 260, "commit"))
    b.append(text(410, 108, "disk", "tiny"))
    b.append(text(668, 108, "row", "tiny"))
    b.append(text(668, 252, "push", "tiny"))
    b.append(text(70, 510, "A missing or stale If-Match returns 428 or 412 before this path.", "small"))
    write("commit-path.svg", "commit", "A wall write commits to SQLite before memory and delivery change.", "".join(b))


def protocol() -> None:
    b = []
    b.append(text(52, 38, "PROTOCOL VERSIONS", "mono"))
    b.append(text(908, 38, "same transport, different frame shapes", "small", "end"))
    cols = [
        ("v1", "legacy client", "welcome + set_color", "colour only", "device list only"),
        ("v2", "legacy controller + client", "wall", "placement + scene", "snapshot + wall_updated"),
        ("v3", "current client + v3 controller", "render", "plan or calibration reason", "snapshot + config_updated"),
    ]
    for i, (name, who, frame, detail, extra) in enumerate(cols):
        x = 58 + i * 300
        b.append(rect(x, 76, 276, 300, "surface", 6))
        b.append(text(x + 16, 104, name, "display"))
        b.append(text(x + 16, 126, who, "label-strong"))
        b.append(line(x + 16, 142, x + 260, 142, "line"))
        b.append(text(x + 16, 172, "device frame", "tiny"))
        b.append(text(x + 16, 194, frame, "mono-strong"))
        b.append(text(x + 16, 220, detail, "small"))
        b.append(text(x + 16, 258, "operator view", "tiny"))
        b.append(text(x + 16, 280, extra, "mono"))
        if name == "v3":
            b.append(text(x + 16, 314, "physical plan", "small"))
            b.append(text(x + 16, 332, "calibration.status", "mono"))
        elif name == "v2":
            b.append(text(x + 16, 314, "capability downgrade", "small"))
            b.append(text(x + 16, 332, "no unadvertised content", "tiny"))
        else:
            b.append(text(x + 16, 314, "byte-compatible", "small"))
            b.append(text(x + 16, 332, "still served", "tiny"))
    # transport band
    b.append(rect(58, 416, 852, 66, "surface-2", 4))
    b.append(text(74, 442, "HTTP", "mono-strong"))
    b.append(text(74, 462, "commands · reads · ranges · uploads", "small"))
    b.append(text(352, 442, "WebSocket", "mono-strong"))
    b.append(text(352, 462, "device push · controller view", "small"))
    b.append(text(688, 442, "polling", "mono-strong"))
    b.append(text(688, 462, "physical console, 1 s while visible", "small"))
    b.append(text(58, 516, "The physical console does not hold a WebSocket. Its Show panel polls playback status.", "small"))
    write("protocol.svg", "proto", "Three protocol versions share HTTP and WebSocket transport but project different frames.", "".join(b))


def geometry() -> None:
    b = []
    b.append(text(52, 38, "COORDINATE SPACES", "mono"))
    b.append(text(908, 38, "one owner for each transform", "small", "end"))
    # panel cross-section
    b.append(rect(58, 86, 338, 300, "surface", 6))
    b.append(text(74, 112, "Panel body", "label-strong"))
    b.append(rect(86, 138, 282, 206, "wall", 4))
    b.append(rect(128, 170, 198, 142, "surface-accent", 2))
    b.append(text(150, 202, "active panel", "label-strong"))
    b.append(text(150, 222, "P: 0,0 → w,h", "mono"))
    b.append(line(86, 170, 128, 170, "line-strong"))
    b.append(line(326, 312, 368, 312, "line-strong"))
    b.append(text(92, 158, "bezel", "tiny"))
    b.append(text(240, 336, "body B", "small", "middle"))
    b.append(text(92, 362, "W: wall millimetres, audience view", "small"))
    # space ladder
    spaces = [
        ("W", "wall mm", "audience view"),
        ("B", "body mm", "centred on tablet"),
        ("P", "panel mm", "active origin"),
        ("C", "CSS px", "calibrated viewport"),
        ("D", "backing px", "DPR applied"),
        ("N", "normalized", "upright source 0..1"),
    ]
    for i, (key, name, sub) in enumerate(spaces):
        y = 92 + i * 44
        b.append(rect(444, y, 280, 34, "surface-2" if i % 2 else "surface", 2))
        b.append(text(456, y + 22, key, "num"))
        b.append(text(486, y + 22, name, "label-strong"))
        b.append(text(600, y + 22, sub, "small"))
        if i < 5:
            b.append(line(557, y + 34, 557, y + 44, "line"))
    # application order, then the matching product
    b.append(rect(58, 404, 852, 128, "surface-accent", 4))
    chain = [("N", "source", 76), ("P", "panel mm", 280), ("C", "CSS px", 490), ("D", "backing px", 700)]
    for key, name, x in chain:
        b.append(rect(x, 420, 130, 38, "surface", 2))
        b.append(text(x + 10, 438, key, "num"))
        b.append(text(x + 34, 438, name, "label-strong"))
    for x, label in ((206, "G"), (410, "U⁻¹"), (620, "DPR")):
        b.append(arrow(x, 439, x + 58, 439, "geom"))
        b.append(text(x + 29, 432, label, "mono-strong", "middle"))
    b.append(text(76, 476, "G = G_N_to_P (server) · U⁻¹ = inverse(U_C_to_P) (client) · DPR = backing scale (device)", "tiny"))
    b.append(text(76, 500, "product:  backingScale × inverse(U_C_to_P) × G_N_to_P × scale(1 / w, 1 / h)", "mono-strong"))
    b.append(text(76, 520, "Apply the product right to left. The chain above is the same order: N → P → C → D.", "small"))
    write("geometry.svg", "geom", "Every pixel crosses a chain of coordinate spaces from source pixels to panel millimetres.", "".join(b))


def playback_timeline() -> None:
    b = []
    b.append(text(52, 38, "ONE CUT", "mono"))
    b.append(text(908, 38, "readiness, commit, and a future effective time", "small", "end"))
    x0, x1 = 150, 900
    axis_y = 92
    b.append(line(x0, axis_y, x1, axis_y, "line-strong"))
    for i in range(0, 6):
        x = x0 + (x1 - x0) * i / 5
        b.append(line(x, axis_y - 5, x, axis_y + 5, "line"))
        b.append(text(x, axis_y - 14, f"{i * 500} ms", "tiny", "middle"))
    rows = [
        ("prepare", 0, 160, "prepare()", 1),
        ("lease", 90, 2000, "renew every 500 ms", 0),
        ("armed", 1000, 340, "commit arrives", 1),
        ("glass", 1340, 60, "cut", 1),
        ("next", 1500, 220, "next prepare", 1),
    ]
    for i, (name, start_ms, duration, note, outside) in enumerate(rows):
        y = 150 + i * 64
        b.append(text(44, y + 20, name, "mono-strong"))
        bar_x = x0 + start_ms / 3000 * (x1 - x0)
        bar_w = max(8, duration / 3000 * (x1 - x0))
        b.append(rect(bar_x, y, bar_w, 30, "surface-warn" if name == "glass" else "surface-accent", 2))
        if outside:
            note_x = bar_x + bar_w + 8
            if note_x > 850:
                note_x = bar_x - 8
                anchor = "end"
            else:
                anchor = "start"
            b.append(text(note_x, y + 20, note, "small", anchor))
        else:
            b.append(text(bar_x + 8, y + 20, note, "small"))
    cut_x = x0 + 1340 / 3000 * (x1 - x0)
    b.append(line(cut_x, 120, cut_x, 468, "arrow-warn", 'stroke-dasharray="4 5"'))
    b.append(text(cut_x + 8, 132, "effective_server_ms", "mono-strong"))
    b.append(text(150, 500, "Lease: 2 s, renewed every 500 ms", "small"))
    b.append(text(470, 500, "Commit lead: 1 s", "small"))
    b.append(text(700, 500, "Online hold: min(dwell / 2, 5 s)", "small"))
    write("playback-timeline.svg", "line", "A cut is a future timestamp backed by a lease per tablet.", "".join(b))

def playback_states() -> None:
    b = []
    b.append(text(52, 38, "SESSION STATES", "mono"))
    b.append(text(908, 38, "the state machine owns the work it cancels", "small", "end"))
    nodes = [
        ("preparing", 80, 100, 150, 54, "surface"),
        ("armed", 300, 100, 150, 54, "surface-accent"),
        ("playing", 520, 100, 150, 54, "surface-accent"),
        ("final", 760, 100, 140, 54, "surface"),
        ("paused", 520, 230, 150, 54, "surface-warn"),
        ("blocked", 80, 300, 150, 54, "surface-bad"),
        ("failed", 300, 300, 150, 54, "surface-bad"),
        ("recovering", 520, 370, 160, 54, "surface-warn"),
        ("stopped", 760, 250, 140, 54, "surface-2"),
    ]
    for name, x, y, w, h, cls in nodes:
        b.append(rect(x, y, w, h, cls, 4))
        b.append(text(x + w / 2, y + h / 2 + 5, name, "label-strong", "middle"))
    # main chain
    b.append(arrow(230, 127, 292, 127, "state"))
    b.append(text(261, 117, "hold", "tiny", "middle"))
    b.append(arrow(450, 127, 512, 127, "state"))
    b.append(text(481, 117, "commit", "tiny", "middle"))
    b.append(arrow(670, 127, 752, 127, "state"))
    b.append(text(711, 117, "last", "tiny", "middle"))
    # pause and resume
    b.append(arrow(595, 154, 595, 222, "state"))
    b.append(text(607, 190, "pause", "tiny"))
    b.append(path("M 670 257 L 700 257 L 700 60 L 155 60 L 155 92", "arrow"))
    b.append(text(400, 72, "resume: re-prepare", "tiny", "middle"))
    # strict timeout and online hold failure
    b.append(arrow(155, 154, 155, 292, "state"))
    b.append(text(167, 226, "timeout", "tiny"))
    b.append(arrow(375, 154, 375, 292, "state", "arrow", dashed=True))
    b.append(text(387, 226, "no ready member", "tiny"))
    # fault and retry, routed left of paused
    b.append(path("M 520 154 L 492 154 L 492 370 L 512 370", "arrow"))
    b.append(text(500, 310, "fault ↓", "tiny"))
    b.append(path("M 520 397 L 468 397 L 468 154 L 512 154", "arrow"))
    b.append(text(460, 410, "↑ retry", "tiny", "end"))
    # stop note
    b.append(text(760, 340, "stopped = Stop", "mono"))
    b.append(text(760, 358, "from any active state", "tiny"))
    b.append(text(80, 430, "blocked = strict terminal", "small"))
    b.append(text(300, 430, "failed = online terminal", "small"))
    b.append(text(540, 486, "armed = online hold only · playing = committed, not yet painted", "tiny"))
    b.append(text(540, 462, "recovering = same occurrence at the playhead", "small"))
    b.append(text(80, 498, "Retry starts a fresh episode after the automatic cap. Pause cancels an armed commit.", "small"))
    write("playback-states.svg", "state", "Playback is a state machine with explicit terminal states.", "".join(b))

def media_pipeline() -> None:
    b = []
    b.append(text(52, 38, "MEDIA PUBLICATION", "mono"))
    b.append(text(908, 38, "bytes before a ready row", "small", "end"))
    stages = [
        ("POST /uploads", "admit · size · type", 60),
        ("staging", "one job, own dir", 236),
        ("worker", "normalize / remux", 412),
        ("validate", "re-hash · dimensions", 588),
        ("publish", "link immutable object", 764),
    ]
    for i, (name, sub, x) in enumerate(stages):
        b.append(rect(x, 96, 150, 78, "surface", 4))
        b.append(text(x + 12, 122, name, "mono-strong"))
        b.append(text(x + 12, 144, sub, "small"))
        if i < 4:
            b.append(arrow(x + 150, 135, x + 176, 135, "media"))
    b.append(rect(60, 222, 854, 90, "surface-2", 4))
    b.append(text(76, 248, "parent re-checks the worker", "label-strong"))
    b.append(text(76, 270, "role · mime · pixel dimensions · video facts · output hash", "small"))
    b.append(text(76, 292, "a worker result is not trusted until the parent verifies the bytes", "small"))
    # two destinations
    b.append(rect(170, 360, 250, 92, "surface-accent", 4))
    b.append(text(188, 386, "objects/<sha>/", "mono-strong"))
    b.append(text(188, 408, "content-addressed", "small"))
    b.append(text(188, 426, "atomic link, never replace", "small"))
    b.append(rect(540, 360, 250, 92, "surface-accent", 4))
    b.append(text(558, 386, "SQLite ready row", "mono-strong"))
    b.append(text(558, 408, "one transaction", "small"))
    b.append(text(558, 426, "points at durable bytes", "small"))
    b.append(arrow(300, 318, 295, 350, "media"))
    b.append(arrow(660, 318, 665, 350, "media"))
    b.append(text(190, 492, "crash between object and row", "small"))
    b.append(text(190, 510, "unlisted object, never served", "small"))
    b.append(text(560, 492, "crash during upload", "small"))
    b.append(text(560, 510, "staging removed on next cleanup", "small"))
    write("media-pipeline.svg", "media", "Bytes become visible only after validation, durable publication, and a ready row.", "".join(b))


def reconnect() -> None:
    b = []
    b.append(text(52, 38, "RECOVERY WINDOW", "mono"))
    b.append(text(908, 38, "same occurrence, live playhead", "small", "end"))
    x0, x1 = 88, 884
    y = 136
    b.append(line(x0, y, x1, y, "line-strong"))
    events = [
        (0, "drop", "socket closes"),
        (150, "backoff", "≤ 5 s cap"),
        (360, "register", "re-register"),
        (520, "prepare", "position-aware"),
        (760, "commit", "common anchor"),
        (900, "playing", "group resumes"),
    ]
    for i, (t, name, sub) in enumerate(events):
        x = x0 + (x1 - x0) * t / 1000
        b.append(dot(x, y, 5, "dot-warn" if i < 3 else "dot"))
        b.append(text(x, y - 18, name, "mono-strong", "middle"))
        b.append(text(x, y + 28, sub, "tiny", "middle"))
    # bars
    b.append(rect(x0, 200, 260, 28, "surface-bad", 2))
    b.append(text(x0 + 8, 219, "freeze cohort", "small"))
    b.append(rect(x0 + 520 / 1000 * (x1 - x0), 200, 290, 28, "surface-accent", 2))
    b.append(text(x0 + 520 / 1000 * (x1 - x0) + 8, 219, "prepare all members", "small"))
    # coalescing callout
    b.append(rect(88, 270, 350, 86, "surface-warn", 4))
    b.append(text(104, 296, "second drop during recovery", "label-strong"))
    b.append(text(104, 318, "coalesced within 2 s", "small"))
    b.append(text(104, 336, "no new attempt consumed", "small"))
    # attempts
    b.append(rect(520, 270, 364, 86, "surface-2", 4))
    b.append(text(536, 296, "bounded automatic attempts", "label-strong"))
    b.append(text(536, 318, "3 attempts → blocked / failed → Retry", "small"))
    b.append(text(536, 336, "operator can stop or start again", "small"))
    b.append(text(88, 420, "A reconnect during video is not a fresh start.", "title"))
    b.append(text(88, 446, "The server freezes the cohort, reads the live position, and re-prepares the same occurrence.", "small"))
    b.append(text(88, 466, "The client's persisted scene is the fallback if recovery cannot finish.", "small"))
    write("reconnect.svg", "rec", "Reconnect during video is a group recovery at the live playhead, not a fresh start.", "".join(b))


def frontends() -> None:
    b = []
    b.append(text(52, 38, "TWO PAGES", "mono"))
    b.append(text(908, 38, "drawing versus editing", "small", "end"))
    # tablet
    b.append(rect(58, 76, 390, 380, "surface", 6))
    b.append(text(74, 102, "Tablet client", "label-strong"))
    b.append(text(74, 120, "frontend/client/", "mono"))
    b.append(rect(90, 144, 326, 238, "wall", 4))
    b.append(rect(116, 170, 126, 92, "surface-accent", 2))
    b.append(rect(250, 170, 126, 92, "surface-accent", 2))
    b.append(rect(116, 270, 260, 84, "surface-warn", 2))
    b.append(text(130, 196, "canvas", "label-strong"))
    b.append(text(130, 214, "stills", "small"))
    b.append(text(264, 196, "canvas", "label-strong"))
    b.append(text(264, 214, "stills", "small"))
    b.append(text(130, 300, "video element", "label-strong"))
    b.append(text(130, 318, "clipped by the same matrix", "small"))
    b.append(text(74, 410, "persisted wall", "mono"))
    b.append(text(74, 430, "restored on stop or close", "small"))
    # console
    b.append(rect(512, 76, 390, 380, "surface", 6))
    b.append(text(528, 102, "Operator workspace", "label-strong"))
    b.append(text(528, 120, "frontend/controller/physical", "mono"))
    b.append(rect(528, 144, 230, 230, "wall", 4))
    b.append(text(544, 170, "stage", "panel-label"))
    b.append(text(544, 188, "SVG · layout geometry", "panel-small"))
    b.append(rect(544, 206, 96, 64, "surface-accent", 2))
    b.append(rect(654, 206, 88, 64, "surface-accent", 2))
    b.append(rect(544, 284, 198, 72, "surface-2", 2))
    b.append(text(560, 310, "selection", "small"))
    b.append(text(560, 328, "draft · undo", "tiny"))
    for i, label in enumerate(["Images", "Tablets", "Arrange", "Saved", "Settings"]):
        y = 144 + i * 46
        style = "surface-accent" if label == "Arrange" else "surface-2"
        b.append(rect(772, y, 114, 38, style, 2))
        b.append(text(786, y + 24, label, "small"))
    b.append(text(528, 410, "draft is local until Apply", "mono"))
    b.append(text(528, 430, "one visible panel", "small"))
    # shared contract
    b.append(rect(58, 484, 844, 50, "surface-accent", 3))
    b.append(text(76, 514, "shared contract: HTTP commands + WebSocket pushes + ETags + the persisted wall", "mono"))
    write("frontends.svg", "ui", "The tablet draws a full-screen wall slice while the console edits and observes.", "".join(b))


def trust() -> None:
    b = []
    b.append(text(52, 38, "TRUST BOUNDARIES", "mono"))
    b.append(text(908, 38, "the proxy authenticates; the app stays loopback", "small", "end"))
    # tablet side
    b.append(rect(56, 96, 210, 250, "surface-2", 6))
    b.append(text(72, 122, "Tablets", "label-strong"))
    b.append(text(72, 140, "hotspot LAN", "small"))
    for i in range(3):
        b.append(rect(74, 160 + i * 52, 174, 38, "wall", 3))
        b.append(text(88, 184 + i * 52, f"#{i + 1}", "num"))
        b.append(text(118, 184 + i * 52, "client page", "panel-label"))
    b.append(text(72, 326, "no pairing", "tiny"))
    # caddy
    b.append(rect(326, 76, 300, 330, "surface", 6))
    b.append(text(342, 102, "Caddy reference", "label-strong"))
    b.append(text(342, 120, "two origins", "small"))
    b.append(rect(342, 144, 268, 96, "surface-accent", 3))
    b.append(text(358, 168, "tablet origin :8443", "mono-strong"))
    b.append(text(358, 188, "allowlist:", "tiny"))
    b.append(text(358, 206, "client · register · ws · assets", "small"))
    b.append(rect(342, 254, 268, 96, "surface-warn", 3))
    b.append(text(358, 278, "operator origin :8444", "mono-strong"))
    b.append(text(358, 298, "Basic auth", "small"))
    b.append(text(358, 316, "sets proxy credential", "small"))
    b.append(text(342, 382, "TLS internal · reference only", "small"))
    # backend
    b.append(rect(680, 76, 222, 330, "surface", 6))
    b.append(text(696, 102, "Backend", "label-strong"))
    b.append(text(696, 120, "loopback :8000", "mono"))
    b.append(rect(696, 144, 190, 60, "surface-2", 3))
    b.append(text(710, 168, "Origin guard", "mono-strong"))
    b.append(text(710, 186, "CSRF fence, not auth", "small"))
    b.append(rect(696, 220, 190, 60, "surface-2", 3))
    b.append(text(710, 244, "Upload admission", "mono-strong"))
    b.append(text(710, 262, "loopback or proxy", "small"))
    b.append(rect(696, 296, 190, 60, "surface-2", 3))
    b.append(text(710, 320, "Asset safety", "mono-strong"))
    b.append(text(710, 338, "hash + O_NOFOLLOW", "small"))
    # arrows
    b.append(arrow(266, 220, 316, 220, "trust"))
    b.append(text(270, 208, "TLS", "tiny"))
    b.append(arrow(626, 190, 670, 190, "trust"))
    b.append(arrow(626, 300, 670, 300, "trust"))
    # risks
    b.append(rect(56, 420, 846, 94, "surface-warn", 4))
    b.append(text(74, 446, "Residual risks", "label-strong"))
    b.append(text(74, 468, "public registration · no device pairing · shared proxy credential · reads are open", "small"))
    b.append(text(74, 490, "installed CA trust, real hotspot, and kiosk behavior remain MISSING", "small"))
    write("trust.svg", "trust", "The reverse proxy is the authentication boundary and the app stays loopback-only.", "".join(b))


def latency() -> None:
    b = []
    b.append(text(52, 38, "TIME BUDGETS", "mono"))
    b.append(text(908, 38, "control loop versus glass", "small", "end"))
    rows = [
        ("heartbeat", "5 s", 5, "surface-2"),
        ("presence timeout", "15 s", 15, "surface-2"),
        ("console poll", "1 s", 1, "surface-2"),
        ("ready lease", "2 s", 2, "surface-accent"),
        ("commit lead", "1 s", 1, "surface-accent"),
        ("prepare timeout", "30 s", 30, "surface-warn"),
        ("reconnect cap", "5 s", 5, "surface-accent"),
    ]
    max_s = 30
    for i, (name, value, seconds, cls) in enumerate(rows):
        y = 92 + i * 48
        b.append(text(56, y + 18, name, "mono-strong"))
        b.append(text(196, y + 18, value, "small"))
        w = 560 * seconds / max_s
        b.append(rect(260, y, max(4, w), 26, cls, 2))
    b.append(line(260, 430, 820, 430, "line-strong"))
    b.append(text(260, 450, "0", "tiny"))
    b.append(text(540, 450, "15 s", "tiny", "middle"))
    b.append(text(820, 450, "30 s", "tiny", "end"))
    b.append(rect(56, 476, 846, 48, "surface-warn", 3))
    b.append(text(72, 506, "Software cut: p95 0.9–1.0 ms  ·  optical target: p95 ≤ 100 ms, max ≤ 250 ms  ·  optical gate MISSING", "mono"))
    write("latency.svg", "lat", "The control loop and the glass have different latency budgets.", "".join(b))


def evidence() -> None:
    b = []
    b.append(text(52, 38, "EVIDENCE LADDER", "mono"))
    b.append(text(908, 38, "each layer proves a different claim", "small", "end"))
    layers = [
        ("Unit + contract", "995 passed", 0.20, "surface-2"),
        ("Node client", "drawing · view · wake lock", 0.38, "surface-2"),
        ("Simulator", "23 scenarios · 1,075 checks", 0.56, "surface"),
        ("Browser runner", "real DOM · canvas · video", 0.74, "surface-accent"),
        ("Hardware gate", "camera · tablets · AP · soak", 0.92, "surface-warn"),
    ]
    for i, (name, sub, width, cls) in enumerate(layers):
        x = 80 + (1 - width) * 400
        y = 88 + i * 70
        b.append(rect(x, y, width * 500, 48, cls, 3))
        b.append(text(x + 14, y + 21, name, "label-strong"))
        b.append(text(x + 14, y + 38, sub, "small"))
    # side notes
    b.append(rect(620, 88, 290, 126, "surface", 3))
    b.append(text(636, 112, "What a pass proves", "label-strong"))
    b.append(text(636, 134, "the code contract, or the DOM", "small"))
    b.append(text(636, 152, "it does not prove a panel", "small"))
    b.append(text(636, 170, "or a real radio", "small"))
    b.append(rect(620, 238, 290, 126, "surface", 3))
    b.append(text(636, 262, "What a gate needs", "label-strong"))
    b.append(text(636, 284, "equipment · operator", "small"))
    b.append(text(636, 302, "artifact hashes · signed row", "small"))
    b.append(text(636, 320, "unobserved intervals recorded", "small"))
    b.append(rect(620, 388, 290, 126, "surface-warn", 3))
    b.append(text(636, 412, "All eight gates", "label-strong"))
    b.append(text(636, 434, "optical · decode/suspend · iOS", "small"))
    b.append(text(636, 452, "calibration · CA trust · Wi-Fi", "small"))
    b.append(text(636, 470, "kiosk · soak", "small"))
    b.append(text(80, 500, "A browser runner is not a hardware result. The kit records that boundary in every report.", "small"))
    write("evidence.svg", "ev", "Evidence layers prove different claims, and the hardware gates remain open.", "".join(b))


def roadmap() -> None:
    b = []
    b.append(text(52, 38, "DELIVERY PHASES", "mono"))
    b.append(text(908, 38, "software closed, hardware open", "small", "end"))
    phases = [
        ("P0", "baseline", "done", "surface-accent"),
        ("R1", "upload + show", "done", "surface-accent"),
        ("R2", "calibration + editor", "done", "surface-accent"),
        ("R3", "clock + hard cuts", "done", "surface-accent"),
        ("R4", "native video", "done", "surface-accent"),
        ("R5", "field readiness", "done", "surface-accent"),
        ("R6", "segmented / live", "not started", "surface-warn"),
    ]
    for i, (name, sub, state, cls) in enumerate(phases):
        x = 56 + (i % 4) * 222
        y = 84 + (i // 4) * 132
        b.append(rect(x, y, 198, 100, cls, 4))
        b.append(text(x + 14, y + 28, name, "num"))
        b.append(text(x + 14, y + 54, sub, "label-strong"))
        b.append(text(x + 14, y + 78, state, "small"))
    # gates
    b.append(rect(56, 360, 846, 96, "surface-warn", 4))
    b.append(text(72, 386, "Open gates", "label-strong"))
    b.append(text(72, 408, "optical still cuts · physical video decode/suspend/recovery · iOS Safari · mixed-model calibration", "small"))
    b.append(text(72, 428, "installed CA trust + origin migration · real Wi-Fi/OS · kiosk · sustained soak", "small"))
    b.append(text(72, 448, "all eight MISSING", "mono-strong"))
    # console
    b.append(rect(56, 478, 846, 52, "surface-2", 3))
    b.append(text(72, 508, "Console: five tasks · image uploads · relative and measured arrangements", "mono"))
    write("roadmap.svg", "road", "Software phases are closed while all eight hardware gates remain open.", "".join(b))


def main() -> None:
    hero_wall()
    system_map()
    commit_path()
    protocol()
    geometry()
    playback_timeline()
    playback_states()
    media_pipeline()
    reconnect()
    frontends()
    trust()
    latency()
    evidence()
    roadmap()
    print(f"wrote {len(list(OUT.glob('*.svg')))} figures to {OUT}")


if __name__ == "__main__":
    main()
