import pytest

from pomodoro.formatting import filled_dots, format_clock, format_duration, format_focus_summary
from pomodoro.notify import toast_message
from pomodoro.timer import Phase


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00"), (59, "00:59"), (60, "01:00"), (52 * 60, "52:00"), (-5, "00:00")],
)
def test_format_clock(seconds: int, expected: str) -> None:
    assert format_clock(seconds) == expected


@pytest.mark.parametrize(
    ("sessions", "focused_minutes", "expected"),
    [
        (0, 0, "No sessions yet"),
        (1, 52, "1 session  ·  52m focused"),
        (2, 104, "2 sessions  ·  1h 44m focused"),
        (2, 90, "2 sessions  ·  1h 30m focused"),
    ],
)
def test_format_focus_summary(sessions: int, focused_minutes: int, expected: str) -> None:
    assert format_focus_summary(sessions, focused_minutes * 60) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0m"), (59, "0m"), (60, "1m"), (14 * 60 + 30, "14m"), (125 * 60, "2h 05m"), (-5, "0m")],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(("sessions", "expected"), [(0, 0), (1, 1), (3, 3), (4, 4), (5, 1), (8, 4)])
def test_filled_dots(sessions: int, expected: int) -> None:
    assert filled_dots(sessions, 4) == expected


def test_toast_after_free_time_says_so() -> None:
    msg = toast_message(Phase.WORK, sessions_done=2, auto_start=True, ended=Phase.FREE)
    assert msg.body.startswith("Free time is over")


def test_toast_for_break_mentions_finished_session() -> None:
    msg = toast_message(Phase.BREAK, sessions_done=3, auto_start=True)
    assert msg.title.startswith("Break time")
    assert "Focus session 3 done" in msg.body
    assert "Press Start" not in msg.body


def test_toast_for_work_mentions_next_session_and_manual_start() -> None:
    msg = toast_message(Phase.WORK, sessions_done=3, auto_start=False)
    assert msg.title.startswith("Back to focus")
    assert "session 4" in msg.body
    assert msg.body.endswith("Press Start when you are ready.")


@pytest.mark.parametrize("phase", list(Phase))
@pytest.mark.parametrize("auto_start", [True, False])
def test_toast_text_is_safe_for_powershell(phase: Phase, auto_start: bool) -> None:
    msg = toast_message(phase, sessions_done=1, auto_start=auto_start)
    for text in (msg.title, msg.body):
        assert "$" not in text
        assert "`" not in text
