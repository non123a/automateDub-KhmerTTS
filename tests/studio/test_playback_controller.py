"""Studio V3.2 dual-audio playback tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtMultimedia import QMediaPlayer

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.playback.playback_controller import _LOADED, PlaybackController
from automatedub_studio.playback.timeline_audio import (
    build_original_audio_clips,
    compute_playback_volume,
    find_active_original_clips,
    find_active_track,
    position_within_original_clip_ms,
    position_within_track_ms,
    track_window_ms,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import KHMER_TTS_TRACK_ID, TimelineClip


def pump_until(predicate, timeout_s: float = 3.0) -> None:
    deadline = monotonic() + timeout_s
    while not predicate() and monotonic() < deadline:
        QCoreApplication.processEvents()


def make_wav(path: Path, seconds: float = 1.0, frame_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * int(frame_rate * seconds))


_HAS_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not available")


def make_playable_video(path: Path, seconds: float = 2.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=64x64:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def make_wav_bytes(seconds: float = 1.0, frame_rate: int = 16000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * int(frame_rate * seconds))
    return buf.getvalue()


def make_track(
    track_id: int = 0,
    delay_ms: int = 0,
    generated_duration: float = 1.0,
    atempo: float = 1.0,
    volume: float = 1.0,
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
    tts_path: Path | None = None,
) -> MixSpeechTrack:
    return MixSpeechTrack(
        id=track_id,
        start=delay_ms / 1000.0,
        end=delay_ms / 1000.0 + generated_duration,
        delay_ms=delay_ms,
        atempo=atempo,
        generated_duration=generated_duration,
        tts_path=tts_path if tts_path is not None else Path(f"/fake/{track_id:04d}.wav"),
        volume=volume,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
    )


def make_segment(
    segment_id: int = 0,
    start: float = 0.0,
    end: float = 1.0,
    offset_ms: int = 0,
) -> Segment:
    return Segment(
        id=segment_id,
        start=start,
        end=end,
        source_text="source",
        target_text="target",
        offset_ms=offset_ms,
    )


# ---------------------------------------------------------------------------
# timeline_audio.py — pure timing math
# ---------------------------------------------------------------------------


def test_track_window_ms_no_speed_change():
    track = make_track(delay_ms=1000, generated_duration=2.0, atempo=1.0)
    assert track_window_ms(track) == (1000, 3000)


def test_track_window_ms_sped_up():
    track = make_track(delay_ms=0, generated_duration=2.0, atempo=2.0)
    assert track_window_ms(track) == (0, 2000)


def test_find_active_track_matches_containing_window():
    track_a = make_track(track_id=0, delay_ms=0, generated_duration=1.0)
    track_b = make_track(track_id=1, delay_ms=1000, generated_duration=1.0)
    assert find_active_track([track_a, track_b], 500) is track_a
    assert find_active_track([track_a, track_b], 1500) is track_b


def test_find_active_track_returns_none_between_windows():
    track_a = make_track(track_id=0, delay_ms=0, generated_duration=1.0)
    track_b = make_track(track_id=1, delay_ms=2000, generated_duration=1.0)
    assert find_active_track([track_a, track_b], 1500) is None


def test_compute_playback_volume_uses_base_volume():
    track = make_track(delay_ms=0, generated_duration=2.0, volume=0.5)
    assert compute_playback_volume(track, 1000) == 0.5


def test_compute_playback_volume_fade_in_ramps_up():
    track = make_track(delay_ms=0, generated_duration=2.0, fade_in_ms=500)
    assert compute_playback_volume(track, 0) == 0.0
    assert compute_playback_volume(track, 250) == 0.5
    assert compute_playback_volume(track, 500) == 1.0


def test_compute_playback_volume_fade_out_ramps_down():
    track = make_track(delay_ms=0, generated_duration=2.0, fade_out_ms=500)
    assert compute_playback_volume(track, 2000) == 0.0
    assert compute_playback_volume(track, 1750) == 0.5
    assert compute_playback_volume(track, 1500) == 1.0


def test_position_within_track_ms_uses_natural_tts_position():
    track = make_track(delay_ms=1000, generated_duration=2.0, atempo=2.0)
    assert position_within_track_ms(track, 1000) == 0
    assert position_within_track_ms(track, 1500) == 500


def test_position_within_track_ms_clamps_before_start():
    track = make_track(delay_ms=1000, generated_duration=2.0)
    assert position_within_track_ms(track, 0) == 0


def test_build_original_audio_clips_uses_segment_timing_and_offset(tmp_path):
    audio_path = tmp_path / "audio.wav"
    segment = make_segment(start=1.0, end=2.5, offset_ms=250)

    clips = build_original_audio_clips(audio_path, [segment])

    assert clips[0].path == audio_path
    assert clips[0].start_ms == 1250
    assert clips[0].end_ms == 2750
    assert clips[0].source_start_ms == 1000


def test_find_active_original_clips_returns_matching_windows(tmp_path):
    clips = build_original_audio_clips(
        tmp_path / "audio.wav",
        [make_segment(0, 0.0, 1.0), make_segment(1, 2.0, 3.0)],
    )
    assert [clip.id for clip in find_active_original_clips(clips, 500)] == [0]
    assert find_active_original_clips(clips, 1500) == []


def test_position_within_original_clip_maps_to_source_audio(tmp_path):
    clip = build_original_audio_clips(
        tmp_path / "audio.wav", [make_segment(start=2.0, end=3.0, offset_ms=500)]
    )[0]
    assert position_within_original_clip_ms(clip, 2600) == 2100


# ---------------------------------------------------------------------------
# PlaybackController — V3.2 dual audio playback
# ---------------------------------------------------------------------------


def test_video_audio_is_always_muted(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)

    video_player.set_audio_muted(False)
    controller.set_sources(None, [], [])
    controller._sync_audio_to_position(0, start_playing=False)

    assert video_player._audio_output.isMuted() is True


def test_playback_no_longer_exposes_playback_modes(qapp):
    controller = PlaybackController(VideoPlayerWidget())

    assert not hasattr(controller, "mode")
    assert not hasattr(controller, "set_mode")


def test_playback_uses_original_audio(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=3.0)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 1.0, 2.0)], [])

    controller.seek(1200)

    assert controller._active_original_clip is not None
    assert controller._original_audio_player.source() == QUrl.fromLocalFile(str(audio_path))


def test_playback_uses_khmer_tts(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=1000, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(None, [], [track])

    controller.seek(1200)

    assert controller._active_khmer_track is track
    assert controller._khmer_audio_player.source() == QUrl.fromLocalFile(str(clip_path))


def test_mute_original_only_khmer_plays(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 1.0)], [track])

    controller.set_original_muted(True)
    controller.seek(500)

    assert controller._active_original_clip is None
    assert controller._active_khmer_track is track
    assert controller._original_audio_player.source().isEmpty()
    assert controller._khmer_audio_player.source() == QUrl.fromLocalFile(str(clip_path))


def test_mute_khmer_only_original_plays(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 1.0)], [track])

    controller.set_khmer_muted(True)
    controller.seek(500)

    assert controller._active_original_clip is not None
    assert controller._active_khmer_track is None
    assert controller._original_audio_player.source() == QUrl.fromLocalFile(str(audio_path))
    assert controller._khmer_audio_player.source().isEmpty()


def test_both_unmuted_both_tracks_are_mixed_by_parallel_players(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 1.0)], [track])

    controller.seek(500)

    assert controller._active_original_clip is not None
    assert controller._active_khmer_track is track
    assert controller._original_audio_player.source() == QUrl.fromLocalFile(str(audio_path))
    assert controller._khmer_audio_player.source() == QUrl.fromLocalFile(str(clip_path))


def test_khmer_volume_applies_fade(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(
        track_id=0, delay_ms=0, generated_duration=1.0, fade_in_ms=500, tts_path=clip_path
    )
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(None, [], [track])

    controller.seek(0)
    assert controller._khmer_audio_output.volume() == 0.0

    controller.seek(500)
    assert controller._khmer_audio_output.volume() == 1.0


def test_khmer_timeline_playback_uses_same_natural_position_as_audition(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=2.0)
    track = make_track(
        track_id=0,
        delay_ms=0,
        generated_duration=2.0,
        atempo=2.0,
        tts_path=clip_path,
    )
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(None, [], [track])

    controller.seek(500)

    assert controller._pending_seek_ms[controller._khmer_audio_player] == 500


def test_khmer_playback_marked_pending_when_play_starts_during_load(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(None, [], [track])

    controller._on_play_requested()

    assert controller._khmer_audio_player in controller._pending_play


def test_sync_reuses_existing_audio_players(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 1.0)], [track])
    original_player = controller._original_audio_player
    khmer_player = controller._khmer_audio_player

    for position_ms in (100, 200, 300):
        controller._maybe_resync(position_ms)

    assert controller._original_audio_player is original_player
    assert controller._khmer_audio_player is khmer_player


class _CountingPlayer:
    def __init__(self, source: QUrl, position: int):
        self._source = source
        self._position = position
        self.play_count = 0
        self.seek_count = 0
        self.stop_count = 0

    def source(self):
        return self._source

    def setSource(self, source):
        self._source = source

    def position(self):
        return self._position

    def setPosition(self, position):
        self.seek_count += 1
        self._position = position

    def playbackState(self):
        return QMediaPlayer.PlaybackState.PlayingState

    def play(self):
        self.play_count += 1

    def stop(self):
        self.stop_count += 1


class _CountingOutput:
    def __init__(self):
        self.volume = 1.0
        self.muted = False

    def setMuted(self, muted):
        self.muted = muted

    def setVolume(self, volume):
        self.volume = volume


def test_stable_active_khmer_clip_is_not_replayed_or_reseeked_each_tick(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=2.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=2.0, tts_path=clip_path)
    controller = PlaybackController(VideoPlayerWidget())
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(clip_path)), position=500)
    fake_output = _CountingOutput()
    controller._khmer_tracks = [track]
    controller._active_khmer_track = track
    controller._khmer_audio_player = fake_player
    controller._khmer_audio_output = fake_output

    controller._sync_khmer_audio(520, start_playing=True)

    assert fake_player.play_count == 0
    assert fake_player.seek_count == 0


def test_active_khmer_clip_allows_normal_drift_without_reseek(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=2.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = TimelineClip(
        id="khmer:0",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=1.0,
        end_time=3.0,
        source_path=clip_path,
    )
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(clip_path)), position=445)
    fake_output = _CountingOutput()
    controller._timeline_clips = [clip]
    controller._active_khmer_clip_ids = {"khmer:0"}
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}

    controller._sync_khmer_audio(1500, start_playing=True)

    assert fake_player.seek_count == 0
    assert fake_player.play_count == 0


def test_active_khmer_clip_reseeks_on_large_drift(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=2.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = TimelineClip(
        id="khmer:0",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=1.0,
        end_time=3.0,
        source_path=clip_path,
    )
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(clip_path)), position=0)
    fake_output = _CountingOutput()
    controller._timeline_clips = [clip]
    controller._active_khmer_clip_ids = {"khmer:0"}
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}

    controller._sync_khmer_audio(1600, start_playing=True)

    assert fake_player.seek_count == 1
    assert fake_player.play_count == 0


def test_original_and_khmer_volumes_are_independent(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    track = make_track(
        track_id=0,
        delay_ms=0,
        generated_duration=1.0,
        volume=0.25,
        tts_path=clip_path,
    )
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 1.0)], [track])

    controller.seek(500)

    assert controller._original_audio_output.volume() == 1.0
    assert controller._khmer_audio_output.volume() == 0.25


def test_stop_stops_video_and_audio(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    controller = PlaybackController(video_player)
    controller.stop()
    assert controller._sync_timer.isActive() is False


def test_pause_stops_sync_timer(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    controller = PlaybackController(video_player)
    controller.play()
    controller.pause()
    assert controller._sync_timer.isActive() is False


def test_play_clip_loads_single_audition_source(qapp, tmp_path):
    clip_path = tmp_path / "clip.wav"
    make_wav(clip_path, seconds=0.5)

    controller = PlaybackController(VideoPlayerWidget())
    controller.play_clip(clip_path)
    assert controller._audition_player.source() == QUrl.fromLocalFile(str(clip_path))


@requires_ffmpeg
def test_play_clip_does_not_move_master_clock(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    make_playable_video(video_path, seconds=10.0)
    clip_path = tmp_path / "clip.wav"
    make_wav(clip_path, seconds=0.5)

    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    pump_until(lambda: video_player._media_player.duration() > 0)
    controller = PlaybackController(video_player)
    controller.seek(3000)
    pump_until(lambda: video_player.position_ms == 3000)

    controller.play_clip(clip_path)
    pump_until(lambda: not controller._audition_player.source().isEmpty())
    assert video_player.position_ms == 3000


def test_play_clip_stops_sync_timer(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    clip_path = tmp_path / "clip.wav"
    make_wav(clip_path, seconds=0.5)

    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    controller = PlaybackController(video_player)
    controller.play()
    controller.play_clip(clip_path)
    assert controller._sync_timer.isActive() is False


def test_resync_reseeks_original_audio_on_drift(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=10.0)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 5.0)], [])
    controller.seek(1000)
    pump_until(lambda: controller._original_audio_player.mediaStatus() == _LOADED)

    controller._original_audio_player.setPosition(5000)
    controller._maybe_resync(1000)
    assert controller._original_audio_player.position() == 1000


def test_resync_ignores_small_original_audio_drift(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=10.0)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_sources(audio_path, [make_segment(0, 0.0, 5.0)], [])
    controller.seek(1000)
    pump_until(lambda: controller._original_audio_player.mediaStatus() == _LOADED)

    controller._original_audio_player.setPosition(1010)
    controller._maybe_resync(1000)
    assert controller._original_audio_player.position() == 1010


def test_make_wav_bytes_returns_valid_wav_bytes():
    assert make_wav_bytes().startswith(b"RIFF")
