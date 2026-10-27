"""Colors and layout, in logical (96 DPI) pixels."""

from pomodoro.timer import Phase

RGB = tuple[int, int, int]
Palette = tuple[RGB, RGB]

BG_TOP: RGB = (24, 21, 38)
BG_BOTTOM: RGB = (10, 10, 16)
FG = "#f4f4f8"
MUTED = "#8b8ba3"
FAINT = "#5c5c74"

PALETTES: dict[Phase, Palette] = {
    Phase.WORK: ((255, 107, 107), (255, 169, 77)),
    Phase.BREAK: ((46, 230, 168), (63, 169, 245)),
}

WINDOW_WIDTH, WINDOW_HEIGHT = 380, 640

RING_CENTER = (190, 252)
RING_RADIUS = 118
RING_STROKE = 12

DOTS_Y = 418
DOT_SPACING = 20
CONTROLS_Y = 522
CONTROL_SPACING = 92
OPTIONS_Y = 600


def hex_color(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
