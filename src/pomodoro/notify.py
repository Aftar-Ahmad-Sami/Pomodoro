"""Chime and Windows toast shown when a phase ends."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pomodoro.config import APP_ID, BREAK_MINUTES, WORK_MINUTES
from pomodoro.timer import Phase

try:
    import winsound
except ImportError:  # Not on Windows: no sound
    winsound = None  # type: ignore[assignment]

try:
    from winotify import Notification, audio
except ImportError:  # No toast support: the chime and window pop still work
    Notification = None

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToastMessage:
    title: str
    body: str


def toast_message(new_phase: Phase, sessions_done: int, auto_start: bool, ended: Phase = Phase.BREAK) -> ToastMessage:
    """Text announcing the phase that just began, after ``ended`` ran out."""
    if new_phase is Phase.BREAK:
        title = f"Break time · {BREAK_MINUTES} min"
        body = f"Focus session {sessions_done} done. Step away from the screen and stretch."
    else:
        title = f"Back to focus · {WORK_MINUTES} min"
        over = "Free time is over" if ended is Phase.FREE else "Break is over"
        body = f"{over}. Time for session {sessions_done + 1}."
    if not auto_start:
        body += " Press Start when you are ready."
    return ToastMessage(title, body)


class Notifier:
    def __init__(self) -> None:
        self._toast_icon: Path | None = None
        if Notification is not None:
            from pomodoro.win32 import register_toast_identity

            try:
                self._toast_icon = register_toast_identity()
            except OSError:
                log.warning("Could not register toast identity", exc_info=True)

    def phase_changed(self, new_phase: Phase, sessions_done: int, auto_start: bool, ended: Phase) -> None:
        self._play_chime(new_phase)
        self._show_toast(toast_message(new_phase, sessions_done, auto_start, ended))

    def _play_chime(self, new_phase: Phase) -> None:
        if winsound is None:
            return
        alias = "SystemExclamation" if new_phase is Phase.BREAK else "SystemAsterisk"
        winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)

    def _show_toast(self, message: ToastMessage) -> None:
        if Notification is None:
            return
        # winotify embeds the text in a PowerShell script: it must not contain $ or backticks
        try:
            toast = Notification(app_id=APP_ID, title=message.title, msg=message.body, icon=str(self._toast_icon or ""))
            toast.set_audio(audio.Silent, loop=False)  # The chime already plays
            toast.show()
        except OSError:
            log.warning("Could not show toast", exc_info=True)  # A failed toast must never stop the timer
