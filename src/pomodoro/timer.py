"""Pomodoro state machine, independent of any UI.

The timer never runs on its own. The caller polls :meth:`PomodoroTimer.update`
regularly; time is read from an injectable monotonic clock so tests can drive it.

Besides work and break, there is a free-time phase that spends the :class:`TimeBank`.
Finishing a work session early (after a minimum amount of work) banks the time left.
"""

from __future__ import annotations

import enum
import math
import time
from collections.abc import Callable

from pomodoro.bank import TimeBank

Clock = Callable[[], float]


class Phase(enum.Enum):
    WORK = "work"
    BREAK = "break"
    FREE = "free"

    @property
    def next(self) -> Phase:
        """The phase that follows this one when it ends or is skipped."""
        return Phase.BREAK if self is Phase.WORK else Phase.WORK


class PomodoroTimer:
    """Cycles through work and break phases, counts work sessions and manages the time bank."""

    def __init__(
        self,
        work_seconds: float,
        break_seconds: float,
        *,
        bank: TimeBank | None = None,
        min_work_to_bank: float = 0.0,
        auto_start: bool = True,
        clock: Clock = time.monotonic,
    ) -> None:
        if work_seconds <= 0 or break_seconds <= 0:
            raise ValueError("phase durations must be positive")
        self._break_seconds = float(break_seconds)
        self._durations = {Phase.WORK: float(work_seconds), Phase.BREAK: self._break_seconds, Phase.FREE: 0.0}
        self._clock = clock
        self.bank = bank if bank is not None else TimeBank()
        self.min_work_to_bank = min_work_to_bank
        self.auto_start = auto_start
        self.sessions_done = 0
        self.focused_seconds = 0.0
        self.phase = Phase.WORK
        self._remaining = self.duration
        self._end_time: float | None = None  # clock deadline while running, None while paused

    # ---------- State ----------

    @property
    def duration(self) -> float:
        return self._durations[self.phase]

    @property
    def running(self) -> bool:
        return self._end_time is not None

    @property
    def remaining(self) -> float:
        """Seconds left in the current phase, never negative."""
        if self._end_time is None:
            return self._remaining
        return max(0.0, self._end_time - self._clock())

    @property
    def elapsed(self) -> float:
        return self.duration - self.remaining

    @property
    def progress(self) -> float:
        """Fraction of the current phase that has elapsed, in [0, 1]."""
        if self.duration <= 0:
            return 0.0
        return min(1.0, max(0.0, 1 - self.remaining / self.duration))

    @property
    def is_fresh(self) -> bool:
        """True when the current phase has not been started yet."""
        return not self.running and self._remaining >= self.duration

    @property
    def remaining_whole_seconds(self) -> int:
        # The small offset keeps a just-started timer showing its full duration
        return max(0, math.ceil(self.remaining - 0.05))

    @property
    def can_finish_early(self) -> bool:
        """True when skipping now would count the work session and bank the time left."""
        return self.phase is Phase.WORK and not self.is_fresh and self.elapsed >= self.min_work_to_bank

    @property
    def banked_total(self) -> float:
        """Seconds in the bank, including unspent free time in progress."""
        return self.bank.balance + (self.remaining if self.phase is Phase.FREE else 0.0)

    # ---------- Controls ----------

    def start(self) -> None:
        if not self.running and self._remaining > 0:
            self._end_time = self._clock() + self._remaining

    def pause(self) -> None:
        if self.running:
            self._remaining = self.remaining
            self._end_time = None

    def toggle(self) -> None:
        if self.running:
            self.pause()
        else:
            self.start()

    def reset(self) -> None:
        """Restarts the focus session. From a break or free time, goes back to focus."""
        self._enter(Phase.WORK, run=False)

    def skip(self) -> float:
        """Moves to the next phase. Returns the seconds banked, if any.

        Skipping work after at least ``min_work_to_bank`` seconds finishes it early: the
        session counts and the time left goes into the bank. Earlier, nothing is counted.
        """
        banked = 0.0
        if self.can_finish_early:
            banked = self.remaining
            self._complete_work(self.elapsed)
            self.bank.deposit(banked)
        self._enter(self.phase.next, run=False)
        return banked

    def select_phase(self, phase: Phase) -> None:
        """Loads ``phase`` from its start, paused. Selecting the current phase changes nothing.

        Free time can only be selected while the bank has a balance.
        """
        if phase is self.phase or (phase is Phase.FREE and self.bank.balance <= 0):
            return
        self._enter(phase, run=False)

    def extend_break(self, seconds: float) -> float:
        """Adds up to ``seconds`` from the bank to the current break. Returns the seconds added."""
        if self.phase is not Phase.BREAK:
            return 0.0
        added = self.bank.withdraw(seconds)
        self._durations[Phase.BREAK] += added
        if self._end_time is None:
            self._remaining += added
        else:
            self._end_time += added
        return added

    def update(self) -> bool:
        """Advances the timer. Returns True if a phase just ran to completion."""
        if not self.running or self.remaining > 0:
            return False
        if self.phase is Phase.WORK:
            self._complete_work(self.duration)
        self._enter(self.phase.next, run=self.auto_start)
        return True

    # ---------- Internals ----------

    def _complete_work(self, worked: float) -> None:
        self.sessions_done += 1
        self.focused_seconds += worked

    def _enter(self, phase: Phase, *, run: bool) -> None:
        if self.phase is Phase.FREE:
            self.bank.deposit(self.remaining)  # unspent free time goes back
        self._durations[Phase.BREAK] = self._break_seconds  # undo any extension
        if phase is Phase.FREE:
            self._durations[Phase.FREE] = self.bank.withdraw(self.bank.balance)
        self.phase = phase
        self._remaining = self.duration
        self._end_time = None
        if run:
            self.start()
