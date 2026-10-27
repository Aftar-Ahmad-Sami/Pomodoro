"""Windows integration. Every call is a no-op on other platforms or older Windows versions."""

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pomodoro.config import APP_ID, APP_NAME, ICON_ICO, ICON_PNG
from pomodoro.theme import RGB

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35
_PROCESS_SYSTEM_DPI_AWARE = 1

# COM interfaces and classes, see the Windows SDK headers (shobjidl_core.h, propsys.h, objidl.h)
_CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
_IID_IPROPERTYSTORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 2

# Method positions in each interface's vtable
_VTBL_QUERY_INTERFACE = 0
_VTBL_RELEASE = 2
_VTBL_SHELL_LINK_SET_DESCRIPTION = 7
_VTBL_SHELL_LINK_SET_WORKING_DIRECTORY = 9
_VTBL_SHELL_LINK_SET_ARGUMENTS = 11
_VTBL_SHELL_LINK_SET_ICON_LOCATION = 17
_VTBL_SHELL_LINK_SET_PATH = 20
_VTBL_PROPERTY_STORE_SET_VALUE = 6
_VTBL_PROPERTY_STORE_COMMIT = 7
_VTBL_PERSIST_FILE_SAVE = 6

# System.AppUserModel.* property keys
_FMTID_APPUSERMODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
_PID_RELAUNCH_COMMAND = 2
_PID_RELAUNCH_ICON_RESOURCE = 3
_PID_RELAUNCH_DISPLAY_NAME_RESOURCE = 4
_PID_ID = 5
_VT_LPWSTR = 31

# Shell folders (CSIDL values), resolved through the API so redirected folders such as a OneDrive Desktop work
CSIDL_PROGRAMS = 0x02
CSIDL_DESKTOPDIRECTORY = 0x10
CSIDL_LOCAL_APPDATA = 0x1C
_MAX_PATH = 260


class _GUID(ctypes.Structure):
    _fields_ = (
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = (("fmtid", _GUID), ("pid", ctypes.c_uint32))


class _PROPVARIANT(ctypes.Structure):
    # Only the VT_LPWSTR case is needed; the padding keeps the full 24-byte layout
    _fields_ = (
        ("vt", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16 * 3),
        ("value", ctypes.c_wchar_p),
        ("padding", ctypes.c_void_p),
    )


# ---------- COM helpers ----------


def _method(obj: ctypes.c_void_p, index: int, restype: Any, *argtypes: Any) -> Any:
    """Returns a callable for the method at ``index`` in a COM object's vtable."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])


def _release(obj: ctypes.c_void_p) -> None:
    if obj:
        _method(obj, _VTBL_RELEASE, ctypes.c_ulong)(obj)


def _query_interface(obj: ctypes.c_void_p, iid: str) -> ctypes.c_void_p:
    out = ctypes.c_void_p()
    query = _method(obj, _VTBL_QUERY_INTERFACE, ctypes.HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    query(obj, ctypes.byref(_GUID.parse(iid)), ctypes.byref(out))
    return out


def _set_app_user_model_properties(store: ctypes.c_void_p, values: Iterable[tuple[int, str]]) -> None:
    """Writes string System.AppUserModel.* properties to an IPropertyStore."""
    set_value = _method(
        store,
        _VTBL_PROPERTY_STORE_SET_VALUE,
        ctypes.HRESULT,
        ctypes.POINTER(_PROPERTYKEY),
        ctypes.POINTER(_PROPVARIANT),
    )
    fmtid = _GUID.parse(_FMTID_APPUSERMODEL)
    for pid, value in values:
        set_value(store, ctypes.byref(_PROPERTYKEY(fmtid, pid)), ctypes.byref(_PROPVARIANT(vt=_VT_LPWSTR, value=value)))


# ---------- Process and window ----------


def enable_dpi_awareness() -> None:
    """Renders sharply on high-DPI screens. Must run before the first window is created."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(_PROCESS_SYSTEM_DPI_AWARE)
    except (AttributeError, OSError):
        log.debug("DPI awareness unavailable", exc_info=True)


def init_process() -> None:
    """Enables high-DPI rendering and gives the app its own taskbar identity.

    Must run before the first window is created.
    """
    enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        log.debug("AppUserModelID unavailable", exc_info=True)


def relaunch_command() -> str:
    """Command line that starts this app again, whether frozen or run from source."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")  # avoids a console window
    return subprocess.list2cmdline([str(pythonw if pythonw.exists() else python), "-m", "pomodoro"])


def _relaunch_icon() -> str:
    # A PyInstaller onefile build unpacks its assets to a temp folder, so point at the exe instead
    icon = sys.executable if getattr(sys, "frozen", False) else str(ICON_ICO)
    return f"{icon},0"


def set_relaunch_properties(window_id: int) -> None:
    """Lets a pinned taskbar button start the app again.

    The process uses an explicit AppUserModelID, so without these window properties
    Windows has no command to run when the pinned button is clicked after the app closes.
    Must be set before the window is first shown.
    """
    store = ctypes.c_void_p()
    try:
        hwnd = ctypes.windll.user32.GetParent(window_id)
        shell32 = ctypes.windll.shell32
        shell32.SHGetPropertyStoreForWindow.restype = ctypes.HRESULT  # raises OSError on failure
        iid = _GUID.parse(_IID_IPROPERTYSTORE)
        shell32.SHGetPropertyStoreForWindow(ctypes.c_void_p(hwnd), ctypes.byref(iid), ctypes.byref(store))
        # The ID goes first; the relaunch properties are only honored alongside it
        _set_app_user_model_properties(
            store,
            (
                (_PID_ID, APP_ID),
                (_PID_RELAUNCH_COMMAND, relaunch_command()),
                (_PID_RELAUNCH_DISPLAY_NAME_RESOURCE, APP_NAME),
                (_PID_RELAUNCH_ICON_RESOURCE, _relaunch_icon()),
            ),
        )
    except (AttributeError, OSError):
        log.warning("Could not set taskbar relaunch properties", exc_info=True)
    finally:
        _release(store)


def style_titlebar(window_id: int, caption: RGB) -> None:
    """Dark title bar in the given color (Windows 11)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window_id)
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), 4)
        r, g, b = caption
        color = ctypes.c_int(r | g << 8 | b << 16)  # COLORREF is 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(color), 4)
    except (AttributeError, OSError):
        log.debug("Title bar styling unavailable", exc_info=True)


