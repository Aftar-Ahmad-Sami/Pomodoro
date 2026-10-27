"""Per-user installer and uninstaller for the packaged app.

``scripts/build.ps1`` freezes this module into ``PomodoroSetup.exe`` with ``Pomodoro.exe``
embedded. Installing needs no admin rights: the app goes to
``%LOCALAPPDATA%\\Programs\\Pomodoro``, with Start Menu and Desktop shortcuts and an entry
under Settings > Apps. The setup exe copies itself there as ``Uninstall.exe``.

Usage::

    PomodoroSetup.exe [--silent] [--no-desktop-shortcut]
    Uninstall.exe --uninstall [--silent]
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from pomodoro import __version__, win32
from pomodoro.config import APP_ID, APP_NAME, ICON_ICO

log = logging.getLogger(__name__)

PUBLISHER = "Aftar Ahmad Sami"
EXE_NAME = f"{APP_NAME}.exe"
UNINSTALLER_NAME = "Uninstall.exe"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
TOAST_KEY = rf"Software\Classes\AppUserModelId\{APP_ID}"
DESCRIPTION = "52/17 focus timer"


class InstallError(Exception):
    """A failure the user can act on; the message is shown to them as is."""


@dataclass(frozen=True)
class Layout:
    """Where an installation puts its files."""

    install_dir: Path
    desktop_shortcut: Path
    start_menu_shortcut: Path
    data_dir: Path  # Written by the app at runtime (see win32.register_toast_identity)

    @property
    def app_exe(self) -> Path:
        return self.install_dir / EXE_NAME

    @property
    def uninstaller(self) -> Path:
        return self.install_dir / UNINSTALLER_NAME

    @classmethod
    def default(cls) -> Layout:
        local = win32.shell_folder(win32.CSIDL_LOCAL_APPDATA)
        shortcut = f"{APP_NAME}.lnk"
        return cls(
            install_dir=local / "Programs" / APP_NAME,
            desktop_shortcut=win32.shell_folder(win32.CSIDL_DESKTOPDIRECTORY) / shortcut,
            start_menu_shortcut=win32.shell_folder(win32.CSIDL_PROGRAMS) / shortcut,
            data_dir=local / APP_NAME,
        )


# ---------- Install ----------


def install(
    layout: Layout,
    app_exe: Path,
    uninstaller: Path | None,
    *,
    desktop_shortcut: bool = True,
    register: bool = True,
) -> None:
    """Copies the app into place and creates its shortcuts.

    ``uninstaller`` is copied next to the app; the uninstall entry in Settings is only
    registered when there is one. Installing over an existing copy upgrades it.
    """
    if not app_exe.is_file():
        raise InstallError(f"The installer is incomplete: {app_exe} is missing.")
    layout.install_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(app_exe, layout.app_exe)
        if uninstaller is not None and uninstaller.resolve() != layout.uninstaller.resolve():
            shutil.copy2(uninstaller, layout.uninstaller)
    except PermissionError as e:
        raise InstallError(f"{APP_NAME} is running. Close it and try again.") from e

    win32.create_shortcut(layout.start_menu_shortcut, layout.app_exe, description=DESCRIPTION)
    if desktop_shortcut:
        win32.create_shortcut(layout.desktop_shortcut, layout.app_exe, description=DESCRIPTION)
    else:
        layout.desktop_shortcut.unlink(missing_ok=True)

    if register and uninstaller is not None:
        _register_uninstall_entry(layout)


def _register_uninstall_entry(layout: Layout) -> None:
    import winreg

    size_kb = sum(f.stat().st_size for f in layout.install_dir.iterdir() if f.is_file()) // 1024
    uninstall = subprocess.list2cmdline([str(layout.uninstaller), "--uninstall"])
    strings = {
        "DisplayName": APP_NAME,
        "DisplayVersion": __version__,
        "Publisher": PUBLISHER,
        "DisplayIcon": f"{layout.app_exe},0",
        "InstallLocation": str(layout.install_dir),
        "UninstallString": uninstall,
        "QuietUninstallString": f"{uninstall} --silent",
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in strings.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, number in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, number)


# ---------- Uninstall ----------


def uninstall(layout: Layout, *, unregister: bool = True) -> None:
    """Removes the app, its shortcuts, its data and its registry entries."""
    try:
        layout.app_exe.unlink(missing_ok=True)
    except PermissionError as e:
        raise InstallError(f"{APP_NAME} is running. Close it and try again.") from e

    for lnk in (layout.desktop_shortcut, layout.start_menu_shortcut):
        lnk.unlink(missing_ok=True)
    shutil.rmtree(layout.data_dir, ignore_errors=True)
    if unregister:
        _delete_registry_keys()

    if _is_running_from(layout.install_dir):
        _remove_after_exit(layout.install_dir)  # A running exe cannot delete itself
    else:
        shutil.rmtree(layout.install_dir, ignore_errors=True)


def _delete_registry_keys() -> None:
    import winreg

    for key in (UNINSTALL_KEY, TOAST_KEY):
        with contextlib.suppress(FileNotFoundError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)


def _is_running_from(folder: Path) -> bool:
    return Path(sys.executable).resolve().parent == folder.resolve()


def _remove_after_exit(folder: Path) -> None:
    # Gives this process (and PyInstaller's bootloader, which holds the exe open) time to exit
    command = f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{folder}"'
    subprocess.Popen(command, cwd=tempfile.gettempdir(), creationflags=subprocess.CREATE_NO_WINDOW)


# ---------- Running the app ----------


def launch(app_exe: Path) -> None:
    env = os.environ.copy()
    # Starting one PyInstaller exe from another: make the child unpack its own files
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(app_exe)], cwd=app_exe.parent, env=env, creationflags=subprocess.DETACHED_PROCESS)


def bundled_app_exe() -> Path:
    """The app exe embedded in the frozen installer, or the local build when run from source."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "payload" / EXE_NAME
    return Path(__file__).resolve().parents[2] / "dist" / EXE_NAME


