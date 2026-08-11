"""About dialog for AutomateDub Studio."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from automatedub_studio.metadata import (
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_GITHUB_URL,
    APP_LICENSE,
    APP_NAME,
    APP_REPORT_BUG_URL,
    APP_VERSION,
    APP_WEBSITE_URL,
)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About AutomateDub Studio")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{APP_NAME}</b>"))
        layout.addWidget(QLabel(f"Version: {APP_VERSION}"))
        layout.addWidget(QLabel(APP_DESCRIPTION))
        layout.addWidget(QLabel(f"Author: {APP_AUTHOR}"))
        layout.addWidget(QLabel(f"License: {APP_LICENSE}"))

        links = QHBoxLayout()
        github = QPushButton("GitHub")
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_GITHUB_URL)))
        links.addWidget(github)
        website = QPushButton("Website")
        website.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_WEBSITE_URL)))
        links.addWidget(website)
        report_bug = QPushButton("Report Bug")
        report_bug.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_REPORT_BUG_URL)))
        links.addWidget(report_bug)
        layout.addLayout(links)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
