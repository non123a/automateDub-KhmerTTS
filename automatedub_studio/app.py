"""QApplication construction for AutomateDub Studio."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from automatedub_studio.project.manager import ProjectManager
from automatedub_studio.ui.home_window import HomeWindow

ORGANIZATION_NAME = "AutomateDub"
APPLICATION_NAME = "AutomateDub Studio"


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    return app


def create_initial_window(project_manager: ProjectManager | None = None) -> HomeWindow:
    """Create the first Studio window shown at application startup."""
    return HomeWindow(project_manager=project_manager)
