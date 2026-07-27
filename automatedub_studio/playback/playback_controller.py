"""PlaybackController: video-as-master-clock playback for Studio V2.

The video is always played from `video.mp4` and is the single authoritative
playback clock (position + play/pause/stop state). Audio always follows the
video's position rather than driving it, per four selectable modes:

- ORIGINAL: the video's own embedded audio (no separate audio player).
- MIXED: `mixed_audio.wav` played through a companion QMediaPlayer.
- KHMER_TTS: `tts_combined.wav` played through a companion QMediaPlayer.
- TIMELINE_PREVIEW: individual per-segment TTS clips played directly from
  the timeline, using the same offset/speed/volume/fade metadata the export
  pipeline uses (`MixSpeechTrack`, via `timeline_audio.py`). No mixing, no
  regeneration, no FFmpeg: this mode only decides, moment to moment, which
  already-generated clip file should be sounding and at what volume.

Switching modes never restarts or resets the master clock position: the
video keeps playing (or stays paused/stopped) exactly where it was, and only
the audio source swaps.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.playback.timeline_audio import (
    compute_playback_volume,
    find_active_track,
    position_within_track_ms,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget

_SYNC_INTERVAL_MS = 100
_DRIFT_THRESHOLD_MS = 40
_LOADED = QMediaPlayer.MediaStatus.LoadedMedia


class PlaybackMode(StrEnum):
    ORIGINAL = "original"
    MIXED = "mixed"
    KHMER_TTS = "khmer_tts"
    TIMELINE_PREVIEW = "timeline_preview"


class PlaybackController(QObject):
    """Coordinates a `VideoPlayerWidget` (master clock) with a companion
    audio player, keeping audio in sync with the video across mode switches.
    """

    def __init__(self, video_player: VideoPlayerWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._video_player = video_player
        self._mode = PlaybackMode.ORIGINAL

        self._mixed_audio_path: Path | None = None
        self._khmer_audio_path: Path | None = None
        self._timeline_tracks: list[MixSpeechTrack] = []
        self._active_timeline_track: MixSpeechTrack | None = None

        self._audio_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_player.setAudioOutput(self._audio_output)
        self._audio_player.mediaStatusChanged.connect(self._on_audio_media_status_changed)
        self._pending_seek_ms: int | None = None
        self._pending_play = False

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(_SYNC_INTERVAL_MS)
        self._sync_timer.timeout.connect(self._on_sync_tick)

        self._video_player.videoPositionChanged.connect(self._on_video_position_changed)
        self._video_player.playRequested.connect(self._on_play_requested)
        self._video_player.pauseRequested.connect(self._on_pause_requested)
        self._video_player.stopRequested.connect(self._on_stop_requested)
        self._video_player.seekRequested.connect(self._on_seek_requested)

    def set_sources(
        self,
        mixed_audio_path: Path | None,
        khmer_audio_path: Path | None,
        timeline_tracks: list[MixSpeechTrack],
    ) -> None:
        """Configure the audio sources available for each mode.

        Call this once the project (and its `EditableSegment` edits) are
        loaded. `timeline_tracks` should come from
        `export_service.build_export_speech_tracks()` so Timeline Preview
        always reflects the current offsets/speed/volume/fades.
        """
        self._mixed_audio_path = mixed_audio_path
        self._khmer_audio_path = khmer_audio_path
        self._timeline_tracks = timeline_tracks
        self._active_timeline_track = None
        self._apply_mode()

    @property
    def mode(self) -> PlaybackMode:
        return self._mode

    def set_mode(self, mode: PlaybackMode) -> None:
        """Switch audio source without touching the master clock position."""
        if mode == self._mode:
            return
        self._mode = mode
        self._apply_mode()

    def play(self) -> None:
        self._video_player.play()

    def pause(self) -> None:
        self._video_player.pause()

    def stop(self) -> None:
        self._video_player.stop()

    def seek(self, position_ms: int) -> None:
        """Scrub: reposition both video and the active audio source."""
        self._video_player.seek(position_ms)

    def _on_play_requested(self) -> None:
        self._start_audio_for_current_position()
        self._sync_timer.start()

    def _on_pause_requested(self) -> None:
        self._audio_player.pause()
        self._sync_timer.stop()

    def _on_stop_requested(self) -> None:
        self._audio_player.stop()
        self._active_timeline_track = None
        self._sync_timer.stop()

    def _on_seek_requested(self, position_ms: int) -> None:
        self._sync_audio_to_position(position_ms)

    def play_clip(self, path: Path) -> None:
        """Play a single clip's audio in isolation (no video required).

        Used for auditioning a timeline clip (e.g. after regeneration)
        without affecting the master clock or any other playback mode.
        """
        self._sync_timer.stop()
        self._audio_output.setVolume(1.0)
        self._load_audio_source(path, position_ms=0, play=True)

    def _load_audio_source(self, path: Path, position_ms: int, *, play: bool) -> None:
        """Set the audio player's source and seek to `position_ms`.

        `QMediaPlayer.setPosition()` is silently dropped while the source is
        still `LoadingMedia`, so a fresh source always defers the seek (and
        optional play) until `_on_audio_media_status_changed` observes
        `LoadedMedia`.
        """
        url = QUrl.fromLocalFile(str(path))
        if self._audio_player.source() == url:
            self._audio_player.setPosition(position_ms)
            if play:
                self._audio_player.play()
            return

        self._audio_player.stop()
        self._pending_seek_ms = position_ms
        self._pending_play = play
        self._audio_player.setSource(url)

    def _on_audio_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != _LOADED or self._pending_seek_ms is None:
            return
        position_ms = self._pending_seek_ms
        play = self._pending_play
        self._pending_seek_ms = None
        self._pending_play = False
        self._audio_player.setPosition(position_ms)
        if play:
            self._audio_player.play()

    def _apply_mode(self) -> None:
        video_muted = self._mode != PlaybackMode.ORIGINAL
        self._video_player.set_audio_muted(video_muted)

        self._active_timeline_track = None
        was_playing = self._video_player.is_playing
        self._audio_player.stop()

        if was_playing:
            self._start_audio_for_current_position()
            self._sync_timer.start()
        else:
            self._sync_audio_to_position(self._video_player.position_ms)

    def _source_path_for_mode(self) -> Path | None:
        if self._mode == PlaybackMode.MIXED:
            return self._mixed_audio_path
        if self._mode == PlaybackMode.KHMER_TTS:
            return self._khmer_audio_path
        return None

    def _start_audio_for_current_position(self) -> None:
        position_ms = self._video_player.position_ms
        if self._mode == PlaybackMode.TIMELINE_PREVIEW:
            self._update_timeline_preview(position_ms, start_playing=True)
            return

        source_path = self._source_path_for_mode()
        if source_path is None:
            return
        self._audio_output.setMuted(False)
        self._load_audio_source(source_path, position_ms, play=True)

    def _on_video_position_changed(self, position_ms: int) -> None:
        if not self._video_player.is_playing:
            return
        self._maybe_resync(position_ms)

    def _on_sync_tick(self) -> None:
        self._maybe_resync(self._video_player.position_ms)

    def _maybe_resync(self, position_ms: int) -> None:
        if self._mode == PlaybackMode.TIMELINE_PREVIEW:
            self._update_timeline_preview(position_ms, start_playing=True)
            return
        if self._mode == PlaybackMode.ORIGINAL:
            return
        if self._audio_player.source().isEmpty():
            return
        drift_ms = abs(self._audio_player.position() - position_ms)
        if drift_ms > _DRIFT_THRESHOLD_MS:
            self._audio_player.setPosition(position_ms)

    def _sync_audio_to_position(self, position_ms: int) -> None:
        if self._mode == PlaybackMode.TIMELINE_PREVIEW:
            self._update_timeline_preview(position_ms, start_playing=False)
            return
        source_path = self._source_path_for_mode()
        if source_path is None:
            return
        self._load_audio_source(source_path, position_ms, play=False)

    def _update_timeline_preview(self, position_ms: int, *, start_playing: bool) -> None:
        track = find_active_track(self._timeline_tracks, position_ms)

        if track is None:
            if self._active_timeline_track is not None:
                self._audio_player.stop()
                self._active_timeline_track = None
            return

        if track is not self._active_timeline_track:
            self._active_timeline_track = track
            self._audio_output.setMuted(False)
            self._audio_output.setVolume(compute_playback_volume(track, position_ms))
            self._load_audio_source(
                track.tts_path, position_within_track_ms(track, position_ms), play=start_playing
            )
        else:
            drift_ms = abs(
                self._audio_player.position() - position_within_track_ms(track, position_ms)
            )
            if drift_ms > _DRIFT_THRESHOLD_MS:
                self._audio_player.setPosition(position_within_track_ms(track, position_ms))
            self._audio_output.setVolume(compute_playback_volume(track, position_ms))
