"""User-facing text derived from timer state."""


def format_clock(seconds: int) -> str:
    """Formats a countdown as ``MM:SS``."""
    mins, secs = divmod(max(0, seconds), 60)
    return f"{mins:02d}:{secs:02d}"


def format_focus_summary(sessions: int, work_minutes: int) -> str:
    """Summarizes completed work sessions, e.g. ``3 sessions  ·  2h 36m focused``."""
    if sessions <= 0:
        return "No sessions yet"
    hours, mins = divmod(sessions * work_minutes, 60)
    focused = f"{hours}h {mins:02d}m" if hours else f"{mins}m"
    return f"{sessions} session{'s' if sessions != 1 else ''}  ·  {focused} focused"


def filled_dots(sessions: int, per_set: int) -> int:
    """Number of progress dots to fill. A finished set stays full until the next session ends."""
    if sessions <= 0:
        return 0
    return sessions % per_set or per_set
