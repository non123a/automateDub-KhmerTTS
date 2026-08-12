from __future__ import annotations

import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QUndoStack

from automatedub_studio.edit.commands import DeleteTimelineClipsCommand
from automatedub_studio.playback.playback_controller import PlaybackController
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment
from automatedub_studio.project.timeline_edits import load_timeline_edits, save_timeline_edits
from automatedub_studio.timeline.timeline_clip import (
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
    TimelineMarker,
)
from automatedub_studio.timeline.timeline_widget import TimelineWidget


def _segment(segment_id: int, start: float, end: float) -> Segment:
    return Segment(
        id=segment_id,
        start=start,
        end=end,
        source_text=f"source {segment_id}",
        target_text=f"target {segment_id}",
    )


def _wav(path: Path, seconds: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


def test_timeline_marker_round_trip(tmp_path):
    timeline = Timeline.default()
    timeline.add_clip(
        TimelineClip(
            id="original:1",
            track_id=ORIGINAL_AUDIO_TRACK_ID,
            start_time=0.0,
            end_time=1.0,
            source_path=tmp_path / "audio.wav",
        )
    )
    timeline.markers.append(
        TimelineMarker(id="marker:0", time_ms=500, comment="cut here")  # type: ignore[name-defined]
    )

    payload = timeline.to_dict()
    restored = Timeline.from_dict(payload)

    assert restored.markers[0].comment == "cut here"
    assert restored.markers[0].time_ms == 500


def test_timeline_search_and_jump(qapp, tmp_path):
    widget = TimelineWidget()
    _wav(tmp_path / "0001.wav")
    widget.load_segments(
        [_segment(1, 0.0, 1.0)],
        audio_path=_wav(tmp_path / "audio.wav"),
        tts_directory=tmp_path,
    )

    matches = widget.find_matching_clips("source 1")

    assert [clip.id for clip in matches] == ["original:1", "khmer:1"]
    assert widget.jump_to_clip("khmer:1") is True
    assert widget.playhead_ms == 0


def test_playback_rate_updates_video_and_pooled_audio_players(qapp):
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_playback_rate(1.5)

    assert controller._video_player.playback_rate == pytest.approx(1.5)
    assert controller._original_audio_player is None
    assert controller._khmer_audio_player.playbackRate() == pytest.approx(1.5)


def test_frame_step_and_segment_navigation_seek(qapp, tmp_path, monkeypatch):
    controller = PlaybackController(VideoPlayerWidget())
    timeline = Timeline.from_clips(
        [
            TimelineClip(
                id="original:1",
                track_id=ORIGINAL_AUDIO_TRACK_ID,
                start_time=1.0,
                end_time=2.0,
                source_path=_wav(tmp_path / "audio.wav"),
            ),
            TimelineClip(
                id="khmer:2",
                track_id=KHMER_TTS_TRACK_ID,
                start_time=3.0,
                end_time=4.0,
                source_path=_wav(tmp_path / "tts.wav"),
            ),
        ]
    )
    controller.set_timeline(timeline)
    monkeypatch.setattr(VideoPlayerWidget, "position_ms", property(lambda self: 1500))

    calls: list[int] = []
    monkeypatch.setattr(controller, "seek", lambda position_ms: calls.append(position_ms))

    controller.step_frame(1)
    controller.previous_segment()
    controller.next_segment()

    assert calls[0] == 1533
    assert calls[1] == 1000
    assert calls[2] == 3000


def test_loop_selection_seeks_back_to_selection_start(qapp, tmp_path, monkeypatch):
    controller = PlaybackController(VideoPlayerWidget())
    clip = TimelineClip(
        id="khmer:1",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=1.0,
        end_time=2.0,
        source_path=_wav(tmp_path / "tts.wav"),
        selected=True,
    )
    controller.set_timeline(Timeline.from_clips([clip]))
    controller.set_loop_selection_enabled(True)

    calls: list[int] = []
    monkeypatch.setattr(controller, "seek", lambda position_ms: calls.append(position_ms))
    controller._maybe_loop(2500)

    assert calls == [1000]


def test_delete_selected_clips_is_undoable(qapp, tmp_path):
    widget = TimelineWidget()
    _wav(tmp_path / "0001.wav")
    widget.load_segments(
        [_segment(1, 0.0, 1.0)],
        audio_path=_wav(tmp_path / "audio.wav"),
        tts_directory=tmp_path,
    )
    clip_item = widget._clips_by_clip_id["khmer:1"]
    clip_item.setSelected(True)
    stack = QUndoStack()

    stack.push(
        DeleteTimelineClipsCommand(
            [clip_item.timeline_clip.id], widget.remove_timeline_clip, widget.add_timeline_clip
        )
    )

    assert widget._clips_by_clip_id.get("khmer:1") is None
    stack.undo()
    assert widget._clips_by_clip_id["khmer:1"].timeline_clip is not None


def test_timeline_edits_include_markers(tmp_path):
    timeline = Timeline.default()
    timeline.markers.append(TimelineMarker(id="marker:0", time_ms=500, comment="note"))

    save_timeline_edits(timeline, tmp_path)
    restored = load_timeline_edits(tmp_path)

    assert restored is not None
    assert restored.markers[0].comment == "note"
