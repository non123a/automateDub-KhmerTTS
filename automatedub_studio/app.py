"""QApplication construction for AutomateDub Studio."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QApplication

from automatedub_studio.project.manager import ProjectManager
from automatedub_studio.settings.manager import SettingsManager
from automatedub_studio.ui.home_window import HomeWindow

ORGANIZATION_NAME = "AutomateDub"
APPLICATION_NAME = "AutomateDub Studio"


class StudioApplication(QApplication):
    """QApplication with operating-system project-open event support."""

    fileOpenRequested = Signal(object)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            self.fileOpenRequested.emit(Path(event.file()))
            return True
        return super().event(event)


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = StudioApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    return app


def create_initial_window(
    project_manager: ProjectManager | None = None,
    settings_manager: SettingsManager | None = None,
) -> HomeWindow:
    """Create the first Studio window shown at application startup."""
    return HomeWindow(project_manager=project_manager, settings_manager=settings_manager)


def startup_paths(argv: list[str]) -> list[Path]:
    """Return local files passed by the operating system or command line."""
    return [Path(value) for value in argv[1:] if not value.startswith("-")]
