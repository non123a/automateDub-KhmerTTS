"""Project browser window for project management actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from automatedub_studio.project.browser import ProjectBrowser


class ProjectBrowserWindow(QMainWindow):
    def __init__(
        self,
        project_path: Path,
        browser: ProjectBrowser | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.browser = browser if browser is not None else ProjectBrowser()
        self.setWindowTitle("Project Browser")

        central = QWidget(self)
        layout = QVBoxLayout(central)
        self.details_label = QLabel()
        self.details_label.setObjectName("project_browser_details")
        layout.addWidget(self.details_label)
        self.rename_button = QPushButton("Rename")
        self.duplicate_button = QPushButton("Duplicate")
        self.archive_button = QPushButton("Archive")
        self.delete_button = QPushButton("Delete")
        for button in (
            self.rename_button,
            self.duplicate_button,
            self.archive_button,
            self.delete_button,
        ):
            layout.addWidget(button)
        self.setCentralWidget(central)
        self.refresh()

    def refresh(self) -> None:
        details = self.browser.details(self.project_path)
        self.details_label.setText(
            "\n".join(
                (
                    f"Name: {details.name}",
                    f"Created: {details.created_at}",
                    f"Modified: {details.last_modified}",
                    f"Status: {details.status}",
                    f"Exports: {len(details.export_history)}",
                )
            )
        )
