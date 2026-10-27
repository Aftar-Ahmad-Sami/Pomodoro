import sys
from pathlib import Path

import pytest

from pomodoro import win32


def test_relaunch_command_from_source_runs_package_without_console() -> None:
    command = win32.relaunch_command()
    assert command.endswith(" -m pomodoro")
    assert command.lower().startswith(str(Path(sys.executable).parent).lower())


def test_relaunch_command_when_frozen_runs_the_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Pomodoro\Pomodoro.exe")
    assert win32.relaunch_command() == r'"C:\Program Files\Pomodoro\Pomodoro.exe"'
