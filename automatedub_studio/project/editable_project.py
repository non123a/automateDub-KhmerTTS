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

    @property
    def is_modified(self) -> bool:
        return self.offset_ms != 0
