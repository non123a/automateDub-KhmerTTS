from __future__ import annotations

from pathlib import Path

from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    AUDIO_TRACK_3_ID,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)
from automatedub_studio.timeline.timeline_widget import TimelineWidget


def _clip(
    clip_id: str,
    track_id: str,
    path: Path,
    start: float = 0.0,
    end: float = 1.0,
) -> TimelineClip:
    return TimelineClip(
        id=clip_id,
        track_id=track_id,
        start_time=start,
        end_time=end,
        source_path=path,
    )


def test_timeline_model_serializes_and_deserializes_tracks(tmp_path: Path):
    timeline = Timeline.default()
    track = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert track is not None
    track.muted = True
    track.solo = True
    track.locked = True
    track.clips.append(_clip("music:1", AUDIO_TRACK_3_ID, tmp_path / "music.wav"))

    restored = Timeline.from_dict(timeline.to_dict())
    restored_track = restored.track_by_id(AUDIO_TRACK_3_ID)

    assert restored_track is not None
    assert restored_track.muted is True
    assert restored_track.solo is True
    assert restored_track.locked is True
    assert restored_track.clips[0].id == "music:1"
    assert restored_track.clips[0].source_path == tmp_path / "music.wav"


def test_playback_active_audio_clips_include_multiple_generic_tracks(tmp_path: Path):
    timeline = Timeline.default()
    original = timeline.track_by_id(ORIGINAL_AUDIO_TRACK_ID)
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    audio_3 = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert original is not None
    assert khmer is not None
    assert audio_3 is not None
    original.clips.append(_clip("original:1", ORIGINAL_AUDIO_TRACK_ID, tmp_path / "audio.wav"))
    khmer.clips.append(_clip("khmer:1", KHMER_TTS_TRACK_ID, tmp_path / "khmer.wav"))
    audio_3.clips.append(_clip("music:1", AUDIO_TRACK_3_ID, tmp_path / "music.wav"))

    active_ids = {clip.id for clip in timeline.active_audio_clips(500)}

    assert active_ids == {"original:1", "khmer:1", "music:1"}


def test_track_mute_prevents_playback_discovery(tmp_path: Path):
    timeline = Timeline.default()
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    audio_3 = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert khmer is not None
    assert audio_3 is not None
    khmer.clips.append(_clip("khmer:1", KHMER_TTS_TRACK_ID, tmp_path / "khmer.wav"))
    audio_3.clips.append(_clip("music:1", AUDIO_TRACK_3_ID, tmp_path / "music.wav"))

    khmer.muted = True

    assert [clip.id for clip in timeline.active_audio_clips(500)] == ["music:1"]


def test_track_solo_filters_playback_discovery(tmp_path: Path):
    timeline = Timeline.default()
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    audio_3 = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert khmer is not None
    assert audio_3 is not None
    khmer.clips.append(_clip("khmer:1", KHMER_TTS_TRACK_ID, tmp_path / "khmer.wav"))
    audio_3.clips.append(_clip("music:1", AUDIO_TRACK_3_ID, tmp_path / "music.wav"))

    audio_3.solo = True

    assert [clip.id for clip in timeline.active_audio_clips(500)] == ["music:1"]


def test_widget_moves_clip_between_audio_tracks_preserving_timing(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    widget.load_segments([segment])
    clip = widget._clips_by_clip_id["khmer:1"].timeline_clip
    assert clip is not None

    moved = widget.move_timeline_clip_to_track("khmer:1", AUDIO_TRACK_3_ID)

    assert moved is True
    assert clip.track_id == AUDIO_TRACK_3_ID
    assert clip.start_time == 1.0
    assert clip.end_time == 2.0


def test_track_lock_prevents_clip_track_move(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    widget.load_segments([segment])
    widget.set_track_locked(AUDIO_TRACK_3_ID, True)

    moved = widget.move_timeline_clip_to_track("khmer:1", AUDIO_TRACK_3_ID)

    assert moved is False
    assert widget._clips_by_clip_id["khmer:1"].timeline_clip.track_id == KHMER_TTS_TRACK_ID
