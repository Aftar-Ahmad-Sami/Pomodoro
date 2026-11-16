"""Slack settings window and its step-by-step setup guide.

Both are dark Toplevel windows matching the main window. The settings window edits
``slack.json`` and can send a test alert; the guide walks through creating the Slack app,
with buttons that copy the manifest and invite command and save the logo.
"""

from __future__ import annotations

import functools
import json
import logging
import shutil
import tkinter as tk
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog

from pomodoro import slack, win32
from pomodoro.config import SLACK_ICON_PNG
from pomodoro.theme import BG_TOP, FAINT, FG, MUTED, PALETTES, TOOLTIP_BG, TOOLTIP_BORDER, hex_color
from pomodoro.timer import Phase

log = logging.getLogger(__name__)

BG = hex_color(BG_TOP)
FIELD_BG = TOOLTIP_BG
BUTTON_BG = TOOLTIP_BORDER
BUTTON_HOVER = "#4b4768"
ACCENT = hex_color(PALETTES[Phase.WORK][0])
ACCENT_HOVER = "#ff8585"
ERROR_COLOR = ACCENT
OK_COLOR = hex_color(PALETTES[Phase.BREAK][0])
LINK_COLOR = hex_color(PALETTES[Phase.BREAK][1])

POLL_MS = 100  # how often a pending test alert is checked
FEEDBACK_MS = 1500  # how long "Copied" / "Saved" replaces a button's text
CONFIRM_MS = 4000  # how long Remove waits for the confirming second click

WIDTH = 400  # logical width of the settings window's content
HELP_WIDTH = 580  # wide, so the guide's steps wrap less
SCREEN_MARGIN = 140  # room left for the taskbar and title bar; the guide scrolls if it needs more


@dataclass(frozen=True)
class Fonts:
    text: str
    semibold: str


# ---------- Widgets ----------


def make_window(parent: tk.Misc, title: str) -> tk.Toplevel:
    """A hidden dark window; call :func:`show_near` once its content is built."""
    top = tk.Toplevel(parent)
    top.withdraw()
    top.title(title)
    top.configure(bg=BG)
    top.resizable(False, False)
    top.transient(parent.winfo_toplevel())
    top.update_idletasks()
    win32.style_titlebar(top.winfo_id(), BG_TOP)
    top.bind("<Escape>", lambda e: top.destroy())
    return top


def show_near(top: tk.Toplevel, anchor: tk.Misc, dx: int = 0) -> None:
    """Shows ``top`` over ``anchor`` (shifted right by ``dx``), kept on screen."""
    top.update_idletasks()
    x = anchor.winfo_rootx() + (anchor.winfo_width() - top.winfo_reqwidth()) // 2 + dx
    y = anchor.winfo_rooty() + 24
    x = max(0, min(x, top.winfo_screenwidth() - top.winfo_reqwidth()))
    # Leave room for the taskbar and the title bar, which reqheight doesn't include
    y = max(0, min(y, top.winfo_screenheight() - top.winfo_reqheight() - 100))
    top.geometry(f"+{x}+{y}")
    top.deiconify()
    top.lift()
    top.focus_force()


def make_button(
    parent: tk.Misc, text: str, command: Callable[[], None], font: Fonts, primary: bool = False
) -> tk.Button:
    bg, hover = (ACCENT, ACCENT_HOVER) if primary else (BUTTON_BG, BUTTON_HOVER)
    button = tk.Button(
        parent,
        text=text,
        command=command,
        font=(font.semibold, 9),
        bg=bg,
        fg="#ffffff" if primary else FG,
        activebackground=hover,
        activeforeground="#ffffff" if primary else FG,
        relief="flat",
        bd=0,
        padx=12,
        pady=5,
        cursor="hand2",
    )
    button.bind("<Enter>", lambda e: button.config(bg=hover))
    button.bind("<Leave>", lambda e: button.config(bg=bg))
    return button


def make_link(parent: tk.Misc, text: str, command: Callable[[], None], font: Fonts) -> tk.Label:
    link = tk.Label(parent, text=text, font=(font.semibold, 9), bg=BG, fg=LINK_COLOR, cursor="hand2")
    link.bind("<Button-1>", lambda e: command())
    link.bind("<Enter>", lambda e: link.config(font=(font.semibold, 9, "underline")))
    link.bind("<Leave>", lambda e: link.config(font=(font.semibold, 9)))
    return link


def make_entry(parent: tk.Misc, font: Fonts, width: int, show: str = "") -> tk.Entry:
    return tk.Entry(
        parent,
        font=(font.text, 10),
        width=width,
        show=show,
        bg=FIELD_BG,
        fg=FG,
        insertbackground=FG,
        selectbackground=BUTTON_HOVER,
        selectforeground=FG,
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=TOOLTIP_BORDER,
        highlightcolor=OK_COLOR,
    )