def register_toast_identity() -> Path:
    """Registers the app's name and icon for toasts.

    Unpackaged apps need this per-user registry entry, otherwise Windows hides or
    mislabels their toasts. Returns a stable icon path for the toast image, since a
    PyInstaller build's own files live in a temp folder that is deleted on exit.
    """
    import winreg

    icon_dir = Path(os.environ["LOCALAPPDATA"]) / APP_NAME
    icon_dir.mkdir(parents=True, exist_ok=True)
    icon = icon_dir / "icon.png"
    shutil.copyfile(ICON_PNG, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))
    return icon


# ---------- Shell folders and shortcuts ----------


def shell_folder(csidl: int) -> Path:
    """Path of a per-user shell folder, e.g. ``CSIDL_DESKTOPDIRECTORY``."""
    buf = ctypes.create_unicode_buffer(_MAX_PATH)
    shell32 = ctypes.windll.shell32
    shell32.SHGetFolderPathW.restype = ctypes.HRESULT
    shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def create_shortcut(lnk: Path, target: Path, *, description: str = "", app_id: str = APP_ID) -> None:
    """Creates a .lnk shortcut tagged with the app's AppUserModelID.

    The ID makes the running window share a taskbar button with pins made from
    the shortcut. Raises OSError on failure.
    """
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.restype = ctypes.c_long  # S_FALSE (already initialized) is fine
    ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    ole32.CoCreateInstance.restype = ctypes.HRESULT

    link, store, persist = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(
            ctypes.byref(_GUID.parse(_CLSID_SHELL_LINK)),
            None,
            _CLSCTX_INPROC_SERVER,
            ctypes.byref(_GUID.parse(_IID_ISHELL_LINK_W)),
            ctypes.byref(link),
        )
        set_str = {
            index: _method(link, index, ctypes.HRESULT, ctypes.c_wchar_p)
            for index in (
                _VTBL_SHELL_LINK_SET_PATH,
                _VTBL_SHELL_LINK_SET_WORKING_DIRECTORY,
                _VTBL_SHELL_LINK_SET_DESCRIPTION,
                _VTBL_SHELL_LINK_SET_ARGUMENTS,
            )
        }
        set_str[_VTBL_SHELL_LINK_SET_PATH](link, str(target))
        set_str[_VTBL_SHELL_LINK_SET_WORKING_DIRECTORY](link, str(target.parent))
        set_str[_VTBL_SHELL_LINK_SET_DESCRIPTION](link, description)
        set_str[_VTBL_SHELL_LINK_SET_ARGUMENTS](link, "")
        set_icon = _method(link, _VTBL_SHELL_LINK_SET_ICON_LOCATION, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)
        set_icon(link, str(target), 0)

        store = _query_interface(link, _IID_IPROPERTYSTORE)
        _set_app_user_model_properties(store, ((_PID_ID, app_id),))
        _method(store, _VTBL_PROPERTY_STORE_COMMIT, ctypes.HRESULT)(store)

        persist = _query_interface(link, _IID_IPERSIST_FILE)
        lnk.parent.mkdir(parents=True, exist_ok=True)
        save = _method(persist, _VTBL_PERSIST_FILE_SAVE, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)
        save(persist, str(lnk), 1)
    finally:
        for obj in (persist, store, link):
            _release(obj)
