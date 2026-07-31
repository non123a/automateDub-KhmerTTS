"""Progress window for managed background exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.export.manager import ExportEvent, ExportManager, ManagedExportResult


class ExportProgressWindow(QWidget):
    def __init__(self, export_manager: ExportManager, parent=None):
        super().__init__(parent)
        self.export_manager = export_manager
        self.output_path: Path | None = None
        self.setWindowTitle("Export Progress")

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Waiting to start...")
        self.status_label.setObjectName("managed_export_status_label")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setObjectName("managed_export_progress")
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.error_label = QLabel("")
        self.error_label.setObjectName("managed_export_error_label")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        self.retry_button = QPushButton("Retry")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.export_manager.retry)
        button_row.addWidget(self.retry_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.export_manager.cancel)
        button_row.addWidget(self.cancel_button)
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
        if event.status == "failed":
            self.status_label.setText(f"{event.stage.value} failed")
            self.error_label.setText(event.error or event.message)
        else:
            self.status_label.setText(f"{event.stage.value}: {event.message or event.status}")
        self.progress.setValue(event.progress)

    def _on_completed(self, result: ManagedExportResult) -> None:
        self.output_path = result.output_path
        self.status_label.setText("Export Complete")
        self.progress.setValue(100)
        self.cancel_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.open_folder_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def _on_failed(self, event: ExportEvent) -> None:
        self.status_label.setText(f"{event.stage.value} failed")
        self.error_label.setText(event.error or event.message)
        self.retry_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def _on_cancelled(self) -> None:
        self.status_label.setText("Export cancelled")
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def _open_folder(self) -> None:
        if self.output_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))
