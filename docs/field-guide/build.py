#!/usr/bin/env python3
"""Build the field-guide site from GUIDE.md.

The Markdown is the source. This script renders it, inlines the local SVG
figures, builds the chapter navigation, and writes index.html.

    ../../.venv/bin/python build.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

ROOT = Path(__file__).parent
GUIDE = ROOT / "GUIDE.md"
TEMPLATE = ROOT / "site" / "template.html"
OUT = ROOT / "index.html"


def slugify(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "section"


def split_front_matter(source: str) -> tuple[dict, str]:
    if not source.startswith("---\n"):
        raise SystemExit("GUIDE.md must start with a YAML front matter block")
    end = source.find("\n---\n", 4)
    if end == -1:
        raise SystemExit("unterminated YAML front matter")
    metadata = yaml.safe_load(source[4:end]) or {}
    return metadata, source[end + 5 :]


def add_heading_ids(rendered: str) -> str:
    used: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        level, inner = match.group(1), match.group(2)
        base = slugify(inner)
        plain = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        slug = base
        index = 2
        while slug in used:
            slug = f"{base}-{index}"
            index += 1
        used.add(slug)
        anchor = (
            f'<a class="heading-anchor" href="#{slug}" tabindex="-1" '
            f'aria-label="Link to section: {html.escape(plain, quote=True)}">#</a>'
        )
        return f'<h{level} id="{slug}">{inner}{anchor}</h{level}>'

    return re.sub(r"<h([2-4])>(.*?)</h\1>", replace, rendered, flags=re.DOTALL)


def inline_figures(rendered: str) -> str:
    pattern = re.compile(
        r'<p>\s*<img\s+src="(figures/[^"]+)"\s+alt="([^"]*)"\s*/?>\s*</p>',
        re.IGNORECASE,
    )
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        path, alt = match.group(1), html.unescape(match.group(2))
        svg_path = ROOT / path
        if not svg_path.is_file():
            raise SystemExit(f"missing figure: {svg_path}")
        svg = svg_path.read_text()
        svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
        svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.IGNORECASE)
        figure_id = f"figure-{slugify(Path(path).stem)}"
        return (
            f'<figure class="figure" id="{figure_id}">'
            f'<div class="figure-art"><button class="figure-zoom" type="button" '
            f'aria-label="Enlarge figure {count}: {html.escape(alt, quote=True)}">'
            f"{svg}</button></div>"
            f'<figcaption><span class="figure-number">Figure {count:02d}</span>'
            f"{html.escape(alt)}</figcaption></figure>"
        )

    return pattern.sub(replace, rendered)


def wrap_tables(rendered: str) -> str:
    return re.sub(
        r"<table>.*?</table>",
        lambda match: f'<div class="table-wrap">{match.group(0)}</div>',
        rendered,
        flags=re.DOTALL,
    )


def mark_blockquotes(rendered: str) -> str:
    def replace(match: re.Match[str]) -> str:
        body = match.group(1)
        if "Pattern to steal" in body:
            return f'<blockquote class="pattern">{body}</blockquote>'
        return f'<blockquote class="note">{body}</blockquote>'

    return re.sub(r"<blockquote>(.*?)</blockquote>", replace, rendered, flags=re.DOTALL)


def split_chapters(rendered: str) -> tuple[str, list[dict]]:
    matches = list(re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', rendered, flags=re.DOTALL))
    if not matches:
        raise SystemExit("GUIDE.md needs at least one level-2 chapter heading")
    intro = rendered[: matches[0].start()]
    chapters: list[dict] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(rendered)
        inner = match.group(2)
        title_html = re.sub(
            r'<a class="heading-anchor".*?</a>', "", inner, flags=re.DOTALL
        )
        title = html.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        chapters.append(
            {
                "id": match.group(1),
                "title": title,
                "number": index + 1,
                "html": rendered[match.start() : end],
            }
        )
    return intro, chapters


def build_nav(chapters: list[dict], groups: list[dict]) -> list[dict]:
    nav = []
    for group in groups or []:
        start, end = int(group["start"]), int(group["end"])
        items = chapters[start - 1 : end]
        if not items:
            continue
        nav.append(
            {
                "label": group["label"],
                "items": items,
            }
        )
    return nav


def main() -> None:
    from make_figures import main as build_figures

    build_figures()
    metadata, body = split_front_matter(GUIDE.read_text())
    md = MarkdownIt("commonmark", {"html": True, "typographer": False}).enable("table")
    rendered = md.render(body)
    rendered = add_heading_ids(rendered)
    rendered = inline_figures(rendered)
    rendered = wrap_tables(rendered)
    rendered = mark_blockquotes(rendered)
    intro, chapters = split_chapters(rendered)
    nav = build_nav(chapters, metadata.get("groups", []))

    hero_figure = metadata.get("hero_figure")
    hero_svg = ""
    if hero_figure:
        hero_svg = (ROOT / hero_figure).read_text()
        hero_svg = re.sub(r"<\?xml[^>]*\?>\s*", "", hero_svg)
        hero_svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", hero_svg, flags=re.IGNORECASE)

    env = Environment(
        loader=FileSystemLoader(ROOT / "site"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("template.html")
    html_out = template.render(
        meta=metadata,
        hero_svg=hero_svg,
        intro=intro,
        chapters=chapters,
        nav=nav,
        chapter_count=len(chapters),
    )
    html_out = "\n".join(line.rstrip() for line in html_out.splitlines()) + "\n"
    OUT.write_text(html_out)
    words = len(re.findall(r"\b\w+\b", body))
    print(f"wrote {OUT} ({words:,} words, {len(chapters)} chapters)")


if __name__ == "__main__":
    main()
