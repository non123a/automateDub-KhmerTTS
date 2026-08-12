"""New Project wizard for AutomateDub Studio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from automatedub_studio.project.manager import NewProjectRequest, project_folder_name
from automatedub_studio.ui.responsive import set_responsive_window_size


class ProjectDetailsPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("New Project")
        self.setSubTitle("Choose the project folder and source video.")

        layout = QFormLayout(self)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setObjectName("project_name_edit")
        self.project_name_edit.textChanged.connect(self._emit_complete_changed)
        layout.addRow("Project Name", self.project_name_edit)

        self.location_edit = QLineEdit()
        self.location_edit.setObjectName("project_location_edit")
        self.location_edit.textChanged.connect(self._emit_complete_changed)
        layout.addRow("Project Location", self._path_row(self.location_edit, self._browse_location))

        self.video_file_edit = QLineEdit()
        self.video_file_edit.setObjectName("video_file_edit")
        self.video_file_edit.textChanged.connect(self._emit_complete_changed)
        layout.addRow("Video File", self._path_row(self.video_file_edit, self._browse_video))

        self.source_language_combo = QComboBox()
        self.source_language_combo.setObjectName("source_language_combo")
        self.source_language_combo.addItems(["Chinese", "Khmer", "English", "Japanese", "Korean"])
        layout.addRow("Source Language", self.source_language_combo)

        self.target_language_combo = QComboBox()
        self.target_language_combo.setObjectName("target_language_combo")
        self.target_language_combo.addItems(["Khmer", "Chinese", "English", "Japanese", "Korean"])
        layout.addRow("Target Language", self.target_language_combo)

    def isComplete(self) -> bool:  # noqa: N802 - Qt override
        return all(
            (
                self.project_name_edit.text().strip(),
                self.location_edit.text().strip(),
                self.video_file_edit.text().strip(),
            )
        )

    def request(self) -> NewProjectRequest:
        return NewProjectRequest(
            project_name=self.project_name_edit.text().strip(),
            project_location=Path(self.location_edit.text()).expanduser(),
            video_file=Path(self.video_file_edit.text()).expanduser(),
            source_language=self.source_language_combo.currentText(),
            target_language=self.target_language_combo.currentText(),
        )

    def _path_row(self, edit: QLineEdit, slot) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        button = QPushButton("Browse...")
        button.clicked.connect(slot)
        layout.addWidget(button)
        return row

    def _browse_location(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Project Location")
        if directory:
            self.location_edit.setText(directory)

    def _browse_video(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Video File",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.webm *.avi);;All Files (*)",
        )
        if path:
            self.video_file_edit.setText(path)

    def _emit_complete_changed(self, _text: str) -> None:
        self.completeChanged.emit()


class ProjectSummaryPage(QWizardPage):
    def __init__(self, details_page: ProjectDetailsPage, parent=None):
        super().__init__(parent)
        self._details_page = details_page
        self.setTitle("Summary")
        self.setSubTitle("Review the new project before it is created.")

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("project_summary_label")
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary_label)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt override
        request = self._details_page.request()
        project_folder = request.project_location / project_folder_name(request.project_name)
        self.summary_label.setText(
            "\n".join(
                (
                    f"Project Name: {request.project_name}",
                    f"Project Folder: {project_folder}",
                    f"Video File: {request.video_file}",
                    f"Source Language: {request.source_language}",
                    f"Target Language: {request.target_language}",
                )
            )
        )


class NewProjectWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.details_page = ProjectDetailsPage(self)
        self.summary_page = ProjectSummaryPage(self.details_page, self)
        self.addPage(self.details_page)
        self.addPage(self.summary_page)
        set_responsive_window_size(
            self,
            minimum=QSize(500, 360),
            preferred=QSize(700, 520),
        )

    def request(self) -> NewProjectRequest:
        return self.details_page.request()
