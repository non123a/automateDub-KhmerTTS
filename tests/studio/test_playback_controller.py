"""Studio V3.2 dual-audio playback tests."""

from __future__ import annotations

import json
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
from automatedub_studio.timeline.timeline_clip import (
    DRAFT_REGENERATION_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)


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


def make_timeline_clip(
    clip_id: str,
    track_id: str,
    path: Path,
    start: float = 0.0,
    end: float = 1.0,
    source_offset: float = 0.0,
    volume: float = 1.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    segment_id: int | None = None,
) -> TimelineClip:
    return TimelineClip(
        id=clip_id,
        track_id=track_id,
        start_time=start,
        end_time=end,
        source_path=path,
        source_offset=source_offset,
        volume=volume,
        fade_in=fade_in,
        fade_out=fade_out,
        segment_id=segment_id,
    )


def make_timeline(*clips: TimelineClip) -> Timeline:
    return Timeline.from_clips(list(clips))


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
    controller.set_timeline(Timeline.default())
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
    clip = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=1.0,
        end=2.0,
        source_offset=1.0,
    )
    controller.set_timeline(make_timeline(clip))

    controller.seek(1200)

    assert controller._active_khmer_clip_ids == {"original:0"}
    player, _output = controller._khmer_clip_players["original:0"]
    assert player.source() == QUrl.fromLocalFile(str(audio_path))


def test_original_segment_23_seeks_into_pipeline_audio_at_source_offset(qapp, tmp_path):
    audio_path = tmp_path / "pipeline" / "audio.wav"
    audio_path.parent.mkdir()
    make_wav(audio_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip(
        "original:23",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=52.32,
        end=53.10,
        source_offset=52.32,
        segment_id=23,
    )
    controller.set_timeline(make_timeline(clip))
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(audio_path)), position=0)
    fake_output = _CountingOutput()
    controller._khmer_clip_players["original:23"] = (fake_player, fake_output)

    controller._sync_timeline_audio(52320, start_playing=False)

    assert controller._active_khmer_clip_ids == {"original:23"}
    assert fake_player.seek_count == 1
    assert fake_player.position() == 52320


def test_original_audio_playback_trace_records_qmediaplayer_seek(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOMATEDUB_ORIGINAL_AUDIO_TRACE", "1")
    audio_path = tmp_path / "pipeline" / "audio.wav"
    audio_path.parent.mkdir()
    make_wav(audio_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip(
        "original:23",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=52.32,
        end=53.10,
        source_offset=52.32,
        segment_id=23,
    )
    controller.set_timeline(make_timeline(clip))
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(audio_path)), position=0)
    fake_output = _CountingOutput()
    controller._khmer_clip_players["original:23"] = (fake_player, fake_output)

    controller._sync_timeline_audio(52320, start_playing=False)

    trace_path = audio_path.parent / "debug" / "original_audio_playback_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    events = trace["events"]
    original_event = next(
        event for event in events if event["event"] == "original_speech_clip_should_play"
    )
    seek_event = next(event for event in events if event["event"] == "setPosition")
    assert original_event["clip"]["id"] == "original:23"
    assert original_event["source_path"] == str(audio_path)
    assert original_event["source_offset"] == 52.32
    assert original_event["elapsed_seconds"] == 0.0
    assert original_event["computed_seek_position_ms"] == 52320
    assert seek_event["position_ms"] == 52320


def test_khmer_segment_at_late_timeline_time_starts_at_clip_zero(qapp, tmp_path):
    clip_path = tmp_path / "tts" / "0023.wav"
    clip_path.parent.mkdir()
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip(
        "khmer:23",
        KHMER_TTS_TRACK_ID,
        clip_path,
        start=52.32,
        end=53.10,
        source_offset=0.0,
        segment_id=23,
    )
    controller.set_timeline(make_timeline(clip))
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(clip_path)), position=200)
    fake_output = _CountingOutput()
    controller._khmer_clip_players["khmer:23"] = (fake_player, fake_output)

    controller._sync_timeline_audio(52320, start_playing=False)

    assert controller._active_khmer_clip_ids == {"khmer:23"}
    assert fake_player.seek_count == 1
    assert fake_player.position() == 0


def test_playback_uses_khmer_tts(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path, start=1.0, end=2.0)
    controller.set_timeline(make_timeline(clip))

    controller.seek(1200)

    assert controller._active_khmer_clip_ids == {"khmer:0"}
    assert controller._khmer_audio_player.source() == QUrl.fromLocalFile(str(clip_path))


