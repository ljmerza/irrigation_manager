"""Generate the Irrigation Manager brand icon.

One geometry drives both outputs so they match: `assets/icon.svg` (source) and
the PNGs Home Assistant serves from `custom_components/irrigation_manager/brand/`
(icon.png 256x256, icon@2x.png 512x512, transparent background).

The PNGs are drawn with Pillow (no SVG renderer is required): the shapes are
rasterised at 4x and downsampled for anti-aliasing.

    python3 assets/render_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "icon.svg"
BRAND_DIR = ROOT / "custom_components" / "irrigation_manager" / "brand"

CANVAS = 512
SUPERSAMPLE = 4

DROP_COLOR = "#1E88E5"
SPROUT_COLOR = "#FFFFFF"

# Water drop: a circle plus a tip joined by tangent lines.
DROP_TIP = (256.0, 36.0)
DROP_CENTER = (256.0, 306.0)
DROP_RADIUS = 172.0

# Sprout inside the drop.
STEM = ((256.0, 440.0), (256.0, 236.0))
STEM_WIDTH = 34.0
LEAVES = (
    ((256.0, 330.0), (136.0, 244.0)),  # (base, tip)
    ((256.0, 290.0), (370.0, 214.0)),
)
LEAF_WIDTH_RATIO = 0.45  # quadratic control offset as a share of leaf length


def _drop_tangents() -> tuple[tuple[float, float], tuple[float, float], float]:
    """Right and left tangent points, and the half-angle from vertical."""
    cx, cy = DROP_CENTER
    distance = cy - DROP_TIP[1]
    alpha = math.acos(DROP_RADIUS / distance)
    dx = DROP_RADIUS * math.sin(alpha)
    dy = DROP_RADIUS * math.cos(alpha)
    return (cx + dx, cy - dy), (cx - dx, cy - dy), alpha


def _leaf_controls(base, tip):
    (x0, y0), (x1, y1) = base, tip
    length = math.hypot(x1 - x0, y1 - y0)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    # Unit normal to the leaf axis.
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    k = LEAF_WIDTH_RATIO * length
    return (mx + nx * k, my + ny * k), (mx - nx * k, my - ny * k)


def _fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def build_svg() -> str:
    right, left, _ = _drop_tangents()
    drop = (
        f"M{_fmt(DROP_TIP[0])} {_fmt(DROP_TIP[1])} "
        f"L{_fmt(right[0])} {_fmt(right[1])} "
        f"A{_fmt(DROP_RADIUS)} {_fmt(DROP_RADIUS)} 0 1 1 {_fmt(left[0])} {_fmt(left[1])}Z"
    )
    leaves = []
    for base, tip in LEAVES:
        c1, c2 = _leaf_controls(base, tip)
        leaves.append(
            f'<path d="M{_fmt(base[0])} {_fmt(base[1])} '
            f"Q{_fmt(c1[0])} {_fmt(c1[1])} {_fmt(tip[0])} {_fmt(tip[1])} "
            f'Q{_fmt(c2[0])} {_fmt(c2[1])} {_fmt(base[0])} {_fmt(base[1])}Z" '
            f'fill="{SPROUT_COLOR}"/>'
        )
    (sx0, sy0), (sx1, sy1) = STEM
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" '
        f'width="{CANVAS}" height="{CANVAS}">\n'
        f'  <path d="{drop}" fill="{DROP_COLOR}"/>\n'
        f'  <path d="M{_fmt(sx0)} {_fmt(sy0)} L{_fmt(sx1)} {_fmt(sy1)}" '
        f'stroke="{SPROUT_COLOR}" stroke-width="{_fmt(STEM_WIDTH)}" stroke-linecap="round"/>\n'
        + "".join(f"  {leaf}\n" for leaf in leaves)
        + "</svg>\n"
    )


def _quad(p0, c, p1, steps: int = 64):
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        yield (
            u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
        )


def render_png(size: int) -> Image.Image:
    scale = CANVAS * SUPERSAMPLE / CANVAS
    big = CANVAS * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x * scale, y * scale)

    # Drop: tip, then the circle from the right tangent clockwise (screen
    # coordinates) around the bottom to the left tangent.
    _, _, alpha = _drop_tangents()
    start = alpha - math.pi / 2
    end = math.pi + math.pi / 2 - alpha
    cx, cy = DROP_CENTER
    points = [pt(*DROP_TIP)]
    steps = 360
    for i in range(steps + 1):
        phi = start + (end - start) * i / steps
        points.append(pt(cx + DROP_RADIUS * math.cos(phi), cy + DROP_RADIUS * math.sin(phi)))
    draw.polygon(points, fill=DROP_COLOR)

    # Stem with round caps.
    (sx0, sy0), (sx1, sy1) = STEM
    half = STEM_WIDTH / 2
    draw.line([pt(sx0, sy0), pt(sx1, sy1)], fill=SPROUT_COLOR, width=round(STEM_WIDTH * scale))
    for x, y in STEM:
        draw.ellipse([pt(x - half, y - half), pt(x + half, y + half)], fill=SPROUT_COLOR)

    for base, tip in LEAVES:
        c1, c2 = _leaf_controls(base, tip)
        outline = list(_quad(base, c1, tip)) + list(_quad(tip, c2, base))
        draw.polygon([pt(x, y) for x, y in outline], fill=SPROUT_COLOR)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    SVG_PATH.write_text(build_svg(), encoding="utf-8")
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    render_png(256).save(BRAND_DIR / "icon.png", optimize=True)
    render_png(512).save(BRAND_DIR / "icon@2x.png", optimize=True)


if __name__ == "__main__":
    main()
