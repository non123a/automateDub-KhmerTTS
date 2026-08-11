"""Progress window for managed background exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.export.manager import (
    ExportEvent,
    ExportManager,
    ManagedExportResult,
)


class ExportProgressWindow(QWidget):
    def __init__(self, export_manager: ExportManager, parent=None):
        super().__init__(parent)
        self.export_manager = export_manager
        self.output_path: Path | None = None
        self.setWindowTitle("Export Progress")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Waiting to start...")
        self.status_label.setObjectName("managed_export_status_label")
        layout.addWidget(self.status_label)
        self.telemetry_label = QLabel("")
        self.telemetry_label.setObjectName("managed_export_telemetry_label")
        self.telemetry_label.setWordWrap(True)
        layout.addWidget(self.telemetry_label)
        self.progress = QProgressBar()
        self.progress.setObjectName("managed_export_progress")
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.error_label = QLabel("")
        self.error_label.setObjectName("managed_export_error_label")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        self.details_group = QGroupBox("Details")
        self.details_group.setCheckable(True)
        self.details_group.setChecked(False)
        details_layout = QFormLayout(self.details_group)
        self.details_settings_label = QLabel(self._settings_text())
        self.details_command_label = QLabel("")
        self.details_encoder_label = QLabel("")
        self.details_codec_label = QLabel("")
        self.details_command_label.setWordWrap(True)
        self.details_output_label = QLabel("")
        self.details_stage_label = QLabel("Waiting to start")
        self.details_log_label = QLabel("")
        self.details_log_label.setWordWrap(True)
        for label in (
            self.details_settings_label,
            self.details_command_label,
            self.details_encoder_label,
            self.details_codec_label,
            self.details_output_label,
            self.details_stage_label,
            self.details_log_label,
        ):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addRow("Selected settings", self.details_settings_label)
        details_layout.addRow("FFmpeg command", self.details_command_label)
        details_layout.addRow("Current encoder", self.details_encoder_label)
        details_layout.addRow("Current codec", self.details_codec_label)
        details_layout.addRow("Output", self.details_output_label)
        details_layout.addRow("Stage", self.details_stage_label)
        details_layout.addRow("Recent FFmpeg log", self.details_log_label)
        layout.addWidget(self.details_group)

        button_row = QHBoxLayout()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.export_manager.retry)
        button_row.addWidget(self.retry_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.export_manager.cancel)
        button_row.addWidget(self.cancel_button)
        self.open_file_button = QPushButton("Open Video")
        self.open_file_button.setEnabled(False)
        self.open_file_button.clicked.connect(self._open_file)
        button_row.addWidget(self.open_file_button)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self._open_folder)
        button_row.addWidget(self.open_folder_button)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self.export_manager.eventEmitted.connect(self._on_event)
        self.export_manager.exportCompleted.connect(self._on_completed)
        self.export_manager.exportFailed.connect(self._on_failed)
        self.export_manager.exportCancelled.connect(self._on_cancelled)

    def _on_event(self, event: ExportEvent) -> None:
        if event.status == "started":
            self.error_label.clear()
            self.retry_button.setEnabled(False)
            self.close_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
        if event.status == "failed":
            self.status_label.setText("Export Failed")
            self.error_label.setText(event.error or event.message)
        else:
            self.status_label.setText(f"{event.stage.value}: {event.message or event.status}")
        if event.frame is not None or event.fps is not None:
            self.telemetry_label.setText(event.message)
        self.details_stage_label.setText(event.stage.value)
        self.details_log_label.setText(event.message or event.error)
        if event.command:
            self.details_command_label.setText(" ".join(event.command))
            if "-c:v" in event.command:
                encoder_index = event.command.index("-c:v") + 1
                if encoder_index < len(event.command):
                    encoder = event.command[encoder_index]
                    self.details_encoder_label.setText(encoder)
                    self.details_codec_label.setText(
                        {
                            "copy": "Original",
                            "libx264": "H.264",
                            "h264_videotoolbox": "H.264",
                            "libx265": "H.265",
                            "hevc_videotoolbox": "H.265",
                        }.get(encoder, encoder)
                    )
        if event.output_size_bytes is not None:
            self.details_output_label.setText(
                f"{self.output_path or self.export_manager.configuration.output_path} "
                f"({_format_bytes(event.output_size_bytes)})"
            )
        stage_index = self.export_manager.stages.index(event.stage)
        stage_progress = stage_index * 100 + event.progress
        self.progress.setValue(round(stage_progress / len(self.export_manager.stages)))

    def _on_completed(self, result: ManagedExportResult) -> None:
        self.output_path = result.output_path
        self.status_label.setText("Export Complete")
        self.telemetry_label.setText("Output verified and ready.")
        self.progress.setValue(100)
        self.retry_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.open_file_button.setEnabled(True)
        self.open_folder_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def _on_failed(self, event: ExportEvent) -> None:
        self.status_label.setText("Export Failed")
        self.error_label.setText(event.error or event.message)
        self.telemetry_label.clear()
        self.retry_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def _on_cancelled(self) -> None:
        self.status_label.setText("Export cancelled")
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def _settings_text(self) -> str:
        config = self.export_manager.configuration
        return (
            f"{config.video_preset.value}; {config.video_quality}; "
            f"{config.audio_mode.value}; {config.subtitle_mode.value}"
        )

    def _open_folder(self) -> None:
        if self.output_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))

    def _open_file(self) -> None:
        if self.output_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path)))

    def closeEvent(self, event) -> None:
        if self.export_manager.is_running:
            event.ignore()
            return
        event.accept()


def _format_bytes(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MB" if value >= 1024 * 1024 else f"{value / 1024:.0f} KB"
