"""Independent timeline clip model for Studio editing and playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

VIDEO_TRACK_ID = "video"
ORIGINAL_AUDIO_TRACK_ID = "original_audio"
KHMER_TTS_TRACK_ID = "khmer_tts"


@dataclass
class TimelineClip:
    """A true timeline clip with state owned independently from transcript data."""

    id: str
    track_id: str
    start_time: float
    end_time: float
    source_path: Path | None
    source_offset: float = 0.0
    volume: float = 1.0
    muted: bool = False
    selected: bool = False
    locked: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    segment_id: int | None = None
    source_text: str = ""
    target_text: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def contains(self, position_seconds: float) -> bool:
        return self.start_time <= position_seconds < self.end_time

    def source_position_ms(self, position_ms: int) -> int:
        elapsed_seconds = max(0.0, position_ms / 1000.0 - self.start_time)
        return round((self.source_offset + elapsed_seconds) * 1000)

    def volume_at(self, position_ms: int) -> float:
        if self.muted:
            return 0.0
        position_seconds = position_ms / 1000.0
        elapsed = position_seconds - self.start_time
        remaining = self.end_time - position_seconds
        volume = self.volume
        if self.fade_in > 0 and elapsed < self.fade_in:
            volume *= max(0.0, elapsed / self.fade_in)
        if self.fade_out > 0 and remaining < self.fade_out:
            volume *= max(0.0, remaining / self.fade_out)
        return max(0.0, min(1.0, volume))


def active_clips(
    clips: list[TimelineClip], track_id: str, position_ms: int
) -> list[TimelineClip]:
    position_seconds = position_ms / 1000.0
    return [
        clip
        for clip in clips
        if clip.track_id == track_id and not clip.muted and clip.contains(position_seconds)
    ]
