"""Segment Inspector: property editor for the selected segment."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import TimelineClip

_PLACEHOLDER = "—"
_STATUS_GENERATED = "Generated"
_STATUS_EDITED = "Edited"
_STATUS_GENERATING = "Generating"
_STATUS_FAILED = "Failed"
_STATUS_NEEDS_REGENERATION = "Needs Regeneration"
_NO_SELECTION_TEXT = "No segment selected."


class SegmentInspectorWidget(QWidget):
    """Inspector panel that shows and edits properties of the selected segment."""

    speedChanged = Signal(float, float)    # (old, new)
    volumeChanged = Signal(float, float)   # (old, new)  value is 0.0–2.0
    fadeInChanged = Signal(int, int)       # (old_ms, new_ms)
    fadeOutChanged = Signal(int, int)      # (old_ms, new_ms)
    lockedChanged = Signal(bool, bool)     # (old, new)
    regenerateRequested = Signal(int)      # segment_id
    clipVolumeChanged = Signal(str, float, float)
    clipMutedChanged = Signal(str, bool, bool)
    clipFadeInChanged = Signal(str, int, int)
    clipFadeOutChanged = Signal(str, int, int)
    clipLockedChanged = Signal(str, bool, bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._segment: Segment | None = None
        self._editable: EditableSegment | None = None
        self._timeline_clip: TimelineClip | None = None
        self._live_offset_ms: int = 0
        self._is_generating: bool = False

        self._stack = QStackedWidget()
        self._empty_label = QLabel(_NO_SELECTION_TEXT)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)

        self._detail_widget = self._build_detail_widget()
        self._multi_widget = self._build_multi_widget()
        self._stack.addWidget(self._empty_label)
        self._stack.addWidget(self._detail_widget)
        self._stack.addWidget(self._multi_widget)
        self._stack.setCurrentWidget(self._empty_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

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

        # Speed
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.50, 2.00)
        self._speed_spin.setSingleStep(0.05)
        self._speed_spin.setDecimals(2)
        self._speed_spin.setValue(1.00)

        # Volume
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 200)
        self._volume_slider.setValue(100)
        self._volume_display = QLabel("100%")
        vol_row = QWidget()
        vol_row_layout = QHBoxLayout(vol_row)
        vol_row_layout.setContentsMargins(0, 0, 0, 0)
        vol_row_layout.addWidget(self._volume_slider)
        vol_row_layout.addWidget(self._volume_display)

        # Fade In / Fade Out
        self._fade_in_spin = QSpinBox()
        self._fade_in_spin.setRange(0, 5000)
        self._fade_in_spin.setSuffix(" ms")

        self._fade_out_spin = QSpinBox()
        self._fade_out_spin.setRange(0, 5000)
        self._fade_out_spin.setSuffix(" ms")

        # Locked
        self._locked_check = QCheckBox()

        form = QFormLayout()
        form.addRow("Segment:", self._id_label)
        form.addRow("Status:", self._status_label)
        form.addRow("Original:", self._original_text_label)
        form.addRow("Khmer:", self._khmer_text_label)
        form.addRow("Start:", self._start_label)
        form.addRow("End:", self._end_label)
        form.addRow("Duration:", self._duration_label)
        form.addRow("Offset:", self._offset_label)
        form.addRow("Speed:", self._speed_spin)
        form.addRow("Volume:", vol_row)
        self._muted_check = QCheckBox()
        form.addRow("Muted:", self._muted_check)
        form.addRow("Fade In:", self._fade_in_spin)
        form.addRow("Fade Out:", self._fade_out_spin)
        form.addRow("Locked:", self._locked_check)

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

        self._regenerate_button = QPushButton("Regenerate")
        self._regenerate_button.clicked.connect(self._on_regenerate_clicked)
        layout.addWidget(self._regenerate_button)

        self._connect_controls()
        return widget

    def _build_multi_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._multi_count_label = QLabel()
        self._multi_average_offset_label = QLabel()
        self._multi_speed_label = QLabel()
        self._multi_volume_label = QLabel()
        self._multi_fade_in_label = QLabel()
        self._multi_fade_out_label = QLabel()
        self._multi_locked_label = QLabel()

        form = QFormLayout()
        form.addRow("Selected:", self._multi_count_label)
        form.addRow("Average Offset:", self._multi_average_offset_label)
        form.addRow("Speed:", self._multi_speed_label)
        form.addRow("Volume:", self._multi_volume_label)
        form.addRow("Fade In:", self._multi_fade_in_label)
        form.addRow("Fade Out:", self._multi_fade_out_label)
        form.addRow("Locked:", self._multi_locked_label)
        layout.addLayout(form)
        layout.addStretch()
        return widget

    def _connect_controls(self) -> None:
        self._speed_spin.valueChanged.connect(self._on_speed_changed)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        self._muted_check.toggled.connect(self._on_muted_changed)
        self._fade_in_spin.valueChanged.connect(self._on_fade_in_changed)
        self._fade_out_spin.valueChanged.connect(self._on_fade_out_changed)
        self._locked_check.toggled.connect(self._on_locked_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_segment(
        self, segment: Segment | None, editable: EditableSegment | None = None
    ) -> None:
        self._timeline_clip = None
        if segment is None:
            self._segment = None
            self._editable = None
            self._stack.setCurrentWidget(self._empty_label)
            return

        self._segment = segment
        self._editable = editable
        self._is_generating = False
        self._regenerate_button.setEnabled(True)

        self._load_into_controls(segment, editable)
        self._stack.setCurrentWidget(self._detail_widget)

    def set_timeline_clip(self, clip: TimelineClip | None) -> None:
        if clip is None:
            self._segment = None
            self._editable = None
            self._timeline_clip = None
            self._stack.setCurrentWidget(self._empty_label)
            return
        self._segment = None
        self._editable = None
        self._timeline_clip = clip
        self._is_generating = False
        self._regenerate_button.setEnabled(clip.segment_id is not None)
        self._load_clip_into_controls(clip)
        self._stack.setCurrentWidget(self._detail_widget)

    def set_timeline_clips(self, clips: list[TimelineClip]) -> None:
        if not clips:
            self.set_timeline_clip(None)
            return
        if len(clips) == 1:
            self.set_timeline_clip(clips[0])
            return
        self._segment = None
        self._editable = None
        self._timeline_clip = None
        self._is_generating = False
        count = len(clips)
        average_offset = round(
            sum((clip.start_time - clip.source_offset) * 1000 for clip in clips) / count
        )
        self._multi_count_label.setText(f"{count} clips")
        self._multi_average_offset_label.setText(self._format_offset(average_offset))
        self._multi_speed_label.setText(_PLACEHOLDER)
        self._multi_volume_label.setText(
            self._format_common_percent([clip.volume for clip in clips])
        )
        self._multi_fade_in_label.setText(
            self._format_common_int([round(clip.fade_in * 1000) for clip in clips], suffix=" ms")
        )
        self._multi_fade_out_label.setText(
            self._format_common_int([round(clip.fade_out * 1000) for clip in clips], suffix=" ms")
        )
        self._multi_locked_label.setText(
            self._format_common_bool([clip.locked for clip in clips])
        )
        self._stack.setCurrentWidget(self._multi_widget)

    def set_segments(
        self,
        segments: list[Segment],
        editables: dict[int, EditableSegment] | None = None,
    ) -> None:
        """Show aggregate state for a multi-selection."""
        if not segments:
            self.set_segment(None)
            return
        if len(segments) == 1:
            editable = editables.get(segments[0].id) if editables else None
            self.set_segment(segments[0], editable)
            return

        self._segment = None
        self._editable = None
        self._is_generating = False
        editables = editables or {}
        count = len(segments)
        average_offset = round(sum(segment.offset_ms for segment in segments) / count)
        editable_values = [
            editables.get(segment.id, EditableSegment(segment.id)) for segment in segments
        ]

        self._multi_count_label.setText(f"{count} clips")
        self._multi_average_offset_label.setText(self._format_offset(average_offset))
        self._multi_speed_label.setText(
            self._format_common_float([editable.speed for editable in editable_values])
        )
        self._multi_volume_label.setText(
            self._format_common_percent([editable.volume for editable in editable_values])
        )
        self._multi_fade_in_label.setText(
            self._format_common_int(
                [editable.fade_in_ms for editable in editable_values],
                suffix=" ms",
            )
        )
        self._multi_fade_out_label.setText(
            self._format_common_int(
                [editable.fade_out_ms for editable in editable_values],
                suffix=" ms",
            )
        )
        self._multi_locked_label.setText(
            self._format_common_bool([editable.locked for editable in editable_values])
        )
        self._stack.setCurrentWidget(self._multi_widget)

    def refresh_offset(self, offset_ms: int) -> None:
        if self._stack.currentWidget() != self._detail_widget:
            return
        self._live_offset_ms = offset_ms
        self._offset_label.setText(self._format_offset(offset_ms))
        self._update_status()

    def refresh_status(self) -> None:
        """Recompute the status label from the current segment/editable state."""
        if self._stack.currentWidget() != self._detail_widget:
            return
        self._update_status()

    def set_generating(self, generating: bool) -> None:
        """Show/hide the live 'Generating' status for the currently displayed segment."""
        if self._stack.currentWidget() != self._detail_widget:
            return
        self._is_generating = generating
        self._regenerate_button.setEnabled(not generating)
        self._update_status()

    def refresh_property(self, field: str, value: object) -> None:
        """Apply an external property update (undo/redo) without emitting signals."""
        if self._stack.currentWidget() != self._detail_widget:
            return
        if field == "speed" and isinstance(value, float):
            self._speed_spin.blockSignals(True)
            self._speed_spin.setValue(value)
            self._speed_spin.blockSignals(False)
        elif field == "volume" and isinstance(value, float):
            self._volume_slider.blockSignals(True)
            self._volume_slider.setValue(round(value * 100))
            self._volume_slider.blockSignals(False)
            self._volume_display.setText(f"{round(value * 100)}%")
        elif field == "muted" and isinstance(value, bool):
            self._muted_check.blockSignals(True)
            self._muted_check.setChecked(value)
            self._muted_check.blockSignals(False)
        elif field == "fade_in_ms" and isinstance(value, int):
            self._fade_in_spin.blockSignals(True)
            self._fade_in_spin.setValue(value)
            self._fade_in_spin.blockSignals(False)
        elif field == "fade_out_ms" and isinstance(value, int):
            self._fade_out_spin.blockSignals(True)
            self._fade_out_spin.setValue(value)
            self._fade_out_spin.blockSignals(False)
        elif field == "locked" and isinstance(value, bool):
            self._locked_check.blockSignals(True)
            self._locked_check.setChecked(value)
            self._locked_check.blockSignals(False)
        # needs_regeneration / last_error / generated_duration have no dedicated
        # control; they only affect the status label, refreshed below.
        self._update_status()

    def refresh_timeline_clip_property(self, field: str, value: object) -> None:
        if field == "fade_in" and isinstance(value, float):
            self.refresh_property("fade_in_ms", round(value * 1000))
        elif field == "fade_out" and isinstance(value, float):
            self.refresh_property("fade_out_ms", round(value * 1000))
        else:
            self.refresh_property(field, value)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_into_controls(
        self, segment: Segment, editable: EditableSegment | None
    ) -> None:
        es = editable
        for ctrl in (
            self._speed_spin,
            self._volume_slider,
            self._muted_check,
            self._fade_in_spin,
            self._fade_out_spin,
            self._locked_check,
        ):
            ctrl.blockSignals(True)

        self._id_label.setText(str(segment.id))
        self._speed_spin.setEnabled(True)
        self._live_offset_ms = segment.offset_ms
        self._original_text_label.setText(segment.source_text or _PLACEHOLDER)
        self._khmer_text_label.setText(segment.target_text)
        self._start_label.setText(f"{segment.start:.3f} s")
        self._end_label.setText(f"{segment.end:.3f} s")
        duration = segment.end - segment.start
        self._duration_label.setText(f"{duration:.3f} s")
        self._offset_label.setText(self._format_offset(segment.offset_ms))

        speed = es.speed if es else 1.0
        volume = es.volume if es else 1.0
        fade_in = es.fade_in_ms if es else 0
        fade_out = es.fade_out_ms if es else 0
        locked = es.locked if es else False

        self._speed_spin.setValue(speed)
        vol_int = round(volume * 100)
        self._volume_slider.setValue(vol_int)
        self._volume_display.setText(f"{vol_int}%")
        self._muted_check.setChecked(False)
        self._fade_in_spin.setValue(fade_in)
        self._fade_out_spin.setValue(fade_out)
        self._locked_check.setChecked(locked)

        for ctrl in (
            self._speed_spin,
            self._volume_slider,
            self._muted_check,
            self._fade_in_spin,
            self._fade_out_spin,
            self._locked_check,
        ):
            ctrl.blockSignals(False)

        self._update_status()

    def _load_clip_into_controls(self, clip: TimelineClip) -> None:
        for ctrl in (
            self._speed_spin,
            self._volume_slider,
            self._muted_check,
            self._fade_in_spin,
            self._fade_out_spin,
            self._locked_check,
        ):
            ctrl.blockSignals(True)

        self._id_label.setText(clip.id)
        self._live_offset_ms = round((clip.start_time - clip.source_offset) * 1000)
        self._original_text_label.setText(clip.source_text or _PLACEHOLDER)
        self._khmer_text_label.setText(clip.target_text or _PLACEHOLDER)
        self._start_label.setText(f"{clip.start_time:.3f} s")
        self._end_label.setText(f"{clip.end_time:.3f} s")
        self._duration_label.setText(f"{clip.duration:.3f} s")
        self._offset_label.setText(self._format_offset(self._live_offset_ms))
        self._speed_spin.setValue(1.0)
        self._speed_spin.setEnabled(False)
        vol_int = round(clip.volume * 100)
        self._volume_slider.setValue(vol_int)
        self._volume_display.setText(f"{vol_int}%")
        self._muted_check.setChecked(clip.muted)
        self._fade_in_spin.setValue(round(clip.fade_in * 1000))
        self._fade_out_spin.setValue(round(clip.fade_out * 1000))
        self._locked_check.setChecked(clip.locked)

        for ctrl in (
            self._speed_spin,
            self._volume_slider,
            self._muted_check,
            self._fade_in_spin,
            self._fade_out_spin,
            self._locked_check,
        ):
            ctrl.blockSignals(False)
        self._update_status()

    def _update_status(self) -> None:
        if self._is_generating:
            self._status_label.setText(_STATUS_GENERATING)
            return
        if self._locked_check.isChecked():
            self._status_label.setText(_STATUS_EDITED)
            return
        if self._timeline_clip is not None:
            is_edited = (
                self._live_offset_ms != 0
                or self._timeline_clip.volume != 1.0
                or self._timeline_clip.muted
                or self._timeline_clip.fade_in != 0
                or self._timeline_clip.fade_out != 0
                or self._timeline_clip.locked
            )
            self._status_label.setText(_STATUS_EDITED if is_edited else _STATUS_GENERATED)
            return
        if self._editable is not None and self._editable.last_error is not None:
            self._status_label.setText(_STATUS_FAILED)
            return
        if self._editable is not None and self._editable.needs_regeneration:
            self._status_label.setText(_STATUS_NEEDS_REGENERATION)
            return

        offset_mod = self._live_offset_ms != 0
        editable_mod = self._editable is not None and self._editable.is_modified
        controls_mod = (
            self._speed_spin.value() != 1.0
            or self._volume_slider.value() != 100
            or self._fade_in_spin.value() != 0
            or self._fade_out_spin.value() != 0
        )
        is_edited = offset_mod or editable_mod or controls_mod
        self._status_label.setText(_STATUS_EDITED if is_edited else _STATUS_GENERATED)

    # ------------------------------------------------------------------
    # Control signal handlers
    # ------------------------------------------------------------------

    def _on_speed_changed(self, new_val: float) -> None:
        old_val = self._editable.speed if self._editable else 1.0
        if abs(new_val - old_val) < 1e-9:
            return
        self.speedChanged.emit(old_val, new_val)
        self._update_status()

    def _on_volume_changed(self, slider_val: int) -> None:
        self._volume_display.setText(f"{slider_val}%")
        new_vol = slider_val / 100.0
        if self._timeline_clip is not None:
            old_vol = self._timeline_clip.volume
            if abs(new_vol - old_vol) < 1e-9:
                return
            self.clipVolumeChanged.emit(self._timeline_clip.id, old_vol, new_vol)
            self._update_status()
            return
        old_vol = self._editable.volume if self._editable else 1.0
        if abs(new_vol - old_vol) < 1e-9:
            return
        self.volumeChanged.emit(old_vol, new_vol)
        self._update_status()

    def _on_muted_changed(self, new_val: bool) -> None:
        if self._timeline_clip is None:
            return
        old_val = self._timeline_clip.muted
        if new_val == old_val:
            return
        self.clipMutedChanged.emit(self._timeline_clip.id, old_val, new_val)
        self._update_status()

    def _on_fade_in_changed(self, new_val: int) -> None:
        if self._timeline_clip is not None:
            old_val = round(self._timeline_clip.fade_in * 1000)
            if new_val == old_val:
                return
            self.clipFadeInChanged.emit(self._timeline_clip.id, old_val, new_val)
            self._update_status()
            return
        old_val = self._editable.fade_in_ms if self._editable else 0
        if new_val == old_val:
            return
        self.fadeInChanged.emit(old_val, new_val)
        self._update_status()

    def _on_fade_out_changed(self, new_val: int) -> None:
        if self._timeline_clip is not None:
            old_val = round(self._timeline_clip.fade_out * 1000)
            if new_val == old_val:
                return
            self.clipFadeOutChanged.emit(self._timeline_clip.id, old_val, new_val)
            self._update_status()
            return
        old_val = self._editable.fade_out_ms if self._editable else 0
        if new_val == old_val:
            return
        self.fadeOutChanged.emit(old_val, new_val)
        self._update_status()

    def _on_locked_changed(self, new_val: bool) -> None:
        if self._timeline_clip is not None:
            old_val = self._timeline_clip.locked
            if new_val == old_val:
                return
            self.clipLockedChanged.emit(self._timeline_clip.id, old_val, new_val)
            self._update_status()
            return
        old_val = self._editable.locked if self._editable else False
        if new_val == old_val:
            return
        self.lockedChanged.emit(old_val, new_val)
        self._update_status()

    def _on_regenerate_clicked(self) -> None:
        if self._segment is not None:
            self.regenerateRequested.emit(self._segment.id)

    @staticmethod
    def _format_offset(offset_ms: int) -> str:
        if offset_ms == 0:
            return "0 ms"
        sign = "+" if offset_ms > 0 else ""
        return f"{sign}{offset_ms} ms"

    @staticmethod
    def _format_common_float(values: list[float]) -> str:
        first = values[0]
        if all(abs(value - first) < 1e-9 for value in values):
            return f"{first:.2f}"
        return "Mixed"

    @staticmethod
    def _format_common_percent(values: list[float]) -> str:
        first = values[0]
        if all(abs(value - first) < 1e-9 for value in values):
            return f"{round(first * 100)}%"
        return "Mixed"

    @staticmethod
    def _format_common_int(values: list[int], *, suffix: str = "") -> str:
        first = values[0]
        if all(value == first for value in values):
            return f"{first}{suffix}"
        return "Mixed"

    @staticmethod
    def _format_common_bool(values: list[bool]) -> str:
        first = values[0]
        if all(value is first for value in values):
            return "Yes" if first else "No"
        return "Mixed"
