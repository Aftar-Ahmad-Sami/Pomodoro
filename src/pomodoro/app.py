"""Tkinter window: draws the timer and wires up its controls.

Graphics are rendered with Pillow (see :mod:`pomodoro.render`) and layered on a canvas.
"""

from __future__ import annotations

import datetime as dt
import functools
import logging
import time
import tkinter as tk
from collections.abc import Callable, Hashable
from pathlib import Path
from tkinter import font as tkfont
from typing import Literal

from PIL import Image, ImageTk

from pomodoro import render, storage, win32
from pomodoro.bank import TimeBank
from pomodoro.config import (
    BANK_DAILY_INTEREST,
    BANK_EXTEND_MINUTES,
    BANK_INTEREST_CAP_MINUTES,
    BANK_MIN_WORK_MINUTES,
    BREAK_MINUTES,
    ICON_ICO,
    ICON_PNG,
    SESSIONS_PER_SET,
    TICK_MS,
    WORK_MINUTES,
)
from pomodoro.formatting import filled_dots, format_clock, format_duration, format_focus_summary
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
    PHASE_SWITCH_PAD,
    PHASE_SWITCH_WIDTH,
    PHASE_SWITCH_Y,
    RING_CENTER,
    TOOLTIP_BG,
    TOOLTIP_BORDER,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    hex_color,
)
from pomodoro.timer import Phase, PomodoroTimer

log = logging.getLogger(__name__)

POP_TOPMOST_MS = 1500  # how long the window stays on top after a phase change
FLASH_MS = 4000  # how long a status message replaces the text under the clock
SAVE_INTERVAL_S = 30  # how often state is saved while the app runs, in case it is killed

ButtonName = Literal["reset", "toggle", "skip"]

PHASE_LABELS = {Phase.WORK: "Focus", Phase.BREAK: "Break", Phase.FREE: "Free"}
PHASE_ORDER = (Phase.WORK, Phase.BREAK, Phase.FREE)  # left to right in the switch
RUNNING_TEXT = {Phase.WORK: "until break", Phase.BREAK: "until focus", Phase.FREE: "of free time left"}
TOOLTIP_DELAY_MS = 400


OptionName = Literal["auto_start", "always_on_top"]
# Anything that shows a tooltip on hover: a round button, a switch segment, an option toggle or the extend link
TooltipTarget = ButtonName | Phase | OptionName | Literal["extend"]


def tooltip_text(target: TooltipTarget, timer: PomodoroTimer) -> str:
    """Describes what clicking ``target`` does right now, with its keyboard shortcut if it has one."""
    if target == "toggle":
        return "Pause · Space" if timer.running else "Start · Space"
    if target == "reset":
        return "Restart focus · R"
    if target == "skip":
        if timer.can_finish_early:
            return f"Finish early, bank {format_duration(timer.remaining)} · S"
        return f"Skip to {PHASE_LABELS[timer.phase.next].lower()} · S"
    if target is Phase.WORK:
        return f"Switch to a {WORK_MINUTES} minute focus session · F"
    if target is Phase.BREAK:
        return f"Switch to a {BREAK_MINUTES} minute break · B"
    if target is Phase.FREE:
        if timer.bank.balance <= 0:
            return f"Finish focus early (after {BANK_MIN_WORK_MINUTES}+ min) to bank free time"
        return f"Spend your {format_duration(timer.bank.balance)} of banked free time · T"
    if target == "auto_start":
        return "Start the next phase by itself when one ends"
    if target == "always_on_top":
        return "Keep this window above other windows"
    return f"Add {BANK_EXTEND_MINUTES}m from your bank ({format_duration(timer.bank.balance)} left) · E"


