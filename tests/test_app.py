"""Logic in the window module that doesn't need a window."""

import pytest

from pomodoro.app import tooltip_text
from pomodoro.bank import TimeBank
from pomodoro.timer import Phase, PomodoroTimer


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def timer(clock: FakeClock) -> PomodoroTimer:
    return PomodoroTimer(52 * 60, 17 * 60, bank=TimeBank(balance=600), min_work_to_bank=25 * 60, clock=clock)


def test_toggle_tooltip_follows_running_state(timer: PomodoroTimer) -> None:
    assert tooltip_text("toggle", timer) == "Start · Space"
    timer.start()
    assert tooltip_text("toggle", timer) == "Pause · Space"


def test_reset_tooltip(timer: PomodoroTimer) -> None:
    assert tooltip_text("reset", timer) == "Restart focus · R"


def test_skip_tooltip_names_next_phase(timer: PomodoroTimer) -> None:
    assert tooltip_text("skip", timer) == "Skip to break · S"
    timer.select_phase(Phase.BREAK)
    assert tooltip_text("skip", timer) == "Skip to focus · S"
    timer.select_phase(Phase.FREE)
    assert tooltip_text("skip", timer) == "Skip to focus · S"


def test_skip_tooltip_offers_to_bank_after_minimum_work(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.now += 40 * 60
    assert tooltip_text("skip", timer) == "Finish early, bank 12m · S"


def test_switch_tooltips_name_length_and_shortcut(timer: PomodoroTimer) -> None:
    assert tooltip_text(Phase.WORK, timer) == "Switch to a 52 minute focus session · F"
    assert tooltip_text(Phase.BREAK, timer) == "Switch to a 17 minute break · B"
    assert tooltip_text(Phase.FREE, timer) == "Spend your 10m of banked free time · T"


def test_free_tooltip_explains_how_to_earn_when_bank_is_empty(clock: FakeClock) -> None:
    timer = PomodoroTimer(52 * 60, 17 * 60, clock=clock)
    assert tooltip_text(Phase.FREE, timer) == "Finish focus early (after 25+ min) to bank free time"


def test_option_and_extend_tooltips(timer: PomodoroTimer) -> None:
    assert tooltip_text("auto_start", timer) == "Start the next phase by itself when one ends"
    assert tooltip_text("always_on_top", timer) == "Keep this window above other windows"
    assert tooltip_text("extend", timer) == "Add 5m from your bank (10m left) · E"
