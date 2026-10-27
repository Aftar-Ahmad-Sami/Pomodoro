"""Install and uninstall into a temporary folder. Registry entries are not touched."""

import sys
from pathlib import Path

import pytest

from pomodoro import installer
from pomodoro.installer import InstallError, Layout

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    return Layout(
        install_dir=tmp_path / "Programs" / "Pomodoro",
        desktop_shortcut=tmp_path / "Desktop" / "Pomodoro.lnk",
        start_menu_shortcut=tmp_path / "Start Menu" / "Pomodoro.lnk",
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def payload(tmp_path: Path) -> Path:
    exe = tmp_path / "build" / "Pomodoro.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ fake app")
    return exe


@pytest.fixture
def setup_exe(tmp_path: Path) -> Path:
    exe = tmp_path / "build" / "PomodoroSetup.exe"
    exe.parent.mkdir(exist_ok=True)
    exe.write_bytes(b"MZ fake installer")
    return exe


def test_install_copies_app_and_creates_shortcuts(layout: Layout, payload: Path, setup_exe: Path) -> None:
    installer.install(layout, payload, setup_exe, register=False)
    assert layout.app_exe.read_bytes() == payload.read_bytes()
    assert layout.uninstaller.read_bytes() == setup_exe.read_bytes()
    assert layout.start_menu_shortcut.is_file()
    assert layout.desktop_shortcut.is_file()


def test_shortcut_points_at_installed_app(layout: Layout, payload: Path) -> None:
    installer.install(layout, payload, None, register=False)
    # A .lnk stores its target as a UTF-16 string
    assert str(layout.app_exe).encode("utf-16-le") in layout.desktop_shortcut.read_bytes()


def test_install_without_desktop_shortcut_removes_old_one(layout: Layout, payload: Path) -> None:
    installer.install(layout, payload, None, register=False)
    installer.install(layout, payload, None, desktop_shortcut=False, register=False)
    assert not layout.desktop_shortcut.exists()
    assert layout.start_menu_shortcut.is_file()


def test_install_fails_clearly_when_payload_missing(layout: Layout, tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="incomplete"):
        installer.install(layout, tmp_path / "missing.exe", None, register=False)


def test_reinstall_upgrades_in_place(layout: Layout, payload: Path) -> None:
    installer.install(layout, payload, None, register=False)
    payload.write_bytes(b"MZ new version")
    installer.install(layout, payload, None, register=False)
    assert layout.app_exe.read_bytes() == b"MZ new version"


def test_uninstall_removes_everything(layout: Layout, payload: Path, setup_exe: Path) -> None:
    installer.install(layout, payload, setup_exe, register=False)
    layout.data_dir.mkdir()
    (layout.data_dir / "icon.png").write_bytes(b"png")

    installer.uninstall(layout, unregister=False)

    for path in (layout.install_dir, layout.desktop_shortcut, layout.start_menu_shortcut, layout.data_dir):
        assert not path.exists()


def test_uninstall_when_not_installed_is_harmless(layout: Layout) -> None:
    installer.uninstall(layout, unregister=False)
