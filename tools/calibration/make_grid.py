"""Generate a common-source PNG with known wall-space distances."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def make_grid(width_mm: int, height_mm: int, spacing_mm: int = 50) -> Image.Image:
    if min(width_mm, height_mm, spacing_mm) <= 0:
        raise ValueError("Wall dimensions and spacing must be positive integers in millimetres.")
    if width_mm * height_mm > 3_000_000:
        raise ValueError("Use a wall at most 3,000,000 square millimetres for this 2 px/mm test image.")
    width, height = width_mm * 2, height_mm * 2
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, width, spacing_mm * 2):
        draw.line((x, 0, x, height), fill="#9aa5b1", width=2)
        draw.text((x + 5, 5), f"{x // 2} mm", fill="#111111")
    for y in range(0, height, spacing_mm * 2):
        draw.line((0, y, width, y), fill="#9aa5b1", width=2)
        draw.text((5, y + 18), f"{y // 2} mm", fill="#111111")
    draw.line((0, 0, width, height), fill="#d12635", width=3)
    draw.line((width, 0, 0, height), fill="#1267a4", width=3)
    radius = min(spacing_mm, width_mm / 4, height_mm / 4)
    cx, cy = width / 2, height / 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="#111111", width=3)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width-mm", required=True, type=int)
    parser.add_argument("--height-mm", required=True, type=int)
    parser.add_argument("--spacing-mm", default=50, type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        image = make_grid(args.width_mm, args.height_mm, args.spacing_mm)
    except ValueError as error:
        parser.error(str(error))
    image.save(args.output, format="PNG")
    print(f"Saved {image.width} × {image.height} px; grid spacing {args.spacing_mm} mm when displayed on matching wall bounds.")


if __name__ == "__main__":
    main()
