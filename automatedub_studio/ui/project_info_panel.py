"""Read-only project information panel."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from automatedub_studio.project.models import Project

_PLACEHOLDER = "—"


class ProjectInfoPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.project_path_label = QLabel(_PLACEHOLDER)
        self.audio_label = QLabel(_PLACEHOLDER)
        self.translation_label = QLabel(_PLACEHOLDER)
        self.tts_directory_label = QLabel(_PLACEHOLDER)
        self.segment_count_label = QLabel(_PLACEHOLDER)
        self.tts_count_label = QLabel(_PLACEHOLDER)
        self.video_label = QLabel(_PLACEHOLDER)

        for label in (
            self.project_path_label,
            self.audio_label,
            self.translation_label,
            self.tts_directory_label,
            self.video_label,
        ):
            label.setWordWrap(True)

        layout = QFormLayout(self)
        layout.addRow("Project Path", self.project_path_label)
        layout.addRow("Audio", self.audio_label)
        layout.addRow("Translation", self.translation_label)
        layout.addRow("TTS Directory", self.tts_directory_label)
        layout.addRow("Segment Count", self.segment_count_label)
        layout.addRow("TTS Count", self.tts_count_label)
        layout.addRow("Video", self.video_label)

    def set_project(self, project: Project | None) -> None:
        if project is None:
            for label in (
                self.project_path_label,
                self.audio_label,
                self.translation_label,
                self.tts_directory_label,
                self.segment_count_label,
                self.tts_count_label,
                self.video_label,
            ):
                label.setText(_PLACEHOLDER)
            return

        self.project_path_label.setText(str(project.project_path))
        self.audio_label.setText(str(project.audio_path))
        self.translation_label.setText(str(project.translation_path))
        self.tts_directory_label.setText(str(project.tts_directory))
        self.segment_count_label.setText(str(project.segment_count))
        self.tts_count_label.setText(str(project.tts_file_count))
        self.video_label.setText(str(project.video_path) if project.has_video else "Missing")
