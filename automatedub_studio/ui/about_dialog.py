"""About dialog for AutomateDub Studio."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

APP_NAME = "AutomateDub Studio"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "AI-assisted dubbing editor for AutomateDub."


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About AutomateDub Studio")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{APP_NAME}</b>"))
        layout.addWidget(QLabel(f"Version: {APP_VERSION}"))
        layout.addWidget(QLabel(APP_DESCRIPTION))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