def flash_button(button: tk.Button, text: str) -> None:
    """Replaces the button's text for a moment, e.g. with "Copied"."""
    original = button.cget("text")
    if original == text:
        return
    button.config(text=text)

    def restore() -> None:
        if button.winfo_exists():
            button.config(text=original)

    button.after(FEEDBACK_MS, restore)


# ---------- Settings ----------


class SlackSettingsWindow:
    """Edits the Slack bot token, channel, member ID and how long alerts are kept."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Fonts,
        scale: float,
        config_path: Path,
        log_path: Path,
        on_change: Callable[[slack.SlackConfig | None], None],
    ) -> None:
        self.fonts = fonts
        self.scale = scale
        self.config_path = config_path
        self.log_path = log_path
        self.on_change = on_change  # called with the saved settings, or None once removed
        self._help: HelpWindow | None = None
        self._confirm_job: str | None = None

        self.top = make_window(parent, "Slack alerts")
        self._build()
        self._fill(slack.load_config(config_path))
        self.top.bind("<Return>", lambda e: self.save())
        show_near(self.top, parent)
        self.token.focus_set()

    @property
    def alive(self) -> bool:
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def lift(self) -> None:
        self.top.deiconify()
        self.top.lift()
        self.top.focus_force()

    def _px(self, v: float) -> int:
        return round(v * self.scale)

    def _build(self) -> None:
        f, px = self.fonts, self._px
        body = tk.Frame(self.top, bg=BG, padx=px(24), pady=px(20))
        body.pack(fill="both")

        tk.Label(body, text="Slack alerts", font=(f.semibold, 13), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(
            body,
            text="When a focus session or break ends, Pomodoro also posts an alert to Slack, "
            "then deletes it after a few hours.",
            font=(f.text, 9),
            bg=BG,
            fg=MUTED,
            justify="left",
            wraplength=px(WIDTH),
        ).pack(anchor="w", pady=(px(2), px(10)))
        make_link(body, "New to this? How to set up Slack →", self.open_help, f).pack(anchor="w", pady=(0, px(14)))

        token_row = self._field(body, "Bot token", "Starts with xoxb-. Stored only on this PC.")
        self.token = make_entry(token_row, f, width=38, show="•")
        self.token.pack(side="left", fill="x", expand=True, ipady=px(5), ipadx=px(4))
        self.show_token = make_button(token_row, "Show", self._toggle_token, f)
        self.show_token.pack(side="left", padx=(px(6), 0))

        channel_row = self._field(
            body, "Channel ID", "Starts with C. Or use your member ID (U…) to get alerts as direct messages."
        )
        self.channel = make_entry(channel_row, f, width=24)
        self.channel.pack(side="left", ipady=px(5), ipadx=px(4))

        mention_row = self._field(
            body, "Your member ID (optional)", "Alerts mention you, so Slack notifies your phone."
        )
        self.mention = make_entry(mention_row, f, width=24)
        self.mention.pack(side="left", ipady=px(5), ipadx=px(4))

        hours_row = self._field(body, "Delete alerts after", None)
        self.hours = make_entry(hours_row, f, width=5)
        self.hours.pack(side="left", ipady=px(5), ipadx=px(4))
        tk.Label(hours_row, text="hours", font=(f.text, 10), bg=BG, fg=MUTED).pack(side="left", padx=(px(6), 0))

        self.status = tk.Label(
            body, text="", font=(f.text, 9), bg=BG, fg=MUTED, justify="left", anchor="w", wraplength=px(WIDTH)
        )
        self.status.pack(fill="x", pady=(px(4), px(12)))

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x")
        self.save_button = make_button(buttons, "Save", self.save, f, primary=True)
        self.save_button.pack(side="right")
        self.test_button = make_button(buttons, "Send test", self.send_test, f)
        self.test_button.pack(side="right", padx=(0, px(8)))
        self.remove_button = make_button(buttons, "Remove", self.remove, f)
        self.remove_button.pack(side="left")

    def _field(self, parent: tk.Misc, label: str, hint: str | None) -> tk.Frame:
        """A labeled row; returns the frame to put the input in."""
        f, px = self.fonts, self._px
        tk.Label(parent, text=label, font=(f.semibold, 9), bg=BG, fg=FG).pack(anchor="w")
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(px(4), 0 if hint else px(10)))
        if hint:
            tk.Label(parent, text=hint, font=(f.text, 8), bg=BG, fg=FAINT, justify="left", wraplength=px(WIDTH)).pack(
                anchor="w", pady=(px(3), px(10))
            )
        return row

    def _fill(self, config: slack.SlackConfig | None) -> None:
        if config is None:
            self.hours.insert(0, f"{slack.DEFAULT_DELETE_AFTER_HOURS:g}")
            self.remove_button.pack_forget()  # nothing to remove yet
            return
        self.token.insert(0, config.token)
        self.channel.insert(0, config.channel)
        self.mention.insert(0, config.mention_user_id or "")
        self.hours.insert(0, f"{config.delete_after_hours:g}")

    def _toggle_token(self) -> None:
        hidden = self.token.cget("show") != ""
        self.token.config(show="" if hidden else "•")
        self.show_token.config(text="Hide" if hidden else "Show")

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status.config(text=text, fg=color)

    def _read(self) -> slack.SlackConfig | None:
        try:
            return slack.parse_config(self.token.get(), self.channel.get(), self.mention.get(), self.hours.get())
        except ValueError as e:
            self._set_status(str(e), ERROR_COLOR)
            return None

    # ---------- Actions ----------

    def save(self) -> None:
        config = self._read()
        if config is None:
            return
        try:
            slack.save_config(self.config_path, config)
        except OSError as e:
            log.warning("Could not save Slack settings", exc_info=True)
            self._set_status(f"Couldn't save the settings: {e.strerror or e}", ERROR_COLOR)
            return
        self.on_change(config)
        self.close()

    def send_test(self) -> None:
        config = self._read()
        if config is None:
            return
        self._set_status("Sending a test alert…")
        self.test_button.config(state="disabled")
        future = slack.SlackAlerts(config, self.log_path).post(slack.check_message(config))
        self.top.after(POLL_MS, self._check_test, future, config)

    def _check_test(self, future: Future[str | None], config: slack.SlackConfig) -> None:
        if not self.alive:
            return
        if not future.done():
            self.top.after(POLL_MS, self._check_test, future, config)
            return
        self.test_button.config(state="normal")
        error = future.result()
        if error is None:
            self._set_status(
                f"Sent! Check Slack for the test alert; it deletes itself after {config.delete_after_hours:g}h. "
                "Click Save to keep these settings.",
                OK_COLOR,
            )
        else:
            self._set_status(f"Couldn't post the test alert. {slack.explain_error(error)}", ERROR_COLOR)

    def remove(self) -> None:
        """Removes the settings after a confirming second click."""
        if self._confirm_job is None:
            self.remove_button.config(text="Click again to remove")
            self._confirm_job = self.top.after(CONFIRM_MS, self._cancel_remove)
            return
        self.top.after_cancel(self._confirm_job)
        self._confirm_job = None
        try:
            slack.remove_config(self.config_path)
        except OSError as e:
            log.warning("Could not remove Slack settings", exc_info=True)
            self._set_status(f"Couldn't remove the settings: {e.strerror or e}", ERROR_COLOR)
            return
        self.on_change(None)
        self.close()

    def _cancel_remove(self) -> None:
        self._confirm_job = None
        if self.alive:
            self.remove_button.config(text="Remove")

    def open_help(self) -> None:
        if self._help is not None and self._help.alive:
            self._help.lift()
            return
        self._help = HelpWindow(self.top, self.fonts, self.scale)

    def close(self) -> None:
        if self._help is not None and self._help.alive:
            self._help.top.destroy()
        self.top.destroy()


# ---------- Setup guide ----------


@dataclass(frozen=True)
class Step:
    title: str
    body: str
    actions: tuple[tuple[str, str], ...] = ()  # (button text, action name)


STEPS = (
    Step(
        "Create the Slack app",
        "Open the Slack apps page, click Create New App → Paste a manifest, pick your workspace, "
        "paste the manifest and click Create.",
        (("Open Slack apps page", "open_apps"), ("Copy manifest", "copy_manifest")),
    ),
    Step(
        "Install it and copy the token",
        "Click Install to Workspace. Then under OAuth & Permissions, copy the Bot User OAuth Token (xoxb-…) "
        "into Bot token. The App token and Slack CLI steps aren't needed.",
    ),
    Step(
        "Invite the bot to a channel",
        "In the Slack channel for your alerts, send:",
        (("Copy /invite @Pomodoro", "copy_invite"),),
    ),
    Step(
        "Copy the channel ID",
        "Click the channel name; the Channel ID (C…) is at the bottom of the About tab. Paste it into Channel ID.",
    ),
    Step(
        "Optional: notifications on your phone",
        "Profile picture → Profile → ⋮ → Copy member ID. Paste it into Your member ID so alerts mention you.",
    ),
    Step(
        "Optional: add the Pomodoro logo",
        "Save the logo and upload it under Basic Information → Display Information → App icon.",
        (("Save logo…", "save_logo"),),
    ),
    Step(
        "Test and save",
        "Click Send test in Slack settings. Once the test alert shows up in Slack, click Save.",
    ),
)

TROUBLESHOOTING = (
    "If the test fails, the settings window says why. The usual causes: the bot isn't invited (step 3), "
    "the channel ID is wrong (step 4), or the token was copied incompletely (step 2)."
)


class HelpWindow:
    """Step-by-step guide to creating the Slack app."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, scale: float) -> None:
        self.fonts = fonts
        self.scale = scale
        self.top = make_window(parent, "Set up Slack alerts")
        self._build()
        # Beside the settings window, so both stay visible (show_near keeps it on screen)
        show_near(self.top, parent, dx=round((WIDTH + HELP_WIDTH) / 2 * scale) + 40)

    @property
    def alive(self) -> bool:
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def lift(self) -> None:
        self.top.deiconify()
        self.top.lift()
        self.top.focus_force()

    def _px(self, v: float) -> int:
        return round(v * self.scale)

    def _build(self) -> None:
        f, px = self.fonts, self._px
        # The guide scrolls inside a canvas when it's taller than the screen
        canvas = tk.Canvas(self.top, bg=BG, highlightthickness=0, bd=0, yscrollincrement=px(20))
        body = tk.Frame(canvas, bg=BG, padx=px(24), pady=px(16))
        canvas.create_window(0, 0, window=body, anchor="nw")
        tk.Label(body, text="Set up Slack alerts", font=(f.semibold, 13), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(
            body,
            text="A one-time setup of about 5 minutes. Keep this guide open next to Slack.",
            font=(f.text, 9),
            bg=BG,
            fg=MUTED,
        ).pack(anchor="w", pady=(px(2), px(12)))

        actions: dict[str, Callable[[tk.Button], None]] = {
            "open_apps": lambda b: self._open(slack.SLACK_APPS_URL, b),
            "copy_manifest": lambda b: self._copy(json.dumps(slack.APP_MANIFEST, indent=2), b),
            "copy_invite": lambda b: self._copy(slack.INVITE_COMMAND, b),
            "save_logo": self._save_logo,
        }
        for number, step in enumerate(STEPS, start=1):
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=(0, px(9)))
            tk.Label(row, text=str(number), font=(f.semibold, 11), bg=BG, fg=ACCENT, width=2, anchor="nw").pack(
                side="left", anchor="n"
            )
            text = tk.Frame(row, bg=BG)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=step.title, font=(f.semibold, 10), bg=BG, fg=FG).pack(anchor="w")
            tk.Label(
                text, text=step.body, font=(f.text, 9), bg=BG, fg=MUTED, justify="left", wraplength=px(HELP_WIDTH - 40)
            ).pack(anchor="w", pady=(px(1), 0))
            if step.actions:
                buttons = tk.Frame(text, bg=BG)
                buttons.pack(anchor="w", pady=(px(5), 0))
                for label, name in step.actions:
                    button = make_button(buttons, label, lambda: None, f)
                    button.config(command=functools.partial(actions[name], button))  # the action updates its button
                    button.pack(side="left", padx=(0, px(6)))

        tk.Frame(body, bg=TOOLTIP_BORDER, height=1).pack(fill="x", pady=(px(2), px(10)))
        tk.Label(
            body, text=TROUBLESHOOTING, font=(f.text, 8), bg=BG, fg=FAINT, justify="left", wraplength=px(HELP_WIDTH)
        ).pack(anchor="w")

        self.top.update_idletasks()
        width, height = body.winfo_reqwidth(), body.winfo_reqheight()
        available = self.top.winfo_screenheight() - px(SCREEN_MARGIN)
        canvas.config(width=width, height=min(height, available), scrollregion=(0, 0, width, height))
        if height > available:
            scrollbar = tk.Scrollbar(self.top, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.config(yscrollcommand=scrollbar.set)
            # Bound on the window, so the wheel scrolls wherever the pointer is inside it
            self.top.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        canvas.pack(side="left", fill="both", expand=True)

    def _copy(self, text: str, button: tk.Button) -> None:
        self.top.clipboard_clear()
        self.top.clipboard_append(text)
        flash_button(button, "Copied ✓")

    def _open(self, url: str, button: tk.Button) -> None:
        webbrowser.open(url)
        flash_button(button, "Opened ✓")

    def _save_logo(self, button: tk.Button) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.top,
            title="Save the Pomodoro logo for Slack",
            initialfile="pomodoro-slack-icon.png",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if not path:
            return
        try:
            shutil.copyfile(SLACK_ICON_PNG, path)
        except OSError:
            log.warning("Could not save the Slack logo to %s", path, exc_info=True)
            flash_button(button, "Couldn't save")
            return
        flash_button(button, "Saved ✓")
