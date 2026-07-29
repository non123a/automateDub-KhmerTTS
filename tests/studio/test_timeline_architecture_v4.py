from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub_studio.playback.playback_controller import PlaybackController
from automatedub_studio.playback.timeline_audio import (
    build_khmer_timeline_clips,
    build_original_timeline_clips,
)
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    TimelineClip,
    active_clips,
)
from automatedub_studio.timeline.timeline_widget import TimelineWidget


def _segment(segment_id: int = 10) -> Segment:
    return Segment(
        id=segment_id,
        start=1.0,
        end=2.0,
        source_text="source",
        target_text="target",
    )


def _track(track_id: int, path: Path, delay_ms: int = 1000) -> MixSpeechTrack:
    return MixSpeechTrack(
        id=track_id,
        start=delay_ms / 1000.0,
        end=delay_ms / 1000.0 + 1.0,
        delay_ms=delay_ms,
        atempo=1.0,
        generated_duration=1.0,
        tts_path=path,
    )


def test_original_and_khmer_timeline_clips_have_independent_ids_and_state(tmp_path):
    audio_path = tmp_path / "audio.wav"
    tts_path = tmp_path / "00010.wav"
    segment = _segment()

    original = build_original_timeline_clips(audio_path, [segment])[0]
    khmer = build_khmer_timeline_clips([_track(segment.id, tts_path)])[0]

    assert original.id == "original:10"
    assert khmer.id == "khmer:10"
    assert original.track_id == ORIGINAL_AUDIO_TRACK_ID
    assert khmer.track_id == KHMER_TTS_TRACK_ID

    original.volume = 0.2
    original.muted = True

    assert khmer.volume == 1.0
    assert khmer.muted is False


def test_timeline_selection_is_clip_id_based_not_segment_deduped(qapp, tmp_path):
    widget = TimelineWidget()
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"]
    khmer = widget._clips_by_clip_id["khmer:10"]

    original.setSelected(True)

    assert [clip.id for clip in widget.selected_timeline_clips] == ["original:10"]
    assert khmer.isSelected() is False


def test_moving_one_timeline_clip_does_not_move_sibling_track_clip(qapp, tmp_path):
    widget = TimelineWidget()
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"]
    khmer = widget._clips_by_clip_id["khmer:10"]
    khmer_x = khmer.sceneBoundingRect().x()

    widget.apply_timeline_clip_offset("original:10", 500)

    assert original.timeline_clip.start_time == 1.5
    assert khmer.timeline_clip.start_time == 1.0
    assert khmer.sceneBoundingRect().x() == khmer_x


def test_active_clips_respects_track_and_clip_mute(tmp_path):
    original = TimelineClip(
        id="original:1",
        track_id=ORIGINAL_AUDIO_TRACK_ID,
        start_time=0.0,
        end_time=1.0,
        source_path=tmp_path / "audio.wav",
        muted=True,
    )
    khmer = TimelineClip(
        id="khmer:1",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=0.0,
        end_time=1.0,
        source_path=tmp_path / "0001.wav",
    )

    assert active_clips([original, khmer], ORIGINAL_AUDIO_TRACK_ID, 500) == []
    assert active_clips([original, khmer], KHMER_TTS_TRACK_ID, 500) == [khmer]


def test_playback_preloads_khmer_sources_without_boundary_set_source(qapp, tmp_path):
    first_path = tmp_path / "0000.wav"
    second_path = tmp_path / "0001.wav"
    first_path.write_bytes(b"placeholder")
    second_path.write_bytes(b"placeholder")
    controller = PlaybackController(VideoPlayerWidget())

    controller.set_sources(
        None,
        [],
        [_track(0, first_path, delay_ms=0), _track(1, second_path, delay_ms=1000)],
    )

    first_player = controller._khmer_clip_players["khmer:0"][0]
    second_player = controller._khmer_clip_players["khmer:1"][0]

    assert first_player.source() == QUrl.fromLocalFile(str(first_path))
    assert second_player.source() == QUrl.fromLocalFile(str(second_path))
    controller._sync_khmer_audio(1200, start_playing=False)
    assert second_player.source() == QUrl.fromLocalFile(str(second_path))
