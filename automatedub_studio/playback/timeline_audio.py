"""Pure timing logic for Timeline Preview playback.

No export, no rebuild, no FFmpeg: these functions only compute where each
already-generated TTS clip sits on the master (video) timeline given the
same per-segment offset/speed/volume/fade metadata the mix/export backend
uses, so switching to Timeline Preview never regenerates or remixes audio.
"""

from __future__ import annotations

from automatedub.vertical_slice.mix import MixSpeechTrack


def track_window_ms(track: MixSpeechTrack) -> tuple[int, int]:
    """Return (start_ms, end_ms) of a track's playback window on the master timeline."""
    playback_duration_ms = (
        track.generated_duration / track.atempo * 1000.0
        if track.atempo > 0
        else track.generated_duration * 1000.0
    )
    start_ms = track.delay_ms
    return start_ms, start_ms + round(playback_duration_ms)


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
    """Map a master-timeline position to a position within the source WAV.

    `atempo` speeds up (or slows down) the source clip, so one second of
    master-timeline elapsed time corresponds to `atempo` seconds of source
    audio.
    """
    start_ms, _ = track_window_ms(track)
    elapsed_master_ms = max(0, position_ms - start_ms)
    return round(elapsed_master_ms * track.atempo)
