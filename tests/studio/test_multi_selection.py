from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QUndoStack
from PySide6.QtTest import QTest

from automatedub_studio.edit.commands import MultiOffsetChangeCommand
from automatedub_studio.inspector.segment_inspector import SegmentInspectorWidget
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem
from automatedub_studio.timeline.timeline_widget import (
    KHMER_TTS_LANE,
    ORIGINAL_AUDIO_LANE,
    TimelineWidget,
)


def _segments(count: int = 4) -> list[Segment]:
    return [
        Segment(
            id=index,
            start=float(index),
            end=float(index) + 0.8,
            source_text=f"source {index}",
            target_text=f"target {index}",
        )
        for index in range(count)
    ]


def _clip_center(
    widget: TimelineWidget,
    segment_id: int,
    lane: int = ORIGINAL_AUDIO_LANE,
) -> QPoint:
    clip = next(clip for clip in widget._clips_by_segment[segment_id] if clip.lane == lane)
    return widget._view.mapFromScene(clip.sceneBoundingRect().center())


def _selected_ids(widget: TimelineWidget) -> list[int]:
    return [segment.id for segment in widget.selected_segments]


def test_ctrl_click_adds_and_removes_clip_from_selection(qapp):
    widget = TimelineWidget()
    widget.resize(700, 220)
    widget.show()
    widget.load_segments(_segments(3))

    QTest.mouseClick(
        widget._view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_clip_center(widget, 0),
    )
    QTest.mouseClick(
        widget._view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        _clip_center(widget, 1),
    )
    assert _selected_ids(widget) == [0, 1]

    QTest.mouseClick(
        widget._view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        _clip_center(widget, 1),
    )
    assert _selected_ids(widget) == [0]


def test_cmd_click_uses_additive_selection_modifier(qapp):
    widget = TimelineWidget()
    widget.load_segments(_segments(2))
    clip0 = widget._clips_by_segment[0][1]
    clip1 = widget._clips_by_segment[1][1]
    clip0.setSelected(True)

    assert widget._view._is_additive_modifier(Qt.KeyboardModifier.MetaModifier)
    widget._view._toggle_clip_selection(clip1)

    assert _selected_ids(widget) == [0, 1]


def test_shift_click_selects_range_on_same_track(qapp):
    widget = TimelineWidget()
    widget.load_segments(_segments(4))
    first = next(clip for clip in widget._clips_by_segment[0] if clip.lane == ORIGINAL_AUDIO_LANE)
    last = next(clip for clip in widget._clips_by_segment[2] if clip.lane == ORIGINAL_AUDIO_LANE)

    widget._view._last_clicked_clip = first
    widget._view._select_range(last)

    assert _selected_ids(widget) == [0, 1, 2]
    assert all(
        clip.lane == ORIGINAL_AUDIO_LANE
        for clip in widget._scene.selectedItems()
        if isinstance(clip, ClipItem)
    )


def test_shift_click_range_selection_is_track_independent(qapp):
    widget = TimelineWidget()
    widget.load_segments(_segments(4))
    first = next(
        clip for clip in widget._clips_by_segment[0] if clip.lane == ORIGINAL_AUDIO_LANE
    )
    last = next(
        clip for clip in widget._clips_by_segment[2] if clip.lane == KHMER_TTS_LANE
    )

    widget._view._last_clicked_clip = first
    widget._view._select_range(last)

    assert _selected_ids(widget) == [2]


def test_marquee_selects_clips_intersecting_drag_rectangle(qapp):
    widget = TimelineWidget()
    widget.resize(700, 220)
    widget.show()
    widget.load_segments(_segments(3))

    lane_one_clip = next(
        clip for clip in widget._clips_by_segment[0] if clip.lane == ORIGINAL_AUDIO_LANE
    )
    empty_scene_pos = QPointF(lane_one_clip.sceneBoundingRect().left() - 20, lane_one_clip.y() + 4)
    start = widget._view.mapFromScene(empty_scene_pos)
    end = _clip_center(widget, 1, lane=ORIGINAL_AUDIO_LANE) + QPoint(20, 10)
    QTest.mousePress(widget._view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(widget._view.viewport(), end)
    QTest.mouseRelease(widget._view.viewport(), Qt.MouseButton.LeftButton, pos=end)

    assert _selected_ids(widget) == [0, 1]


def test_multi_drag_moves_selected_timeline_clips_preserving_relative_offsets(qapp):
    widget = TimelineWidget()
    segments = _segments(3)
    segments[0].offset_ms = 100
    segments[1].offset_ms = 250
    widget.load_segments(segments)
    widget._clips_by_segment[0][1].setSelected(True)
    widget._clips_by_segment[1][1].setSelected(True)
    widget._view._drag_clip = widget._clips_by_segment[0][1]
    widget._view._drag_start_offsets_ms = widget._view._selected_unlocked_clip_offsets()

    moved = widget._view._moved_offsets(333)
    for clip_id, offset_ms in moved.items():
        widget.apply_timeline_clip_offset(clip_id, offset_ms)

    moved_clips = {clip.id: clip for clip in widget.selected_timeline_clips}
    assert moved_clips["khmer:0"].start_time == 0.433
    assert moved_clips["khmer:1"].start_time == 1.583
    spacing_ms = round(
        (moved_clips["khmer:1"].start_time - moved_clips["khmer:0"].start_time) * 1000
    )
    assert spacing_ms == 1150
    assert widget._clips_by_clip_id["original:0"].timeline_clip.start_time == 0.1


def test_multi_offset_command_undo_redo_moves_selection_as_one_command(qapp):
    segments = _segments(2)
    calls: list[tuple[int, int]] = []
    stack = QUndoStack()
    command = MultiOffsetChangeCommand(
        segments,
        {0: 0, 1: 100},
        {0: 250, 1: 350},
        apply_cb=lambda segment_id, offset_ms: calls.append((segment_id, offset_ms)),
    )

    stack.push(command)
    assert stack.count() == 1
    assert segments[0].offset_ms == 250
    assert segments[1].offset_ms == 350

    stack.undo()
    assert segments[0].offset_ms == 0
    assert segments[1].offset_ms == 100

    stack.redo()
    assert segments[0].offset_ms == 250
    assert segments[1].offset_ms == 350
    assert calls[-2:] == [(0, 250), (1, 350)]


def test_inspector_multi_selection_shows_count_average_and_common_properties(qapp):
    inspector = SegmentInspectorWidget()
    segments = _segments(2)
    segments[0].offset_ms = 100
    segments[1].offset_ms = 300
    editables = {
        0: EditableSegment(id=0, speed=1.2, volume=0.8, locked=True),
        1: EditableSegment(id=1, speed=1.2, volume=0.8, locked=True),
    }

    inspector.set_segments(segments, editables)

    assert inspector._stack.currentWidget() is inspector._multi_widget
    assert inspector._multi_count_label.text() == "2 clips"
    assert inspector._multi_average_offset_label.text() == "+200 ms"
    assert inspector._multi_speed_label.text() == "1.20"
    assert inspector._multi_volume_label.text() == "80%"
    assert inspector._multi_locked_label.text() == "Yes"


def test_inspector_multi_selection_shows_mixed_values(qapp):
    inspector = SegmentInspectorWidget()
    segments = _segments(2)
    editables = {
        0: EditableSegment(id=0, speed=1.0, volume=0.8),
        1: EditableSegment(id=1, speed=1.2, volume=1.0),
    }

    inspector.set_segments(segments, editables)

    assert inspector._multi_speed_label.text() == "Mixed"
    assert inspector._multi_volume_label.text() == "Mixed"
