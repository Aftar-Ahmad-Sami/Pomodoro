"""Smoke tests: every graphic renders at the expected size for common DPI scales."""

import pytest

from pomodoro import render
from pomodoro.theme import PALETTES, PHASE_SWITCH_HEIGHT, PHASE_SWITCH_WIDTH, WINDOW_HEIGHT, WINDOW_WIDTH
from pomodoro.timer import Phase

SCALES = [1.0, 1.5]
COLORS = PALETTES[Phase.WORK]


@pytest.mark.parametrize("scale", SCALES)
def test_background_fills_window(scale: float) -> None:
    img = render.render_background(scale, COLORS[0])
    assert img.size == (round(WINDOW_WIDTH * scale), round(WINDOW_HEIGHT * scale))


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("fraction", [0.0, 0.0001, 0.5, 1.0])
def test_ring_size_is_independent_of_progress(scale: float, fraction: float) -> None:
    empty = render.render_ring(scale, 0.0, COLORS)
    img = render.render_ring(scale, fraction, COLORS)
    assert img.mode == "RGBA"
    assert img.size == empty.size


@pytest.mark.parametrize("kind", ["play", "pause", "skip", "reset"])
@pytest.mark.parametrize("primary", [True, False])
@pytest.mark.parametrize("hover", [True, False])
def test_button_renders(kind: render.ButtonKind, primary: bool, hover: bool) -> None:
    img = render.render_button(1.0, kind, COLORS, hover, primary)
    assert img.mode == "RGBA"
    assert img.size[0] == img.size[1] > 0


@pytest.mark.parametrize("on", [True, False])
def test_toggle_renders(on: bool) -> None:
    assert render.render_toggle(1.0, on, COLORS).size == (38, 22)


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize(("active", "hover"), [(0, None), (1, None), (0, 1), (1, 1)])
def test_phase_switch_renders(scale: float, active: int, hover: int | None) -> None:
    img = render.render_phase_switch(scale, active, hover, COLORS)
    assert img.size == (round(PHASE_SWITCH_WIDTH * scale), round(PHASE_SWITCH_HEIGHT * scale))
    # The highlighted segment is opaque in its middle
    w, h = img.size
    assert img.getpixel((w // 4 + active * w // 2, h // 2))[3] == 255  # type: ignore[index]


@pytest.mark.parametrize("filled", [True, False])
def test_dot_renders(filled: bool) -> None:
    assert render.render_dot(1.0, filled, COLORS[0]).size == (10, 10)


def test_lerp_endpoints() -> None:
    assert render.lerp((0, 0, 0), (200, 100, 50), 0) == (0, 0, 0)
    assert render.lerp((0, 0, 0), (200, 100, 50), 1) == (200, 100, 50)
    assert render.lerp((0, 0, 0), (200, 100, 50), 0.5) == (100, 50, 25)
