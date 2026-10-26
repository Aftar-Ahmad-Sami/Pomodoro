<img src="assets/icon.png" width="96" align="right" alt="Pomodoro icon">

# Pomodoro

A Windows desktop timer for the **52/17 productivity rule**: 52 minutes of focused work, then a 17 minute break, repeated.

## Features

- Glowing progress ring with a coral theme for focus and a mint theme for breaks
- Start/Pause, Reset and Skip controls
- Windows notification, a chime and the window popping to the front when a phase ends
- Auto-start of the next phase and "always on top" toggles
- Session dots and total focused time
- Dark Windows 11 title bar, sharp on high-DPI screens
- Countdown shown in the window title (visible on the taskbar)

Keyboard shortcuts: `Space` start/pause, `R` reset, `S` skip.

## Run from source

Uses the `misc` conda env:

```powershell
conda activate misc
pip install -r requirements.txt
python pomodoro.py
```

## Build a standalone .exe

With PyInstaller installed in `misc` (`pip install pyinstaller`), run:

```powershell
.\build.ps1
```

The executable is written to `dist\Pomodoro.exe`. The script adds conda's Tcl/Tk DLLs explicitly; a plain `pyinstaller` call from conda leaves them out and the exe fails with `DLL load failed while importing _tkinter`.

## Customizing

- Intervals: `WORK_MINUTES` and `BREAK_MINUTES` at the top of `pomodoro.py`
- Icon: edit and run `python make_icon.py` to regenerate `assets/icon.ico` and `assets/icon.png`
