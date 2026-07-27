"""Tests for TimelineWidget and ClipItem."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem
from automatedub_studio.timeline.timeline_widget import (
    BASE_PIXELS_PER_SECOND,
    LANE_COUNT,
    LANE_LABEL_WIDTH,
    SCENE_MARGIN_H,
    TimelineWidget,
)


def _make_segments(count: int = 3) -> list[Segment]:
    return [
        Segment(
            id=i,
            start=float(i * 2),
            end=float(i * 2 + 1),
            source_text=f"source {i}",
            target_text=f"target {i}",
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_timeline_widget_creates(qapp):
    widget = TimelineWidget()
    assert widget is not None


def test_timeline_has_scene(qapp):
    widget = TimelineWidget()
    assert widget._scene is not None


def test_timeline_initial_no_clips(qapp):
    widget = TimelineWidget()
    assert widget._clips == []


def test_timeline_selected_segment_is_none_initially(qapp):
    widget = TimelineWidget()
    assert widget.selected_segment is None


# ---------------------------------------------------------------------------
# load_segments
# ---------------------------------------------------------------------------


def test_load_segments_creates_clips(qapp):
    widget = TimelineWidget()
    segments = _make_segments(5)

    widget.load_segments(segments)

    # LANE_COUNT clips per segment
    assert len(widget._clips) == 5 * LANE_COUNT


def test_load_segments_creates_clip_items(qapp):
    widget = TimelineWidget()
    segments = _make_segments(3)

    widget.load_segments(segments)

    for clip in widget._clips:
        assert isinstance(clip, ClipItem)


def test_load_segments_clip_x_position(qapp):
    widget = TimelineWidget()
    segments = [Segment(id=0, start=2.0, end=3.0, source_text="s", target_text="t")]

    widget.load_segments(segments)

    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + 2.0 * BASE_PIXELS_PER_SECOND
    first_clip = widget._clips[0]
    assert abs(first_clip.rect().x() - expected_x) < 0.1


def test_load_segments_clip_width(qapp):
    widget = TimelineWidget()
    segments = [Segment(id=0, start=1.0, end=3.0, source_text="s", target_text="t")]

    widget.load_segments(segments)

    expected_width = 2.0 * BASE_PIXELS_PER_SECOND
    first_clip = widget._clips[0]
    assert abs(first_clip.rect().width() - expected_width) < 0.1


def test_load_segments_stores_segment_on_clip(qapp):
    widget = TimelineWidget()
    seg = Segment(id=7, start=0.0, end=1.0, source_text="src", target_text="tgt")
    widget.load_segments([seg])

    assert widget._clips[0].segment is seg


def test_load_segments_empty_list(qapp):
    widget = TimelineWidget()
    widget.load_segments([])
    assert widget._clips == []


def test_reload_replaces_clips(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(3))
    widget.load_segments(_make_segments(2))
    assert len(widget._clips) == 2 * LANE_COUNT


# ---------------------------------------------------------------------------
# Playhead
# ---------------------------------------------------------------------------


def test_playhead_created_after_load(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(2))
    assert widget._playhead is not None


def test_set_playhead_position_moves_line(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(2))

    widget.set_playhead_position(5000)  # 5 seconds

    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + 5.0 * BASE_PIXELS_PER_SECOND
    assert abs(widget._playhead.line().x1() - expected_x) < 0.1


def test_set_playhead_position_zero(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(1))

    widget.set_playhead_position(0)

    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H
    assert abs(widget._playhead.line().x1() - expected_x) < 0.1


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_selecting_clip_sets_selected_segment(qapp):
    widget = TimelineWidget()
    segments = _make_segments(3)
    widget.load_segments(segments)

    clip = widget._clips[1]  # lane 1 (Khmer TTS) — selectable
    clip.setSelected(True)

    assert widget.selected_segment is clip.segment


def test_deselecting_clears_selected_segment(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(2))

    widget._clips[1].setSelected(True)  # lane 1 — selectable
    widget._scene.clearSelection()

    assert widget.selected_segment is None


def test_selection_signal_emitted(qapp):
    widget = TimelineWidget()
    widget.load_segments(_make_segments(2))

    received: list = []
    widget.segmentSelected.connect(received.append)

    widget._clips[1].setSelected(True)  # lane 1 — selectable

    assert len(received) >= 1
    assert received[-1] is widget._clips[1].segment


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------


def test_zoom_changes_view_transform(qapp):
    widget = TimelineWidget()
    initial_scale = widget._view.transform().m11()

    widget._apply_zoom(2.0)

    assert widget._view.transform().m11() > initial_scale


def test_zoom_in_increases_zoom_value(qapp):
    widget = TimelineWidget()
    widget._apply_zoom(2.0)
    assert widget._zoom > 1.0


def test_zoom_out_decreases_zoom_value(qapp):
    widget = TimelineWidget()
    widget._apply_zoom(0.5)
    assert widget._zoom < 1.0


def test_zoom_clamps_at_minimum(qapp):
    widget = TimelineWidget()
    for _ in range(100):
        widget._apply_zoom(0.1)
    assert widget._zoom >= 0.05


def test_zoom_clamps_at_maximum(qapp):
    widget = TimelineWidget()
    for _ in range(100):
        widget._apply_zoom(10.0)
    assert widget._zoom <= 20.0


def test_zoom_only_scales_horizontally(qapp):
    widget = TimelineWidget()
    widget._apply_zoom(3.0)
    transform = widget._view.transform()
    assert abs(transform.m22() - 1.0) < 0.001


# ---------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------


def test_clip_tooltip_contains_id(qapp):
    seg = Segment(id=42, start=1.0, end=2.0, source_text="src", target_text="tgt")
    widget = TimelineWidget()
    widget.load_segments([seg])
    assert "42" in widget._clips[0].toolTip()


def test_clip_tooltip_contains_timing(qapp):
    seg = Segment(id=1, start=1.5, end=3.0, source_text="src", target_text="tgt")
    widget = TimelineWidget()
    widget.load_segments([seg])
    tip = widget._clips[0].toolTip()
    assert "1.500" in tip
    assert "3.000" in tip


def test_clip_tooltip_contains_target_text(qapp):
    seg = Segment(id=0, start=0.0, end=1.0, source_text="hello", target_text="world")
    widget = TimelineWidget()
    widget.load_segments([seg])
    assert "world" in widget._clips[0].toolTip()


def test_clip_tooltip_contains_source_text_when_present(qapp):
    seg = Segment(id=0, start=0.0, end=1.0, source_text="hello", target_text="world")
    widget = TimelineWidget()
    widget.load_segments([seg])
    assert "hello" in widget._clips[0].toolTip()


def test_clip_tooltip_omits_source_label_when_empty(qapp):
    seg = Segment(id=0, start=0.0, end=1.0, source_text="", target_text="world")
    widget = TimelineWidget()
    widget.load_segments([seg])
    assert "Source:" not in widget._clips[0].toolTip()
