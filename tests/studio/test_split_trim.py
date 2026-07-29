from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QUndoStack

from automatedub_studio.edit.commands import SplitSegmentCommand, TrimSegmentCommand
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem
from automatedub_studio.timeline.timeline_widget import (
    BASE_PIXELS_PER_SECOND,
    MIN_CLIP_DURATION_SECONDS,
    TimelineWidget,
)


def _segment(
    segment_id: int = 1,
    start: float = 1.0,
    end: float = 3.0,
    offset_ms: int = 0,
) -> Segment:
    return Segment(
        id=segment_id,
        start=start,
        end=end,
        source_text="source",
        target_text="target",
        offset_ms=offset_ms,
    )


def test_split_command_creates_two_adjacent_clips_preserving_properties(qapp):
    segments = [_segment(1, 1.0, 3.0, offset_ms=120)]
    editables = {1: EditableSegment(id=1, speed=1.2, volume=0.8, locked=True)}
    calls = []
    command = SplitSegmentCommand(
        segments,
        segments[0],
        split_seconds=2.0,
        new_segment_id=2,
        editables=editables,
        apply_cb=lambda: calls.append("applied"),
    )

    command.redo()

    assert [(segment.id, segment.start, segment.end) for segment in segments] == [
        (1, 1.0, 2.0),
        (2, 2.0, 3.0),
    ]
    assert segments[1].offset_ms == 120
    assert editables[2].speed == 1.2
    assert editables[2].volume == 0.8
    assert editables[2].locked is True
    assert calls == ["applied"]


def test_split_command_undo_redo(qapp):
    segments = [_segment(1, 1.0, 3.0)]
    editables: dict[int, EditableSegment] = {}
    stack = QUndoStack()
    command = SplitSegmentCommand(
        segments,
        segments[0],
        split_seconds=2.0,
        new_segment_id=2,
        editables=editables,
        apply_cb=lambda: None,
    )

    stack.push(command)
    assert len(segments) == 2

    stack.undo()
    assert [(segment.id, segment.start, segment.end) for segment in segments] == [(1, 1.0, 3.0)]

    stack.redo()
    assert [(segment.id, segment.start, segment.end) for segment in segments] == [
        (1, 1.0, 2.0),
        (2, 2.0, 3.0),
    ]


def test_left_trim_changes_start_and_preserves_end(qapp):
    widget = TimelineWidget()
    segment = _segment(1, 1.0, 3.0)
    widget.load_segments([segment], duration_ms=5000)

    widget.apply_trim(segment.id, 1.5, 3.0)

    assert segment.start == 1.5
    assert segment.end == 3.0
    clip = widget._clips_by_segment[segment.id][0]
    assert abs(clip.rect().width() - 1.5 * BASE_PIXELS_PER_SECOND) < 0.1


def test_right_trim_changes_end_and_preserves_start(qapp):
    widget = TimelineWidget()
    segment = _segment(1, 1.0, 3.0)
    widget.load_segments([segment], duration_ms=5000)

    widget.apply_trim(segment.id, 1.0, 2.4)

    assert segment.start == 1.0
    assert segment.end == 2.4
    clip = widget._clips_by_segment[segment.id][0]
    assert abs(clip.rect().width() - 1.4 * BASE_PIXELS_PER_SECOND) < 0.1


def test_trim_command_undo_redo(qapp):
    segment = _segment(1, 1.0, 3.0)
    calls: list[tuple[int, float, float]] = []
    stack = QUndoStack()
    command = TrimSegmentCommand(
        segment,
        old_start=1.0,
        old_end=3.0,
        new_start=1.5,
        new_end=2.5,
        apply_cb=lambda segment_id, start, end: calls.append((segment_id, start, end)),
    )

    stack.push(command)
    assert (segment.start, segment.end) == (1.5, 2.5)

    stack.undo()
    assert (segment.start, segment.end) == (1.0, 3.0)

    stack.redo()
    assert (segment.start, segment.end) == (1.5, 2.5)
    assert calls[-1] == (1, 1.5, 2.5)


def test_invalid_trim_cannot_cross_zero_duration(qapp):
    widget = TimelineWidget()
    segment = _segment(1, 1.0, 3.0)
    widget.load_segments([segment], duration_ms=5000)

    start, end = widget.constrain_trim(segment.id, 3.5, 3.0)

    assert end - start >= MIN_CLIP_DURATION_SECONDS - 1e-9
    assert start < end


def test_invalid_trim_cannot_overlap_neighbor(qapp):
    widget = TimelineWidget()
    first = _segment(1, 1.0, 2.0)
    second = _segment(2, 2.5, 4.0)
    widget.load_segments([first, second], duration_ms=5000)

    widget.apply_trim(first.id, 1.0, 3.0)

    assert first.end == 2.5


def test_invalid_trim_cannot_exceed_source_audio_length(qapp):
    widget = TimelineWidget()
    segment = _segment(1, 1.0, 3.0)
    widget.load_segments([segment], duration_ms=3500)

    widget.apply_trim(segment.id, 1.0, 4.0)

    assert segment.end == 3.5


def test_trim_handle_hit_testing(qapp):
    segment = _segment()
    clip = ClipItem(segment, 0, 0, 100, 40, lane=1)

    assert clip.trim_handle_at(clip.rect().center()) is None
    assert clip.trim_handle_at(clip.rect().topLeft()) == "left"
    assert clip.trim_handle_at(clip.rect().topRight()) == "right"
