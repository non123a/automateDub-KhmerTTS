"""Export progress dialog for AutomateDub Studio."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from automatedub import process
from automatedub_studio.backend.export_service import ExportResult, ExportStage
from automatedub_studio.ui.responsive import scrollable_content, set_responsive_window_size

_STAGES = [
    ExportStage.PREPARING,
    ExportStage.MIXING_AUDIO,
    ExportStage.RENDERING_VIDEO,
    ExportStage.FINALIZING,
    ExportStage.COMPLETED,
]
_STAGE_INDEX = {s: i for i, s in enumerate(_STAGES)}


class ExportProgressDialog(QDialog):
    """Shows export progress with stage label, progress bar, elapsed time, and cancel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporting…")
        set_responsive_window_size(
            self,
            minimum=QSize(420, 220),
            preferred=QSize(520, 280),
        )
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._start_time: float = time.monotonic()
        self._output_path: Path | None = None
        self._finished = False

        layout = QVBoxLayout(self)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        self._stage_label = QLabel("Preparing…")
        self._stage_label.setWordWrap(True)
        self._stage_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout.addWidget(self._stage_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, len(_STAGES) - 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout.addWidget(self._progress_bar)

        time_row = QHBoxLayout()
        self._elapsed_label = QLabel("Elapsed: 0s")
        time_row.addWidget(self._elapsed_label)
        time_row.addStretch()
        content_layout.addLayout(time_row)
        content_layout.addStretch(1)
        self.content_scroll = scrollable_content(content)
        self.content_scroll.setObjectName("legacy_export_progress_content_scroll")
        layout.addWidget(self.content_scroll, 1)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)

        self._open_file_button = QPushButton("Open File")
        self._open_file_button.setVisible(False)
        self._open_file_button.clicked.connect(self._on_open_file)

        self._open_folder_button = QPushButton("Open Folder")
        self._open_folder_button.setVisible(False)
        self._open_folder_button.clicked.connect(self._on_open_folder)

        self._close_button = QPushButton("Close")
        self._close_button.setVisible(False)
        self._close_button.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._cancel_button)
        btn_row.addWidget(self._open_file_button)
        btn_row.addWidget(self._open_folder_button)
        btn_row.addWidget(self._close_button)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Emitted when user clicks Cancel
        self._cancelled = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    def on_stage_changed(self, stage_value: str) -> None:
        try:
            stage = ExportStage(stage_value)
        except ValueError:
            return
        index = _STAGE_INDEX.get(stage, 0)
        self._progress_bar.setValue(index)
        if stage == ExportStage.COMPLETED:
            self._stage_label.setText("Completed")
        else:
            self._stage_label.setText(f"{stage.value}…")

    def on_finished(self, result: ExportResult) -> None:
        self._output_path = result.output_path
        self._finished = True
        self._timer.stop()
        self.setWindowTitle("Export Complete")
        self._stage_label.setText("Export Complete")
        self._progress_bar.setValue(len(_STAGES) - 1)
        self._elapsed_label.setText(f"Elapsed: {self._elapsed_str()}")
        self._cancel_button.setVisible(False)
        self._open_file_button.setVisible(True)
        self._open_folder_button.setVisible(True)
        self._close_button.setVisible(True)

    def on_error(self, message: str) -> None:
        self._finished = True
        self._timer.stop()
        self.setWindowTitle("Export Failed")
        self._stage_label.setText(f"Error: {message}")
        self._cancel_button.setVisible(False)
        self._close_button.setVisible(True)

    def _tick(self) -> None:
        self._elapsed_label.setText(f"Elapsed: {self._elapsed_str()}")

    def _elapsed_str(self) -> str:
        elapsed = int(time.monotonic() - self._start_time)
        if elapsed < 60:
            return f"{elapsed}s"
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes}m {seconds}s"

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._cancel_button.setEnabled(False)
        self._stage_label.setText("Cancelling…")

    def _on_open_file(self) -> None:
        if self._output_path is not None:
            if sys.platform == "darwin":
                process.popen(["open", str(self._output_path)])
            elif sys.platform == "win32":
                process.popen(["explorer", str(self._output_path)])
            else:
                process.popen(["xdg-open", str(self._output_path)])

    def _on_open_folder(self) -> None:
        if self._output_path is not None:
            folder = str(self._output_path.parent)
            if sys.platform == "darwin":
                process.popen(["open", folder])
            elif sys.platform == "win32":
                process.popen(["explorer", folder])
            else:
                process.popen(["xdg-open", folder])

    def closeEvent(self, event):
        if not self._finished:
            event.ignore()
        else:
            super().closeEvent(event)
