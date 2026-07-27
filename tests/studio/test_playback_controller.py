"""Studio V2 — Professional Playback.

Tests for:
- timeline_audio.py: pure per-track timing/volume math for Timeline Preview
- playback_controller.py: PlaybackController mode switching, play/pause/stop,
  seek, clip preview, and video/audio synchronization
"""

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

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.playback.playback_controller import (
    _LOADED,
    PlaybackController,
    PlaybackMode,
)
from automatedub_studio.playback.timeline_audio import (
    compute_playback_volume,
    find_active_track,
    position_within_track_ms,
    track_window_ms,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget


def pump_until(predicate, timeout_s: float = 3.0) -> None:
    """Process Qt events until `predicate()` is true or `timeout_s` elapses.

    Needed because QMediaPlayer loads media asynchronously even against the
    offscreen ffmpeg backend used in tests.
    """
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
    """Generate a real, decodable MP4 (no fake header bytes).

    `QMediaPlayer` silently drops `setPosition()` calls while the source is
    a fake/undecodable file, so tests asserting on `position_ms` need a real
    file the ffmpeg-backed Qt Multimedia backend can actually load.
    """
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={seconds}",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", str(seconds), "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
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


# ---------------------------------------------------------------------------
# timeline_audio.py — pure timing math
# ---------------------------------------------------------------------------


def test_track_window_ms_no_speed_change():
    track = make_track(delay_ms=1000, generated_duration=2.0, atempo=1.0)
    assert track_window_ms(track) == (1000, 3000)


def test_track_window_ms_sped_up():
    # atempo > 1.0 means the clip plays faster, so its window shrinks.
    track = make_track(delay_ms=0, generated_duration=2.0, atempo=2.0)
    assert track_window_ms(track) == (0, 1000)


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


def test_position_within_track_ms_scales_by_atempo():
    track = make_track(delay_ms=1000, generated_duration=2.0, atempo=2.0)
    assert position_within_track_ms(track, 1000) == 0
    assert position_within_track_ms(track, 1500) == 1000


def test_position_within_track_ms_clamps_before_start():
    track = make_track(delay_ms=1000, generated_duration=2.0)
    assert position_within_track_ms(track, 0) == 0


# ---------------------------------------------------------------------------
# PlaybackController — construction and mode switching
# ---------------------------------------------------------------------------


def test_controller_starts_in_original_mode(qapp):
    controller = PlaybackController(VideoPlayerWidget())
    assert controller.mode == PlaybackMode.ORIGINAL


def test_original_mode_leaves_video_audio_unmuted(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)
    controller.set_sources(None, None, [])
    assert video_player._audio_output.isMuted() is False


def test_switching_to_mixed_mode_mutes_video_audio(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)
    controller.set_mode(PlaybackMode.MIXED)
    assert video_player._audio_output.isMuted() is True


def test_switching_to_khmer_mode_mutes_video_audio(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)
    controller.set_mode(PlaybackMode.KHMER_TTS)
    assert video_player._audio_output.isMuted() is True


def test_switching_to_timeline_preview_mutes_video_audio(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)
    controller.set_mode(PlaybackMode.TIMELINE_PREVIEW)
    assert video_player._audio_output.isMuted() is True


def test_switching_back_to_original_unmutes_video_audio(qapp):
    video_player = VideoPlayerWidget()
    controller = PlaybackController(video_player)
    controller.set_mode(PlaybackMode.MIXED)
    controller.set_mode(PlaybackMode.ORIGINAL)
    assert video_player._audio_output.isMuted() is False


def test_switching_to_same_mode_is_a_no_op(qapp):
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.ORIGINAL)
    assert controller.mode == PlaybackMode.ORIGINAL


@requires_ffmpeg
def test_mode_switch_does_not_touch_master_clock_position(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    make_playable_video(video_path, seconds=10.0)
    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    pump_until(lambda: video_player._has_video and video_player._media_player.duration() > 0)
    controller = PlaybackController(video_player)

    controller.seek(5000)
    pump_until(lambda: video_player.position_ms == 5000)
    controller.set_mode(PlaybackMode.MIXED)
    assert video_player.position_ms == 5000
    controller.set_mode(PlaybackMode.KHMER_TTS)
    assert video_player.position_ms == 5000


# ---------------------------------------------------------------------------
# PlaybackController — sources per mode
# ---------------------------------------------------------------------------


def test_set_sources_mixed_mode_loads_mixed_audio_path(qapp, tmp_path):
    mixed_path = tmp_path / "mixed_audio.wav"
    make_wav(mixed_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.MIXED)
    controller.set_sources(mixed_path, None, [])
    controller.seek(0)
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(mixed_path))


