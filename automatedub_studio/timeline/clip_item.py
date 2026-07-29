"""ClipItem: QGraphicsRectItem representing one segment on the timeline."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.waveform_cache import (
    DEFAULT_BUCKET_COUNT,
    WaveformCache,
    WaveformError,
)
from automatedub_studio.timeline.waveform_renderer import paint_waveform

WAVEFORM_MARGIN = 2.0

LANE_COLORS = {
    0: QColor("#5094D9"),
    1: QColor("#60C080"),
}
LOCKED_COLOR = QColor("#8888AA")

SELECTED_PEN_COLOR = QColor("#FF8800")
SELECTED_PEN_WIDTH = 3
NORMAL_PEN_WIDTH = 1

CLIP_CORNER_RADIUS = 3.0

STATUS_GENERATING = "generating"
STATUS_FAILED = "failed"
STATUS_NEEDS_REGENERATION = "needs_regeneration"

STATUS_COLORS = {
    STATUS_GENERATING: QColor("#D9B84D"),
    STATUS_FAILED: QColor("#D9534F"),
    STATUS_NEEDS_REGENERATION: QColor("#B06E3A"),
}
STATUS_ICONS = {
    STATUS_GENERATING: "⏳",  # hourglass
    STATUS_FAILED: "⚠",  # warning sign
    STATUS_NEEDS_REGENERATION: "↻",  # clockwise arrow
}


class ClipItem(QGraphicsRectItem):
    """A single segment rectangle on the timeline."""

    def __init__(
        self,
        segment: Segment,
        x: float,
        y: float,
        width: float,
        height: float,
        lane: int,
        wav_path: Path | None = None,
        waveform_cache: WaveformCache | None = None,
        wav_start_seconds: float = 0.0,
        wav_end_seconds: float | None = None,
        waveform_bucket_count: int = DEFAULT_BUCKET_COUNT,
    ):
        super().__init__(x, y, width, height)
        self.segment = segment
        self.lane = lane
        self.locked = False
        self.status: str | None = None
        self._wav_path = wav_path
        self._waveform_cache = waveform_cache
        self._wav_start_seconds = wav_start_seconds
        self._wav_end_seconds = wav_end_seconds
        self._waveform_bucket_count = waveform_bucket_count

        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(LANE_COLORS.get(lane, QColor("#888888"))))
        self.setPen(QPen(QColor("#333333"), NORMAL_PEN_WIDTH))

        self._id_label = QGraphicsTextItem(str(segment.id), self)
        self._id_label.setDefaultTextColor(Qt.GlobalColor.white)
        self._center_label()

        self._lock_label: QGraphicsTextItem | None = None

        self.setToolTip(self._build_tooltip(segment))

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self._refresh_visuals()

    def set_wav_path(self, wav_path: Path | None) -> None:
        """Point this clip at a (possibly new) WAV file and force a repaint.

        Called after regeneration so the waveform reflects the new audio
        instead of a stale cached rendering of the previous WAV.
        """
        self._wav_path = wav_path
        if self._waveform_cache is not None and wav_path is not None:
            self._waveform_cache.invalidate(wav_path)
        self.update()

    def set_status(self, status: str | None) -> None:
        """status is one of STATUS_GENERATING/STATUS_FAILED/STATUS_NEEDS_REGENERATION or None."""
        self.status = status
        self._refresh_visuals()

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._wav_path is None or self._waveform_cache is None:
            return
        try:
            peaks = self._waveform_cache.get_or_compute(
                self._wav_path,
                bucket_count=self._waveform_bucket_count,
                start_seconds=self._wav_start_seconds,
                end_seconds=self._wav_end_seconds,
            )
        except WaveformError:
            return
        rect = self.rect().adjusted(
            WAVEFORM_MARGIN, WAVEFORM_MARGIN, -WAVEFORM_MARGIN, -WAVEFORM_MARGIN
        )
        paint_waveform(painter, rect, peaks)

    def _refresh_visuals(self) -> None:
        # Precedence: Generating > Locked > Failed/Needs Regeneration > lane default.
        if self.status == STATUS_GENERATING:
            color = STATUS_COLORS[STATUS_GENERATING]
            icon = STATUS_ICONS[STATUS_GENERATING]
        elif self.locked:
            color = LOCKED_COLOR
            icon = "\U0001f512"
        elif self.status in (STATUS_FAILED, STATUS_NEEDS_REGENERATION):
            color = STATUS_COLORS[self.status]
            icon = STATUS_ICONS[self.status]
        else:
            color = LANE_COLORS.get(self.lane, QColor("#888888"))
            icon = None

        self.setBrush(QBrush(color))
        self._set_badge_icon(icon)

    def _set_badge_icon(self, icon: str | None) -> None:
        if icon is not None:
            if self._lock_label is None:
                self._lock_label = QGraphicsTextItem(icon, self)
                self._lock_label.setDefaultTextColor(Qt.GlobalColor.white)
                r = self.rect()
                self._lock_label.setPos(r.x() + r.width() - 18, r.y() + 2)
            else:
                self._lock_label.setPlainText(icon)
        elif self._lock_label is not None:
            self._lock_label.setParentItem(None)
            self._lock_label = None

    def _center_label(self) -> None:
        rect = self.rect()
        label_rect = self._id_label.boundingRect()
        self._id_label.setPos(
            rect.x() + (rect.width() - label_rect.width()) / 2,
            rect.y() + (rect.height() - label_rect.height()) / 2,
        )

    @staticmethod
    def _build_tooltip(segment: Segment) -> str:
        duration = segment.end - segment.start
        lines = [
            f"ID: {segment.id}",
            f"Start: {segment.start:.3f}s",
            f"End:   {segment.end:.3f}s",
            f"Duration: {duration:.3f}s",
        ]
        if segment.source_text:
            lines.insert(1, f"Source: {segment.source_text}")
        lines.append(f"Target: {segment.target_text}")
        return "\n".join(lines)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemSelectedHasChanged:
            pen_color = SELECTED_PEN_COLOR if value else QColor("#333333")
            self.setPen(QPen(pen_color, SELECTED_PEN_WIDTH if value else NORMAL_PEN_WIDTH))
        return super().itemChange(change, value)
