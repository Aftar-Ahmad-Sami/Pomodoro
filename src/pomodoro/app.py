"""Tkinter window: draws the timer and wires up its controls.

Graphics are rendered with Pillow (see :mod:`pomodoro.render`) and layered on a canvas.
"""

from __future__ import annotations

import functools
import logging
import tkinter as tk
from collections.abc import Callable, Hashable
from tkinter import font as tkfont
from typing import Literal

from PIL import Image, ImageTk

from pomodoro import render, win32
from pomodoro.config import BREAK_MINUTES, ICON_ICO, ICON_PNG, SESSIONS_PER_SET, TICK_MS, WORK_MINUTES
from pomodoro.formatting import filled_dots, format_clock, format_focus_summary
from pomodoro.notify import Notifier
from pomodoro.theme import (
    BG_TOP,
    CONTROL_SPACING,
    CONTROLS_Y,
    DOT_SPACING,
    DOTS_Y,
    FAINT,
    FG,
    MUTED,
    OPTIONS_Y,
    PALETTES,
    RING_CENTER,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    hex_color,
)
from pomodoro.timer import Phase, PomodoroTimer

log = logging.getLogger(__name__)

POP_TOPMOST_MS = 1500  # how long the window stays on top after a phase change

ButtonName = Literal["reset", "toggle", "skip"]


