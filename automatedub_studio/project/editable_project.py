"""Editable overlay layer for a Studio project.

EditableSegment carries all user-controlled per-segment parameters.
The original Segment (from translation.json) is never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EditableSegment:
    id: int
    offset_ms: int = 0
    speed: float = 1.0
    volume: float = 1.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    voice_id: str | None = None
    edited_text: str | None = None
    locked: bool = False
    needs_regeneration: bool = False
    last_error: str | None = None
    generated_duration: float | None = None

    @property
    def is_modified(self) -> bool:
        return (
            self.offset_ms != 0
            or self.speed != 1.0
            or self.volume != 1.0
            or self.fade_in_ms != 0
            or self.fade_out_ms != 0
            or self.locked
            or self.needs_regeneration
            or self.voice_id is not None
            or self.edited_text is not None
        )
