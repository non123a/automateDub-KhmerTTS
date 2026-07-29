"""Shared timeline interaction state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TimelinePlaybackState(StrEnum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass
class TimelineState:
    current_time_ms: int = 0
    playback_state: TimelinePlaybackState = TimelinePlaybackState.STOPPED
    selected_clip_ids: set[str] = field(default_factory=set)

    def set_current_time(self, time_ms: int) -> None:
        self.current_time_ms = max(0, time_ms)
