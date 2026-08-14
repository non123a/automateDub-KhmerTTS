"""PlaybackController: generic timeline playback for Studio.

The video player is visual-only and always muted. It provides the master
timeline position and transport state. Audio playback is derived from all
audio tracks in the editor Timeline model.

Normal playback automatically starts/stops whichever clips are active at the
current video timeline position. Double-click audition remains a separate
single-clip preview path.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.timeline.timeline_clip import (
    ORIGINAL_AUDIO_TRACK_ID,
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
    AudioClipIntervalIndex,
    Timeline,
    TimelineClip,
)

_SYNC_INTERVAL_MS = 100
_DRIFT_THRESHOLD_MS = 500
_LOADED = QMediaPlayer.MediaStatus.LoadedMedia
_ORIGINAL_AUDIO_TRACE_ENABLED = "AUTOMATEDUB_ORIGINAL_AUDIO_TRACE"


class PlaybackController(QObject):
    """Coordinates visual video playback with generic timeline audio players."""

    def __init__(self, video_player: VideoPlayerWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._video_player = video_player
        self._video_player.set_audio_muted(True)

        self._timeline = Timeline.default()
        self._timeline_clips: list[TimelineClip] = []
        self._audio_index = AudioClipIntervalIndex([])
        self._active_khmer_clip_ids: set[str] = set()
        self._playback_rate = 1.0
        self._loop_selection_enabled = False
        self._shutdown = False

        # Original Movie Audio is optional and owns no player until inserted.
        self._original_audio_player: QMediaPlayer | None = None
        self._original_audio_output: QAudioOutput | None = None
        self._khmer_audio_player, self._khmer_audio_output = self._make_audio_player()
        self._audition_player, self._audition_output = self._make_audio_player()
        self._available_audio_players: list[tuple[QMediaPlayer, QAudioOutput]] = [
            (self._khmer_audio_player, self._khmer_audio_output)
        ]
        self._all_pool_players = list(self._available_audio_players)
        self._khmer_clip_players: dict[str, tuple[QMediaPlayer, QAudioOutput]] = {}
        self._clip_source_fingerprints: dict[str, tuple[Path, int | None, int | None]] = {}

        # Opt-in performance counters.  These stay in memory during normal use
        # and are sampled by the editor diagnostics layer when enabled.
        self._tick_count = 0
        self._tick_total_seconds = 0.0
        self._tick_worst_seconds = 0.0
        self._lookup_total_seconds = 0.0
        self._play_request_started: float | None = None
        self._first_play_lookup_seconds = 0.0
        self._first_play_active_players = 0

        self._pending_seek_ms: dict[QMediaPlayer, int] = {}
        self._pending_play: set[QMediaPlayer] = set()
        self._audio_outputs_by_player: dict[QMediaPlayer, QAudioOutput] = {}
        self._audio_player_labels: dict[QMediaPlayer, str] = {}
        self._player_clip_ids: dict[QMediaPlayer, str] = {}
        self._trace_original_audio_path: Path | None = None
        self._trace_original_audio_events: list[dict[str, Any]] = []
        self._trace_original_audio_sequence = 0
        for player, output, label in (
            (self._khmer_audio_player, self._khmer_audio_output, "shared_timeline_audio_player"),
            (self._audition_player, self._audition_output, "audition_player"),
        ):
            self._connect_audio_player(player, output, label)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(_SYNC_INTERVAL_MS)
        self._sync_timer.timeout.connect(self._on_sync_tick)

        self._video_player.videoPositionChanged.connect(self._on_video_position_changed)
        self._video_player.playRequested.connect(self._on_play_requested)
        self._video_player.pauseRequested.connect(self._on_pause_requested)
        self._video_player.stopRequested.connect(self._on_stop_requested)
        self._video_player.seekRequested.connect(self._on_seek_requested)

    def _connect_audio_player(
        self, player: QMediaPlayer, output: QAudioOutput, label: str
    ) -> None:
        self._audio_outputs_by_player[player] = output
        self._audio_player_labels[player] = label
        player.mediaStatusChanged.connect(
            lambda status, media_player=player: self._on_audio_media_status_signal(
                media_player, status
            )
        )
        player.playbackStateChanged.connect(
            lambda state, media_player=player: self._trace_qmedia_player_event(
                media_player, "playbackStateChanged", playback_state=self._enum_name(state)
            )
        )
        player.positionChanged.connect(
            lambda position, media_player=player: self._trace_qmedia_player_event(
                media_player, "positionChanged", position_ms=int(position)
            )
        )
        player.errorOccurred.connect(
            lambda error, error_string="", media_player=player: self._trace_qmedia_player_event(
                media_player,
                "errorOccurred",
                error=self._enum_name(error),
                error_string=str(error_string),
            )
        )
        player.durationChanged.connect(
            lambda duration, media_player=player: self._trace_qmedia_player_event(
                media_player, "durationChanged", duration_ms=int(duration)
            )
        )

    def _apply_playback_rate(self, rate: float) -> None:
        self._video_player.set_playback_rate(rate)
        players = [self._audition_player, *[player for player, _ in self._all_pool_players]]
        if self._original_audio_player is not None:
            players.append(self._original_audio_player)
        for player in players:
            if hasattr(player, "setPlaybackRate"):
                player.setPlaybackRate(rate)

    def set_timeline_clips(self, timeline_clips: list[TimelineClip]) -> None:
        self.set_timeline(Timeline.from_clips(timeline_clips))

    def set_timeline(self, timeline: Timeline) -> None:
        self._video_player.set_audio_muted(True)
        self._timeline = timeline
        self._timeline_clips = timeline.all_clips()
        audio_tracks = [
            track
            for track in timeline.tracks
            if track.is_audio and not track.reference_only and not track.muted
        ]
        soloed_track_ids = {track.id for track in audio_tracks if track.solo}
        if soloed_track_ids:
            audio_tracks = [
                track for track in audio_tracks if track.id in soloed_track_ids
            ]
        self._audio_index = AudioClipIntervalIndex(
            [
                clip
                for track in audio_tracks
                for clip in track.clips
                if clip.source_path is not None
                and not clip.muted
                and (clip.segment_id is None or clip.source_path.is_file())
            ]
        )
        self._ensure_original_audio_trace_path_from_timeline()
        self._apply_playback_rate(self._playback_rate)
        valid_clip_ids = {
            clip.id for clip in self._audio_index.active_at(self._video_player.position_ms)
        }
        for clip_id in list(self._khmer_clip_players):
            if clip_id not in valid_clip_ids:
                self._release_audio_player(clip_id)
        self._active_khmer_clip_ids.clear()
        self._sync_audio_to_position(
            self._video_player.position_ms,
            start_playing=self._video_player.is_playing,
        )

    def set_playback_rate(self, rate: float) -> None:
        self._playback_rate = max(0.25, min(4.0, rate))
        self._apply_playback_rate(self._playback_rate)

    def set_loop_selection_enabled(self, enabled: bool) -> None:
        self._loop_selection_enabled = enabled

    def step_frame(self, direction: int = 1) -> None:
        frame_ms = 33
        self.seek(max(0, self._video_player.position_ms + frame_ms * direction))

    def previous_segment(self) -> None:
        position_ms = self._video_player.position_ms
        starts = [
            round(clip.start_time * 1000)
            for clip in self._timeline.all_clips()
            if round(clip.start_time * 1000) < position_ms
        ]
        if starts:
            self.seek(max(starts))

    def next_segment(self) -> None:
        position_ms = self._video_player.position_ms
        starts = [
            round(clip.start_time * 1000)
            for clip in self._timeline.all_clips()
            if round(clip.start_time * 1000) > position_ms
        ]
        if starts:
            self.seek(min(starts))

    def set_original_muted(self, muted: bool) -> None:
        self.set_track_muted("original_audio", muted)
        self._sync_audio_to_position(
            self._video_player.position_ms, start_playing=self._video_player.is_playing
        )

    def set_khmer_muted(self, muted: bool) -> None:
        self.set_track_muted("khmer_tts", muted)
        self._sync_audio_to_position(
            self._video_player.position_ms, start_playing=self._video_player.is_playing
        )

    def set_track_muted(self, track_id: str, muted: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.muted = muted
            self.set_timeline(self._timeline)

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.solo = solo
            self.set_timeline(self._timeline)

    def play(self) -> None:
        self._video_player.play()

    def toggle_play_pause(self) -> None:
        if self._video_player.is_playing:
            self.pause()
        else:
            self.play()

    def pause(self) -> None:
        self._video_player.pause()

    def pause_for_export(self) -> None:
        """Pause active editor media while preserving the playhead for export."""
        self.pause()
        self._pause_player(self._audition_player)

    def stop(self) -> None:
        self._video_player.stop()

    def seek(self, position_ms: int) -> None:
        self._video_player.seek(position_ms)

    def play_clip(self, path: Path) -> None:
        """Play one clip in isolation for double-click audition."""
        self._sync_timer.stop()
        if self._original_audio_player is not None:
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
        player.setPlaybackRate(self._playback_rate)
        return player, output

    @staticmethod
    def _enum_name(value: object) -> str:
        return getattr(value, "name", str(value))

    def _trace_player_replacement(self, player: QMediaPlayer, clip: TimelineClip) -> None:
        previous_clip_id = self._player_clip_ids.get(player)
        if previous_clip_id is None or previous_clip_id == clip.id:
            return
        self._trace_qmedia_player_event(
            player,
            "player_source_replaced_before_playback",
            clip=clip,
            previous_clip_id=previous_clip_id,
            replacement_clip_id=clip.id,
            replacement_source=str(clip.source_path) if clip.source_path else None,
        )

    def _trace_original_clip_should_play(
        self,
        clip: TimelineClip,
        player: QMediaPlayer,
        *,
        position_ms: int,
        source_position_ms: int,
    ) -> None:
        if not self._is_original_speech_clip(clip):
            return
        elapsed_seconds = max(0.0, position_ms / 1000.0 - clip.start_time)
        self._ensure_original_audio_trace_path(clip)
        self._trace_qmedia_player_event(
            player,
            "original_speech_clip_should_play",
            clip=clip,
            source_path=str(clip.source_path) if clip.source_path else None,
            source_offset=clip.source_offset,
            elapsed_seconds=elapsed_seconds,
            computed_seek_position_ms=source_position_ms,
            timeline_position_ms=position_ms,
        )

    @staticmethod
    def _is_original_speech_clip(clip: TimelineClip) -> bool:
        return clip.track_id == ORIGINAL_AUDIO_TRACK_ID and clip.segment_id is not None

    def _ensure_original_audio_trace_path(self, clip: TimelineClip) -> None:
        if self._trace_original_audio_path is not None or clip.source_path is None:
            return
        if clip.source_path.parent.name == "pipeline":
            trace_dir = clip.source_path.parent / "debug"
        else:
            trace_dir = clip.source_path.parent
        self._trace_original_audio_path = trace_dir / "original_audio_playback_trace.json"

    def _ensure_original_audio_trace_path_from_timeline(self) -> None:
        if self._trace_original_audio_path is not None:
            return
        for clip in self._timeline.all_clips():
            if self._is_original_speech_clip(clip) and clip.source_path is not None:
                self._ensure_original_audio_trace_path(clip)
                return

    def _trace_qmedia_player_event(
        self,
        player: QMediaPlayer,
        event: str,
        *,
        clip: TimelineClip | None = None,
        **details: Any,
    ) -> None:
        # This trace rewrites a growing JSON file for every Qt media signal.
        # It is forensic instrumentation, never normal editor work.
        if os.environ.get(_ORIGINAL_AUDIO_TRACE_ENABLED) != "1":
            return
        if clip is not None and self._is_original_speech_clip(clip):
            self._ensure_original_audio_trace_path(clip)
        if self._trace_original_audio_path is None:
            return
        self._trace_original_audio_sequence += 1
        record: dict[str, Any] = {
            "sequence": self._trace_original_audio_sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "player_id": hex(id(player)),
            "player_label": self._audio_player_labels.get(player, "timeline_audio_player"),
            "associated_clip_id": self._player_clip_ids.get(player),
        }
        if clip is not None:
            record["clip"] = {
                "id": clip.id,
                "track_id": clip.track_id,
                "segment_id": clip.segment_id,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "source_path": str(clip.source_path) if clip.source_path else None,
                "source_offset": clip.source_offset,
                "muted": clip.muted,
                "volume": clip.volume,
            }
        record.update(self._player_snapshot(player))
        record.update(details)
        self._trace_original_audio_events.append(record)
        self._write_original_audio_trace()

    def _player_snapshot(self, player: QMediaPlayer) -> dict[str, Any]:
        output = self._audio_outputs_by_player.get(player)
        snapshot: dict[str, Any] = {
            "source": self._safe_player_value(player, "source", self._url_to_string),
            "media_status": self._safe_player_value(player, "mediaStatus", self._enum_name),
            "playback_state": self._safe_player_value(player, "playbackState", self._enum_name),
            "position_ms": self._safe_player_value(player, "position"),
            "duration_ms": self._safe_player_value(player, "duration"),
            "is_seekable": self._safe_player_value(player, "isSeekable"),
            "has_audio": self._safe_player_value(player, "hasAudio"),
        }
        if output is not None:
            snapshot["volume"] = self._safe_output_value(output, "volume")
            snapshot["muted"] = self._safe_output_value(output, "isMuted")
        else:
            snapshot["volume"] = None
            snapshot["muted"] = None
        return snapshot

    @staticmethod
    def _safe_player_value(
        player: QMediaPlayer,
        method_name: str,
        transform: Callable[[Any], Any] | None = None,
    ) -> Any:
        method = getattr(player, method_name, None)
        if method is None:
            return None
        try:
            value = method()
            if transform is not None:
                return transform(value)
            return value
        except RuntimeError as exc:
            return f"<RuntimeError: {exc}>"
        except Exception as exc:  # pragma: no cover - diagnostic safety net
            return f"<{type(exc).__name__}: {exc}>"

    @staticmethod
    def _safe_output_value(output: QAudioOutput, method_name: str) -> Any:
        value_or_method = getattr(output, method_name, None)
        if value_or_method is None:
            return None
        try:
            if callable(value_or_method):
                return value_or_method()
            return value_or_method
        except RuntimeError as exc:
            return f"<RuntimeError: {exc}>"
        except Exception as exc:  # pragma: no cover - diagnostic safety net
            return f"<{type(exc).__name__}: {exc}>"

    @staticmethod
    def _url_to_string(url: QUrl) -> str:
        return url.toLocalFile() or url.toString()

    def _write_original_audio_trace(self) -> None:
        if self._trace_original_audio_path is None:
            return
        try:
            self._trace_original_audio_path.parent.mkdir(parents=True, exist_ok=True)
            self._trace_original_audio_path.write_text(
                json.dumps(
                    {
                        "trace": "original_audio_playback",
                        "events": self._trace_original_audio_events,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def performance_snapshot(self) -> dict[str, int | bool]:
        """Return lightweight playback facts for opt-in editor diagnostics."""
        players = list(self._khmer_clip_players.values())
        active = self._active_audio_clips(self._video_player.position_ms)
        return {
            "video_players": 1,
            "audio_players": (
                2 + len(self._all_pool_players) + int(self._original_audio_player is not None)
            ),
            "timeline_clip_players": len(players),
            "available_pooled_players": len(self._available_audio_players),
            "active_audio_clips": len(active),
            "original_audio_enabled": any(
                clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID for clip in active
            ),
            "tts_enabled": any(clip.track_id == "khmer_tts" for clip in active),
            "playback_tick_rate_hz": 1000 // _SYNC_INTERVAL_MS,
            "maximum_simultaneous_overlap": self._audio_index.maximum_overlap,
            "average_playback_tick_ms": round(
                self._tick_total_seconds * 1000 / self._tick_count, 3
            ) if self._tick_count else 0.0,
            "worst_playback_tick_ms": round(self._tick_worst_seconds * 1000, 3),
            "active_clip_lookup_ms_total": round(self._lookup_total_seconds * 1000, 3),
            "first_play_active_audio_players": self._first_play_active_players,
            "first_play_active_clip_lookup_ms": round(
                self._first_play_lookup_seconds * 1000, 3
            ),
        }

    def _release_all_clip_players(self) -> None:
        for clip_id in list(self._khmer_clip_players):
            self._release_audio_player(clip_id)
        self._active_khmer_clip_ids.clear()

    def shutdown(self) -> None:
        """Stop timers and release all Qt Multimedia children deterministically."""
        if self._shutdown:
            return
        self._shutdown = True
        self._sync_timer.stop()
        self._release_all_clip_players()
        if self._original_audio_player is not None:
            self._stop_player(self._original_audio_player)
        self._original_audio_player = None
        self._original_audio_output = None
        for player, output in self._all_pool_players:
            self._stop_player(player)
            player.setSource(QUrl())
            player.deleteLater()
            output.deleteLater()
        self._all_pool_players.clear()
        self._available_audio_players.clear()
        self._stop_player(self._audition_player)
        self._audition_player.setSource(QUrl())
        self._audition_player.deleteLater()
        self._audition_output.deleteLater()

    def _acquire_audio_player(self, clip: TimelineClip) -> tuple[QMediaPlayer, QAudioOutput]:
        if clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID:
            if self._original_audio_player is None or self._original_audio_output is None:
                self._original_audio_player, self._original_audio_output = self._make_audio_player()
                self._connect_audio_player(
                    self._original_audio_player,
                    self._original_audio_output,
                    "original_movie_audio_player",
                )
            return self._original_audio_player, self._original_audio_output
        if self._available_audio_players:
            return self._available_audio_players.pop()
        player, output = self._make_audio_player()
        self._connect_audio_player(player, output, "timeline_audio_pool_player")
        self._all_pool_players.append((player, output))
        return player, output

    def _release_audio_player(self, clip_id: str) -> None:
        assignment = self._khmer_clip_players.pop(clip_id, None)
        if assignment is None:
            return
        player, output = assignment
        self._stop_player(player)
        self._pending_seek_ms.pop(player, None)
        self._pending_play.discard(player)
        self._clip_source_fingerprints.pop(clip_id, None)
        if player is self._original_audio_player:
            player.setSource(QUrl())
            self._audio_outputs_by_player.pop(player, None)
            self._audio_player_labels.pop(player, None)
            self._player_clip_ids.pop(player, None)
            player.deleteLater()
            output.deleteLater()
            self._original_audio_player = None
            self._original_audio_output = None
            return
        self._available_audio_players.append((player, output))

    @staticmethod
    def _source_fingerprint(path: Path) -> tuple[Path, int | None, int | None]:
        try:
            stat = path.stat()
            return path, stat.st_mtime_ns, stat.st_size
        except OSError:
            return path, None, None

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
        self._trace_qmedia_player_event(
            player,
            "setSource",
            source=str(path),
            pending_seek_ms=position_ms,
            pending_play=play,
        )
        player.setSource(url)

    def _on_audio_media_status_signal(
        self, player: QMediaPlayer, status: QMediaPlayer.MediaStatus
    ) -> None:
        self._trace_qmedia_player_event(
            player, "mediaStatusChanged", media_status=self._enum_name(status)
        )
        self._on_audio_media_status_changed(player, status)

    def _on_audio_media_status_changed(
        self, player: QMediaPlayer, status: QMediaPlayer.MediaStatus
    ) -> None:
        if status != _LOADED or player not in self._pending_seek_ms:
            return
        position_ms = self._pending_seek_ms.pop(player)
        play = player in self._pending_play
        self._pending_play.discard(player)
        self._trace_qmedia_player_event(
            player,
            "setPosition",
            position_ms=position_ms,
            reason="media_loaded_pending_seek",
            pending_play=play,
        )
        player.setPosition(position_ms)
        if play:
            self._play_if_needed(player)

    def _on_play_requested(self) -> None:
        self._play_request_started = time.perf_counter()
        self._video_player.set_audio_muted(True)
        self._sync_audio_to_position(
            self._video_player.position_ms, start_playing=True
        )
        self._first_play_active_players = len(self._khmer_clip_players)
        self._sync_timer.start()

    def _on_pause_requested(self) -> None:
        for player, _output in self._khmer_clip_players.values():
            self._pause_player(player)
        self._sync_timer.stop()

    def _on_stop_requested(self) -> None:
        for player, _output in self._khmer_clip_players.values():
            self._stop_player(player)
        self._active_khmer_clip_ids = set()
        self._sync_timer.stop()

    def _on_seek_requested(self, position_ms: int) -> None:
        self._sync_audio_to_position(
            position_ms, start_playing=self._video_player.is_playing, force_seek=True
        )

    def _on_video_position_changed(self, position_ms: int) -> None:
        if self._video_player.is_playing:
            self._maybe_loop(position_ms)

    def _on_sync_tick(self) -> None:
        started = time.perf_counter()
        self._maybe_resync(self._video_player.position_ms)
        self._maybe_loop(self._video_player.position_ms)
        elapsed = time.perf_counter() - started
        self._tick_count += 1
        self._tick_total_seconds += elapsed
        self._tick_worst_seconds = max(self._tick_worst_seconds, elapsed)

    def _maybe_resync(self, position_ms: int) -> None:
        self._sync_audio_to_position(position_ms, start_playing=self._video_player.is_playing)

    def _maybe_loop(self, position_ms: int) -> None:
        if not self._loop_selection_enabled:
            return
        loop_start, loop_end = self._selected_loop_bounds()
        if loop_start is None or loop_end is None or loop_end <= loop_start:
            return
        if position_ms >= loop_end:
            self.seek(loop_start)

    def _selected_loop_bounds(self) -> tuple[int | None, int | None]:
        selected = [clip for clip in self._timeline.all_clips() if clip.selected]
        if not selected:
            return None, None
        start = min(clip.start_time for clip in selected)
        end = max(clip.end_time for clip in selected)
        return round(start * 1000), round(end * 1000)

    def _sync_audio_to_position(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        self._video_player.set_audio_muted(True)
        self._sync_timeline_audio(
            position_ms, start_playing=start_playing, force_seek=force_seek
        )

    def _sync_timeline_audio(
        self, position_ms: int, *, start_playing: bool, force_seek: bool = False
    ) -> None:
        lookup_started = time.perf_counter()
        current_active = {
            clip.id: clip
            for clip in self._active_audio_clips(position_ms)
            if clip.source_path is not None
        }
        lookup_elapsed = time.perf_counter() - lookup_started
        self._lookup_total_seconds += lookup_elapsed
        if self._play_request_started is not None:
            self._first_play_lookup_seconds = lookup_elapsed
            self._play_request_started = None
        for clip_id in list(self._khmer_clip_players):
            if clip_id not in current_active:
                self._release_audio_player(clip_id)
        for clip_id, clip in current_active.items():
            player, output = self._khmer_clip_players.get(clip_id, (None, None))
            if player is None or output is None:
                player, output = self._acquire_audio_player(clip)
                self._khmer_clip_players[clip_id] = (player, output)
            self._audio_outputs_by_player.setdefault(player, output)
            self._player_clip_ids[player] = clip.id
            source_position_ms = clip.source_position_ms(position_ms)
            self._trace_original_clip_should_play(
                clip,
                player,
                position_ms=position_ms,
                source_position_ms=source_position_ms,
            )
            output.setMuted(False)
            output.setVolume(clip.volume_at(position_ms))
            if clip.source_path is not None:
                url = QUrl.fromLocalFile(str(clip.source_path))
                fingerprint = self._source_fingerprint(clip.source_path)
                known_fingerprint = self._clip_source_fingerprints.get(clip_id)
                if (
                    player.source() != url
                    or (
                        known_fingerprint is not None
                        and known_fingerprint != fingerprint
                    )
                ):
                    if player.source() == url:
                        player.setSource(QUrl())
                    self._load_audio_source(
                        player,
                        clip.source_path,
                        source_position_ms,
                        play=start_playing,
                        force_seek=True,
                    )
                    self._clip_source_fingerprints[clip_id] = fingerprint
                    continue
                self._clip_source_fingerprints[clip_id] = fingerprint
            if clip_id not in self._active_khmer_clip_ids:
                self._seek_if_needed(player, source_position_ms, force=True)
            else:
                self._seek_if_needed(player, source_position_ms, force=force_seek)
            if start_playing:
                self._request_play(player)
        self._active_khmer_clip_ids = set(current_active)

    def _active_audio_clips(self, position_ms: int) -> list[TimelineClip]:
        return self._audio_index.active_at(position_ms)

    def _seek_if_needed(self, player: QMediaPlayer, position_ms: int, *, force: bool) -> None:
        if player in self._pending_seek_ms:
            if force or abs(self._pending_seek_ms[player] - position_ms) > _DRIFT_THRESHOLD_MS:
                self._trace_qmedia_player_event(
                    player,
                    "pending_seek_updated",
                    position_ms=position_ms,
                    force=force,
                    previous_pending_seek_ms=self._pending_seek_ms[player],
                )
                self._pending_seek_ms[player] = position_ms
            return
        if force or abs(player.position() - position_ms) > _DRIFT_THRESHOLD_MS:
            self._trace_qmedia_player_event(
                player,
                "setPosition",
                position_ms=position_ms,
                force=force,
                current_player_position_ms=int(player.position()),
            )
            player.setPosition(position_ms)

    def _request_play(self, player: QMediaPlayer) -> None:
        self._trace_qmedia_player_event(
            player, "_request_play", pending_seek=player in self._pending_seek_ms
        )
        if player in self._pending_seek_ms:
            self._pending_play.add(player)
            return
        self._play_if_needed(player)

    def _play_if_needed(self, player: QMediaPlayer) -> None:
        if player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self._trace_qmedia_player_event(player, "play")
            player.play()

    def _pause_player(self, player: QMediaPlayer) -> None:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._trace_qmedia_player_event(player, "pause")
            player.pause()

    def _stop_player(self, player: QMediaPlayer) -> None:
        if player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._trace_qmedia_player_event(player, "stop")
            player.stop()
