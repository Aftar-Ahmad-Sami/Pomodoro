"""Pillow rendering of the timer's graphics.

Shapes are drawn at ``SS`` times their target size and downscaled for smooth edges.
Every function takes ``scale``, the display's DPI scale factor (1.0 at 96 DPI).
"""

import math
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter

from pomodoro.theme import (
    BG_BOTTOM,
    BG_TOP,
    PHASE_SWITCH_HEIGHT,
    PHASE_SWITCH_PAD,
    PHASE_SWITCH_WIDTH,
    RGB,
    RING_CENTER,
    RING_RADIUS,
    RING_STROKE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    Palette,
)

SS = 3  # supersampling factor
LANCZOS = Image.Resampling.LANCZOS
WHITE: RGB = (255, 255, 255)

ButtonKind = Literal["play", "pause", "skip", "reset"]


def lerp(a: RGB, b: RGB, t: float) -> RGB:
    r, g, bl = (round(x + (y - x) * t) for x, y in zip(a, b, strict=True))
    return r, g, bl


def diagonal_gradient(w: int, h: int, c1: RGB, c2: RGB) -> Image.Image:
    v = Image.linear_gradient("L")
    mask = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90), 0.5).resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), mask)


def render_background(scale: float, accent: RGB) -> Image.Image:
    w, h = round(WINDOW_WIDTH * scale), round(WINDOW_HEIGHT * scale)
    grad = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), BG_BOTTOM), Image.new("RGB", (w, h), BG_TOP), grad)

    # Soft accent glow behind the ring, blurred at low resolution for speed
    q = 4
    glow = Image.new("L", (w // q, h // q), 0)
    cx, cy = RING_CENTER[0] * scale / q, RING_CENTER[1] * scale / q
    r = 150 * scale / q
    ImageDraw.Draw(glow).ellipse((cx - r, cy - r, cx + r, cy + r), fill=62)
    glow = glow.filter(ImageFilter.GaussianBlur(70 * scale / q)).resize((w, h), Image.Resampling.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), accent), img, glow)


def render_ring(scale: float, fraction: float, colors: Palette) -> Image.Image:
    """Progress ring filled clockwise from 12 o'clock by ``fraction`` (0 to 1)."""
    pad = 28
    size = round((RING_RADIUS + pad) * 2 * scale)
    big = size * SS
    c = big / 2
    r = RING_RADIUS * scale * SS
    sw = round(RING_STROKE * scale * SS)
    box = (c - r - sw / 2, c - r - sw / 2, c + r + sw / 2, c + r + sw / 2)

    track = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(track).ellipse(box, outline=(255, 255, 255, 20), width=sw)

    arc = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(arc)
    extent = 360 * fraction
    end_angle = -90 + extent
    if extent > 0.05:
        steps = max(1, math.ceil(extent / 1.5))
        for i in range(steps):
            a0 = -90 + extent * i / steps
            a1 = -90 + extent * (i + 1) / steps
            col = lerp(colors[0], colors[1], (a0 + 90) / 360)
            d.arc(box, a0, a1 + 0.6, fill=(*col, 255), width=sw)
        for ang in (-90, end_angle):
            col = lerp(colors[0], colors[1], (ang + 90) / 360)
            x = c + r * math.cos(math.radians(ang))
            y = c + r * math.sin(math.radians(ang))
            d.ellipse((x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2), fill=(*col, 255))

    # Bright knob marking the current position
    x = c + r * math.cos(math.radians(end_angle))
    y = c + r * math.sin(math.radians(end_angle))
    k = sw * 0.3
    d.ellipse((x - k, y - k, x + k, y + k), fill=(255, 255, 255, 255))

    track = track.resize((size, size), LANCZOS)
    arc = arc.resize((size, size), LANCZOS)
    glow = arc.filter(ImageFilter.GaussianBlur(10 * scale))
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.9)))
    return Image.alpha_composite(Image.alpha_composite(track, glow), arc)


