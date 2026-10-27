<img src="src/pomodoro/assets/icon.png" width="96" align="right" alt="Pomodoro icon">

# Pomodoro

[![CI](https://github.com/Aftar-Ahmad-Sami/Pomodoro/actions/workflows/ci.yml/badge.svg)](https://github.com/Aftar-Ahmad-Sami/Pomodoro/actions/workflows/ci.yml)

A Windows desktop timer for the **52/17 productivity rule**: 52 minutes of focused work, then a 17 minute break, repeated.

- [Features](#features)
- [Install](#install)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Building](#building)
- [Customizing](#customizing)

## Features

- Glowing progress ring with a coral theme for focus and a mint theme for breaks
- Focus / Break / Free switch to jump straight to any phase, e.g. for a 17 minute break on its own
- Time bank: finish focus early and the leftover minutes become guilt-free free time, which earns interest until you spend it
- Start/Pause, Reset and Skip controls, with keyboard shortcuts; hover over a button to see what it does and its shortcut
- Windows notification, a chime and the window popping to the front when a phase ends
- Auto-start of the next phase and "always on top" toggles
- Session dots and total focused time
- Countdown in the window title, visible on the taskbar
- Dark Windows 11 title bar, sharp on high-DPI screens
- Installs like regular Windows software: Desktop and Start menu shortcuts, a taskbar pin that keeps working after the app is closed, and an uninstaller in Settings

## Install

**Requirements:** Windows 10 or 11. No admin rights needed.

1. Get `PomodoroSetup.exe`: download it from the latest [CI run](https://github.com/Aftar-Ahmad-Sami/Pomodoro/actions/workflows/ci.yml) (artifact `pomodoro-windows`), or [build it yourself](#building).
2. Run it, choose whether to add a desktop shortcut, and click **Install**.

Setup installs for the current user only:

| What | Where |
| --- | --- |
| App and uninstaller | `%LOCALAPPDATA%\Programs\Pomodoro` |
| Shortcuts | Start menu, and the Desktop if selected |
| Uninstall entry | **Settings → Apps → Installed apps** |
| App data (time bank, settings, notification icon) | `%LOCALAPPDATA%\Pomodoro` |

Running setup again upgrades an existing install in place.

**Uninstall** from **Settings → Apps → Installed apps → Pomodoro → Uninstall**. This removes everything in the table above, including your banked time. Upgrading by running setup again keeps it.

**Scripted install** (for example, when deploying to several machines):

```powershell
PomodoroSetup.exe --silent [--no-desktop-shortcut]
"$env:LOCALAPPDATA\Programs\Pomodoro\Uninstall.exe" --uninstall --silent
```

Both exit with code 0 on success and 1 on failure.

## Usage

Press **Space** (or the round button) to start. To run a break on its own, click **Break · 17m** at the top (or press `B`), then start it. When a phase ends, Pomodoro chimes, shows a notification and comes to the front; with **Auto-start** on, the next phase starts by itself.

| Key | Action |
| --- | --- |
| `Space` | Start / pause |
| `R` | Reset: restart the focus session (from a break or free time, go back to focus) |
| `S` | Skip to the next phase. After 25+ minutes of focus, this finishes the session early and banks the time left (see below) |
| `F` / `B` / `T` | Switch to focus / break / free time, paused at the start. Does nothing if already there |
| `E` | During a break, extend it by 5 minutes from the time bank |

The dots show progress through a set of four focus sessions; the line below them shows the total time focused since the app was opened.

### Time bank

Finish early, keep the time. If you're done with your work before the 52 minutes are up, press **Skip** (`S`): as long as you worked at least 25 minutes, the session counts and the minutes you didn't need go into your time bank as guilt-free free time. Skipping earlier than 25 minutes banks nothing, so quitting at minute 5 can't earn 47 minutes.

Spend it two ways:

- **Free time:** pick **Free** in the switch (or press `T`) and start it. It counts down your balance; pause or switch away and whatever is left stays banked. When it runs out, Pomodoro moves to focus.
- **Longer breaks:** during a break, click **+5m from bank** (or press `E`).

Or invest it: unspent time earns **10% interest per day**, compounding, until the balance reaches 4 hours. Banked time never expires. The balance is saved in `%LOCALAPPDATA%\Pomodoro\state.json`, along with the Auto-start and Always on top settings.

## Troubleshooting

**"Windows protected your PC" when running setup.** The installer isn't code-signed, so SmartScreen warns about it. Click **More info → Run anyway**.

**Setup says Pomodoro is running.** Close the Pomodoro window and run setup again; Windows doesn't allow replacing an app while it runs.

**A taskbar pin does nothing when clicked.** It was pinned from an older version, from before the app told Windows how to relaunch it. Right-click it, choose **Unpin from taskbar**, open Pomodoro from the Start menu and pin it again.

**No notifications appear.** Check that notifications are on for Pomodoro under **Settings → System → Notifications**, and that Do Not Disturb or Focus is off. The chime and the window popping up work regardless.

## Development

Requires Python 3.10+ on Windows. Use either a virtual environment inside the project:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

or, with Anaconda, any conda environment:

```powershell
conda activate <env>
pip install -e ".[dev]"
```

Run the app from source with `pomodoro` or `python -m pomodoro`.

Checks (CI runs all of them on every push and pull request, see [ci.yml](.github/workflows/ci.yml)):

```powershell
pytest                 # tests
ruff check .           # lint
ruff format .          # format
mypy                   # type check (strict)
```

### Project layout

```
src/pomodoro/
  app.py         Tkinter window: layout, drawing and input handling
  timer.py       Work/break/free state machine, independent of the UI
  bank.py        Time bank: banked minutes and daily interest
  storage.py     Saves the bank and settings between launches
  render.py      Pillow rendering of the ring, buttons, toggles and dots
  notify.py      Chime and Windows toast when a phase ends
  win32.py       Windows integration: DPI, title bar, taskbar identity, shortcuts
  installer.py   Per-user installer and uninstaller, built into PomodoroSetup.exe
  formatting.py  User-facing text derived from timer state
  theme.py       Colors and layout
  config.py      Durations and app identity
  assets/        Icon files
scripts/
  build.ps1      Builds Pomodoro.exe and PomodoroSetup.exe
  make_icon.py   Regenerates the icon files
tests/           Timer, bank, storage, formatting, rendering, installer and Windows tests
```

The timer takes its clock as a parameter, so its behavior is tested with a fake clock and no window. The installer tests install into a temporary folder and don't touch the registry.

## Building

With the environment from [Development](#development) activated:

```powershell
pip install -e ".[build]"
.\scripts\build.ps1
```

This writes two files to `dist\`:

- `Pomodoro.exe`: the app on its own, runnable from anywhere
- `PomodoroSetup.exe`: the installer, with the app inside

The script prints the Python it uses, picked in this order: `-Python <path\to\python.exe>` if given, the activated venv, the activated conda environment, the project's `.venv`, then `python` on PATH. It stops with a clear message if PyInstaller isn't installed there. With a conda interpreter it also bundles conda's Tcl/Tk DLLs, which PyInstaller misses on its own (the exe would otherwise fail with `DLL load failed while importing _tkinter`).

CI builds both files on every push and keeps them as the `pomodoro-windows` artifact.

## Customizing

- Intervals: `WORK_MINUTES` and `BREAK_MINUTES` in [config.py](src/pomodoro/config.py)
- Colors: [theme.py](src/pomodoro/theme.py)
- Icon: edit and run `python scripts/make_icon.py` to regenerate the files in `src/pomodoro/assets/`

Rebuild and rerun setup afterwards to update the installed app.

## License

Copyright 2026 Aftar Ahmad Sami. Licensed under the [Apache License 2.0](LICENSE).