class PomodoroApp:
    def __init__(
        self,
        root: tk.Tk,
        timer: PomodoroTimer,
        notifier: Notifier,
        *,
        state_path: Path | None = None,
        always_on_top: bool = False,
    ) -> None:
        self.root = root
        self.timer = timer
        self.notifier = notifier
        self.state_path = state_path
        self.scale = root.winfo_fpixels("1i") / 96

        self.always_on_top = always_on_top
        self.hover: ButtonName | None = None
        self.switch_hover: Phase | None = None
        self._flash_text: str | None = None
        self._flash_job: str | None = None
        self._last_save = time.monotonic()
        self._images: dict[Hashable, ImageTk.PhotoImage] = {}
        self._ring_key: tuple[Phase, int] | None = None
        self._ring_img: ImageTk.PhotoImage | None = None
        self._logo: ImageTk.PhotoImage | None = None
        self._bg_phase: Phase | None = None
        self._tooltip_job: str | None = None
        self._tooltip_target: TooltipTarget | None = None  # what the mouse is over
        self._tooltip_text: str | None = None  # text of the visible tooltip, None when hidden

        self._setup_window()
        self._build_ui()
        self._apply_topmost()
        self._render()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
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
        self._tooltip_font = (text, 9)

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

        # Focus / Break / Free switch
        cx, cy = RING_CENTER
        self.switch_item = c.create_image(px(cx), px(PHASE_SWITCH_Y))
        c.tag_bind(self.switch_item, "<Motion>", lambda e: self._set_switch_hover(self._switch_phase_at(e.x)))
        c.tag_bind(self.switch_item, "<Leave>", lambda e: self._set_switch_hover(None))
        c.tag_bind(self.switch_item, "<Button-1>", lambda e: self.select_phase(self._switch_phase_at(e.x)))
        self.switch_labels: dict[Phase, int] = {}
        for i, phase in enumerate(PHASE_ORDER):
            item = c.create_text(px(self._switch_segment_center(i)), px(PHASE_SWITCH_Y), font=(semibold, 9))
            self.switch_labels[phase] = item
            self._bind_switch_label(item, phase)

        # Ring and its text
        self.ring_item = c.create_image(px(cx), px(cy))
        self.phase_text = c.create_text(px(cx), px(cy - 52), font=(semibold, 10))
        self.time_text = c.create_text(px(cx), px(cy + 2), font=(display, 46), fill=FG)
        self.sub_text = c.create_text(px(cx), px(cy + 52), font=(text, 10), fill=MUTED)
        self.extend_text = c.create_text(
            px(cx), px(cy + 78), text=f"+{BANK_EXTEND_MINUTES}m from bank", font=(semibold, 9), state="hidden"
        )
        c.tag_bind(self.extend_text, "<Button-1>", lambda e: self.extend_break())
        c.tag_bind(self.extend_text, "<Enter>", lambda e: self._hover_link("extend"))
        c.tag_bind(self.extend_text, "<Leave>", lambda e: self._hover_link(None))

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
        self.toggles: dict[OptionName, int] = {}
        options: tuple[tuple[OptionName, str, int], ...] = (
            ("auto_start", "Auto-start", 62),
            ("always_on_top", "Always on top", 200),
        )
        for option, label, x in options:
            sw = c.create_image(px(x), px(OPTIONS_Y), anchor="w")
            lbl = c.create_text(px(x + 46), px(OPTIONS_Y), text=label, font=(text, 10), fill=MUTED, anchor="w")
            self.toggles[option] = sw
            for item in (sw, lbl):
                self._bind_option(item, option)

        self.root.bind("<space>", lambda e: self.toggle())
        self.root.bind("r", lambda e: self.reset())
        self.root.bind("s", lambda e: self.skip())
        self.root.bind("f", lambda e: self.select_phase(Phase.WORK))
        self.root.bind("b", lambda e: self.select_phase(Phase.BREAK))
        self.root.bind("t", lambda e: self.select_phase(Phase.FREE))
        self.root.bind("e", lambda e: self.extend_break())

    def _bind_button(self, item: int, name: ButtonName, action: Callable[[], None]) -> None:
        c = self.canvas
        c.tag_bind(item, "<Enter>", lambda e: self._set_hover(name))
        c.tag_bind(item, "<Leave>", lambda e: self._set_hover(None))
        c.tag_bind(item, "<Button-1>", lambda e: self._click_button(action))

    def _bind_switch_label(self, item: int, phase: Phase) -> None:
        c = self.canvas
        c.tag_bind(item, "<Enter>", lambda e: self._set_switch_hover(phase))
        c.tag_bind(item, "<Leave>", lambda e: self._set_switch_hover(None))
        c.tag_bind(item, "<Button-1>", lambda e: self.select_phase(phase))

    @staticmethod
    def _switch_segment_center(index: int) -> float:
        segment = (PHASE_SWITCH_WIDTH - 2 * PHASE_SWITCH_PAD) / len(PHASE_ORDER)
        return RING_CENTER[0] - PHASE_SWITCH_WIDTH / 2 + PHASE_SWITCH_PAD + segment * (index + 0.5)

    def _switch_phase_at(self, x: int) -> Phase:
        """The switch segment under canvas x coordinate ``x``."""
        left = self.px(RING_CENTER[0] - PHASE_SWITCH_WIDTH / 2)
        index = int((x - left) / self.px(PHASE_SWITCH_WIDTH) * len(PHASE_ORDER))
        return PHASE_ORDER[min(len(PHASE_ORDER) - 1, max(0, index))]

    def _bind_option(self, item: int, option: OptionName) -> None:
        c = self.canvas
        c.tag_bind(item, "<Button-1>", lambda e: self._click_button(lambda: self._flip(option)))
        c.tag_bind(item, "<Enter>", lambda e: self._hover_link(option))
        c.tag_bind(item, "<Leave>", lambda e: self._hover_link(None))

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
        label = PHASE_LABELS[phase]
        c.itemconfig(self.phase_text, text="  ".join(label.upper()), fill=hex_color(colors[0]))
        c.itemconfig(self.time_text, text=clock)
        c.itemconfig(self.sub_text, text=self._flash_text or self._status_text())
        c.itemconfig(self.extend_text, state="normal" if self._can_extend() else "hidden", fill=hex_color(colors[0]))

        filled = filled_dots(timer.sessions_done, SESSIONS_PER_SET)
        for i, item in enumerate(self.dot_items):
            on = i < filled
            img = self._cached(("dot", on, phase), functools.partial(render.render_dot, scale, on, colors[0]))
            c.itemconfig(item, image=img)
        c.itemconfig(self.sessions_text, text=format_focus_summary(timer.sessions_done, timer.focused_seconds))

        self._render_controls()
        self._refresh_tooltip()
        self.root.title(f"{clock} · {label}")

    def _status_text(self) -> str:
        """The line under the clock."""
        timer = self.timer
        if timer.running:
            if timer.can_finish_early:
                return f"done? press S to bank {format_duration(timer.remaining)}"
            return RUNNING_TEXT[timer.phase]
        if timer.is_fresh:
            return "press space to start"
        return "paused"

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

        active = PHASE_ORDER.index(phase)
        hovered = PHASE_ORDER.index(self.switch_hover) if self.switch_hover else None
        img = self._cached(
            ("switch", phase, hovered),
            functools.partial(render.render_phase_switch, scale, len(PHASE_ORDER), active, hovered, colors),
        )
        self.canvas.itemconfig(self.switch_item, image=img)
        lengths = {
            Phase.WORK: f"{WORK_MINUTES}m",
            Phase.BREAK: f"{BREAK_MINUTES}m",
            Phase.FREE: format_duration(self.timer.banked_total),
        }
        for label_phase, item in self.switch_labels.items():
            self.canvas.itemconfig(
                item,
                text=f"{PHASE_LABELS[label_phase]} · {lengths[label_phase]}",
                fill=self._switch_label_color(label_phase),
            )

    def _switch_label_color(self, label_phase: Phase) -> str:
        if label_phase is self.timer.phase:
            return "#ffffff"  # on the gradient
        if not self._can_select(label_phase):
            return FAINT
        return FG if label_phase is self.switch_hover else MUTED

    def _can_extend(self) -> bool:
        """Whether the "+5m from bank" link is shown."""
        return self.timer.phase is Phase.BREAK and self.timer.bank.balance >= 60

    def _can_select(self, phase: Phase) -> bool:
        return phase is not Phase.FREE or self.timer.bank.balance > 0

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
        self._hover_tooltip(name)

    def _hover_link(self, target: OptionName | Literal["extend"] | None) -> None:
        """Hover handling for the text-like controls: hand cursor plus tooltip."""
        self.canvas.config(cursor="hand2" if target else "")
        self._hover_tooltip(target)

    def _click_button(self, action: Callable[[], None]) -> None:
        self._hide_tooltip()
        action()

    # ---------- Tooltips ----------

    def _hover_tooltip(self, target: TooltipTarget | None) -> None:
        """Shows ``target``'s tooltip after a short delay, or hides the tooltip for None."""
        if target == self._tooltip_target:
            return
        self._hide_tooltip()
        self._tooltip_target = target
        if target is not None:
            self._tooltip_job = self.root.after(TOOLTIP_DELAY_MS, self._show_tooltip)

    def _tooltip_anchor(self, target: TooltipTarget) -> tuple[float, float]:
        """Canvas point the tooltip is centered on: above the round buttons, below everything else."""
        c, px = self.canvas, self.px
        if isinstance(target, Phase):
            return px(self._switch_segment_center(PHASE_ORDER.index(target))), px(PHASE_SWITCH_Y + 30)
        if target == "extend":
            x, y = c.coords(self.extend_text)
            return x, y + px(24)
        if target == "auto_start" or target == "always_on_top":
            x, y = c.coords(self.toggles[target])
            return x + px(19), y + px(23)  # the toggle is anchored at its left edge and 38 wide
        x, y = c.coords(self.buttons[target])
        return x, y - px(50)

    def _show_tooltip(self) -> None:
        self._tooltip_job = None
        self.canvas.delete("tooltip")
        target = self._tooltip_target
        if target is None:
            return
        c, px = self.canvas, self.px
        x, y = self._tooltip_anchor(target)
        self._tooltip_text = tooltip_text(target, self.timer)
        text = c.create_text(x, y, text=self._tooltip_text, fill=FG, font=self._tooltip_font, tags="tooltip")
        x0, y0, x1, y1 = c.bbox(text)
        pad_x, pad_y = px(8), px(4)
        c.create_rectangle(
            x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y, fill=TOOLTIP_BG, outline=TOOLTIP_BORDER, tags="tooltip"
        )
        c.tag_raise(text)
        # Keep the tooltip inside the window
        margin = px(6)
        overflow_right = x1 + pad_x - (px(WINDOW_WIDTH) - margin)
        overflow_left = margin - (x0 - pad_x)
        c.move("tooltip", -max(0.0, overflow_right) + max(0.0, overflow_left), 0)

    def _hide_tooltip(self) -> None:
        if self._tooltip_job is not None:
            self.root.after_cancel(self._tooltip_job)
            self._tooltip_job = None
        self.canvas.delete("tooltip")
        self._tooltip_text = None

    def _refresh_tooltip(self) -> None:
        """Keeps a visible tooltip current, e.g. after Space starts the timer or a break ends."""
        target = self._tooltip_target
        if self._tooltip_text is None or target is None:
            return
        if target == "extend" and not self._can_extend():
            self._hide_tooltip()
        elif tooltip_text(target, self.timer) != self._tooltip_text:
            self._show_tooltip()

    def _set_switch_hover(self, phase: Phase | None) -> None:
        # Every segment but the current one explains itself, including a greyed-out Free
        self._hover_tooltip(phase if phase is not self.timer.phase else None)
        if phase is not None and (phase is self.timer.phase or not self._can_select(phase)):
            phase = None
        if phase is self.switch_hover:
            return  # <Motion> fires constantly; only redraw when the segment changes
        self.switch_hover = phase
        self.canvas.config(cursor="hand2" if phase else "")
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
        self._save()

    def toggle(self) -> None:
        self.timer.toggle()
        self._render()

    def reset(self) -> None:
        self.timer.reset()
        self._changed()

    def skip(self) -> None:
        banked = self.timer.skip()
        if banked >= 60:
            self.flash(f"+{format_duration(banked)} banked as free time")
        self._changed()

    def select_phase(self, phase: Phase) -> None:
        self.timer.select_phase(phase)
        self._set_switch_hover(None)
        self._changed()

    def extend_break(self) -> None:
        added = self.timer.extend_break(BANK_EXTEND_MINUTES * 60)
        if added > 0:
            self.flash(f"break extended by {format_duration(added)}")
        self._changed()

    def flash(self, text: str) -> None:
        """Shows ``text`` under the clock for a few seconds."""
        self._flash_text = text
        if self._flash_job is not None:
            self.root.after_cancel(self._flash_job)
        self._flash_job = self.root.after(FLASH_MS, self._end_flash)
        self._render()

    def _end_flash(self) -> None:
        self._flash_text = None
        self._flash_job = None
        self._render()

    def _changed(self) -> None:
        """Redraws and saves after an action that can move time in or out of the bank."""
        self._render()
        self._save()

    def _tick(self) -> None:
        timer = self.timer
        if timer.running:
            ended = timer.phase
            if timer.update():
                self._on_phase_completed(ended)
            self._render()
        gained = timer.bank.accrue(dt.date.today())  # in case the app stays open past midnight
        if gained >= 60:
            self.flash(f"+{format_duration(gained)} interest on your free time")
        if time.monotonic() - self._last_save >= SAVE_INTERVAL_S:
            self._save()
        self.root.after(TICK_MS, self._tick)

    def _on_phase_completed(self, ended: Phase) -> None:
        timer = self.timer
        self._save()
        self.notifier.phase_changed(timer.phase, timer.sessions_done, timer.auto_start, ended)

        # Pop the window to the front so the user notices the phase change
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(POP_TOPMOST_MS, self._apply_topmost)
        self.root.focus_force()

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", self.always_on_top)

    # ---------- Persistence ----------

    def _save(self) -> None:
        self._last_save = time.monotonic()
        if self.state_path is None:
            return
        state = storage.SavedState(
            bank_seconds=self.timer.banked_total,
            interest_date=self.timer.bank.interest_date,
            auto_start=self.timer.auto_start,
            always_on_top=self.always_on_top,
        )
        storage.save(self.state_path, state)

    def _close(self) -> None:
        self._save()
        self.root.destroy()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    win32.init_process()
    state_path = storage.default_path()
    state = storage.load(state_path)
    today = dt.date.today()
    bank = TimeBank(
        balance=state.bank_seconds,
        interest_date=state.interest_date or today,
        daily_interest=BANK_DAILY_INTEREST,
        interest_cap=BANK_INTEREST_CAP_MINUTES * 60,
    )
    interest = bank.accrue(today)

    root = tk.Tk()
    timer = PomodoroTimer(
        WORK_MINUTES * 60,
        BREAK_MINUTES * 60,
        bank=bank,
        min_work_to_bank=BANK_MIN_WORK_MINUTES * 60,
        auto_start=state.auto_start,
    )
    app = PomodoroApp(root, timer, Notifier(), state_path=state_path, always_on_top=state.always_on_top)
    if interest >= 60:
        app.flash(f"+{format_duration(interest)} interest on your free time")
    root.mainloop()


if __name__ == "__main__":
    main()
