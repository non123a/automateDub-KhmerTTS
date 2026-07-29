"""QUndoCommand subclasses for segment property editing."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from shutil import copyfile
from typing import Any

from PySide6.QtGui import QUndoCommand

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.models import Segment


class ClipClipboard:
    """In-memory Studio clipboard for copied timeline clips."""

    def __init__(self) -> None:
        self._segments: list[Segment] = []
        self._editables: dict[int, Any] = {}

    def replace(self, segments: list[Segment], editables: dict[int, Any]) -> None:
        ordered = sorted(segments, key=lambda segment: (segment.start, segment.id))
        self._segments = [deepcopy(segment) for segment in ordered]
        self._editables = {
            segment.id: deepcopy(editables[segment.id])
            for segment in ordered
            if segment.id in editables
        }

    @property
    def is_empty(self) -> bool:
        return not self._segments

    @property
    def segments(self) -> list[Segment]:
        return [deepcopy(segment) for segment in self._segments]

    @property
    def editables(self) -> dict[int, Any]:
        return deepcopy(self._editables)


class PropertyChangeCommand(QUndoCommand):
    """Record a change to any named EditableSegment property."""

    def __init__(
        self,
        segment_id: int,
        field: str,
        old_value: Any,
        new_value: Any,
        apply_cb: Callable[[int, str, Any], None],
    ):
        super().__init__(f"Change {field} for segment {segment_id}")
        self._segment_id = segment_id
        self._field = field
        self._old = old_value
        self._new = new_value
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._apply_cb(self._segment_id, self._field, self._old)

    def redo(self) -> None:
        self._apply_cb(self._segment_id, self._field, self._new)


class TimelineClipPropertyChangeCommand(QUndoCommand):
    """Record a property change on one independent TimelineClip."""

    def __init__(
        self,
        clip_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        apply_cb: Callable[[str, str, Any], None],
    ):
        super().__init__(f"Change {field} for clip {clip_id}")
        self._clip_id = clip_id
        self._field = field
        self._old = old_value
        self._new = new_value
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._apply_cb(self._clip_id, self._field, self._old)

    def redo(self) -> None:
        self._apply_cb(self._clip_id, self._field, self._new)


class MultiTimelineClipPropertyChangeCommand(QUndoCommand):
    """Record property changes for multiple TimelineClips as one undo step."""

    def __init__(
        self,
        field: str,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
        apply_cb: Callable[[str, str, Any], None],
    ):
        super().__init__(f"Change {field} for {len(new_values)} clips")
        self._field = field
        self._old = dict(old_values)
        self._new = dict(new_values)
        self._apply_cb = apply_cb

    def undo(self) -> None:
        for clip_id, value in self._old.items():
            self._apply_cb(clip_id, self._field, value)

    def redo(self) -> None:
        for clip_id, value in self._new.items():
            self._apply_cb(clip_id, self._field, value)


class TimelineClipOffsetChangeCommand(QUndoCommand):
    """Record an offset change for one independent TimelineClip."""

    def __init__(
        self,
        clip_id: str,
        old_offset_ms: int,
        new_offset_ms: int,
        apply_cb: Callable[[str, int], None],
    ):
        super().__init__(f"Move clip {clip_id}")
        self._clip_id = clip_id
        self._old = old_offset_ms
        self._new = new_offset_ms
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._apply_cb(self._clip_id, self._old)

    def redo(self) -> None:
        self._apply_cb(self._clip_id, self._new)


class MultiTimelineClipOffsetChangeCommand(QUndoCommand):
    """Record multiple TimelineClip offset changes as one undoable move."""

    def __init__(
        self,
        old_offsets_ms: dict[str, int],
        new_offsets_ms: dict[str, int],
        apply_cb: Callable[[str, int], None],
    ):
        super().__init__(f"Move {len(new_offsets_ms)} clips")
        self._old = dict(old_offsets_ms)
        self._new = dict(new_offsets_ms)
        self._apply_cb = apply_cb

    def undo(self) -> None:
        for clip_id, offset_ms in self._old.items():
            self._apply_cb(clip_id, offset_ms)

    def redo(self) -> None:
        for clip_id, offset_ms in self._new.items():
            self._apply_cb(clip_id, offset_ms)


class TimelineClipTrimCommand(QUndoCommand):
    """Record a trim change for one independent TimelineClip."""

    def __init__(
        self,
        clip_id: str,
        old_start: float,
        old_end: float,
        new_start: float,
        new_end: float,
        apply_cb: Callable[[str, float, float], None],
    ):
        super().__init__(f"Trim clip {clip_id}")
        self._clip_id = clip_id
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._apply_cb(self._clip_id, self._old_start, self._old_end)

    def redo(self) -> None:
        self._apply_cb(self._clip_id, self._new_start, self._new_end)


class OffsetChangeCommand(QUndoCommand):
    """Record a single offset_ms change for undo/redo."""

    def __init__(
        self,
        segment: Segment,
        old_offset_ms: int,
        new_offset_ms: int,
        apply_cb: Callable[[int, int], None],
    ):
        super().__init__(f"Move segment {segment.id}")
        self._segment = segment
        self._old = old_offset_ms
        self._new = new_offset_ms
        # apply_cb(segment_id, offset_ms) — repositions clip + refreshes inspector
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._segment.offset_ms = self._old
        self._apply_cb(self._segment.id, self._old)

    def redo(self) -> None:
        self._segment.offset_ms = self._new
        self._apply_cb(self._segment.id, self._new)


class MultiOffsetChangeCommand(QUndoCommand):
    """Record multiple segment offset changes as one undoable move."""

    def __init__(
        self,
        segments: list[Segment],
        old_offsets_ms: dict[int, int],
        new_offsets_ms: dict[int, int],
        apply_cb: Callable[[int, int], None],
    ):
        super().__init__(f"Move {len(new_offsets_ms)} segments")
        self._segments = {segment.id: segment for segment in segments}
        self._old = dict(old_offsets_ms)
        self._new = dict(new_offsets_ms)
        self._apply_cb = apply_cb

    def undo(self) -> None:
        for segment_id, offset_ms in self._old.items():
            segment = self._segments.get(segment_id)
            if segment is not None:
                segment.offset_ms = offset_ms
            self._apply_cb(segment_id, offset_ms)

    def redo(self) -> None:
        for segment_id, offset_ms in self._new.items():
            segment = self._segments.get(segment_id)
            if segment is not None:
                segment.offset_ms = offset_ms
            self._apply_cb(segment_id, offset_ms)


class TrimSegmentCommand(QUndoCommand):
    """Record a segment start/end trim."""

    def __init__(
        self,
        segment: Segment,
        old_start: float,
        old_end: float,
        new_start: float,
        new_end: float,
        apply_cb: Callable[[int, float, float], None],
    ):
        super().__init__(f"Trim segment {segment.id}")
        self._segment = segment
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end
        self._apply_cb = apply_cb

    def undo(self) -> None:
        self._segment.start = self._old_start
        self._segment.end = self._old_end
        self._apply_cb(self._segment.id, self._old_start, self._old_end)

    def redo(self) -> None:
        self._segment.start = self._new_start
        self._segment.end = self._new_end
        self._apply_cb(self._segment.id, self._new_start, self._new_end)


class SplitSegmentCommand(QUndoCommand):
    """Replace one segment with two adjacent segments as one undoable edit."""

    def __init__(
        self,
        segments: list[Segment],
        segment: Segment,
        split_seconds: float,
        new_segment_id: int,
        editables: dict[int, Any],
        apply_cb: Callable[[], None],
    ):
        super().__init__(f"Split segment {segment.id}")
        self._segments = segments
        self._original = segment
        self._split_seconds = split_seconds
        self._new_segment_id = new_segment_id
        self._editables = editables
        self._apply_cb = apply_cb
        self._original_end = segment.end
        self._new_segment = replace(
            segment,
            id=new_segment_id,
            start=split_seconds,
            end=segment.end,
        )
        self._new_editable = deepcopy(editables.get(segment.id))

    def undo(self) -> None:
        self._original.end = self._original_end
        if self._new_segment in self._segments:
            self._segments.remove(self._new_segment)
        self._editables.pop(self._new_segment_id, None)
        self._sort_segments()
        self._apply_cb()

    def redo(self) -> None:
        self._original.end = self._split_seconds
        if self._new_segment not in self._segments:
            self._segments.append(self._new_segment)
        if self._new_editable is not None:
            self._new_editable.id = self._new_segment_id
            self._editables[self._new_segment_id] = deepcopy(self._new_editable)
        self._sort_segments()
        self._apply_cb()

    def _sort_segments(self) -> None:
        self._segments.sort(key=lambda segment: (segment.start, segment.id))


class PasteSegmentsCommand(QUndoCommand):
    """Paste copied segments as new IDs with preserved editable/audio state."""

    def __init__(
        self,
        segments: list[Segment],
        source_segments: list[Segment],
        paste_start_seconds: float,
        new_segment_ids: list[int],
        editables: dict[int, Any],
        source_editables: dict[int, Any],
        tts_directory: Path | None,
        apply_cb: Callable[[list[int], bool], None],
    ):
        super().__init__(f"Paste {len(source_segments)} clips")
        self._segments = segments
        self._source_segments = sorted(
            [deepcopy(segment) for segment in source_segments],
            key=lambda segment: (segment.start, segment.id),
        )
        self._paste_start_seconds = paste_start_seconds
        self._new_segment_ids = list(new_segment_ids)
        self._editables = editables
        self._source_editables = deepcopy(source_editables)
        self._tts_directory = tts_directory
        self._apply_cb = apply_cb
        self._new_segments = self._build_new_segments()
        self._new_editables = self._build_new_editables()

    @property
    def new_segment_ids(self) -> list[int]:
        return list(self._new_segment_ids)

    def undo(self) -> None:
        for segment in list(self._new_segments):
            if segment in self._segments:
                self._segments.remove(segment)
            self._editables.pop(segment.id, None)
            self._remove_tts_copy(segment.id)
        self._sort_segments()
        self._apply_cb([], False)

    def redo(self) -> None:
        for segment in self._new_segments:
            if segment not in self._segments:
                self._segments.append(segment)
            if segment.id in self._new_editables:
                self._editables[segment.id] = deepcopy(self._new_editables[segment.id])
            self._copy_tts(segment)
        self._sort_segments()
        self._apply_cb(self._new_segment_ids, True)

    def _build_new_segments(self) -> list[Segment]:
        if not self._source_segments:
            return []
        base_start = min(segment.start for segment in self._source_segments)
        new_segments = []
        for source, new_id in zip(self._source_segments, self._new_segment_ids, strict=True):
            delta = source.start - base_start
            duration = source.end - source.start
            new_start = self._paste_start_seconds + delta
            new_segments.append(
                replace(source, id=new_id, start=new_start, end=new_start + duration)
            )
        return new_segments

    def _build_new_editables(self) -> dict[int, Any]:
        new_editables: dict[int, Any] = {}
        for source, new_id in zip(self._source_segments, self._new_segment_ids, strict=True):
            editable = self._source_editables.get(source.id)
            if editable is not None:
                copied = deepcopy(editable)
                copied.id = new_id
                new_editables[new_id] = copied
        return new_editables

    def _copy_tts(self, segment: Segment) -> None:
        if self._tts_directory is None:
            return
        source_id = self._source_id_for_new_id(segment.id)
        if source_id is None:
            return
        source_path = tts_segment_output_path(self._tts_directory, source_id)
        destination_path = tts_segment_output_path(self._tts_directory, segment.id)
        if source_path.is_file():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source_path, destination_path)

    def _remove_tts_copy(self, segment_id: int) -> None:
        if self._tts_directory is None:
            return
        path = tts_segment_output_path(self._tts_directory, segment_id)
        if path.is_file():
            path.unlink()

    def _source_id_for_new_id(self, segment_id: int) -> int | None:
        try:
            index = self._new_segment_ids.index(segment_id)
        except ValueError:
            return None
        return self._source_segments[index].id

    def _sort_segments(self) -> None:
        self._segments.sort(key=lambda segment: (segment.start, segment.id))
