"""QUndoCommand subclasses for offset editing."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from automatedub_studio.project.models import Segment


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
