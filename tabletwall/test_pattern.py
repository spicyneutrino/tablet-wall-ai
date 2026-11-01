"""Bounded, deterministic diagnostic PNG generation.

The grid is an ordinary generated image for a committed physical wall. It
takes the wall's intended millimetre bounds, including a nonzero or negative
origin, and draws 50 mm grid lines, readable coordinate labels, corner
orientation markers, a cross-axis target, and a scale bar. Millimetres are
intended coordinates copied from the committed layout; the image does not
measure the wall or claim real accuracy.

This module only returns bytes and JSON-ready metadata. It performs no
database work, live file writes, scene mutation, or content-mode changes.
Publishing the bytes to the existing asset store and exposing the HTTP route
belong to the integration owner.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

GRID_INTERVAL_MM = 50.0
MAJOR_INTERVAL_MM = 250.0
MAX_EDGE_PX = 4096
MAX_PIXELS = 12_000_000
MAX_WALL_MM = 10_000.0
MIN_WALL_MM = 50.0
MAX_ASPECT = 1000.0
MAX_AXIS_TICKS = 256
MIN_GRID_EDGE_PX = 64
BLACK_SIZE_PX = 64

BACKGROUND = (248, 248, 244)
MINOR_LINE = (120, 120, 120)
MAJOR_LINE = (40, 82, 160)
AXIS_LINE = (0, 112, 192)
BORDER = (20, 20, 20)
TEXT = (20, 20, 20)
WHITE = (255, 255, 255)
CORNER_COLORS = (
    ("TL", (196, 32, 32)),
    ("TR", (24, 128, 64)),
    ("BR", (204, 120, 0)),
    ("BL", (40, 72, 180)),
)


class PatternError(ValueError):
    """A requested pattern or wall bounds cannot produce a bounded image."""


@dataclass(frozen=True, slots=True)
class PatternImage:
    """A generated PNG plus safe, JSON-ready descriptive metadata."""

    data: bytes
    metadata: dict[str, Any]

    @property
    def png(self) -> bytes:
        return self.data


def generate_test_pattern(
    pattern: str, *, bounds: Mapping[str, Any] | None = None
) -> PatternImage:
    """Generate ``grid`` from committed mm bounds or the small ``black`` image."""
    if pattern == "grid":
        if bounds is None:
            raise PatternError("grid requires committed physical bounds")
        return generate_grid(bounds)
    if pattern == "black":
        return generate_black()
    raise PatternError("pattern must be 'grid' or 'black'")


def generate_black() -> PatternImage:
    """Return a small, fully opaque black PNG for the Blank wall action."""
    width = height = BLACK_SIZE_PX
    image = Image.new("RGB", (width, height), (0, 0, 0))
    data = _png_bytes(image)
    return PatternImage(
        data=data,
        metadata={
            "pattern": "black",
            "content_type": "image/png",
            "format": "PNG",
            "mode": "RGB",
            "opaque": True,
            "width": width,
            "height": height,
            "byte_length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bounds_mm": None,
            "purpose": "Blank wall",
            "note": "A small ordinary opaque black PNG. It is not a new content mode.",
            "accuracy_claimed": False,
        },
    )


def generate_grid(bounds: Mapping[str, Any]) -> PatternImage:
    """Render the bounded 50 mm test grid for the supplied mm bounds."""
    x, y, width_mm, height_mm = _wall_bounds(bounds)
    scale, px_width, px_height = _pixel_geometry(width_mm, height_mm)
    x_ticks = _ticks(x, width_mm, axis="x")
    y_ticks = _ticks(y, height_mm, axis="y")

    font_size = max(10, min(48, int(min(px_width, px_height) / 32)))
    small_size = max(8, font_size // 2)
    font = _font(font_size)
    small_font = _font(small_size)
    margin = max(3, font_size // 2)

    image = Image.new("RGB", (px_width, px_height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_border(draw, px_width, px_height)
    _draw_grid_lines(draw, x, y, scale, px_width, px_height, x_ticks, y_ticks)
    origin_marker = _draw_origin_marker(
        draw, x, y, scale, px_width, px_height, width_mm, height_mm
    )

    target_mm = _target_size_mm(width_mm, height_mm)
    target_px = _draw_shape_target(
        draw=draw,
        px_width=px_width,
        px_height=px_height,
        target_mm=target_mm,
        scale=scale,
        font=font,
        background=BACKGROUND,
    )
    bar_mm, bar_px = _draw_scale_bar(
        draw=draw,
        px_width=px_width,
        px_height=px_height,
        width_mm=width_mm,
        scale=scale,
        font=small_font,
        font_size=font_size,
        margin=margin,
    )

    x_label_stride = _label_stride(x_ticks, scale, font_size)
    y_label_stride = _label_stride(y_ticks, scale, font_size)
    x_labels = [x_ticks[index] for index in range(0, len(x_ticks), x_label_stride)]
    y_labels = [y_ticks[index] for index in range(0, len(y_ticks), y_label_stride)]
    _draw_axis_labels(
        draw=draw,
        x=x,
        y=y,
        scale=scale,
        px_width=px_width,
        px_height=px_height,
        x_labels=x_labels,
        y_labels=y_labels,
        font=font,
        font_size=font_size,
        margin=margin,
    )
    corner_markers = _draw_corner_markers(
        draw=draw,
        px_width=px_width,
        px_height=px_height,
        font=small_font,
    )
    _draw_footer(
        draw=draw,
        px_width=px_width,
        px_height=px_height,
        font=small_font,
        font_size=font_size,
        small_size=small_size,
        margin=margin,
    )

    data = _png_bytes(image)
    image_aspect = px_width / px_height
    source_aspect = width_mm / height_mm
    aspect_deviation = abs(image_aspect / source_aspect - 1.0)
    metadata = {
        "pattern": "grid",
        "content_type": "image/png",
        "format": "PNG",
        "mode": "RGB",
        "opaque": True,
        "width": px_width,
        "height": px_height,
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bounds_mm": {
            "x": x,
            "y": y,
            "width": width_mm,
            "height": height_mm,
        },
        "origin_mm": [x, y],
        "extent_mm": [width_mm, height_mm],
        "negative_bounds": bool(x < 0 or y < 0),
        "pixels_per_mm": scale,
        "mm_per_pixel": 1.0 / scale,
        "aspect": {
            "source": source_aspect,
            "image": image_aspect,
            "deviation": aspect_deviation,
            "preserved": aspect_deviation <= 0.02,
        },
        "grid": {
            "interval_mm": GRID_INTERVAL_MM,
            "major_interval_mm": MAJOR_INTERVAL_MM,
            "x_ticks_mm": x_ticks,
            "y_ticks_mm": y_ticks,
            "vertical_lines": len(x_ticks),
            "horizontal_lines": len(y_ticks),
            "total_lines": len(x_ticks) + len(y_ticks),
            "x_labels_mm": x_labels,
            "y_labels_mm": y_labels,
            "label_interval_mm": {
                "x": GRID_INTERVAL_MM * x_label_stride,
                "y": GRID_INTERVAL_MM * y_label_stride,
            },
            "label_count": len(x_labels) + len(y_labels),
            "corner_markers": corner_markers,
            "cross_axis": True,
            "origin_marker_px": origin_marker,
            "scale_bar_mm": bar_mm,
            "scale_bar_px": bar_px,
            "shape_target_mm": target_mm,
            "shape_target_px": target_px,
        },
        "limits": {
            "max_edge_px": MAX_EDGE_PX,
            "max_pixels": MAX_PIXELS,
            "max_wall_mm": MAX_WALL_MM,
            "min_wall_mm": MIN_WALL_MM,
            "max_axis_ticks": MAX_AXIS_TICKS,
        },
        "note": (
            "Millimetre values are intended coordinates copied from the committed "
            "physical layout. The pattern does not measure the wall and does not "
            "claim real-world dimensional accuracy."
        ),
        "accuracy_claimed": False,
        "provenance": {
            "source": "committed physical bounds",
            "generated": True,
            "interval_mm": GRID_INTERVAL_MM,
        },
    }
    return PatternImage(data=data, metadata=metadata)


def _wall_bounds(bounds: Mapping[str, Any]) -> tuple[float, float, float, float]:
    if not isinstance(bounds, Mapping):
        raise PatternError("bounds must be an object")
    for key in ("x", "y", "width", "height"):
        if key not in bounds:
            raise PatternError(f"bounds.{key} is required")
    x = _finite(bounds["x"], "bounds.x")
    y = _finite(bounds["y"], "bounds.y")
    width = _finite(bounds["width"], "bounds.width")
    height = _finite(bounds["height"], "bounds.height")
    if width <= 0 or height <= 0:
        raise PatternError("bounds width and height must be positive")
    if width < MIN_WALL_MM or height < MIN_WALL_MM:
        raise PatternError(
            f"bounds must be at least {MIN_WALL_MM:g} mm on each axis for a "
            f"{GRID_INTERVAL_MM:g} mm grid"
        )
    if width > MAX_WALL_MM or height > MAX_WALL_MM:
        raise PatternError(
            f"bounds must not exceed {MAX_WALL_MM:g} mm on either axis"
        )
    if max(width, height) / min(width, height) > MAX_ASPECT:
        raise PatternError("bounds aspect ratio is too extreme for a usable test grid")
    for origin, extent in ((x, width), (y, height)):
        end = origin + extent
        if not math.isfinite(end) or math.ulp(end) > GRID_INTERVAL_MM / 1000:
            raise PatternError("bounds origin cannot represent the grid coordinates precisely")
    return x, y, width, height


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatternError(f"{field} must be a finite number")
    try:
        number = float(value)
    except OverflowError as error:
        raise PatternError(f"{field} must be finite") from error
    if not math.isfinite(number):
        raise PatternError(f"{field} must be finite")
    return number


def _pixel_geometry(
    width_mm: float, height_mm: float
) -> tuple[float, int, int]:
    scale = min(
        MAX_EDGE_PX / width_mm,
        MAX_EDGE_PX / height_mm,
        math.sqrt(MAX_PIXELS / (width_mm * height_mm)),
    )
    if not math.isfinite(scale) or scale <= 0:
        raise PatternError("bounds cannot produce a bounded pixel scale")
    px_width = max(1, int(math.floor(width_mm * scale)))
    px_height = max(1, int(math.floor(height_mm * scale)))
    if px_width > MAX_EDGE_PX or px_height > MAX_EDGE_PX:
        raise PatternError("generated image would exceed the per-edge bound")
    if px_width * px_height > MAX_PIXELS:
        raise PatternError("generated image would exceed the pixel budget")
    if px_width < MIN_GRID_EDGE_PX or px_height < MIN_GRID_EDGE_PX:
        raise PatternError(
            "generated image would be too small for readable grid labels and corner markers"
        )
    return scale, px_width, px_height


def _ticks(origin: float, extent: float, *, axis: str) -> list[float]:
    first_index = math.ceil((origin - 1e-9) / GRID_INTERVAL_MM)
    last_index = math.floor((origin + extent + 1e-9) / GRID_INTERVAL_MM)
    count = last_index - first_index + 1
    if count <= 0:
        return []
    if count > MAX_AXIS_TICKS:
        raise PatternError(
            f"{axis} axis would draw {count} grid lines, above the bounded "
            f"{MAX_AXIS_TICKS} limit"
        )
    ticks = []
    for index in range(first_index, last_index + 1):
        value = index * GRID_INTERVAL_MM
        ticks.append(0.0 if value == 0 else float(value))
    return ticks


def _pixel(tick_mm: float, origin: float, scale: float, limit: int) -> int:
    value = int(round((tick_mm - origin) * scale))
    return max(0, min(limit - 1, value))


def _draw_border(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    inset = max(1, min(width, height) // 400)
    draw.rectangle(
        [inset, inset, width - 1 - inset, height - 1 - inset],
        outline=BORDER,
        width=inset,
    )


def _draw_grid_lines(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    scale: float,
    px_width: int,
    px_height: int,
    x_ticks: list[float],
    y_ticks: list[float],
) -> None:
    for tick in x_ticks:
        major = _is_major(tick)
        px = _pixel(tick, x, scale, px_width)
        draw.line(
            [(px, 0), (px, px_height - 1)],
            fill=MAJOR_LINE if major else MINOR_LINE,
            width=3 if major else 1,
        )
    for tick in y_ticks:
        major = _is_major(tick)
        py = _pixel(tick, y, scale, px_height)
        draw.line(
            [(0, py), (px_width - 1, py)],
            fill=MAJOR_LINE if major else MINOR_LINE,
            width=3 if major else 1,
        )


def _is_major(tick_mm: float) -> bool:
    return abs(tick_mm / MAJOR_INTERVAL_MM - round(tick_mm / MAJOR_INTERVAL_MM)) < 1e-9


def _draw_origin_marker(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    scale: float,
    width: int,
    height: int,
    width_mm: float,
    height_mm: float,
) -> list[int] | None:
    if not (x <= 0 <= x + width_mm and y <= 0 <= y + height_mm):
        return None
    cx = _pixel(0.0, x, scale, width)
    cy = _pixel(0.0, y, scale, height)
    arm = max(10, min(width, height) // 40)
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=AXIS_LINE, width=3)
    draw.line([(cx, cy - arm), (cx, cy + arm)], fill=AXIS_LINE, width=3)
    draw.ellipse(
        [cx - arm // 3, cy - arm // 3, cx + arm // 3, cy + arm // 3],
        outline=AXIS_LINE,
        width=2,
    )
    return [cx, cy]


def _target_size_mm(width_mm: float, height_mm: float) -> float:
    smallest = min(width_mm, height_mm)
    for candidate in (100.0, 50.0, 25.0, 10.0):
        if candidate <= smallest * 0.5:
            return candidate
    return max(5.0, smallest * 0.25)


def _draw_shape_target(
    *,
    draw: ImageDraw.ImageDraw,
    px_width: int,
    px_height: int,
    target_mm: float,
    scale: float,
    font: Font,
    background: tuple[int, int, int],
) -> int:
    side = max(4, min(int(round(target_mm * scale)), px_width // 2, px_height // 2))
    left = (px_width - side) // 2
    top = (px_height - side) // 2
    right = left + side
    bottom = top + side
    draw.rectangle([left, top, right, bottom], outline=(20, 20, 20), width=3)
    draw.ellipse([left, top, right, bottom], outline=AXIS_LINE, width=3)
    draw.line([(left, top), (right, bottom)], fill=AXIS_LINE, width=2)
    draw.line([(left, bottom), (right, top)], fill=AXIS_LINE, width=2)
    _label(
        draw,
        f"{target_mm:g} mm shape target",
        (left + right) / 2,
        bottom + max(10, side // 8),
        font,
        TEXT,
        background,
    )
    return side


def _draw_scale_bar(
    *,
    draw: ImageDraw.ImageDraw,
    px_width: int,
    px_height: int,
    width_mm: float,
    scale: float,
    font: Font,
    font_size: int,
    margin: int,
) -> tuple[float, int]:
    bar_mm = 100.0
    while bar_mm > width_mm * 0.6 and bar_mm > 10.0:
        bar_mm /= 2.0
    bar_px = max(8, int(round(bar_mm * scale)))
    bar_px = min(bar_px, px_width - 2 * margin)
    x0 = margin + 2
    y0 = max(margin + 2, px_height - margin - font_size - 60)
    x1 = x0 + bar_px
    draw.rectangle([x0, y0, x1, y0 + 8], fill=(20, 20, 20))
    draw.line([(x0, y0 - 4), (x0, y0 + 12)], fill=(20, 20, 20), width=2)
    draw.line([(x1, y0 - 4), (x1, y0 + 12)], fill=(20, 20, 20), width=2)
    _label(
        draw,
        f"{bar_mm:g} mm",
        (x0 + x1) / 2,
        y0 - 12,
        font,
        TEXT,
        BACKGROUND,
    )
    return bar_mm, bar_px


def _label_stride(ticks: list[float], scale: float, font_size: int) -> int:
    if len(ticks) <= 1:
        return 1
    spacing = GRID_INTERVAL_MM * scale
    needed = font_size * 3.2
    stride = max(1, int(math.ceil(needed / max(spacing, 1.0))))
    if len(range(0, len(ticks), stride)) > MAX_AXIS_TICKS:
        stride = max(1, int(math.ceil(len(ticks) / MAX_AXIS_TICKS)))
    return stride


def _draw_axis_labels(
    *,
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    scale: float,
    px_width: int,
    px_height: int,
    x_labels: list[float],
    y_labels: list[float],
    font: Font,
    font_size: int,
    margin: int,
) -> None:
    for tick in x_labels:
        px = _pixel(tick, x, scale, px_width)
        text = f"{tick:g}"
        top = margin + font_size // 2 + 2
        bottom = px_height - margin - font_size // 2 - 2
        _label(draw, text, px, top, font, TEXT, BACKGROUND)
        _label(draw, text, px, bottom, font, TEXT, BACKGROUND)
    for tick in y_labels:
        py = _pixel(tick, y, scale, px_height)
        text = f"{tick:g}"
        _label(draw, text, margin + 24, py, font, TEXT, BACKGROUND)
        _label(draw, text, px_width - margin - 24, py, font, TEXT, BACKGROUND)


def _draw_corner_markers(
    *,
    draw: ImageDraw.ImageDraw,
    px_width: int,
    px_height: int,
    font: Font,
) -> list[dict[str, Any]]:
    size = max(10, min(96, px_width // 10, px_height // 10))
    inset = max(2, min(px_width, px_height) // 200)
    positions = {
        "TL": (inset, inset),
        "TR": (px_width - inset - size, inset),
        "BR": (px_width - inset - size, px_height - inset - size),
        "BL": (inset, px_height - inset - size),
    }
    markers = []
    for label, color in CORNER_COLORS:
        left, top = positions[label]
        right, bottom = left + size, top + size
        draw.rectangle([left, top, right, bottom], fill=color)
        _label(
            draw,
            label,
            (left + right) / 2,
            (top + bottom) / 2,
            font,
            WHITE,
            None,
        )
        markers.append({
            "label": label,
            "box_px": [left, top, right, bottom],
            "color": list(color),
        })
    return markers


def _draw_footer(
    *,
    draw: ImageDraw.ImageDraw,
    px_width: int,
    px_height: int,
    font: Font,
    font_size: int,
    small_size: int,
    margin: int,
) -> None:
    if px_height < 120:
        return
    _label(
        draw,
        "mm coordinates are intended, not measured accuracy",
        px_width / 2,
        margin + font_size + small_size // 2 + 8,
        font,
        TEXT,
        BACKGROUND,
    )


def _label(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: float,
    center_y: float,
    font: Font,
    fill: tuple[int, int, int],
    background: tuple[int, int, int] | None,
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    left = center_x - width / 2 - box[0]
    top = center_y - height / 2 - box[1]
    if background is not None:
        draw.rectangle(
            [left - 2, top - 2, left + width + 2, top + height + 2],
            fill=background,
        )
    draw.text((left, top), text, font=font, fill=fill)


def _font(size: int) -> Font:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
