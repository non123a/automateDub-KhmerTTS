from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF

from automatedub_studio.playback.playback_controller import PlaybackController
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    AUDIO_TRACK_3_ID,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)
from automatedub_studio.timeline.timeline_widget import (
    AUDIO_TRACK_3_LANE,
    TimelineWidget,
    _lane_y,
)


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


def test_timeline_move_clip_updates_time_track_and_allows_overlap(tmp_path: Path):
    timeline = Timeline.default()
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    audio_3 = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert khmer is not None
    assert audio_3 is not None
    first = _clip("clip:1", KHMER_TTS_TRACK_ID, tmp_path / "one.wav", 0.0, 5.0)
    second = _clip("clip:2", AUDIO_TRACK_3_ID, tmp_path / "two.wav", 2.0, 6.0)
    khmer.clips.append(first)
    audio_3.clips.append(second)

    moved = timeline.move_clip("clip:1", AUDIO_TRACK_3_ID, 2.0)

    assert moved is True
    assert first.track_id == AUDIO_TRACK_3_ID
    assert first.start_time == 2.0
    assert first.end_time == 7.0
    assert {clip.id for clip in timeline.active_audio_clips(3000)} == {"clip:1", "clip:2"}


def test_widget_move_clip_updates_time_track_and_emits_once(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    changes: list[None] = []
    widget.timelineChanged.connect(lambda: changes.append(None))
    widget.load_segments([segment])

    moved = widget.move_timeline_clip("khmer:1", AUDIO_TRACK_3_ID, 2.25)

    clip = widget._clips_by_clip_id["khmer:1"].timeline_clip
    assert moved is True
    assert clip.track_id == AUDIO_TRACK_3_ID
    assert clip.start_time == 2.25
    assert clip.end_time == 3.25
    assert changes == [None]


def test_track_lock_prevents_clip_track_move(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    widget.load_segments([segment])
    widget.set_track_locked(AUDIO_TRACK_3_ID, True)

    moved = widget.move_timeline_clip_to_track("khmer:1", AUDIO_TRACK_3_ID)

    assert moved is False
    assert widget._clips_by_clip_id["khmer:1"].timeline_clip.track_id == KHMER_TTS_TRACK_ID


def test_widget_move_clip_rejects_locked_track_without_emit(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    changes: list[None] = []
    widget.timelineChanged.connect(lambda: changes.append(None))
    widget.load_segments([segment])
    widget.set_track_locked(AUDIO_TRACK_3_ID, True)
    changes.clear()

    moved = widget.move_timeline_clip("khmer:1", AUDIO_TRACK_3_ID, 2.25)

    clip = widget._clips_by_clip_id["khmer:1"].timeline_clip
    assert moved is False
    assert clip.track_id == KHMER_TTS_TRACK_ID
    assert clip.start_time == 1.0
    assert changes == []


def test_drop_signal_moves_clip_to_target_track_and_emits_change(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    changes: list[None] = []
    widget.timelineChanged.connect(lambda: changes.append(None))
    widget.load_segments([segment])

    widget._on_clip_track_change_requested("khmer:1", AUDIO_TRACK_3_ID)

    assert widget._clips_by_clip_id["khmer:1"].timeline_clip.track_id == AUDIO_TRACK_3_ID
    assert changes == [None]


def test_drag_preview_visibly_moves_clip_to_hovered_track(qapp):
    widget = TimelineWidget()
    segment = Segment(id=1, start=1.0, end=2.0, source_text="source", target_text="target")
    widget.load_segments([segment])
    clip_item = widget._clips_by_clip_id["khmer:1"]
    widget._view._drag_clip = clip_item

    widget._view._drag_grab_offset_x = 10.0
    widget._view._drag_grab_offset_y = 10.0
    widget._view._preview_drag_to_scene_position(
        QPointF(widget._time_to_x(2.0) + 10, _lane_y(AUDIO_TRACK_3_LANE) + 10)
    )

    assert clip_item.lane == AUDIO_TRACK_3_LANE
    assert clip_item.rect().x() == widget._time_to_x(2.0)
    assert clip_item.rect().y() == _lane_y(AUDIO_TRACK_3_LANE) + 4


def test_playback_reflects_timeline_track_mutation(tmp_path: Path):
    timeline = Timeline.default()
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    audio_3 = timeline.track_by_id(AUDIO_TRACK_3_ID)
    assert khmer is not None
    assert audio_3 is not None
    khmer.muted = True
    clip = _clip("clip:1", KHMER_TTS_TRACK_ID, tmp_path / "clip.wav")
    khmer.clips.append(clip)

    assert timeline.active_audio_clips(500) == []

    assert timeline.move_clip_to_track("clip:1", AUDIO_TRACK_3_ID) is True

    assert timeline.active_audio_clips(500) == [clip]


def test_playback_controller_receives_mutated_timeline(qapp, tmp_path: Path):
    timeline = Timeline.default()
    khmer = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    assert khmer is not None
    khmer.muted = True
    clip = _clip("clip:1", KHMER_TTS_TRACK_ID, tmp_path / "clip.wav")
    khmer.clips.append(clip)
    controller = PlaybackController(VideoPlayerWidget())

    controller.set_timeline(timeline)
    controller.seek(500)
    assert controller._active_khmer_clip_ids == set()

    timeline.move_clip_to_track("clip:1", AUDIO_TRACK_3_ID)
    controller.set_timeline(timeline)
    controller.seek(500)

    assert controller._active_khmer_clip_ids == {"clip:1"}
