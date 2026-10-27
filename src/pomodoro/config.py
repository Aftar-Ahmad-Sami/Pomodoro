"""Timer settings and application identity."""

from pathlib import Path

APP_NAME = "Pomodoro"
APP_ID = "Pomodoro.52-17"  # Windows AppUserModelID: groups the taskbar icon and labels toasts

WORK_MINUTES = 52
BREAK_MINUTES = 17
SESSIONS_PER_SET = 4
TICK_MS = 200

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PNG = ASSETS_DIR / "icon.png"
ICON_ICO = ASSETS_DIR / "icon.ico"
