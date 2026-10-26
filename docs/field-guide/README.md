# Field guide

The current project guide lives here.

- `GUIDE.md` is the source. Edit this when the system changes.
- `index.html` is generated. Open it in a browser.
- `figures/` contains the SVG figures. `make_figures.py` writes them.
- `site/` contains the template, CSS, JavaScript, and bundled fonts.

Rebuild after editing the Markdown or the figure generator:

```bash
make guide
```

`build.py` regenerates the SVG files before it renders the page. Run
`make_figures.py` alone only when you want to inspect the figures without
rebuilding the site.

The site has no runtime dependency on a server. Open `index.html` directly.
The Markdown images and the site figures are the same SVG files; the build
inlines them so they can follow the page theme.
