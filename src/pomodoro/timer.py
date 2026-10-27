"""Pomodoro state machine, independent of any UI.

The timer never runs on its own. The caller polls :meth:`PomodoroTimer.update`
regularly; time is read from an injectable monotonic clock so tests can drive it.
"""

from __future__ import annotations

import enum
import math
import time
from collections.abc import Callable

Clock = Callable[[], float]


class Phase(enum.Enum):
    WORK = "work"
    BREAK = "break"

    @property
    def other(self) -> Phase:
        return Phase.BREAK if self is Phase.WORK else Phase.WORK


class PomodoroTimer:
    """Alternates between work and break phases and counts completed work sessions."""

    def __init__(
        self,
        work_seconds: float,
        break_seconds: float,
        *,
        auto_start: bool = True,
        clock: Clock = time.monotonic,
    ) -> None:
        if work_seconds <= 0 or break_seconds <= 0:
            raise ValueError("phase durations must be positive")
        self._durations = {Phase.WORK: float(work_seconds), Phase.BREAK: float(break_seconds)}
        self._clock = clock
        self.auto_start = auto_start
        self.sessions_done = 0
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
    def progress(self) -> float:
        """Fraction of the current phase that has elapsed, in [0, 1]."""
        return min(1.0, max(0.0, 1 - self.remaining / self.duration))

    @property
    def is_fresh(self) -> bool:
        """True when the current phase has not been started yet."""
        return not self.running and self._remaining >= self.duration

    @property
    def remaining_whole_seconds(self) -> int:
        # The small offset keeps a just-started timer showing its full duration
        return max(0, math.ceil(self.remaining - 0.05))

    # ---------- Controls ----------

    def start(self) -> None:
        if not self.running:
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
        """Restarts the focus session. During a break, ends the break and starts over from focus."""
        self._enter(Phase.WORK, run=False)

    def skip(self) -> None:
        """Moves to the next phase without counting the current one as completed."""
        self._enter(self.phase.other, run=False)

    def update(self) -> bool:
        """Advances the timer. Returns True if a phase just ran to completion."""
        if not self.running or self.remaining > 0:
            return False
        if self.phase is Phase.WORK:
            self.sessions_done += 1
        self._enter(self.phase.other, run=self.auto_start)
        return True

    def _enter(self, phase: Phase, *, run: bool) -> None:
        self.phase = phase
        self._remaining = self.duration
        self._end_time = None
        if run:
            self.start()