def test_mute_original_only_khmer_plays(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, start=0.0, end=1.0
    )
    khmer = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    controller.set_timeline(make_timeline(original, khmer))

    controller.set_original_muted(True)
    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"khmer:0"}
    player, _output = controller._khmer_clip_players["khmer:0"]
    assert player.source() == QUrl.fromLocalFile(str(clip_path))


def test_mute_khmer_only_original_plays(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, start=0.0, end=1.0
    )
    khmer = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    controller.set_timeline(make_timeline(original, khmer))

    controller.set_khmer_muted(True)
    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0"}
    player, _output = controller._khmer_clip_players["original:0"]
    assert player.source() == QUrl.fromLocalFile(str(audio_path))


def test_both_unmuted_both_tracks_are_mixed_by_parallel_players(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, start=0.0, end=1.0
    )
    khmer = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    controller.set_timeline(make_timeline(original, khmer))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0", "khmer:0"}
    assert {
        player.source()
        for player, _output in controller._khmer_clip_players.values()
    } == {
        QUrl.fromLocalFile(str(audio_path)),
        QUrl.fromLocalFile(str(clip_path)),
    }


def test_same_segment_original_and_khmer_both_play_as_independent_tracks(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    khmer = make_timeline_clip(
        "khmer:0", KHMER_TTS_TRACK_ID, clip_path, start=0.0, end=1.0, segment_id=0
    )
    controller.set_timeline(make_timeline(original, khmer))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0", "khmer:0"}


def test_original_only_segment_plays_without_requiring_khmer_clip(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=2.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    controller.set_timeline(make_timeline(original))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0"}


def test_all_unmuted_audio_tracks_mix_without_original_khmer_fallback(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=5.0)
    controller = PlaybackController(VideoPlayerWidget())
    khmer0 = tmp_path / "tts0.wav"
    khmer1 = tmp_path / "tts1.wav"
    khmer3 = tmp_path / "tts3.wav"
    make_wav(khmer0, seconds=1.0)
    make_wav(khmer1, seconds=1.0)
    make_wav(khmer3, seconds=1.0)
    clips = [
        make_timeline_clip(
            "original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, 0.0, 1.0, segment_id=0
        ),
        make_timeline_clip(
            "khmer:0", KHMER_TTS_TRACK_ID, khmer0, 0.0, 1.0, segment_id=0
        ),
        make_timeline_clip(
            "original:1", ORIGINAL_AUDIO_TRACK_ID, audio_path, 1.0, 2.0, segment_id=1
        ),
        make_timeline_clip(
            "khmer:1", KHMER_TTS_TRACK_ID, khmer1, 1.0, 2.0, segment_id=1
        ),
        make_timeline_clip(
            "original:2", ORIGINAL_AUDIO_TRACK_ID, audio_path, 2.0, 3.0, segment_id=2
        ),
        make_timeline_clip(
            "original:3", ORIGINAL_AUDIO_TRACK_ID, audio_path, 3.0, 4.0, segment_id=3
        ),
        make_timeline_clip(
            "khmer:3", KHMER_TTS_TRACK_ID, khmer3, 3.0, 4.0, segment_id=3
        ),
    ]
    controller.set_timeline(make_timeline(*clips))

    assert {clip.id for clip in controller._active_audio_clips(500)} == {
        "original:0",
        "khmer:0",
    }
    assert {clip.id for clip in controller._active_audio_clips(1500)} == {
        "original:1",
        "khmer:1",
    }
    assert [clip.id for clip in controller._active_audio_clips(2500)] == ["original:2"]
    assert {clip.id for clip in controller._active_audio_clips(3500)} == {
        "original:3",
        "khmer:3",
    }


def test_muted_khmer_leaves_original_track_playing_independently(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    khmer_path = tmp_path / "tts0.wav"
    make_wav(audio_path, seconds=5.0)
    make_wav(khmer_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original_clips = [
        make_timeline_clip(
            f"original:{segment_id}",
            ORIGINAL_AUDIO_TRACK_ID,
            audio_path,
            float(segment_id),
            float(segment_id + 1),
            segment_id=segment_id,
        )
        for segment_id in range(4)
    ]
    khmer_clips = [
        make_timeline_clip(
            f"khmer:{segment_id}",
            KHMER_TTS_TRACK_ID,
            khmer_path,
            float(segment_id),
            float(segment_id + 1),
            segment_id=segment_id,
        )
        for segment_id in (0, 1, 3)
    ]
    controller.set_timeline(make_timeline(*(original_clips + khmer_clips)))

    controller.set_khmer_muted(True)

    assert [clip.id for clip in controller._active_audio_clips(500)] == ["original:0"]
    assert [clip.id for clip in controller._active_audio_clips(1500)] == ["original:1"]
    assert [clip.id for clip in controller._active_audio_clips(2500)] == ["original:2"]
    assert [clip.id for clip in controller._active_audio_clips(3500)] == ["original:3"]


def test_missing_khmer_source_is_skipped_while_original_track_still_plays(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    missing_khmer_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    khmer = make_timeline_clip(
        "khmer:0",
        KHMER_TTS_TRACK_ID,
        missing_khmer_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    controller.set_timeline(make_timeline(original, khmer))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0"}
    player, _output = controller._khmer_clip_players["original:0"]
    assert player.source() == QUrl.fromLocalFile(str(audio_path))


def test_soloed_missing_khmer_source_does_not_auto_fallback_to_original(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    missing_khmer_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    timeline = Timeline.default()
    original_track = timeline.track_by_id(ORIGINAL_AUDIO_TRACK_ID)
    khmer_track = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    assert original_track is not None
    assert khmer_track is not None
    khmer_track.solo = True
    original_track.clips.append(
        make_timeline_clip(
            "original:0",
            ORIGINAL_AUDIO_TRACK_ID,
            audio_path,
            start=0.0,
            end=1.0,
            segment_id=0,
        )
    )
    khmer_track.clips.append(
        make_timeline_clip(
            "khmer:0",
            KHMER_TTS_TRACK_ID,
            missing_khmer_path,
            start=0.0,
            end=1.0,
            segment_id=0,
        )
    )
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_timeline(timeline)

    controller.seek(500)

    assert controller._active_khmer_clip_ids == set()


def test_draft_khmer_and_original_same_segment_all_mix_when_unmuted(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    khmer_path = tmp_path / "0000.wav"
    draft_path = tmp_path / "draft.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(khmer_path, seconds=1.0)
    make_wav(draft_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    khmer = make_timeline_clip(
        "khmer:0", KHMER_TTS_TRACK_ID, khmer_path, start=0.0, end=1.0, segment_id=0
    )
    draft = make_timeline_clip(
        "draft:0",
        DRAFT_REGENERATION_TRACK_ID,
        draft_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    controller.set_timeline(make_timeline(original, khmer, draft))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0", "khmer:0", "draft:0"}
    player, _output = controller._khmer_clip_players["draft:0"]
    assert player.source() == QUrl.fromLocalFile(str(draft_path))


def test_missing_draft_source_is_skipped_while_other_tracks_mix(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    khmer_path = tmp_path / "0000.wav"
    missing_draft_path = tmp_path / "draft.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(khmer_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0",
        ORIGINAL_AUDIO_TRACK_ID,
        audio_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    khmer = make_timeline_clip(
        "khmer:0", KHMER_TTS_TRACK_ID, khmer_path, start=0.0, end=1.0, segment_id=0
    )
    draft = make_timeline_clip(
        "draft:0",
        DRAFT_REGENERATION_TRACK_ID,
        missing_draft_path,
        start=0.0,
        end=1.0,
        segment_id=0,
    )
    controller.set_timeline(make_timeline(original, khmer, draft))

    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"original:0", "khmer:0"}


def test_background_original_clip_plays_original_audio(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=3.0)
    controller = PlaybackController(VideoPlayerWidget())
    background = TimelineClip(
        id="background:original:0",
        track_id=ORIGINAL_AUDIO_TRACK_ID,
        start_time=1.0,
        end_time=2.0,
        source_path=audio_path,
        source_offset=1.0,
        locked=True,
        is_background=True,
    )
    controller.set_timeline(Timeline.from_clips([background]))

    controller.seek(1500)

    assert controller._active_khmer_clip_ids == {"background:original:0"}
    player, _output = controller._khmer_clip_players["background:original:0"]
    assert player.source() == QUrl.fromLocalFile(str(audio_path))


def test_khmer_volume_applies_fade(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip(
        "khmer:0", KHMER_TTS_TRACK_ID, clip_path, fade_in=0.5
    )
    controller.set_timeline(make_timeline(clip))

    controller.seek(0)
    assert controller._khmer_audio_output.volume() == 0.0

    controller.seek(500)
    assert controller._khmer_audio_output.volume() == 1.0


def test_khmer_timeline_playback_uses_same_natural_position_as_audition(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=2.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path, end=2.0)
    controller.set_timeline(make_timeline(clip))

    controller.seek(500)

    assert controller._pending_seek_ms[controller._khmer_audio_player] == 500


def test_khmer_playback_marked_pending_when_play_starts_during_load(qapp, tmp_path):
    clip_path = tmp_path / "0000.wav"
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    controller.set_timeline(make_timeline(clip))

    controller._on_play_requested()

    assert controller._khmer_audio_player in controller._pending_play


def test_sync_reuses_existing_audio_players(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip("original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path)
    khmer = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    controller.set_timeline(make_timeline(original, khmer))
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
        self.source_calls: list[QUrl] = []

    def source(self):
        return self._source

    def setSource(self, source):
        self.source_calls.append(source)
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
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path, end=2.0)
    fake_player = _CountingPlayer(QUrl.fromLocalFile(str(clip_path)), position=500)
    fake_output = _CountingOutput()
    controller.set_timeline(make_timeline(clip))
    controller._active_khmer_clip_ids = {"khmer:0"}
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}

    controller._sync_timeline_audio(520, start_playing=True)

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
    controller.set_timeline(make_timeline(clip))
    controller._active_khmer_clip_ids = {"khmer:0"}
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}

    controller._sync_timeline_audio(1500, start_playing=True)

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
    controller.set_timeline(make_timeline(clip))
    controller._active_khmer_clip_ids = {"khmer:0"}
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}

    controller._sync_timeline_audio(1600, start_playing=True)

    assert fake_player.seek_count == 1
    assert fake_player.play_count == 0


def test_changed_file_at_same_clip_source_url_is_reloaded(qapp, tmp_path):
    clip_path = tmp_path / "khmer_0.wav"
    make_wav(clip_path, seconds=1.0)
    url = QUrl.fromLocalFile(str(clip_path))
    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, clip_path)
    fake_player = _CountingPlayer(url, position=0)
    fake_output = _CountingOutput()
    controller._khmer_clip_players = {"khmer:0": (fake_player, fake_output)}
    controller._clip_source_fingerprints = {
        "khmer:0": (clip_path, 1, 1),
    }

    controller.set_timeline(make_timeline(clip))

    assert fake_player.source_calls == [QUrl(), url]


def test_original_and_khmer_volumes_are_independent(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    clip_path = tmp_path / "0000.wav"
    make_wav(audio_path, seconds=2.0)
    make_wav(clip_path, seconds=1.0)
    controller = PlaybackController(VideoPlayerWidget())
    original = make_timeline_clip(
        "original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, volume=1.0
    )
    khmer = make_timeline_clip(
        "khmer:0", KHMER_TTS_TRACK_ID, clip_path, volume=0.25
    )
    controller.set_timeline(make_timeline(original, khmer))

    controller.seek(500)

    assert {
        clip_id: output.volume()
        for clip_id, (_player, output) in controller._khmer_clip_players.items()
    } == {"original:0": 1.0, "khmer:0": 0.25}


def test_stop_stops_video_and_audio(qapp, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    video_player = VideoPlayerWidget()
    video_player.load_video(video_path)
    controller = PlaybackController(video_player)
    controller.stop()
    assert controller._sync_timer.isActive() is False


def test_pause_for_export_preserves_position_and_quiesces_timeline_audio(qapp, tmp_path):
    audio_path = tmp_path / "clip.wav"
    make_wav(audio_path, seconds=1.0)
    video = VideoPlayerWidget()
    controller = PlaybackController(video)
    controller.set_timeline(
        make_timeline(make_timeline_clip("khmer:0", KHMER_TTS_TRACK_ID, audio_path))
    )
    controller.seek(500)
    original_position = video.position_ms
    controller._sync_timer.start()

    controller.pause_for_export()

    assert video.position_ms == original_position
    assert not controller._sync_timer.isActive()
    assert all(
        player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        for player, _output in controller._khmer_clip_players.values()
    )


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
    clip = make_timeline_clip("original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, end=5.0)
    controller.set_timeline(make_timeline(clip))
    controller.seek(1000)
    player, _output = controller._khmer_clip_players["original:0"]
    pump_until(lambda: player.mediaStatus() == _LOADED)

    player.setPosition(5000)
    controller._maybe_resync(1000)
    assert player.position() == 1000


def test_resync_ignores_small_original_audio_drift(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    make_wav(audio_path, seconds=10.0)

    controller = PlaybackController(VideoPlayerWidget())
    clip = make_timeline_clip("original:0", ORIGINAL_AUDIO_TRACK_ID, audio_path, end=5.0)
    controller.set_timeline(make_timeline(clip))
    controller.seek(1000)
    player, _output = controller._khmer_clip_players["original:0"]
    pump_until(lambda: player.mediaStatus() == _LOADED)

    player.setPosition(1010)
    controller._maybe_resync(1000)
    assert player.position() == 1010


def test_make_wav_bytes_returns_valid_wav_bytes():
    assert make_wav_bytes().startswith(b"RIFF")
