"""Tests for waveform_renderer: pure bar geometry and QPainter drawing."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from PySide6.QtCore import QRectF

from automatedub_studio.timeline.waveform_cache import WaveformPeaks
from automatedub_studio.timeline.waveform_renderer import (
    compute_bar_geometry,
    paint_waveform,
)

# ---------------------------------------------------------------------------
# compute_bar_geometry
# ---------------------------------------------------------------------------


def test_compute_bar_geometry_empty_peaks_returns_empty():
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=())
    assert compute_bar_geometry(rect, peaks) == []


def test_compute_bar_geometry_zero_width_rect_returns_empty():
    rect = QRectF(0, 0, 0, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),))
    assert compute_bar_geometry(rect, peaks) == []


def test_compute_bar_geometry_zero_height_rect_returns_empty():
    rect = QRectF(0, 0, 100, 0)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),))
    assert compute_bar_geometry(rect, peaks) == []


def test_compute_bar_geometry_returns_one_bar_per_bucket():
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0), (0.5, 0.5), (-0.5, -0.5)))
    bars = compute_bar_geometry(rect, peaks)
    assert len(bars) == 3


def test_compute_bar_geometry_bars_evenly_spaced():
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),) * 4)
    bars = compute_bar_geometry(rect, peaks)
    xs = [x for x, _, _ in bars]
    bucket_width = 100 / 4
    expected = [bucket_width / 2 + i * bucket_width for i in range(4)]
    for actual_x, expected_x in zip(xs, expected, strict=True):
        assert abs(actual_x - expected_x) < 1e-6


def test_compute_bar_geometry_zero_peak_centers_at_midline():
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),))
    (_, y_top, y_bottom) = compute_bar_geometry(rect, peaks)[0]
    mid_y = rect.y() + rect.height() / 2.0
    assert abs(y_top - mid_y) < 1e-6
    assert abs(y_bottom - mid_y) < 1e-6


def test_compute_bar_geometry_full_range_spans_rect_height():
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((-1.0, 1.0),))
    (_, y_top, y_bottom) = compute_bar_geometry(rect, peaks)[0]
    assert abs(y_top - rect.y()) < 1e-6
    assert abs(y_bottom - (rect.y() + rect.height())) < 1e-6


def test_compute_bar_geometry_respects_rect_offset():
    rect = QRectF(10, 20, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),))
    (x, y_top, y_bottom) = compute_bar_geometry(rect, peaks)[0]
    assert x == rect.x() + rect.width() / 2.0
    mid_y = rect.y() + rect.height() / 2.0
    assert abs(y_top - mid_y) < 1e-6
    assert abs(y_bottom - mid_y) < 1e-6


# ---------------------------------------------------------------------------
# paint_waveform
# ---------------------------------------------------------------------------


def test_paint_waveform_noop_when_no_peaks():
    painter = MagicMock()
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=())

    paint_waveform(painter, rect, peaks)

    painter.save.assert_not_called()
    painter.drawLine.assert_not_called()


def test_paint_waveform_draws_one_line_per_bucket():
    painter = MagicMock()
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.5), (-0.5, 0.0), (0.2, 0.8)))

    paint_waveform(painter, rect, peaks)

    assert painter.drawLine.call_count == 3


def test_paint_waveform_saves_clips_and_restores():
    painter = MagicMock()
    rect = QRectF(0, 0, 100, 50)
    peaks = WaveformPeaks(peaks=((0.0, 0.0),))

    paint_waveform(painter, rect, peaks)

    painter.save.assert_called_once()
    painter.setClipRect.assert_called_once_with(rect)
    painter.restore.assert_called_once()
    assert painter.method_calls.index(call.save()) < painter.method_calls.index(
        call.restore()
    )
