"""PlaybackController: dual-audio timeline playback for Studio V3.2.

The video player is visual-only and always muted. It provides the master
timeline position and transport state. Audio playback is derived from the two
permanent timeline audio tracks:

- Original Audio: windows inside extracted `audio.wav`, generated from segment
  timing.
- Khmer TTS: existing per-segment TTS WAVs represented as `MixSpeechTrack`s.

Normal playback automatically starts/stops whichever clips are active at the
current video timeline position. Double-click audition remains a separate
single-clip preview path.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.playback.timeline_audio import (
    OriginalAudioClip,
    build_original_audio_clips,
    compute_playback_volume,
    find_active_original_clips,
    find_active_track,
    position_within_original_clip_ms,
    position_within_track_ms,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment

_SYNC_INTERVAL_MS = 100
_DRIFT_THRESHOLD_MS = 40
_LOADED = QMediaPlayer.MediaStatus.LoadedMedia


class PlaybackController(QObject):
    """Coordinates visual video playback with two timeline audio players."""

    def __init__(self, video_player: VideoPlayerWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._video_player = video_player
        self._video_player.set_audio_muted(True)

        self._original_audio_clips: list[OriginalAudioClip] = []
        self._khmer_tracks: list[MixSpeechTrack] = []
        self._active_original_clip: OriginalAudioClip | None = None
        self._active_khmer_track: MixSpeechTrack | None = None
        self._original_muted = False
        self._khmer_muted = False

        self._original_audio_player, self._original_audio_output = self._make_audio_player()
        self._khmer_audio_player, self._khmer_audio_output = self._make_audio_player()
        self._audition_player, self._audition_output = self._make_audio_player()

        self._pending_seek_ms: dict[QMediaPlayer, int] = {}
        self._pending_play: set[QMediaPlayer] = set()
        for player in (
            self._original_audio_player,
            self._khmer_audio_player,
            self._audition_player,
        ):
            player.mediaStatusChanged.connect(
                lambda status, media_player=player: self._on_audio_media_status_changed(
                    media_player, status
                )
            )

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
        original_audio_path: Path | None,
        original_segments: list[Segment],
        khmer_tracks: list[MixSpeechTrack],
    ) -> None:
        """Configure the two permanent timeline audio tracks."""
        self._video_player.set_audio_muted(True)
        self._original_audio_clips = build_original_audio_clips(
            original_audio_path, original_segments
        )
        self._khmer_tracks = khmer_tracks
        self._active_original_clip = None
        self._active_khmer_track = None
        self._sync_audio_to_position(self._video_player.position_ms, start_playing=False)

    def set_original_muted(self, muted: bool) -> None:
        self._original_muted = muted
        if muted:
            self._original_audio_player.stop()
            self._original_audio_player.setSource(QUrl())
            self._active_original_clip = None
        else:
            self._sync_audio_to_position(
                self._video_player.position_ms, start_playing=self._video_player.is_playing
            )

    def set_khmer_muted(self, muted: bool) -> None:
        self._khmer_muted = muted
        if muted:
            self._khmer_audio_player.stop()
            self._khmer_audio_player.setSource(QUrl())
            self._active_khmer_track = None
        else:
            self._sync_audio_to_position(
                self._video_player.position_ms, start_playing=self._video_player.is_playing
            )

    def play(self) -> None:
        self._video_player.play()

    def pause(self) -> None:
        self._video_player.pause()

    def stop(self) -> None:
        self._video_player.stop()

    def seek(self, position_ms: int) -> None:
        self._video_player.seek(position_ms)

    def play_clip(self, path: Path) -> None:
        """Play one clip in isolation for double-click audition."""
        self._sync_timer.stop()
        self._original_audio_player.pause()
        self._khmer_audio_player.pause()
        self._audition_output.setVolume(1.0)
        self._audition_output.setMuted(False)
        self._load_audio_source(self._audition_player, path, position_ms=0, play=True)

    def _make_audio_player(self) -> tuple[QMediaPlayer, QAudioOutput]:
        player = QMediaPlayer(self)
        output = QAudioOutput(self)
        player.setAudioOutput(output)
        return player, output

    def _load_audio_source(
        self, player: QMediaPlayer, path: Path, position_ms: int, *, play: bool
    ) -> None:
        url = QUrl.fromLocalFile(str(path))
        if player.source() == url:
            player.setPosition(position_ms)
            if play:
                player.play()
            return

        player.stop()
        self._pending_seek_ms[player] = position_ms
        if play:
            self._pending_play.add(player)
        else:
            self._pending_play.discard(player)
        player.setSource(url)

    def _on_audio_media_status_changed(
        self, player: QMediaPlayer, status: QMediaPlayer.MediaStatus
    ) -> None:
        if status != _LOADED or player not in self._pending_seek_ms:
            return
        position_ms = self._pending_seek_ms.pop(player)
        play = player in self._pending_play
        self._pending_play.discard(player)
        player.setPosition(position_ms)
        if play:
            player.play()

    def _on_play_requested(self) -> None:
        self._video_player.set_audio_muted(True)
        self._sync_audio_to_position(self._video_player.position_ms, start_playing=True)
        self._sync_timer.start()

    def _on_pause_requested(self) -> None:
        self._original_audio_player.pause()
        self._khmer_audio_player.pause()
        self._sync_timer.stop()

    def _on_stop_requested(self) -> None:
        self._original_audio_player.stop()
        self._khmer_audio_player.stop()
        self._active_original_clip = None
        self._active_khmer_track = None
        self._sync_timer.stop()

    def _on_seek_requested(self, position_ms: int) -> None:
        self._sync_audio_to_position(position_ms, start_playing=self._video_player.is_playing)

    def _on_video_position_changed(self, position_ms: int) -> None:
        if self._video_player.is_playing:
            self._maybe_resync(position_ms)

    def _on_sync_tick(self) -> None:
        self._maybe_resync(self._video_player.position_ms)

    def _maybe_resync(self, position_ms: int) -> None:
        self._sync_audio_to_position(position_ms, start_playing=self._video_player.is_playing)

    def _sync_audio_to_position(self, position_ms: int, *, start_playing: bool) -> None:
        self._video_player.set_audio_muted(True)
        self._sync_original_audio(position_ms, start_playing=start_playing)
        self._sync_khmer_audio(position_ms, start_playing=start_playing)

    def _sync_original_audio(self, position_ms: int, *, start_playing: bool) -> None:
        if self._original_muted:
            self._original_audio_player.stop()
            self._active_original_clip = None
            return

        active_clips = find_active_original_clips(self._original_audio_clips, position_ms)
        clip = active_clips[0] if active_clips else None
        if clip is None:
            self._original_audio_player.stop()
            self._active_original_clip = None
            return

        source_position_ms = position_within_original_clip_ms(clip, position_ms)
        self._original_audio_output.setMuted(False)
        self._original_audio_output.setVolume(clip.volume)
        if clip != self._active_original_clip:
            self._active_original_clip = clip
            self._load_audio_source(
                self._original_audio_player,
                clip.path,
                source_position_ms,
                play=start_playing,
            )
            return

        drift_ms = abs(self._original_audio_player.position() - source_position_ms)
        if drift_ms > _DRIFT_THRESHOLD_MS:
            self._original_audio_player.setPosition(source_position_ms)
        if start_playing:
            self._original_audio_player.play()

    def _sync_khmer_audio(self, position_ms: int, *, start_playing: bool) -> None:
        if self._khmer_muted:
            self._khmer_audio_player.stop()
            self._active_khmer_track = None
            return

        track = find_active_track(self._khmer_tracks, position_ms)
        if track is None:
            self._khmer_audio_player.stop()
            self._active_khmer_track = None
            return

        source_position_ms = position_within_track_ms(track, position_ms)
        self._khmer_audio_output.setMuted(False)
        self._khmer_audio_output.setVolume(compute_playback_volume(track, position_ms))
        if track is not self._active_khmer_track:
            self._active_khmer_track = track
            self._load_audio_source(
                self._khmer_audio_player,
                track.tts_path,
                source_position_ms,
                play=start_playing,
            )
            return

        drift_ms = abs(self._khmer_audio_player.position() - source_position_ms)
        if drift_ms > _DRIFT_THRESHOLD_MS:
            self._khmer_audio_player.setPosition(source_position_ms)
        if start_playing:
            self._khmer_audio_player.play()
