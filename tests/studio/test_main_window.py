from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMenu

from automatedub_studio.ui.main_window import WINDOW_TITLE, MainWindow


def _memory_settings() -> QSettings:
    return QSettings("automatedub-test", "MainWindowTest")


def _menu_titles(window: MainWindow) -> list[str]:
    return [menu.title().replace("&", "") for menu in window.menuBar().findChildren(QMenu)]


def _action_texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_window_title(qapp):
    window = MainWindow(settings=_memory_settings())

    assert window.windowTitle() == WINDOW_TITLE == "AutomateDub Studio"


def test_menu_bar_has_file_and_help_menus(qapp):
    window = MainWindow(settings=_memory_settings())

    assert "File" in _menu_titles(window)
    assert "Help" in _menu_titles(window)


def test_file_menu_has_open_project_and_exit(qapp):
    window = MainWindow(settings=_memory_settings())
    file_menu = next(m for m in window.menuBar().findChildren(QMenu) if m.title() == "&File")

    assert _action_texts(file_menu) == ["Open Project...", "Exit"]
    assert window.open_project_action.isEnabled() is False


def test_help_menu_has_about(qapp):
    window = MainWindow(settings=_memory_settings())
    help_menu = next(m for m in window.menuBar().findChildren(QMenu) if m.title() == "&Help")

    assert _action_texts(help_menu) == ["About"]


def test_status_bar_shows_ready(qapp):
    window = MainWindow(settings=_memory_settings())

    assert window.statusBar().currentMessage() == "Ready"


def test_exit_action_closes_window(qapp):
    window = MainWindow(settings=_memory_settings())
    window.show()

    window.exit_action.trigger()

    assert window.isVisible() is False


def test_geometry_persists_across_instances(qapp, tmp_path):
    settings_path = tmp_path / "settings.ini"

    settings1 = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window1 = MainWindow(settings=settings1)
    window1.resize(800, 600)
    window1.close()
    settings1.sync()

    settings2 = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window2 = MainWindow(settings=settings2)

    assert abs(window2.size().width() - 800) <= 5
    assert abs(window2.size().height() - 600) <= 5
