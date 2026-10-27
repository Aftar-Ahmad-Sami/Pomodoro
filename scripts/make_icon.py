"""Generates src/pomodoro/assets/icon.ico and icon.png.

The logo is a split ring: a coral arc for the 52 focus minutes and a
mint arc for the 17 break minutes.

Usage: python scripts/make_icon.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RGB = tuple[int, int, int]
Palette = tuple[RGB, RGB]

SS = 4  # supersampling factor
FOCUS: Palette = ((255, 107, 107), (255, 169, 77))
BREAK: Palette = ((46, 230, 168), (63, 169, 245))
BG: Palette = ((44, 38, 72), (14, 12, 22))
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "pomodoro" / "assets"


def lerp(a: RGB, b: RGB, t: float) -> RGB:
    r, g, bl = (round(x + (y - x) * t) for x, y in zip(a, b, strict=True))
    return r, g, bl


def diagonal_gradient(size: int, c1: RGB, c2: RGB) -> Image.Image:
    v = Image.linear_gradient("L").resize((size, size))
    mask = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90), 0.5)
    return Image.composite(Image.new("RGB", (size, size), c2), Image.new("RGB", (size, size), c1), mask)


def draw_arc(
    draw: ImageDraw.ImageDraw, c: float, r: float, sw: int, start: float, extent: float, colors: Palette
) -> None:
    box = (c - r - sw / 2, c - r - sw / 2, c + r + sw / 2, c + r + sw / 2)
    steps = max(1, math.ceil(extent / 1.5))
    for i in range(steps):
        a0 = start + extent * i / steps
        a1 = start + extent * (i + 1) / steps
        col = lerp(colors[0], colors[1], (i + 0.5) / steps)
        draw.arc(box, a0, a1 + 0.6, fill=(*col, 255), width=sw)
    for ang, col in ((start, colors[0]), (start + extent, colors[1])):
        x = c + r * math.cos(math.radians(ang))
        y = c + r * math.sin(math.radians(ang))
        draw.ellipse((x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2), fill=(*col, 255))


def render(size: int) -> Image.Image:
    big = size * SS
    c = big / 2

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.23, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(diagonal_gradient(big, *BG), (0, 0), mask)

    small = size <= 32
    r = big * (0.29 if small else 0.28)
    sw = round(big * (0.15 if small else 0.11))

    # Gap between arcs must clear the round caps
    cap_deg = math.degrees((sw / 2) / r)
    half_gap = cap_deg + (7 if small else 5)
    focus_deg = 360 * 52 / 69

    rings = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(rings)
    draw_arc(d, c, r, sw, -90 + half_gap, focus_deg - 2 * half_gap, FOCUS)
    draw_arc(d, c, r, sw, -90 + focus_deg + half_gap, 360 - focus_deg - 2 * half_gap, BREAK)

    if not small:
        glow = rings.filter(ImageFilter.GaussianBlur(big * 0.04))
        img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, rings)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = [render(s) for s in ICO_SIZES]
    frames[-1].save(
        OUT_DIR / "icon.ico",
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )
    frames[-1].save(OUT_DIR / "icon.png")
    print(f"Wrote {OUT_DIR / 'icon.ico'} and {OUT_DIR / 'icon.png'}")


if __name__ == "__main__":
    main()
