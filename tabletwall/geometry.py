"""Canonical physical geometry for version 3 (R2).

Spaces and directions (ROADMAP "Define the spaces and directions"):

* ``W`` wall millimetres, X right and Y down, viewed from the audience.
* ``B`` body millimetres, centred on the tablet body in its native
  orientation.
* ``P`` active-panel millimetres, origin at the active panel's top-left in
  that native orientation.
* ``C`` CSS pixels relative to the stable usable render rectangle.
* ``D`` canvas backing pixels.
* ``N`` normalized upright source, both axes 0..1.

Matrices are six-number Canvas arrays ``[a,b,c,d,e,f]`` with column vectors,
so ``x' = a*x + c*y + e`` and ``y' = b*x + d*y + f``. Multiplication applies
the rightmost matrix first. Positive rotation is clockwise in this Y-down
system. The server owns ``G_N_to_P``; the client owns its calibrated
``U_C_to_P`` and composes the backing transform.
"""

import math
from typing import Any

Matrix = tuple[float, float, float, float, float, float]
Point = tuple[float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class GeometryError(ValueError):
    """A measurement or calibration that cannot describe a physical panel."""


def multiply(left: Matrix, right: Matrix) -> Matrix:
    """``left * right``: the result applies ``right`` first."""
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def inverse(matrix: Matrix) -> Matrix:
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise GeometryError("matrix is not invertible")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * f - d * e) / determinant,
        (b * e - a * f) / determinant,
    )


def apply(matrix: Matrix, point: Point) -> Point:
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def translate(tx: float, ty: float) -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, float(tx), float(ty))


def scale(sx: float, sy: float) -> Matrix:
    if sx == 0 or sy == 0:
        raise GeometryError("scale must be non-zero")
    return (float(sx), 0.0, 0.0, float(sy), 0.0, 0.0)


