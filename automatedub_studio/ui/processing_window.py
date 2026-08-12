"""Processing progress window for newly created projects."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.pipeline.jobs import STAGE_TTS_GENERATION
from automatedub_studio.pipeline.manager import PipelineEvent, PipelineManager, PipelineResult
from automatedub_studio.ui.responsive import scrollable_content, set_responsive_window_size


class ProcessingWindow(QMainWindow):
    """Displays pipeline progress by observing PipelineManager events."""

    openEditorRequested = Signal(object)

    def __init__(self, pipeline_manager: PipelineManager, parent=None):
        super().__init__(parent)
        self.pipeline_manager = pipeline_manager
        self.project_path: Path | None = None
        self.stage_labels: dict[str, QLabel] = {}
        self.stage_status: dict[str, str] = {}

        self.setWindowTitle("Processing Project")
        central = QWidget(self)
        layout = QVBoxLayout(central)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        title = QLabel("Processing Project")
        title.setObjectName("processing_title")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(title)

        self.status_label = QLabel("Waiting to start...")
        self.status_label.setObjectName("processing_status")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("processing_progress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        content_layout.addWidget(self.progress)

        self.stage_container = QWidget()
        self.stage_layout = QVBoxLayout(self.stage_container)
        content_layout.addWidget(self.stage_container)

        self.error_label = QLabel("")
        self.error_label.setObjectName("processing_error")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(self.error_label)
        content_layout.addStretch(1)
        self.content_scroll = scrollable_content(content)
        self.content_scroll.setObjectName("processing_content_scroll")
        layout.addWidget(self.content_scroll, 1)

        button_row = QWidget()
        button_layout = QGridLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("processing_retry_button")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.pipeline_manager.retry)
        button_layout.addWidget(self.retry_button, 0, 0)

        self.skip_tts_button = QPushButton("Skip TTS & Open Editor")
        self.skip_tts_button.setObjectName("processing_skip_tts_button")
        self.skip_tts_button.setEnabled(False)
        self.skip_tts_button.clicked.connect(
            self.pipeline_manager.skip_tts_and_open_editor
        )
        button_layout.addWidget(self.skip_tts_button, 0, 1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("processing_cancel_button")
        self.cancel_button.clicked.connect(self.pipeline_manager.cancel)
        button_layout.addWidget(self.cancel_button, 1, 0)

        self.open_editor_button = QPushButton("Open Editor")
        self.open_editor_button.setObjectName("processing_open_editor_button")
        self.open_editor_button.setEnabled(False)
        self.open_editor_button.clicked.connect(self._open_editor)
        button_layout.addWidget(self.open_editor_button, 1, 1)

        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("processing_close_button")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button, 1, 2)

        layout.addWidget(button_row)

        self.setCentralWidget(central)
        set_responsive_window_size(
            self,
            minimum=QSize(480, 360),
            preferred=QSize(700, 620),
        )
        self._initialize_stages()
        self._connect_manager()

    def _initialize_stages(self) -> None:
        while self.stage_labels:
            _stage_id, label = self.stage_labels.popitem()
            self.stage_layout.removeWidget(label)
            label.deleteLater()

        self.stage_status.clear()
        for stage in self.pipeline_manager.stages:
            self.stage_status[stage.id] = "pending"
            label = QLabel(self._format_stage(stage.label, "pending", 0))
            label.setObjectName(f"processing_stage_{stage.id}")
            self.stage_layout.addWidget(label)
            self.stage_labels[stage.id] = label

    def _connect_manager(self) -> None:
        self.pipeline_manager.eventEmitted.connect(self._on_pipeline_event)
        self.pipeline_manager.pipelineCompleted.connect(self._on_pipeline_completed)
        self.pipeline_manager.pipelineFailed.connect(self._on_pipeline_failed)
        self.pipeline_manager.pipelineCancelled.connect(self._on_pipeline_cancelled)

    def _on_pipeline_event(self, event: PipelineEvent) -> None:
        self.stage_status[event.stage_id] = event.status
        label = self.stage_labels.get(event.stage_id)
        if label is not None:
            label.setText(
                self._format_stage(
                    event.label,
                    event.status,
                    event.progress,
                    event.message,
                )
            )
        if event.status in {"started", "progress"}:
            self.status_label.setText(event.message or event.label)
            self.progress.setValue(event.progress)
        elif event.status == "completed":
            self.status_label.setText(f"{event.label} completed")
            self.progress.setValue(100)
        elif event.status == "warning":
            self.status_label.setText(event.message or event.label)
            self.progress.setValue(100)
        elif event.status == "failed":
            self.status_label.setText(f"{event.label} failed")
            self.error_label.setText(event.error or event.message)

    def _on_pipeline_completed(self, result: PipelineResult) -> None:
        self.project_path = result.project.project_path
        self.status_label.setText("Project Ready")
        self.progress.setValue(100)
        self.retry_button.setEnabled(False)
        self.skip_tts_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.open_editor_button.setEnabled(result.skipped_tts)
        self.close_button.setEnabled(True)
        if not result.skipped_tts:
            self._open_editor()
            self.close()

    def _on_pipeline_failed(self, event: PipelineEvent) -> None:
        self.status_label.setText(f"{event.label} failed")
        self.error_label.setText(event.error or event.message)
        self.retry_button.setEnabled(True)
        self.skip_tts_button.setEnabled(event.stage_id == STAGE_TTS_GENERATION)
        self.cancel_button.setEnabled(True)
        self.open_editor_button.setEnabled(False)
        self.close_button.setEnabled(False)

    def _on_pipeline_cancelled(self) -> None:
        self.status_label.setText("Cancelled")
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def _open_editor(self) -> None:
        if self.project_path is not None:
            self.openEditorRequested.emit(self.project_path)

    @staticmethod
    def _format_stage(label: str, status: str, progress: int, message: str = "") -> str:
        icon = {
            "complete": "✓",
            "completed": "✓",
            "started": "⏳",
            "progress": "⏳",
            "pending": "",
            "failed": "✗",
            "warning": "⚠",
        }.get(status, "")
        suffix = f" {progress}%" if status == "progress" else ""
        if status == "warning" and message:
            suffix = f" — {message}"
        return f"{icon} {label}{suffix}".strip()