def test_set_sources_khmer_mode_loads_tts_combined_path(qapp, tmp_path):
    khmer_path = tmp_path / "tts_combined.wav"
    make_wav(khmer_path)
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.KHMER_TTS)
    controller.set_sources(None, khmer_path, [])
    controller.seek(0)
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(khmer_path))


def test_mixed_mode_without_source_does_not_raise(qapp):
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.MIXED)
    controller.set_sources(None, None, [])
    controller.seek(0)
    assert controller._audio_player.source().isEmpty()


# ---------------------------------------------------------------------------
# PlaybackController — play / pause / stop
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PlaybackController — Timeline Preview
# ---------------------------------------------------------------------------


def test_timeline_preview_selects_active_track_on_seek(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.TIMELINE_PREVIEW)
    controller.set_sources(None, None, [track])

    controller.seek(200)
    assert controller._active_timeline_track is track
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(clip_path))


def test_timeline_preview_clears_active_track_between_clips(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_path)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.TIMELINE_PREVIEW)
    controller.set_sources(None, None, [track])

    controller.seek(200)
    assert controller._active_timeline_track is track

    controller.seek(5000)
    assert controller._active_timeline_track is None


def test_timeline_preview_switches_between_two_clips(qapp, tmp_path):
    clip_a = tmp_path / "0000.wav"
    clip_b = tmp_path / "0001.wav"
    make_wav(clip_a, seconds=1.0)
    make_wav(clip_b, seconds=1.0)
    track_a = make_track(track_id=0, delay_ms=0, generated_duration=1.0, tts_path=clip_a)
    track_b = make_track(track_id=1, delay_ms=2000, generated_duration=1.0, tts_path=clip_b)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.TIMELINE_PREVIEW)
    controller.set_sources(None, None, [track_a, track_b])

    controller.seek(200)
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(clip_a))

    controller.seek(2200)
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(clip_b))


def test_timeline_preview_applies_fade_volume(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    track = make_track(
        track_id=0, delay_ms=0, generated_duration=1.0, fade_in_ms=500, tts_path=clip_path
    )

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.TIMELINE_PREVIEW)
    controller.set_sources(None, None, [track])

    controller.seek(0)
    assert controller._audio_output.volume() == 0.0

    controller.seek(500)
    assert controller._audio_output.volume() == 1.0


# ---------------------------------------------------------------------------
# PlaybackController — Play Clip (single-clip audition)
# ---------------------------------------------------------------------------


def test_play_clip_loads_and_plays_single_source(qapp, tmp_path):
    clip_path = tmp_path / "clip.wav"
    make_wav(clip_path, seconds=0.5)

    controller = PlaybackController(VideoPlayerWidget())
    controller.play_clip(clip_path)
    assert controller._audio_player.source() == QUrl.fromLocalFile(str(clip_path))


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
    pump_until(lambda: not controller._audio_player.source().isEmpty())
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


# ---------------------------------------------------------------------------
# PlaybackController — video/audio synchronization
# ---------------------------------------------------------------------------


def test_resync_reseeks_audio_on_drift(qapp, tmp_path):
    mixed_path = tmp_path / "mixed_audio.wav"
    make_wav(mixed_path, seconds=10.0)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.MIXED)
    controller.set_sources(mixed_path, None, [])
    controller.seek(0)
    pump_until(lambda: controller._audio_player.mediaStatus() == _LOADED)

    controller._audio_player.setPosition(5000)
    controller._maybe_resync(1000)
    assert controller._audio_player.position() == 1000


def test_resync_ignores_small_drift(qapp, tmp_path):
    mixed_path = tmp_path / "mixed_audio.wav"
    make_wav(mixed_path, seconds=10.0)

    controller = PlaybackController(VideoPlayerWidget())
    controller.set_mode(PlaybackMode.MIXED)
    controller.set_sources(mixed_path, None, [])
    controller.seek(1000)
    pump_until(lambda: controller._audio_player.mediaStatus() == _LOADED)

    controller._audio_player.setPosition(1010)
    controller._maybe_resync(1000)
    assert controller._audio_player.position() == 1010


def test_resync_no_op_in_original_mode(qapp, tmp_path):
    controller = PlaybackController(VideoPlayerWidget())
    assert controller.mode == PlaybackMode.ORIGINAL
    controller._maybe_resync(1000)
    assert controller._audio_player.source().isEmpty()
