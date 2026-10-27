"""User-facing text derived from timer state."""


def format_clock(seconds: int) -> str:
    """Formats a countdown as ``MM:SS``."""
    mins, secs = divmod(max(0, seconds), 60)
    return f"{mins:02d}:{secs:02d}"


def format_duration(seconds: float) -> str:
    """Formats a span in whole minutes, e.g. ``45m`` or ``2h 05m``. Partial minutes round down."""
    hours, mins = divmod(int(max(0.0, seconds)) // 60, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def format_focus_summary(sessions: int, focused_seconds: float) -> str:
    """Summarizes completed work sessions, e.g. ``3 sessions  ·  2h 36m focused``."""
    if sessions <= 0:
        return "No sessions yet"
    return f"{sessions} session{'s' if sessions != 1 else ''}  ·  {format_duration(focused_seconds)} focused"


def filled_dots(sessions: int, per_set: int) -> int:
    """Number of progress dots to fill. A finished set stays full until the next session ends."""
    if sessions <= 0:
        return 0
    return sessions % per_set or per_set
