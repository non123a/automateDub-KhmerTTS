"""Segment Inspector: read-only panel showing details for the selected segment."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.project.models import Segment

_PLACEHOLDER = "—"
_STATUS_DEFAULT = "Generated"
_NO_SELECTION_TEXT = "No segment selected."


class SegmentInspectorWidget(QWidget):
    """Inspector panel for the currently selected segment.

    Displays segment ID, status, texts, timing, and placeholder values for
    offset/speed/volume/voice. Three disabled buttons (Play Original, Play
    Khmer, Compare) are shown but not yet functional.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._stack = QStackedWidget()

        self._empty_label = QLabel(_NO_SELECTION_TEXT)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)

        self._detail_widget = self._build_detail_widget()

        self._stack.addWidget(self._empty_label)
        self._stack.addWidget(self._detail_widget)
        self._stack.setCurrentWidget(self._empty_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    def _build_detail_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._id_label = QLabel()
        self._status_label = QLabel()
        self._original_text_label = QLabel()
        self._original_text_label.setWordWrap(True)
        self._khmer_text_label = QLabel()
        self._khmer_text_label.setWordWrap(True)
        self._start_label = QLabel()
        self._end_label = QLabel()
        self._duration_label = QLabel()
        self._offset_label = QLabel()
        self._speed_label = QLabel()
        self._volume_label = QLabel()
        self._voice_label = QLabel()

        form = QFormLayout()
        form.addRow("Segment:", self._id_label)
        form.addRow("Status:", self._status_label)
        form.addRow("Original Text:", self._original_text_label)
        form.addRow("Khmer Text:", self._khmer_text_label)
        form.addRow("Start:", self._start_label)
        form.addRow("End:", self._end_label)
        form.addRow("Duration:", self._duration_label)
        form.addRow("Offset:", self._offset_label)
        form.addRow("Speed:", self._speed_label)
        form.addRow("Volume:", self._volume_label)
        form.addRow("Voice:", self._voice_label)

        layout.addLayout(form)
        layout.addStretch()

        button_group = QGroupBox("Playback")
        button_layout = QHBoxLayout(button_group)

        self._play_original_button = QPushButton("Play Original")
        self._play_original_button.setEnabled(False)
        self._play_khmer_button = QPushButton("Play Khmer")
        self._play_khmer_button.setEnabled(False)
        self._compare_button = QPushButton("Compare")
        self._compare_button.setEnabled(False)

        button_layout.addWidget(self._play_original_button)
        button_layout.addWidget(self._play_khmer_button)
        button_layout.addWidget(self._compare_button)

        layout.addWidget(button_group)

        return widget

    def set_segment(self, segment: Segment | None) -> None:
        """Update the inspector to show the given segment (or clear if None)."""
        if segment is None:
            self._stack.setCurrentWidget(self._empty_label)
            return

        self._id_label.setText(str(segment.id))
        self._status_label.setText(_STATUS_DEFAULT)
        self._original_text_label.setText(segment.source_text or _PLACEHOLDER)
        self._khmer_text_label.setText(segment.target_text)
        self._start_label.setText(f"{segment.start:.3f} s")
        self._end_label.setText(f"{segment.end:.3f} s")
        duration = segment.end - segment.start
        self._duration_label.setText(f"{duration:.3f} s")
        self._offset_label.setText("0 ms")
        self._speed_label.setText("1.00")
        self._volume_label.setText("100%")
        self._voice_label.setText("Default Voice")

        self._stack.setCurrentWidget(self._detail_widget)
