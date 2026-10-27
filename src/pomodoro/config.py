"""Timer settings and application identity."""

from pathlib import Path

APP_NAME = "Pomodoro"
APP_ID = "Pomodoro.52-17"  # Windows AppUserModelID: groups the taskbar icon and labels toasts

WORK_MINUTES = 52
BREAK_MINUTES = 17
SESSIONS_PER_SET = 4
TICK_MS = 200

# Time bank: leftover focus time saved as guilt-free free time
BANK_MIN_WORK_MINUTES = 25  # finishing earlier than this banks nothing
BANK_DAILY_INTEREST = 0.10  # unspent balance grows by this fraction per day
BANK_INTEREST_CAP_MINUTES = 240  # interest stops once the balance reaches this
BANK_EXTEND_MINUTES = 5  # minutes a break is extended by per click

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PNG = ASSETS_DIR / "icon.png"
ICON_ICO = ASSETS_DIR / "icon.ico"
