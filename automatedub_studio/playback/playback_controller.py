"""PlaybackController: generic timeline playback for Studio.

The video player is visual-only and always muted. It provides the master
timeline position and transport state. Audio playback is derived from all
audio tracks in the editor Timeline model.

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
    build_khmer_timeline_clips,
    build_original_audio_clips,
    build_original_timeline_clips,
    find_active_original_clips,
    find_active_track,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)

_SYNC_INTERVAL_MS = 100
_DRIFT_THRESHOLD_MS = 500
_LOADED = QMediaPlayer.MediaStatus.LoadedMedia


class PlaybackController(QObject):
    """Coordinates visual video playback with generic timeline audio players."""

    def __init__(self, video_player: VideoPlayerWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._video_player = video_player
        self._video_player.set_audio_muted(True)

        self._original_audio_clips: list[OriginalAudioClip] = []
        self._khmer_tracks: list[MixSpeechTrack] = []
        self._timeline = Timeline.default()
        self._timeline_clips: list[TimelineClip] = []
        self._active_original_clip: OriginalAudioClip | None = None
        self._active_khmer_track: MixSpeechTrack | None = None
        self._active_original_timeline_clip: TimelineClip | None = None
        self._active_khmer_clip_ids: set[str] = set()
        self._original_muted = False
        self._khmer_muted = False
        self._track_mutes: dict[str, bool] = {}

        self._original_audio_player, self._original_audio_output = self._make_audio_player()
        self._khmer_audio_player, self._khmer_audio_output = self._make_audio_player()
        self._audition_player, self._audition_output = self._make_audio_player()
        self._khmer_clip_players: dict[str, tuple[QMediaPlayer, QAudioOutput]] = {}

        self._pending_seek_ms: dict[QMediaPlayer, int] = {}
        self._pending_play: set[QMediaPlayer] = set()
        for player in (
            self._original_audio_player,
            self._khmer_audio_player,
            self._audition_player,
        ):
            self._connect_audio_player(player)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(_SYNC_INTERVAL_MS)
        self._sync_timer.timeout.connect(self._on_sync_tick)

        self._video_player.videoPositionChanged.connect(self._on_video_position_changed)
        self._video_player.playRequested.connect(self._on_play_requested)
        self._video_player.pauseRequested.connect(self._on_pause_requested)
        self._video_player.stopRequested.connect(self._on_stop_requested)
        self._video_player.seekRequested.connect(self._on_seek_requested)

    def _connect_audio_player(self, player: QMediaPlayer) -> None:
        player.mediaStatusChanged.connect(
            lambda status, media_player=player: self._on_audio_media_status_changed(
                media_player, status
            )
        )

    def set_sources(
        self,
        original_audio_path: Path | None,
        original_segments: list[Segment],
        khmer_tracks: list[MixSpeechTrack],
    ) -> None:
        """Compatibility adapter from import/export artifacts to timeline clips."""
        self._original_audio_clips = build_original_audio_clips(
            original_audio_path, original_segments
        )
        self._khmer_tracks = khmer_tracks
        self.set_timeline_clips(
            [
            *build_original_timeline_clips(original_audio_path, original_segments),
            *build_khmer_timeline_clips(khmer_tracks),
            ]
        )

    def set_timeline_clips(self, timeline_clips: list[TimelineClip]) -> None:
        """Configure playback from the editor's TimelineClip source of truth."""
        self.set_timeline(Timeline.from_clips(timeline_clips))

    def set_timeline(self, timeline: Timeline) -> None:
        """Configure playback from the editor's generic Timeline source of truth."""
        self._video_player.set_audio_muted(True)
        self._timeline = timeline
        self._apply_compat_track_mutes()
        self._timeline_clips = timeline.all_clips()
        self._configure_timeline_clip_players()
        self._active_original_clip = None
        self._active_khmer_track = None
        self._active_original_timeline_clip = None
        self._active_khmer_clip_ids = set()
        self._sync_audio_to_position(self._video_player.position_ms, start_playing=False)

    def set_original_muted(self, muted: bool) -> None:
        self._original_muted = muted
        self.set_track_muted(ORIGINAL_AUDIO_TRACK_ID, muted)
        if muted:
            self._stop_player(self._original_audio_player)
            self._original_audio_player.setSource(QUrl())
            self._active_original_clip = None
        else:
            self._sync_audio_to_position(
                self._video_player.position_ms, start_playing=self._video_player.is_playing
            )

    def set_khmer_muted(self, muted: bool) -> None:
        self._khmer_muted = muted
        self.set_track_muted(KHMER_TTS_TRACK_ID, muted)
        if muted:
            for player, _output in self._khmer_clip_players.values():
                self._stop_player(player)
            for clip_id, (player, _output) in self._khmer_clip_players.items():
                clip = next(
                    (item for item in self._timeline_clips if item.id == clip_id),
                    None,
                )
                if clip is not None and clip.track_id == KHMER_TTS_TRACK_ID:
                    player.setSource(QUrl())
            self._active_khmer_track = None
            self._active_khmer_clip_ids = set()
        else:
            self._configure_timeline_clip_players()
            self._sync_audio_to_position(
                self._video_player.position_ms, start_playing=self._video_player.is_playing
            )

    def set_track_muted(self, track_id: str, muted: bool) -> None:
        self._track_mutes[track_id] = muted
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.muted = muted

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.solo = solo

    def play(self) -> None:
        self._video_player.play()

    def toggle_play_pause(self) -> None:
        if self._video_player.is_playing:
            self.pause()
        else:
            self.play()

    def pause(self) -> None:
        self._video_player.pause()

    def stop(self) -> None:
        self._video_player.stop()

    def seek(self, position_ms: int) -> None:
        self._video_player.seek(position_ms)

    def play_clip(self, path: Path) -> None:
        """Play one clip in isolation for double-click audition."""
        self._sync_timer.stop()
        self._pause_player(self._original_audio_player)
        for player, _output in self._khmer_clip_players.values():
            self._pause_player(player)
        self._audition_output.setVolume(1.0)
        self._audition_output.setMuted(False)
        self._load_audio_source(self._audition_player, path, position_ms=0, play=True)

    def _make_audio_player(self) -> tuple[QMediaPlayer, QAudioOutput]:
        player = QMediaPlayer(self)
        output = QAudioOutput(self)
        player.setAudioOutput(output)
        return player, output

    def _configure_timeline_clip_players(self) -> None:
        """Preload audio clip sources into reusable clip-scoped players."""
        audio_clips = [
            clip
            for clip in self._timeline_clips
            if clip.track_id != "video" and clip.source_path is not None
        ]
        wanted_ids = {clip.id for clip in audio_clips}
        for clip_id in list(self._khmer_clip_players):
            if clip_id not in wanted_ids:
                player, _output = self._khmer_clip_players.pop(clip_id)
                self._stop_player(player)
                player.setSource(QUrl())

        for clip in audio_clips:
            if clip.id in self._khmer_clip_players:
                player, _output = self._khmer_clip_players[clip.id]
            elif clip.track_id == ORIGINAL_AUDIO_TRACK_ID and not any(
                player is self._original_audio_player
                for player, _output in self._khmer_clip_players.values()
            ):
                player, output = self._original_audio_player, self._original_audio_output
                self._khmer_clip_players[clip.id] = (player, output)
            elif not any(
                player is self._khmer_audio_player
                for player, _output in self._khmer_clip_players.values()
            ):
                player, output = self._khmer_audio_player, self._khmer_audio_output
                self._khmer_clip_players[clip.id] = (player, output)
            else:
                player, output = self._make_audio_player()
                self._connect_audio_player(player)
                self._khmer_clip_players[clip.id] = (player, output)
            url = QUrl.fromLocalFile(str(clip.source_path))
            if player.source() != url:
                self._stop_player(player)
                self._pending_seek_ms[player] = 0
                self._pending_play.discard(player)
                player.setSource(url)

    def _apply_compat_track_mutes(self) -> None:
        for track_id, muted in self._track_mutes.items():
            track = self._timeline.track_by_id(track_id)
            if track is not None:
                track.muted = muted

    def _load_audio_source(
        self,
        player: QMediaPlayer,
        path: Path,
        position_ms: int,
        *,
        play: bool,
        force_seek: bool = False,
    ) -> None:
        url = QUrl.fromLocalFile(str(path))
        if player.source() == url:
            self._seek_if_needed(player, position_ms, force=force_seek)
            if play:
                self._request_play(player)
            return

        self._stop_player(player)
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
            self._play_if_needed(player)

    def _on_play_requested(self) -> None:
        self._video_player.set_audio_muted(True)
        self._sync_audio_to_position(
            self._video_player.position_ms, start_playing=True, force_seek=True
        )
        self._sync_timer.start()

    def _on_pause_requested(self) -> None:
        self._pause_player(self._original_audio_player)
        for player, _output in self._khmer_clip_players.values():
            self._pause_player(player)
        self._sync_timer.stop()

    def _on_stop_requested(self) -> None:
        self._stop_player(self._original_audio_player)
        for player, _output in self._khmer_clip_players.values():
            self._stop_player(player)
        self._active_original_clip = None
        self._active_khmer_track = None
        self._active_khmer_clip_ids = set()
        self._sync_timer.stop()

    def _on_seek_requested(self, position_ms: int) -> None:
        self._sync_audio_to_position(
            position_ms, start_playing=self._video_player.is_playing, force_seek=True
        )

    def _on_video_position_changed(self, position_ms: int) -> None:
        if self._video_player.is_playing:
            self._maybe_resync(position_ms)

    def _on_sync_tick(self) -> None:
        self._maybe_resync(self._video_player.position_ms)

    def _maybe_resync(self, position_ms: int) -> None:
        self._sync_audio_to_position(position_ms, start_playing=self._video_player.is_playing)

    def _sync_audio_to_position(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        self._video_player.set_audio_muted(True)
        self._sync_timeline_audio(
            position_ms, start_playing=start_playing, force_seek=force_seek
        )

    def _sync_original_audio(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        self._sync_timeline_audio(
            position_ms, start_playing=start_playing, force_seek=force_seek
        )

    def _sync_khmer_audio(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        self._sync_timeline_audio(
            position_ms, start_playing=start_playing, force_seek=force_seek
        )

    def _sync_timeline_audio(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        current_active = {
            clip.id: clip
            for clip in self._active_audio_clips(position_ms)
            if clip.source_path is not None
        }
        for clip_id, (player, _output) in self._khmer_clip_players.items():
            if clip_id not in current_active:
                self._stop_player(player)
        for clip_id, clip in current_active.items():
            player, output = self._khmer_clip_players.get(
                clip_id, (self._khmer_audio_player, self._khmer_audio_output)
            )
            source_position_ms = clip.source_position_ms(position_ms)
            output.setMuted(False)
            output.setVolume(clip.volume_at(position_ms))
            if clip.source_path is not None:
                url = QUrl.fromLocalFile(str(clip.source_path))
                if player.source() != url:
                    self._load_audio_source(
                        player,
                        clip.source_path,
                        source_position_ms,
                        play=start_playing,
                        force_seek=True,
                    )
                    continue
            if clip_id not in self._active_khmer_clip_ids:
                self._seek_if_needed(player, source_position_ms, force=True)
            else:
                self._seek_if_needed(player, source_position_ms, force=force_seek)
            if start_playing:
                self._request_play(player)
        self._active_khmer_clip_ids = set(current_active)

        original_clips = [
            clip for clip in current_active.values() if clip.track_id == ORIGINAL_AUDIO_TRACK_ID
        ]
        self._active_original_timeline_clip = original_clips[0] if original_clips else None
        legacy_active = find_active_original_clips(self._original_audio_clips, position_ms)
        self._active_original_clip = (
            legacy_active[0]
            if self._active_original_timeline_clip is not None and legacy_active
            else None
        )
        self._active_khmer_track = (
            find_active_track(self._khmer_tracks, position_ms)
            if any(clip.track_id == KHMER_TTS_TRACK_ID for clip in current_active.values())
            else None
        )

    def _active_audio_clips(self, position_ms: int) -> list[TimelineClip]:
        if self._timeline.all_clips():
            return self._timeline.active_audio_clips(position_ms)
        return [
            clip
            for clip in self._timeline_clips
            if clip.track_id != "video"
            and not clip.muted
            and clip.source_path is not None
            and clip.contains(position_ms / 1000.0)
        ]

    def _seek_if_needed(self, player: QMediaPlayer, position_ms: int, *, force: bool) -> None:
        if player in self._pending_seek_ms:
            if force or abs(self._pending_seek_ms[player] - position_ms) > _DRIFT_THRESHOLD_MS:
                self._pending_seek_ms[player] = position_ms
            return
        if force or abs(player.position() - position_ms) > _DRIFT_THRESHOLD_MS:
            player.setPosition(position_ms)

    def _request_play(self, player: QMediaPlayer) -> None:
        if player in self._pending_seek_ms:
            self._pending_play.add(player)
            return
        self._play_if_needed(player)

    @staticmethod
    def _play_if_needed(player: QMediaPlayer) -> None:
        if player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            player.play()

    @staticmethod
    def _pause_player(player: QMediaPlayer) -> None:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()

    @staticmethod
    def _stop_player(player: QMediaPlayer) -> None:
        if player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            player.stop()