class PomodoroApp:
    def __init__(self, root: tk.Tk, timer: PomodoroTimer, notifier: Notifier) -> None:
        self.root = root
        self.timer = timer
        self.notifier = notifier
        self.scale = root.winfo_fpixels("1i") / 96

        self.always_on_top = False
        self.hover: ButtonName | None = None
        self._images: dict[Hashable, ImageTk.PhotoImage] = {}
        self._ring_key: tuple[Phase, int] | None = None
        self._ring_img: ImageTk.PhotoImage | None = None
        self._logo: ImageTk.PhotoImage | None = None
        self._bg_phase: Phase | None = None

        self._setup_window()
        self._build_ui()
        self._render()
        self.root.after(TICK_MS, self._tick)

    def px(self, v: float) -> float:
        return v * self.scale

    def _setup_window(self) -> None:
        self.root.configure(bg=hex_color(BG_TOP))
        self.root.resizable(False, False)
        self.root.geometry(f"{round(self.px(WINDOW_WIDTH))}x{round(self.px(WINDOW_HEIGHT))}")
        try:
            self.root.iconbitmap(default=str(ICON_ICO))  # type: ignore[no-untyped-call]  # untyped in typeshed
        except tk.TclError:
            log.debug("Window icon unavailable", exc_info=True)
        # The native window must exist before it is styled, and the taskbar reads the
        # relaunch properties when the window is shown, so set them while it is hidden
        self.root.withdraw()
        self.root.update_idletasks()
        win32.set_relaunch_properties(self.root.winfo_id())
        win32.style_titlebar(self.root.winfo_id(), BG_TOP)
        self.root.deiconify()

    def _cached(self, key: Hashable, factory: Callable[[], Image.Image]) -> ImageTk.PhotoImage:
        if key not in self._images:
            self._images[key] = ImageTk.PhotoImage(factory())
        return self._images[key]

    # ---------- Layout ----------

    def _build_ui(self) -> None:
        families = set(tkfont.families())

        def pick(*names: str) -> str:
            return next((n for n in names if n in families), "Segoe UI")

        display = pick("Segoe UI Variable Display Light", "Segoe UI Light")
        semibold = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
        text = pick("Segoe UI Variable Text", "Segoe UI")

        px = self.px
        c = self.canvas = tk.Canvas(
            self.root,
            width=px(WINDOW_WIDTH),
            height=px(WINDOW_HEIGHT),
            highlightthickness=0,
            bd=0,
            bg=hex_color(BG_TOP),
        )
        c.pack()

        self.bg_item = c.create_image(0, 0, anchor="nw")

        # Header: logo + name
        try:
            logo = Image.open(ICON_PNG).resize((round(px(24)), round(px(24))), render.LANCZOS)
            self._logo = ImageTk.PhotoImage(logo)
            c.create_image(px(28), px(36), image=self._logo, anchor="w")
        except OSError:
            log.debug("Logo unavailable", exc_info=True)
        c.create_text(px(60), px(36), text="Pomodoro", font=(semibold, 11), fill=FG, anchor="w")
        c.create_text(
            px(WINDOW_WIDTH - 28),
            px(36),
            text=f"{WORK_MINUTES} / {BREAK_MINUTES}",
            font=(text, 10),
            fill=FAINT,
            anchor="e",
        )

        # Ring and its text
        cx, cy = RING_CENTER
        self.ring_item = c.create_image(px(cx), px(cy))
        self.phase_text = c.create_text(px(cx), px(cy - 52), font=(semibold, 10))
        self.time_text = c.create_text(px(cx), px(cy + 2), font=(display, 46), fill=FG)
        self.sub_text = c.create_text(px(cx), px(cy + 52), font=(text, 10), fill=MUTED)

        # Session progress dots
        start = cx - DOT_SPACING * (SESSIONS_PER_SET - 1) / 2
        self.dot_items = [c.create_image(px(start + i * DOT_SPACING), px(DOTS_Y)) for i in range(SESSIONS_PER_SET)]
        self.sessions_text = c.create_text(px(cx), px(DOTS_Y + 26), font=(text, 10), fill=MUTED)

        # Controls
        self.buttons: dict[ButtonName, int] = {
            "reset": c.create_image(px(cx - CONTROL_SPACING), px(CONTROLS_Y)),
            "toggle": c.create_image(px(cx), px(CONTROLS_Y)),
            "skip": c.create_image(px(cx + CONTROL_SPACING), px(CONTROLS_Y)),
        }
        actions: dict[ButtonName, Callable[[], None]] = {"reset": self.reset, "toggle": self.toggle, "skip": self.skip}
        for name, item in self.buttons.items():
            self._bind_button(item, name, actions[name])

        # Option toggles
        self.toggles: dict[str, int] = {}
        for option, label, x in (("auto_start", "Auto-start", 62), ("always_on_top", "Always on top", 200)):
            sw = c.create_image(px(x), px(OPTIONS_Y), anchor="w")
            lbl = c.create_text(px(x + 46), px(OPTIONS_Y), text=label, font=(text, 10), fill=MUTED, anchor="w")
            self.toggles[option] = sw
            for item in (sw, lbl):
                self._bind_option(item, option)

        self.root.bind("<space>", lambda e: self.toggle())
        self.root.bind("r", lambda e: self.reset())
        self.root.bind("s", lambda e: self.skip())

    def _bind_button(self, item: int, name: ButtonName, action: Callable[[], None]) -> None:
        c = self.canvas
        c.tag_bind(item, "<Enter>", lambda e: self._set_hover(name))
        c.tag_bind(item, "<Leave>", lambda e: self._set_hover(None))
        c.tag_bind(item, "<Button-1>", lambda e: action())

    def _bind_option(self, item: int, option: str) -> None:
        c = self.canvas
        c.tag_bind(item, "<Button-1>", lambda e: self._flip(option))
        c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))

    # ---------- Drawing ----------

    def _render(self) -> None:
        scale, timer = self.scale, self.timer
        phase = timer.phase
        colors = PALETTES[phase]
        c = self.canvas

        if self._bg_phase != phase:
            self._bg_phase = phase
            bg = self._cached(("bg", phase), functools.partial(render.render_background, scale, colors[0]))
            c.itemconfig(self.bg_item, image=bg)

        fraction = timer.progress
        ring_key = (phase, round(fraction * 360 * 4))
        if ring_key != self._ring_key:
            self._ring_key = ring_key
            self._ring_img = ImageTk.PhotoImage(render.render_ring(scale, fraction, colors))
            c.itemconfig(self.ring_item, image=self._ring_img)

        clock = format_clock(timer.remaining_whole_seconds)
        label = "Focus" if phase is Phase.WORK else "Break"
        if timer.running:
            sub = "until break" if phase is Phase.WORK else "until focus"
        elif timer.is_fresh:
            sub = "press space to start"
        else:
            sub = "paused"

        c.itemconfig(self.phase_text, text="  ".join(label.upper()), fill=hex_color(colors[0]))
        c.itemconfig(self.time_text, text=clock)
        c.itemconfig(self.sub_text, text=sub)

        filled = filled_dots(timer.sessions_done, SESSIONS_PER_SET)
        for i, item in enumerate(self.dot_items):
            on = i < filled
            img = self._cached(("dot", on, phase), functools.partial(render.render_dot, scale, on, colors[0]))
            c.itemconfig(item, image=img)
        c.itemconfig(self.sessions_text, text=format_focus_summary(timer.sessions_done, WORK_MINUTES))

        self._render_controls()
        self.root.title(f"{clock} · {label}")

    def _render_controls(self) -> None:
        scale, phase = self.scale, self.timer.phase
        colors = PALETTES[phase]
        for name, item in self.buttons.items():
            primary = name == "toggle"
            kind = self._button_kind(name)
            hover = self.hover == name
            key = ("btn", kind, phase if primary else None, hover)
            img = self._cached(key, functools.partial(render.render_button, scale, kind, colors, hover, primary))
            self.canvas.itemconfig(item, image=img)
        for option, item in self.toggles.items():
            on = self._option(option)
            img = self._cached(("toggle", on, phase), functools.partial(render.render_toggle, scale, on, colors))
            self.canvas.itemconfig(item, image=img)

    def _button_kind(self, name: ButtonName) -> render.ButtonKind:
        if name == "reset":
            return "reset"
        if name == "skip":
            return "skip"
        return "pause" if self.timer.running else "play"

    # ---------- Interaction ----------

    def _set_hover(self, name: ButtonName | None) -> None:
        self.hover = name
        self.canvas.config(cursor="hand2" if name else "")
        self._render_controls()

    def _option(self, name: str) -> bool:
        return self.timer.auto_start if name == "auto_start" else self.always_on_top

    def _flip(self, name: str) -> None:
        if name == "auto_start":
            self.timer.auto_start = not self.timer.auto_start
        else:
            self.always_on_top = not self.always_on_top
            self._apply_topmost()
        self._render_controls()

    def toggle(self) -> None:
        self.timer.toggle()
        self._render()

    def reset(self) -> None:
        self.timer.reset()
        self._render()

    def skip(self) -> None:
        self.timer.skip()
        self._render()

    def _tick(self) -> None:
        if self.timer.running:
            if self.timer.update():
                self._on_phase_completed()
            self._render()
        self.root.after(TICK_MS, self._tick)

    def _on_phase_completed(self) -> None:
        timer = self.timer
        self.notifier.phase_changed(timer.phase, timer.sessions_done, timer.auto_start)

        # Pop the window to the front so the user notices the phase change
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(POP_TOPMOST_MS, self._apply_topmost)
        self.root.focus_force()

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", self.always_on_top)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    win32.init_process()
    root = tk.Tk()
    timer = PomodoroTimer(WORK_MINUTES * 60, BREAK_MINUTES * 60)
    PomodoroApp(root, timer, Notifier())
    root.mainloop()


if __name__ == "__main__":
    main()
