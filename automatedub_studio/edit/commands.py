"""QUndoCommand subclasses for segment property editing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QUndoCommand

from automatedub_studio.project.models import Segment


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
