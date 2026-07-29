"""Pure timing logic for Studio timeline playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.project.models import Segment


@dataclass(frozen=True)
class OriginalAudioClip:
    id: int
    path: Path
    start_ms: int
    end_ms: int
    source_start_ms: int
    volume: float = 1.0


def build_original_audio_clips(
    audio_path: Path | None, segments: list[Segment]
) -> list[OriginalAudioClip]:
    """Build timeline clips referencing windows inside the extracted source audio."""
    if audio_path is None:
        return []
    clips = []
    for segment in sorted(segments, key=lambda item: (item.start, item.id)):
        duration_ms = max(0, round((segment.end - segment.start) * 1000))
        timeline_start_ms = round(segment.start * 1000) + segment.offset_ms
        clips.append(
            OriginalAudioClip(
                id=segment.id,
                path=audio_path,
                start_ms=timeline_start_ms,
                end_ms=timeline_start_ms + duration_ms,
                source_start_ms=round(segment.start * 1000),
            )
        )
    return clips


def find_active_original_clips(
    clips: list[OriginalAudioClip], position_ms: int
) -> list[OriginalAudioClip]:
    """Return Original Audio clips active at a master timeline position."""
    return [clip for clip in clips if clip.start_ms <= position_ms < clip.end_ms]


def position_within_original_clip_ms(clip: OriginalAudioClip, position_ms: int) -> int:
    """Map master timeline position to the corresponding source audio position."""
    return clip.source_start_ms + max(0, position_ms - clip.start_ms)


def track_window_ms(track: MixSpeechTrack) -> tuple[int, int]:
    """Return (start_ms, end_ms) of a track's playback window on the master timeline."""
    start_ms = track.delay_ms
    return start_ms, start_ms + round(track.generated_duration * 1000.0)


def find_active_track(
    tracks: list[MixSpeechTrack], position_ms: int
) -> MixSpeechTrack | None:
    """Return the track whose playback window contains `position_ms`, if any.

    Tracks are assumed to not meaningfully overlap; if they do, the first
    match (by list order) wins.
    """
    for track in tracks:
        start_ms, end_ms = track_window_ms(track)
        if start_ms <= position_ms < end_ms:
            return track
    return None


def compute_playback_volume(track: MixSpeechTrack, position_ms: int) -> float:
    """Apply the track's base volume plus linear fade-in/fade-out ramps."""
    start_ms, end_ms = track_window_ms(track)
    elapsed_ms = position_ms - start_ms
    remaining_ms = end_ms - position_ms

    volume = track.volume
    if track.fade_in_ms > 0 and elapsed_ms < track.fade_in_ms:
        volume *= max(0.0, elapsed_ms / track.fade_in_ms)
    if track.fade_out_ms > 0 and remaining_ms < track.fade_out_ms:
        volume *= max(0.0, remaining_ms / track.fade_out_ms)
    return max(0.0, min(1.0, volume))


def position_within_track_ms(track: MixSpeechTrack, position_ms: int) -> int:
    """Map a master-timeline position to a position within the source WAV."""
    start_ms, _ = track_window_ms(track)
    elapsed_master_ms = max(0, position_ms - start_ms)
    return elapsed_master_ms
