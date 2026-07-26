"""QApplication construction for AutomateDub Studio."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

ORGANIZATION_NAME = "AutomateDub"
APPLICATION_NAME = "AutomateDub Studio"


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    return app