def self_exe() -> Path | None:
    """This installer's own exe, which doubles as the uninstaller. None when run from source."""
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


# ---------- UI ----------


class InstallerWindow:
    """A small native-looking dialog: install location, options, Install/Cancel."""

    def __init__(self, root: tk.Tk, layout: Layout) -> None:
        self.root = root
        self.layout = layout
        self.desktop = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)

        root.title(f"{APP_NAME} {__version__} Setup")
        root.resizable(False, False)
        try:
            root.iconbitmap(default=str(ICON_ICO))  # type: ignore[no-untyped-call]  # untyped in typeshed
        except tk.TclError:
            log.debug("Window icon unavailable", exc_info=True)

        frame = ttk.Frame(root, padding=(24, 20))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Install {APP_NAME}", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(frame, text="A desktop timer for 52 minutes of focus and 17 minute breaks.", foreground="#555").pack(
            anchor="w", pady=(2, 16)
        )

        ttk.Label(frame, text="Install location").pack(anchor="w")
        location = ttk.Entry(frame, width=60)
        location.insert(0, str(layout.install_dir))
        location.configure(state="readonly")
        location.pack(anchor="w", fill="x", pady=(2, 14))

        ttk.Checkbutton(frame, text="Create a desktop shortcut", variable=self.desktop).pack(anchor="w")
        ttk.Checkbutton(frame, text=f"Launch {APP_NAME} when setup finishes", variable=self.launch_after).pack(
            anchor="w", pady=(4, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(22, 0))
        self.install_button = ttk.Button(buttons, text="Install", command=self._install, default="active")
        self.install_button.pack(side="left")
        ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="left", padx=(8, 0))
        root.bind("<Return>", lambda e: self._install())
        root.bind("<Escape>", lambda e: root.destroy())

    def _install(self) -> None:
        self.install_button.configure(state="disabled")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            install(self.layout, bundled_app_exe(), self_exe(), desktop_shortcut=self.desktop.get())
        except (InstallError, OSError) as e:
            log.exception("Install failed")
            self.root.config(cursor="")
            self.install_button.configure(state="normal")
            messagebox.showerror(f"{APP_NAME} Setup", str(e), parent=self.root)
            return
        if self.launch_after.get():
            launch(self.layout.app_exe)
        else:
            messagebox.showinfo(
                f"{APP_NAME} Setup", f"{APP_NAME} is installed. Find it on the Start menu.", parent=self.root
            )
        self.root.destroy()


def _run_uninstall(layout: Layout, silent: bool) -> int:
    if silent:
        try:
            uninstall(layout)
        except (InstallError, OSError):
            log.exception("Uninstall failed")
            return 1
        return 0

    title = f"Uninstall {APP_NAME}"
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(title, f"Remove {APP_NAME} and its shortcuts from this PC?", parent=root):
        return 1
    try:
        uninstall(layout)
    except (InstallError, OSError) as e:
        log.exception("Uninstall failed")
        messagebox.showerror(title, str(e), parent=root)
        return 1
    messagebox.showinfo(title, f"{APP_NAME} was removed.", parent=root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="PomodoroSetup", description=f"Installs {APP_NAME} for the current user.")
    parser.add_argument("--uninstall", action="store_true", help="remove the installed app")
    parser.add_argument("--silent", action="store_true", help="run without any windows")
    parser.add_argument("--no-desktop-shortcut", action="store_true", help="skip the desktop shortcut")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    win32.enable_dpi_awareness()
    layout = Layout.default()

    if args.uninstall:
        return _run_uninstall(layout, args.silent)
    if args.silent:
        try:
            install(layout, bundled_app_exe(), self_exe(), desktop_shortcut=not args.no_desktop_shortcut)
        except (InstallError, OSError):
            log.exception("Install failed")
            return 1
        return 0

    root = tk.Tk()
    InstallerWindow(root, layout)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