def render_button(scale: float, kind: ButtonKind, colors: Palette, hover: bool, primary: bool) -> Image.Image:
    """Round control button. The primary button is larger, filled with the phase gradient and has a halo."""
    diam = 68 if primary else 48
    pad = 22 if primary else 4
    size = round((diam + pad * 2) * scale)
    big = size * SS
    c = big / 2
    rad = diam * scale * SS / 2
    u = diam * scale * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    circle = (c - rad, c - rad, c + rad, c + rad)

    if primary:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).ellipse(circle, fill=255)
        c1, c2 = colors
        if hover:
            c1, c2 = lerp(c1, WHITE, 0.15), lerp(c2, WHITE, 0.15)
        img.paste(diagonal_gradient(big, big, c1, c2), (0, 0), mask)
        icon_color = (255, 255, 255, 255)
    else:
        fill = (255, 255, 255, 30 if hover else 14)
        ImageDraw.Draw(img).ellipse(circle, fill=fill, outline=(255, 255, 255, 34), width=round(scale * SS))
        icon_color = (236, 236, 245, 255) if hover else (196, 196, 214, 255)

    d = ImageDraw.Draw(img)
    if kind == "play":
        d.polygon([(c - 0.11 * u, c - 0.17 * u), (c - 0.11 * u, c + 0.17 * u), (c + 0.18 * u, c)], fill=icon_color)
    elif kind == "pause":
        bw, bh, gap = 0.085 * u, 0.30 * u, 0.075 * u
        for x0 in (c - gap / 2 - bw, c + gap / 2):
            d.rounded_rectangle((x0, c - bh / 2, x0 + bw, c + bh / 2), radius=bw * 0.35, fill=icon_color)
    elif kind == "skip":
        d.polygon([(c - 0.15 * u, c - 0.14 * u), (c - 0.15 * u, c + 0.14 * u), (c + 0.07 * u, c)], fill=icon_color)
        d.rounded_rectangle((c + 0.09 * u, c - 0.14 * u, c + 0.15 * u, c + 0.14 * u), radius=0.02 * u, fill=icon_color)
    elif kind == "reset":
        r = 0.18 * u
        lw = round(0.055 * u)
        d.arc((c - r - lw / 2, c - r - lw / 2, c + r + lw / 2, c + r + lw / 2), -40, 255, fill=icon_color, width=lw)
        tip_y = c - r
        d.polygon(
            [(c + 0.10 * u, tip_y), (c - 0.02 * u, tip_y - 0.10 * u), (c - 0.02 * u, tip_y + 0.10 * u)],
            fill=icon_color,
        )

    img = img.resize((size, size), LANCZOS)
    if primary:
        # Colored halo under the primary button
        halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hr = rad / SS
        hc = size / 2
        ImageDraw.Draw(halo).ellipse(
            (hc - hr, hc - hr + 4 * scale, hc + hr, hc + hr + 4 * scale),
            fill=(*colors[0], 150 if hover else 110),
        )
        halo = halo.filter(ImageFilter.GaussianBlur(12 * scale))
        img = Image.alpha_composite(halo, img)
    return img


def render_toggle(scale: float, on: bool, colors: Palette) -> Image.Image:
    w, h = 38, 22
    bw, bh = round(w * scale * SS), round(h * scale * SS)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if on:
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh / 2, fill=255)
        img.paste(diagonal_gradient(bw, bh, *colors), (0, 0), mask)
    else:
        d.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh / 2, fill=(255, 255, 255, 34))
    m = bh * 0.14
    kd = bh - 2 * m
    kx = bw - m - kd if on else m
    d.ellipse((kx, m, kx + kd, m + kd), fill=(255, 255, 255, 255) if on else (190, 190, 206, 255))
    return img.resize((round(w * scale), round(h * scale)), LANCZOS)


def render_phase_switch(scale: float, active: int, hover: int | None, colors: Palette) -> Image.Image:
    """Two-segment pill; segment ``active`` (0 or 1) is filled with the phase gradient.

    The labels are canvas text drawn on top, so they match the rest of the UI's fonts.
    """
    w, h = round(PHASE_SWITCH_WIDTH * scale * SS), round(PHASE_SWITCH_HEIGHT * scale * SS)
    pad = PHASE_SWITCH_PAD * scale * SS
    seg_w = (w - 2 * pad) / 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        (0, 0, w - 1, h - 1),
        radius=h / 2,
        fill=(255, 255, 255, 14),
        outline=(255, 255, 255, 26),
        width=round(scale * SS),
    )

    def segment(i: int) -> tuple[float, float, float, float]:
        x0 = pad + i * seg_w
        return x0, pad, x0 + seg_w, h - pad

    if hover is not None and hover != active:
        d.rounded_rectangle(segment(hover), radius=(h - 2 * pad) / 2, fill=(255, 255, 255, 18))

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(segment(active), radius=(h - 2 * pad) / 2, fill=255)
    img.paste(diagonal_gradient(w, h, *colors), (0, 0), mask)
    return img.resize((round(PHASE_SWITCH_WIDTH * scale), round(PHASE_SWITCH_HEIGHT * scale)), LANCZOS)


def render_dot(scale: float, filled: bool, color: RGB) -> Image.Image:
    size = round(10 * scale)
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if filled:
        d.ellipse((0, 0, big - 1, big - 1), fill=(*color, 255))
    else:
        d.ellipse((0, 0, big - 1, big - 1), outline=(255, 255, 255, 60), width=round(1.5 * scale * SS))
    return img.resize((size, size), LANCZOS)
