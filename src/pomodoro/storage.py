"""Saves the app's state between launches as a small JSON file."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pomodoro.config import APP_NAME

log = logging.getLogger(__name__)

FORMAT_VERSION = 1


def default_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "state.json"


@dataclass
class SavedState:
    bank_seconds: float = 0.0
    interest_date: dt.date | None = None
    auto_start: bool = True
    always_on_top: bool = False


def load(path: Path) -> SavedState:
    """Reads saved state. A missing or unreadable file gives the defaults."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SavedState(
            bank_seconds=max(0.0, float(data.get("bank_seconds", 0.0))),
            interest_date=dt.date.fromisoformat(data["interest_date"]) if data.get("interest_date") else None,
            auto_start=bool(data.get("auto_start", True)),
            always_on_top=bool(data.get("always_on_top", False)),
        )
    except FileNotFoundError:
        return SavedState()
    except (OSError, ValueError, TypeError, AttributeError):
        log.warning("Ignoring unreadable state file %s", path, exc_info=True)
        return SavedState()


def save(path: Path, state: SavedState) -> None:
    """Writes state atomically, so a crash mid-write never corrupts the file."""
    data = {
        "version": FORMAT_VERSION,
        "bank_seconds": round(state.bank_seconds, 1),
        "interest_date": state.interest_date.isoformat() if state.interest_date else None,
        "auto_start": state.auto_start,
        "always_on_top": state.always_on_top,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        log.warning("Could not save state to %s", path, exc_info=True)
