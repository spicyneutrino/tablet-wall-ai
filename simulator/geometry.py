"""Quantitative wall geometry for the tablet-wall simulator.

Pure, dependency-free arithmetic that re-implements the rules PROTOCOL.md
states in "Wall coordinate space", "Aspect and seam caveats" and "Still
images" (fit = centred cover):

* the **visible rect** — a placement's footprint shrunk by its bezel;
* the client's **centred cover** of that rect into its viewport (scale, the
  crop offsets ``ox``/``oy``, and the wall-space window that is actually
  displayed);
* **tiling metrics** — union area, overlap area, uncovered area — for a set
  of placements, so "the grid tiles the wall exactly" is a number and not a
  claim;
* **seam gaps** — wall units (and device pixels) of content that neither of
  two adjacent devices draws.

Nothing here imports the app. Scenarios compare these numbers with what the
server actually put on the wire, which is what makes them a check instead of
a restatement of the same code.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

# "Equal enough" for geometry computed in binary floats: an exactly-matching
# aspect ratio can still land a few 1e-13 off after a division and a
# subtraction. 1e-9 wall units is far below anything a tablet could show.
EPS = 1e-9


class GeometryError(ValueError):
    """A placement/viewport triple the geometry model cannot map."""


# ---------------------------------------------------------------------------
# visible rect (PROTOCOL.md "Wall coordinate space")
# ---------------------------------------------------------------------------


def visible_rect(placement: Mapping[str, Any]) -> dict[str, float]:
    """Footprint minus bezel: ``{x + left, y + top, w - left - right, …}``.

    Raises ``GeometryError`` when the bezel leaves no positive area — the
    server refuses those with 422, so seeing one here means the wire and the
    specification disagree.
    """
    x = float(placement["x"])
    y = float(placement["y"])
    w = float(placement["w"])
    h = float(placement["h"])
    bezel = placement.get("bezel") or {}
    left = float(bezel.get("left", 0) or 0)
    right = float(bezel.get("right", 0) or 0)
    top = float(bezel.get("top", 0) or 0)
    bottom = float(bezel.get("bottom", 0) or 0)

    rect = {
        "x": x + left,
        "y": y + top,
        "w": w - left - right,
        "h": h - top - bottom,
    }
    if rect["w"] <= 0 or rect["h"] <= 0:
        raise GeometryError(f"bezel leaves no visible area: {placement!r}")
    return rect


# ---------------------------------------------------------------------------
# centred cover (PROTOCOL.md "Aspect and seam caveats", client rendering 3/5)
# ---------------------------------------------------------------------------


def centred_cover(
    rect_w: float, rect_h: float, vp_w: float, vp_h: float
) -> tuple[float, float, float]:
    """The client's cover mapping of a rect into a viewport.

    Returns ``(scale, ox, oy)`` where ``scale`` is wall units -> device
    pixels and ``ox``/``oy`` are how much of the rect is cropped off *each*
    side (the rect centre is pinned to the viewport centre). The displayed
    wall window is therefore ``[ox, rect_w - ox] x [oy, rect_h - oy]`` in
    rect-local coordinates.

    A viewport aspect equal to the rect's aspect crops nothing; a viewport
    *wider* than the rect crops vertically only, a *taller* one horizontally
    only — that asymmetry is the whole of the seam story below.
    """
    if rect_w <= 0 or rect_h <= 0:
        raise GeometryError("visible rect must be positive")
    if vp_w <= 0 or vp_h <= 0:
        raise GeometryError("viewport must be positive")
    scale = max(vp_w / rect_w, vp_h / rect_h)
    ox = (rect_w - vp_w / scale) / 2
    oy = (rect_h - vp_h / scale) / 2
    # An exactly matching aspect must crop nothing; floats can leave a
    # hair's-breadth residue (sometimes slightly negative), which no screen
    # could ever show. Snap that residue to zero so callers can assert
    # "gap == 0" exactly for the matched cases.
    if abs(ox) < EPS:
        ox = 0.0
    if abs(oy) < EPS:
        oy = 0.0
    return scale, ox, oy


def aspect(width: float, height: float) -> float:
    """Aspect ratio ``w / h`` (raises for a degenerate height)."""
    if height <= 0:
        raise GeometryError("non-positive height")
    return width / height


def displayed_window(
    rect: Mapping[str, float], viewport: tuple[float, float]
) -> dict[str, float]:
    """The wall-space window a client actually draws: rect inset by the crop.

    Returned in absolute wall coordinates so two neighbours can be compared
    edge to edge.
    """
    scale, ox, oy = centred_cover(
        rect["w"], rect["h"], float(viewport[0]), float(viewport[1])
    )
    return {
        "x0": rect["x"] + ox,
        "y0": rect["y"] + oy,
        "x1": rect["x"] + rect["w"] - ox,
        "y1": rect["y"] + rect["h"] - oy,
        "scale": scale,
        "ox": ox,
        "oy": oy,
    }


# ---------------------------------------------------------------------------
# seam geometry
# ---------------------------------------------------------------------------


def seam_gap(
    rect_a: Mapping[str, float],
    rect_b: Mapping[str, float],
    viewport_a: tuple[float, float],
    viewport_b: tuple[float, float],
    axis: str,
) -> dict[str, float]:
    """How much content the seam between two neighbours hides.

    ``rect_a`` is the left one for ``axis == "x"`` (a vertical seam) and the
    upper one for ``axis == "y"`` (a horizontal seam); ``rect_b`` is the
    other. Each rect may be a *visible* rect, so bezels are part of the
    answer: the distance between the two rects is simply added to the two
    cover crops.

    For a vertical seam, device A draws wall ``[Ax + oxA, …]`` while device B
    starts at ``Bx + oxB``; the strip ``gap`` wall units wide is drawn by
    neither (a negative gap means they overlap and draw it twice). Returns
    the gap in wall units, each device's own crop, and that crop converted
    to device pixels at the device's cover scale.
    """
    if axis not in ("x", "y"):
        raise GeometryError(f"unknown seam axis {axis!r}")
    scale_a, oxa, oya = centred_cover(
        rect_a["w"], rect_a["h"], float(viewport_a[0]), float(viewport_a[1])
    )
    scale_b, oxb, oyb = centred_cover(
        rect_b["w"], rect_b["h"], float(viewport_b[0]), float(viewport_b[1])
    )
    if axis == "x":
        separation = rect_b["x"] - (rect_a["x"] + rect_a["w"])
        gap, ca, cb = separation + oxa + oxb, oxa, oxb
        px_a, px_b = oxa * scale_a, oxb * scale_b
    else:
        separation = rect_b["y"] - (rect_a["y"] + rect_a["h"])
        gap, ca, cb = separation + oya + oyb, oya, oyb
        px_a, px_b = oya * scale_a, oyb * scale_b
    return {
        "gap": gap,
        "crop_a": ca,
        "crop_b": cb,
        "px_a": px_a,
        "px_b": px_b,
    }


def adjacent_pairs(
    cells: Mapping[str, Mapping[str, Any]]
) -> list[tuple[str, str, str, float]]:
    """Pairs of cells that share an edge segment of positive length.

    Each entry is ``(left_or_upper_id, right_or_lower_id, axis, shared_len)``:
    ``axis == "x"`` means a vertical seam (side by side), ``axis == "y"`` a
    horizontal seam (one above the other). Cells meeting only at a corner are
    deliberately not a pair — a corner is not a seam.
    """
    ids = list(cells)
    pairs: list[tuple[str, str, str, float]] = []
    for index, first in enumerate(ids):
        a = cells[first]
        ax, ay, aw, ah = a["x"], a["y"], a["w"], a["h"]
        for second in ids[index + 1 :]:
            b = cells[second]
            bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
            y_overlap = min(ay + ah, by + bh) - max(ay, by)
            x_overlap = min(ax + aw, bx + bw) - max(ax, bx)
            if y_overlap > 0:
                if ax + aw == bx:
                    pairs.append((first, second, "x", float(y_overlap)))
                elif bx + bw == ax:
                    pairs.append((second, first, "x", float(y_overlap)))
            if x_overlap > 0:
                if ay + ah == by:
                    pairs.append((first, second, "y", float(x_overlap)))
                elif by + bh == ay:
                    pairs.append((second, first, "y", float(x_overlap)))
    return pairs


# ---------------------------------------------------------------------------
# tiling metrics
# ---------------------------------------------------------------------------


def _intervals(ranges: Sequence[tuple[int, int]]) -> list[int]:
    """Sorted list of distinct coordinates, including the piecewise cuts."""
    cuts = {value for start, end in ranges for value in (start, end)}
    return sorted(cuts)


def union_area(
    rects: Iterable[Sequence[float]], clip: tuple[int, int, int, int] | None = None
) -> float:
    """Area of the union of axis-aligned rects (coordinate compression).

    Exact for integer coordinates and exact enough for halves: the cuts are
    taken from the rect edges themselves, so every elementary rectangle lies
    wholly inside or wholly outside each rect. ``clip`` limits the result to
    ``(x0, y0, x1, y1)``.
    """
    boxes = []
    for rect in rects:
        x, y, w, h = rect[0], rect[1], rect[2], rect[3]
        boxes.append((float(x), float(y), float(x + w), float(y + h)))
    if clip is not None:
        cx0, cy0, cx1, cy1 = (float(v) for v in clip)
        clipped = []
        for x0, y0, x1, y1 in boxes:
            x0, y0 = max(x0, cx0), max(y0, cy0)
            x1, y1 = min(x1, cx1), min(y1, cy1)
            if x1 > x0 and y1 > y0:
                clipped.append((x0, y0, x1, y1))
        boxes = clipped
    if not boxes:
        return 0.0

    xs = _intervals([(b[0], b[2]) for b in boxes])
    ys = _intervals([(b[1], b[3]) for b in boxes])
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x1 <= x0:
            continue
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            if y1 <= y0:
                continue
            for bx0, by0, bx1, by1 in boxes:
                if bx0 <= x0 and y0 >= by0 and bx1 >= x1 and by1 >= y1:
                    total += (x1 - x0) * (y1 - y0)
                    break
    return total


def tiling_report(
    cells: Mapping[str, Mapping[str, Any]], wall_w: int, wall_h: int
) -> dict[str, Any]:
    """Numbers behind "these cells tile the wall exactly".

    ``exact_partition`` is true only when the cells are all positive, all
    inside the wall, pairwise non-overlapping (``overlap_area == 0``) and
    together covering every wall unit (``uncovered_area == 0``).
    """
    rects = [
        (cell["x"], cell["y"], cell["w"], cell["h"]) for cell in cells.values()
    ]
    degenerate = sorted(
        device_id
        for device_id, cell in cells.items()
        if cell["w"] <= 0 or cell["h"] <= 0
    )
    out_of_bounds = sorted(
        device_id
        for device_id, cell in cells.items()
        if cell["x"] < 0
        or cell["y"] < 0
        or cell["x"] + cell["w"] > wall_w
        or cell["y"] + cell["h"] > wall_h
    )
    sum_area = float(sum(cell["w"] * cell["h"] for cell in cells.values()))
    union = union_area(rects)
    covered = union_area(rects, clip=(0, 0, wall_w, wall_h))
    wall_area = float(wall_w * wall_h)
    overlap_area = max(0.0, sum_area - union)
    outside_area = max(0.0, union - covered)
    uncovered_area = max(0.0, wall_area - covered)
    return {
        "cell_count": len(rects),
        "wall_area": wall_area,
        "sum_area": sum_area,
        "union_area": union,
        "covered_area": covered,
        "overlap_area": overlap_area,
        "outside_area": outside_area,
        "uncovered_area": uncovered_area,
        "degenerate": degenerate,
        "out_of_bounds": out_of_bounds,
        "exact_partition": (
            not degenerate
            and not out_of_bounds
            and overlap_area <= EPS
            and uncovered_area <= EPS
            and outside_area <= EPS
        ),
    }
