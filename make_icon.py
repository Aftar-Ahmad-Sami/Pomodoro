"""Generates assets/icon.ico and assets/icon.png.

The logo is a split ring: a coral arc for the 52 focus minutes and a
mint arc for the 17 break minutes.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # supersampling factor
FOCUS = ((255, 107, 107), (255, 169, 77))
BREAK = ((46, 230, 168), (63, 169, 245))
BG = ((44, 38, 72), (14, 12, 22))
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def diagonal_gradient(size, c1, c2):
    v = Image.linear_gradient("L").resize((size, size))
    mask = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90), 0.5)
    return Image.composite(Image.new("RGB", (size, size), c2), Image.new("RGB", (size, size), c1), mask)


def draw_arc(draw, c, r, sw, start, extent, colors):
    box = (c - r - sw / 2, c - r - sw / 2, c + r + sw / 2, c + r + sw / 2)
    steps = max(1, math.ceil(extent / 1.5))
    for i in range(steps):
        a0 = start + extent * i / steps
        a1 = start + extent * (i + 1) / steps
        col = lerp(colors[0], colors[1], (i + 0.5) / steps)
        draw.arc(box, a0, a1 + 0.6, fill=col + (255,), width=sw)
    for ang, col in ((start, colors[0]), (start + extent, colors[1])):
        x = c + r * math.cos(math.radians(ang))
        y = c + r * math.sin(math.radians(ang))
        draw.ellipse((x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2), fill=col + (255,))


def render(size):
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = [render(s) for s in ICO_SIZES]
    frames[-1].save(
        os.path.join(OUT_DIR, "icon.ico"),
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )
    frames[-1].save(os.path.join(OUT_DIR, "icon.png"))
    print("Wrote assets/icon.ico and assets/icon.png")


if __name__ == "__main__":
    main()
