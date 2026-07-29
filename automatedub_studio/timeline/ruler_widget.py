"""Reusable timeline ruler rendering and snapping helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

DEFAULT_SNAP_INTERVAL_MS = 100
MIN_MINOR_TICK_SPACING_PX = 6.0
RULER_HEIGHT = 34

RULER_BG_COLOR = QColor("#242424")
RULER_TEXT_COLOR = QColor("#D8D8D8")
RULER_MINOR_COLOR = QColor("#626262")
RULER_MAJOR_COLOR = QColor("#A8A8A8")
RULER_PLAYHEAD_COLOR = QColor("#FF4444")


@dataclass(frozen=True)
class RulerTick:
    time_ms: int
    x: float
    major: bool


def format_timestamp(time_ms: int) -> str:
    """Format a timeline timestamp as MM:SS, or HH:MM:SS after one hour."""
    total_seconds = max(0, time_ms) // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def snap_offset(offset_ms: int, interval_ms: int = DEFAULT_SNAP_INTERVAL_MS) -> int:
    """Snap an offset to the nearest interval, using half-up rounding."""
    if interval_ms <= 0:
        return offset_ms
    return math.floor(offset_ms / interval_ms + 0.5) * interval_ms


def minor_tick_interval_ms(
    zoom: float,
    pixels_per_second: float,
    min_spacing_px: float = MIN_MINOR_TICK_SPACING_PX,
) -> int:
    """Return the visible minor tick interval for the current zoom level.

    The base grid is 100 ms. When zoomed far out, adjacent 100 ms ticks would
    collapse into unreadable bands, so the visible interval grows in 100 ms
    steps until there is enough screen space between ticks.
    """
    base_interval_ms = DEFAULT_SNAP_INTERVAL_MS
    px_per_base_interval = pixels_per_second * max(zoom, 0.001) * base_interval_ms / 1000.0
    if px_per_base_interval >= min_spacing_px:
        return base_interval_ms
    multiplier = max(1, math.ceil(min_spacing_px / px_per_base_interval))
    return base_interval_ms * multiplier


def generate_ruler_ticks(
    duration_ms: int,
    zoom: float,
    pixels_per_second: float,
    min_minor_spacing_px: float = MIN_MINOR_TICK_SPACING_PX,
) -> list[RulerTick]:
    """Generate major one-second ticks plus zoom-aware minor ticks."""
    duration_ms = max(0, duration_ms)
    minor_interval = minor_tick_interval_ms(zoom, pixels_per_second, min_minor_spacing_px)
    last_tick_ms = int(math.ceil(duration_ms / minor_interval) * minor_interval)
    ticks: dict[int, RulerTick] = {}

    for time_ms in range(0, last_tick_ms + 1, minor_interval):
        ticks[time_ms] = RulerTick(
            time_ms=time_ms,
            x=time_ms / 1000.0 * pixels_per_second,
            major=time_ms % 1000 == 0,
        )

    last_major_ms = int(math.ceil(duration_ms / 1000) * 1000)
    for time_ms in range(0, last_major_ms + 1, 1000):
        ticks[time_ms] = RulerTick(
            time_ms=time_ms,
            x=time_ms / 1000.0 * pixels_per_second,
            major=True,
        )

    return [ticks[key] for key in sorted(ticks)]


class TimelineRulerWidget(QWidget):
    """Paints the time ruler above the timeline scene."""

    def __init__(
        self,
        *,
        pixels_per_second: float,
        time_origin_x: float,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._pixels_per_second = pixels_per_second
        self._time_origin_x = time_origin_x
        self._duration_ms = 0
        self._zoom = 1.0
        self._scroll_x = 0
        self._playhead_ms = 0
        self.setFixedHeight(RULER_HEIGHT)

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, duration_ms)
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.001, zoom)
        self.update()

    def set_scroll_value(self, scroll_x: int) -> None:
        self._scroll_x = scroll_x
        self.update()

    def set_playhead_position(self, position_ms: int) -> None:
        self._playhead_ms = max(0, position_ms)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), RULER_BG_COLOR)

        ticks = generate_ruler_ticks(
            max(self._duration_ms, self._playhead_ms),
            self._zoom,
            self._pixels_per_second,
        )
        origin_x = self._time_origin_x * self._zoom - self._scroll_x
        height = self.height()
        font_metrics = QFontMetrics(painter.font())

        for tick in ticks:
            x = origin_x + tick.x * self._zoom
            if x < -80 or x > self.width() + 80:
                continue
            if tick.major:
                painter.setPen(QPen(RULER_MAJOR_COLOR, 1))
                painter.drawLine(round(x), 8, round(x), height)
                label = format_timestamp(tick.time_ms)
                painter.setPen(RULER_TEXT_COLOR)
                painter.drawText(
                    round(x) + 4,
                    4,
                    font_metrics.horizontalAdvance(label) + 4,
                    14,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    label,
                )
            else:
                painter.setPen(QPen(RULER_MINOR_COLOR, 1))
                painter.drawLine(round(x), height - 9, round(x), height)

        playhead_x = origin_x + self._playhead_ms / 1000.0 * self._pixels_per_second * self._zoom
        if -10 <= playhead_x <= self.width() + 10:
            painter.setPen(QPen(RULER_PLAYHEAD_COLOR, 2))
            painter.drawLine(round(playhead_x), 0, round(playhead_x), height)
            label = format_timestamp(self._playhead_ms)
            painter.setPen(RULER_PLAYHEAD_COLOR)
            painter.drawText(
                round(playhead_x) + 4,
                height - 16,
                font_metrics.horizontalAdvance(label) + 4,
                14,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
