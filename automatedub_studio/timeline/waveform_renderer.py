"""Vector waveform drawing via QPainter.

Pure drawing logic only -- this module never reads a WAV file or computes
peaks (see waveform_cache.py for that). Geometry computation is split out
from the actual QPainter calls so bucket-to-rect scaling can be unit tested
without a real paint device.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen

from automatedub_studio.timeline.waveform_cache import WaveformPeaks

WAVEFORM_COLOR = QColor(255, 255, 255, 150)
WAVEFORM_PEN_WIDTH = 1.0

# (x, y_top, y_bottom) for one vertical min/max bar.
BarGeometry = tuple[float, float, float]


def compute_bar_geometry(rect: QRectF, peaks: WaveformPeaks) -> list[BarGeometry]:
    """Map *peaks* buckets onto *rect*, returning one vertical bar per bucket.

    Bars are evenly spaced across the rect's width and vertically centered,
    scaled to the rect's height. Returns an empty list if there is nothing
    to draw (no peaks, or a degenerate rect).
    """
    bucket_count = len(peaks.peaks)
    if bucket_count == 0 or rect.width() <= 0 or rect.height() <= 0:
        return []

    mid_y = rect.y() + rect.height() / 2.0
    half_height = rect.height() / 2.0
    bucket_width = rect.width() / bucket_count

    bars: list[BarGeometry] = []
    for index, (lo, hi) in enumerate(peaks.peaks):
        x = rect.x() + index * bucket_width + bucket_width / 2.0
        y_top = mid_y - hi * half_height
        y_bottom = mid_y - lo * half_height
        bars.append((x, y_top, y_bottom))
    return bars


def paint_waveform(painter: QPainter, rect: QRectF, peaks: WaveformPeaks) -> None:
    """Draw *peaks* as vertical bars clipped inside *rect* using vector lines.

    No-op when there is nothing to draw. Never rasterizes -- draws directly
    with QPainter so it stays sharp at any zoom level.
    """
    bars = compute_bar_geometry(rect, peaks)
    if not bars:
        return

    painter.save()
    painter.setClipRect(rect)
    painter.setPen(QPen(WAVEFORM_COLOR, WAVEFORM_PEN_WIDTH))
    for x, y_top, y_bottom in bars:
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bottom))
    painter.restore()
