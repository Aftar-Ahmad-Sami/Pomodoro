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
- Focus / Break switch to jump straight to either phase, e.g. for a 17 minute break on its own
- Start/Pause, Reset and Skip controls, with keyboard shortcuts
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
| App data (notification icon) | `%LOCALAPPDATA%\Pomodoro` |

Running setup again upgrades an existing install in place.

**Uninstall** from **Settings → Apps → Installed apps → Pomodoro → Uninstall**. This removes everything in the table above.

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
| `R` | Reset: restart the focus session (during a break, go back to focus) |
| `S` | Skip to the next phase. A skipped focus session isn't counted |
| `F` / `B` | Switch to focus / break, paused at the start of that phase. Does nothing if already in it |

The dots show progress through a set of four focus sessions; the line below them shows the total time focused since the app was opened.

## Troubleshooting

**"Windows protected your PC" when running setup.** The installer isn't code-signed, so SmartScreen warns about it. Click **More info → Run anyway**.

**Setup says Pomodoro is running.** Close the Pomodoro window and run setup again; Windows doesn't allow replacing an app while it runs.

**A taskbar pin does nothing when clicked.** It was pinned from an older version, from before the app told Windows how to relaunch it. Right-click it, choose **Unpin from taskbar**, open Pomodoro from the Start menu and pin it again.

**No notifications appear.** Check that notifications are on for Pomodoro under **Settings → System → Notifications**, and that Do Not Disturb or Focus is off. The chime and the window popping up work regardless.

## Development

Requires Python 3.10+ on Windows. Everything runs from a virtual environment inside the project, no Anaconda needed:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
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
  timer.py       Work/break state machine, independent of the UI
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
tests/           Timer, formatting, rendering, installer and Windows integration tests
```

The timer takes its clock as a parameter, so its behavior is tested with a fake clock and no window. The installer tests install into a temporary folder and don't touch the registry.

## Building

```powershell
pip install -e ".[build]"
.\scripts\build.ps1
```

This writes two files to `dist\`:

- `Pomodoro.exe`: the app on its own, runnable from anywhere
- `PomodoroSetup.exe`: the installer, with the app inside

The script uses `.venv` by default; pass `-Python <path\to\python.exe>` to use another interpreter. With a conda interpreter it also bundles conda's Tcl/Tk DLLs, which PyInstaller misses on its own (the exe would otherwise fail with `DLL load failed while importing _tkinter`).

CI builds both files on every push and keeps them as the `pomodoro-windows` artifact.

## Customizing

- Intervals: `WORK_MINUTES` and `BREAK_MINUTES` in [config.py](src/pomodoro/config.py)
- Colors: [theme.py](src/pomodoro/theme.py)
- Icon: edit and run `python scripts/make_icon.py` to regenerate the files in `src/pomodoro/assets/`

Rebuild and rerun setup afterwards to update the installed app.

## License

Copyright 2026 Aftar Ahmad Sami. Licensed under the [Apache License 2.0](LICENSE).
