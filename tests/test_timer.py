import pytest

from pomodoro.bank import TimeBank
from pomodoro.timer import Phase, PomodoroTimer

WORK, BREAK = 100.0, 20.0
MIN_WORK = 50.0  # minimum work before finishing early banks time


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def timer(clock: FakeClock) -> PomodoroTimer:
    return PomodoroTimer(WORK, BREAK, min_work_to_bank=MIN_WORK, clock=clock)


def test_starts_fresh_in_work_phase(timer: PomodoroTimer) -> None:
    assert timer.phase is Phase.WORK
    assert not timer.running
    assert timer.is_fresh
    assert timer.remaining == WORK
    assert timer.progress == 0.0
    assert timer.sessions_done == 0


def test_rejects_non_positive_durations() -> None:
    with pytest.raises(ValueError):
        PomodoroTimer(0, BREAK)


def test_counts_down_while_running(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(30)
    assert timer.remaining == pytest.approx(70)
    assert timer.progress == pytest.approx(0.3)
    assert not timer.is_fresh


def test_pause_freezes_remaining_time(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(30)
    timer.pause()
    clock.advance(500)
    assert not timer.running
    assert timer.remaining == pytest.approx(70)

    timer.toggle()
    clock.advance(10)
    assert timer.remaining == pytest.approx(60)


def test_remaining_whole_seconds_shows_full_duration_at_start(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(0.01)
    assert timer.remaining_whole_seconds == WORK
    clock.advance(0.5)
    assert timer.remaining_whole_seconds == WORK
    clock.advance(1)
    assert timer.remaining_whole_seconds == WORK - 1


def test_update_does_nothing_before_phase_ends(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(WORK - 1)
    assert timer.update() is False
    assert timer.phase is Phase.WORK


def test_completed_work_counts_session_and_auto_starts_break(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(WORK + 5)
    assert timer.update() is True
    assert timer.phase is Phase.BREAK
    assert timer.sessions_done == 1
    assert timer.running
    assert timer.remaining == BREAK


def test_completed_break_returns_to_work_without_counting(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(WORK)
    timer.update()
    clock.advance(BREAK)
    assert timer.update() is True
    assert timer.phase is Phase.WORK
    assert timer.sessions_done == 1


def test_without_auto_start_next_phase_waits(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, auto_start=False, clock=clock)
    timer.start()
    clock.advance(WORK)
    timer.update()
    assert timer.phase is Phase.BREAK
    assert not timer.running
    assert timer.is_fresh


def test_skip_moves_on_without_counting_or_starting(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(10)
    timer.skip()
    assert timer.phase is Phase.BREAK
    assert timer.sessions_done == 0
    assert not timer.running
    assert timer.remaining == BREAK


def test_reset_during_work_restarts_work(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(40)
    timer.reset()
    assert timer.phase is Phase.WORK
    assert not timer.running
    assert timer.remaining == WORK


def test_reset_during_break_returns_to_work(timer: PomodoroTimer) -> None:
    timer.skip()
    timer.reset()
    assert timer.phase is Phase.WORK
    assert timer.remaining == WORK


def test_select_break_loads_full_break_paused(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(10)
    timer.select_phase(Phase.BREAK)
    assert timer.phase is Phase.BREAK
    assert not timer.running
    assert timer.is_fresh
    assert timer.remaining == BREAK
    assert timer.sessions_done == 0


def test_select_current_phase_keeps_progress(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(10)
    timer.select_phase(Phase.WORK)
    assert timer.running
    assert timer.remaining == pytest.approx(WORK - 10)


def test_selected_break_runs_into_focus(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.select_phase(Phase.BREAK)
    timer.start()
    clock.advance(BREAK)
    assert timer.update() is True
    assert timer.phase is Phase.WORK
    assert timer.sessions_done == 0


def test_update_is_idle_while_paused(timer: PomodoroTimer, clock: FakeClock) -> None:
    clock.advance(WORK * 10)
    assert timer.update() is False
    assert timer.phase is Phase.WORK


# ---------- Time bank ----------


def test_finishing_early_counts_session_and_banks_time_left(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(70)
    assert timer.can_finish_early
    banked = timer.skip()
    assert banked == pytest.approx(30)
    assert timer.bank.balance == pytest.approx(30)
    assert timer.sessions_done == 1
    assert timer.focused_seconds == pytest.approx(70)
    assert timer.phase is Phase.BREAK
    assert not timer.running


def test_skipping_before_minimum_work_banks_nothing(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(MIN_WORK - 1)
    assert not timer.can_finish_early
    assert timer.skip() == 0
    assert timer.bank.balance == 0
    assert timer.sessions_done == 0


def test_completed_work_adds_full_duration_to_focus_time(timer: PomodoroTimer, clock: FakeClock) -> None:
    timer.start()
    clock.advance(WORK)
    timer.update()
    assert timer.focused_seconds == WORK
    assert timer.bank.balance == 0


def test_free_time_needs_a_balance(timer: PomodoroTimer) -> None:
    timer.select_phase(Phase.FREE)
    assert timer.phase is Phase.WORK


def test_free_time_spends_the_bank(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=60), clock=clock)
    timer.select_phase(Phase.FREE)
    assert timer.phase is Phase.FREE
    assert timer.remaining == 60
    assert timer.banked_total == 60
    timer.start()
    clock.advance(25)
    assert timer.banked_total == pytest.approx(35)


def test_leaving_free_time_returns_unspent_minutes(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=60), clock=clock)
    timer.select_phase(Phase.FREE)
    timer.start()
    clock.advance(25)
    timer.select_phase(Phase.WORK)
    assert timer.bank.balance == pytest.approx(35)
    assert timer.phase is Phase.WORK


def test_free_time_running_out_moves_to_focus(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=60), clock=clock)
    timer.select_phase(Phase.FREE)
    timer.start()
    clock.advance(60)
    assert timer.update() is True
    assert timer.phase is Phase.WORK
    assert timer.bank.balance == 0
    assert timer.sessions_done == 0


def test_extend_break_draws_from_bank(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=8), clock=clock)
    timer.skip()
    timer.start()
    clock.advance(5)
    assert timer.extend_break(5) == 5
    assert timer.remaining == pytest.approx(BREAK - 5 + 5)
    assert timer.extend_break(5) == 3  # only 3 left in the bank
    assert timer.bank.balance == 0


def test_extension_lasts_only_for_that_break(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=10), clock=clock)
    timer.skip()
    timer.extend_break(10)
    timer.skip()  # back to focus
    timer.skip()  # next break
    assert timer.duration == BREAK


def test_extend_does_nothing_outside_breaks(clock: FakeClock) -> None:
    timer = PomodoroTimer(WORK, BREAK, bank=TimeBank(balance=10), clock=clock)
    assert timer.extend_break(5) == 0
    assert timer.bank.balance == 10