def rotate(angle_degrees: float) -> Matrix:
    """Clockwise rotation in a Y-down coordinate system."""
    radians = math.radians(angle_degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return (cosine, sine, -sine, cosine, 0.0, 0.0)


def quarter_turn(quarter: int, viewport_width: float, viewport_height: float) -> Matrix:
    """The CSS-to-rotated-CSS map from ROADMAP "Keep mount and browser
    orientation separate".

    ``viewport_width``/``viewport_height`` are the usable viewport before
    rotation. The rotated bounding box is translated back to a positive
    corner by this matrix; the caller adds the panel offset afterwards.
    """
    if quarter not in (0, 1, 2, 3):
        raise GeometryError("quarter_turn must be 0, 1, 2 or 3")
    if viewport_width <= 0 or viewport_height <= 0:
        raise GeometryError("viewport dimensions must be positive")
    w, h = float(viewport_width), float(viewport_height)
    return {
        0: (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        1: (0.0, 1.0, -1.0, 0.0, h, 0.0),
        2: (-1.0, 0.0, 0.0, -1.0, w, h),
        3: (0.0, -1.0, 1.0, 0.0, 0.0, w),
    }[quarter]


def body_geometry(
    active_width: float, active_height: float, bezels: dict[str, float]
) -> tuple[float, float, Point]:
    """Body width, body height and the active top-left in centered body
    coordinates. Bezels are native-edge millimetres and cannot be negative."""
    if active_width <= 0 or active_height <= 0:
        raise GeometryError("active dimensions must be positive")
    left = _nonnegative(bezels.get("left"), "left bezel")
    top = _nonnegative(bezels.get("top"), "top bezel")
    right = _nonnegative(bezels.get("right"), "right bezel")
    bottom = _nonnegative(bezels.get("bottom"), "bottom bezel")
    width = left + active_width + right
    height = top + active_height + bottom
    return width, height, (-width / 2 + left, -height / 2 + top)


def _nonnegative(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GeometryError(f"{label} must be a number")
    if not math.isfinite(value) or value < 0:
        raise GeometryError(f"{label} must be finite and non-negative")
    return float(value)


def fit_matrix(
    bounds: tuple[float, float, float, float],
    source_width: float,
    source_height: float,
    fit: str = "cover",
) -> Matrix:
    """Normalized upright source to wall millimetres for one global fit.

    ``bounds`` is ``(x, y, width, height)`` in wall millimetres. The image
    keeps its complete upright aspect; contain/alpha regions get an explicit
    background from the renderer. There is no hidden per-device crop.
    """
    x, y, width, height = (float(value) for value in bounds)
    if width <= 0 or height <= 0 or source_width <= 0 or source_height <= 0:
        raise GeometryError("bounds and source dimensions must be positive")
    if fit == "cover":
        factor = max(width / source_width, height / source_height)
    elif fit == "contain":
        factor = min(width / source_width, height / source_height)
    else:
        raise GeometryError(f"unsupported fit {fit!r}")
    draw_width = factor * source_width
    draw_height = factor * source_height
    return (
        draw_width,
        0.0,
        0.0,
        draw_height,
        x + (width - draw_width) / 2,
        y + (height - draw_height) / 2,
    )


def panel_to_wall(
    active_origin: Point,
    center_mm: Point,
    nudge_mm: Point,
    mount_angle: float,
) -> Matrix:
    """``M_P_to_W`` for one measured body and slot."""
    body = translate(center_mm[0] + nudge_mm[0], center_mm[1] + nudge_mm[1])
    return multiply(
        multiply(body, rotate(mount_angle)),
        translate(active_origin[0], active_origin[1]),
    )


def normalized_source_to_panel(
    *,
    active_size: tuple[float, float],
    bezels: dict[str, float],
    center_mm: Point,
    nudge_mm: Point,
    mount_angle: float,
    bounds: tuple[float, float, float, float],
    source_size: tuple[float, float],
    fit: str = "cover",
) -> dict[str, Any]:
    """The server-owned ``G_N_to_P`` plus the panel clip and derived body."""
    active_width, active_height = active_size
    body_width, body_height, active_origin = body_geometry(
        active_width, active_height, bezels
    )
    panel_to_w = panel_to_wall(active_origin, center_mm, nudge_mm, mount_angle)
    fit_n_to_w = fit_matrix(bounds, source_size[0], source_size[1], fit)
    panel_from_source = multiply(inverse(panel_to_w), fit_n_to_w)
    return {
        "panel_from_source": list(panel_from_source),
        "panel_to_wall": list(panel_to_w),
        "body": {"width": body_width, "height": body_height},
        "active": {"x": active_origin[0], "y": active_origin[1],
                   "width": active_width, "height": active_height},
        "clip": {"x": 0.0, "y": 0.0, "width": active_width, "height": active_height},
    }


def css_to_panel(
    *,
    viewport_width: float,
    viewport_height: float,
    quarter: int,
    panel_offset_mm: Point,
    mm_per_css: Point,
) -> Matrix:
    """``U_C_to_P``: calibrated CSS pixels to active-panel millimetres."""
    mm_x, mm_y = mm_per_css
    if mm_x <= 0 or mm_y <= 0:
        raise GeometryError("mm_per_css must be positive")
    # Q operates in millimetres and the rightmost scale maps CSS to mm, so
    # its turning dimensions are the usable viewport already in mm.
    return multiply(
        translate(panel_offset_mm[0], panel_offset_mm[1]),
        multiply(
            quarter_turn(quarter, viewport_width * mm_x, viewport_height * mm_y),
            scale(mm_x, mm_y),
        ),
    )


def backing_scale(backing: tuple[float, float], rect: tuple[float, float]) -> Matrix:
    """The actual backing/rectangle ratios, including integer rounding."""
    if rect[0] <= 0 or rect[1] <= 0:
        raise GeometryError("render rectangle must be positive")
    return scale(backing[0] / rect[0], backing[1] / rect[1])


def canvas_transform(
    *,
    backing: tuple[float, float],
    rect: tuple[float, float],
    calibration: dict[str, Any],
    panel_from_source: Matrix,
    source_size: tuple[float, float],
) -> Matrix:
    """``D = backingScale * inverse(U_C_to_P) * G_N_to_P * diag(1/W,1/H)``."""
    u_c_to_p = css_to_panel(
        viewport_width=calibration["viewport_width"],
        viewport_height=calibration["viewport_height"],
        quarter=calibration["quarter_turn"],
        panel_offset_mm=(calibration["panel_offset_mm"][0],
                         calibration["panel_offset_mm"][1]),
        mm_per_css=(calibration["mm_per_css"][0], calibration["mm_per_css"][1]),
    )
    source_to_normalized = scale(1.0 / source_size[0], 1.0 / source_size[1])
    return multiply(
        backing_scale(backing, rect),
        multiply(inverse(u_c_to_p), multiply(panel_from_source, source_to_normalized)),
    )


def canvas_transform_components(
    *,
    backing: tuple[float, float],
    rect: tuple[float, float],
    calibration: dict[str, Any],
    panel_from_source: Matrix,
    source_size: tuple[float, float],
) -> dict[str, Any]:
    """The transform plus the panel clip expressed in backing pixels.

    The clip is computed under ``backingScale * inverse(U_C_to_P)`` only, so a
    renderer can apply it before drawing the image under the full transform.
    """
    u_c_to_p = css_to_panel(
        viewport_width=calibration["viewport_width"],
        viewport_height=calibration["viewport_height"],
        quarter=calibration["quarter_turn"],
        panel_offset_mm=tuple(calibration["panel_offset_mm"]),
        mm_per_css=tuple(calibration["mm_per_css"]),
    )
    clip = calibration.get("clip") or {
        "x": 0.0, "y": 0.0,
        "width": calibration.get("panel_width", 0.0),
        "height": calibration.get("panel_height", 0.0),
    }
    clip_matrix = multiply(backing_scale(backing, rect), inverse(u_c_to_p))
    corners = [
        apply(clip_matrix, (clip["x"], clip["y"])),
        apply(clip_matrix, (clip["x"] + clip["width"], clip["y"])),
        apply(clip_matrix, (clip["x"], clip["y"] + clip["height"])),
        apply(clip_matrix, (clip["x"] + clip["width"], clip["y"] + clip["height"])),
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return {
        "matrix": list(canvas_transform(
            backing=backing, rect=rect, calibration=calibration,
            panel_from_source=panel_from_source, source_size=source_size,
        )),
        "clip": {"x": min(xs), "y": min(ys),
                 "width": max(xs) - min(xs), "height": max(ys) - min(ys)},
    }
