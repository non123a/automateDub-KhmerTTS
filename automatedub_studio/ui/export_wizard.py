"""Export wizard for configuring render output."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from automatedub_studio.export.manager import (
    AudioMode,
    ExportConfiguration,
    SubtitleMode,
)


class ExportWizard(QDialog):
    def __init__(
        self,
        default_output_folder: Path,
        default_filename: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Video")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.output_folder_edit = QLineEdit(str(default_output_folder))
        self.output_folder_edit.setObjectName("export_output_folder_edit")
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.output_folder_edit)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_output_folder)
        folder_row.addWidget(browse)
        form.addRow("Output Folder", folder_row)

        self.filename_edit = QLineEdit(default_filename)
        self.filename_edit.setObjectName("export_filename_edit")
        form.addRow("Filename", self.filename_edit)

        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("export_quality_combo")
        self.quality_combo.addItems(["High", "Medium", "Draft"])
        form.addRow("Video Quality", self.quality_combo)

        self.codec_combo = QComboBox()
        self.codec_combo.setObjectName("export_codec_combo")
        self.codec_combo.addItem("H.264", "h264")
        form.addRow("Codec", self.codec_combo)

        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.setObjectName("export_audio_mode_combo")
        self.audio_mode_combo.addItem("Khmer only", AudioMode.KHMER_ONLY.value)
        self.audio_mode_combo.addItem("Original only", AudioMode.ORIGINAL_ONLY.value)
        self.audio_mode_combo.addItem("Mixed", AudioMode.MIXED.value)
        self.audio_mode_combo.setCurrentIndex(2)
        form.addRow("Audio Mode", self.audio_mode_combo)

        self.subtitle_mode_combo = QComboBox()
        self.subtitle_mode_combo.setObjectName("export_subtitle_mode_combo")
        self.subtitle_mode_combo.addItem("None", SubtitleMode.NONE.value)
        self.subtitle_mode_combo.addItem("Burned-in", SubtitleMode.BURNED_IN.value)
        self.subtitle_mode_combo.addItem("External SRT", SubtitleMode.EXTERNAL_SRT.value)
        form.addRow("Subtitle Mode", self.subtitle_mode_combo)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def configuration(self) -> ExportConfiguration:
        return ExportConfiguration(
            output_folder=Path(self.output_folder_edit.text()).expanduser(),
            filename=self.filename_edit.text().strip(),
            video_quality=self.quality_combo.currentText(),
            codec=str(self.codec_combo.currentData()),
            audio_mode=AudioMode(str(self.audio_mode_combo.currentData())),
            subtitle_mode=SubtitleMode(str(self.subtitle_mode_combo.currentData())),
        )

    def _browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Export Folder")
        if folder:
            self.output_folder_edit.setText(folder)
