"""Home window for AutomateDub Studio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.pipeline.manager import PipelineManager
from automatedub_studio.project.manager import ProjectManager
from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.settings.manager import SettingsManager
from automatedub_studio.ui.about_dialog import AboutDialog
from automatedub_studio.ui.new_project_wizard import NewProjectWizard
from automatedub_studio.ui.processing_window import ProcessingWindow
from automatedub_studio.ui.settings_window import SettingsWindow


class HomeWindow(QMainWindow):
    """Application entry window for Studio workflows."""

    openProjectRequested = Signal(object)

    def __init__(
        self,
        project_manager: ProjectManager | None = None,
        settings_manager: SettingsManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_manager = project_manager if project_manager is not None else ProjectManager()
        self.settings_manager = (
            settings_manager if settings_manager is not None else SettingsManager()
        )
        self.processing_windows: list[ProcessingWindow] = []
        self.pipeline_managers: list[PipelineManager] = []
        self.settings_windows: list[SettingsWindow] = []

        self.setWindowTitle("AutomateDub Studio")
        central = QWidget(self)
        layout = QVBoxLayout(central)

        title = QLabel("<b>AutomateDub Studio</b>")
        title.setObjectName("home_title")
        layout.addWidget(title)

        self.new_project_button = QPushButton("New Project")
        self.new_project_button.setObjectName("new_project_button")
        self.new_project_button.clicked.connect(self._new_project)
        layout.addWidget(self.new_project_button)

        self.open_project_button = QPushButton("Open Project")
        self.open_project_button.setObjectName("open_project_button")
        self.open_project_button.clicked.connect(self._open_project)
        layout.addWidget(self.open_project_button)

        self.recent_projects_label = QLabel("Recent Projects\nNo recent projects yet.")
        self.recent_projects_label.setObjectName("recent_projects_placeholder")
        layout.addWidget(self.recent_projects_label)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("settings_button")
        self.settings_button.clicked.connect(self._show_settings)
        layout.addWidget(self.settings_button)

        self.about_button = QPushButton("About")
        self.about_button.setObjectName("about_button")
        self.about_button.clicked.connect(self._show_about)
        layout.addWidget(self.about_button)
        layout.addStretch(1)

        self.setCentralWidget(central)

    def _new_project(self) -> None:
        wizard = NewProjectWizard(self)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return

        pipeline_manager = PipelineManager(
            wizard.request(),
            project_manager=self.project_manager,
            provider_manager=ProviderManager(self.settings_manager.tool_config()),
            tool_config=self.settings_manager.tool_config(),
        )
        processing_window = ProcessingWindow(pipeline_manager)
        processing_window.openEditorRequested.connect(self.openProjectRequested.emit)
        self.pipeline_managers.append(pipeline_manager)
        self.processing_windows.append(processing_window)
        processing_window.show()
        pipeline_manager.start()

    def _open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Project")
        if directory:
            self.openProjectRequested.emit(Path(directory))

    def _show_settings(self) -> None:
        window = SettingsWindow(self.settings_manager, parent=self)
        self.settings_windows.append(window)
        window.show()

    def _show_about(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()
