from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QUrl

from automatedub.vertical_slice.mix import MixSpeechTrack
from automatedub.vertical_slice.tts import tts_segment_output_path
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
    Timeline,
    TimelineClip,
    active_clips,
)
from automatedub_studio.timeline.timeline_widget import TimelineWidget
from automatedub_studio.ui.main_window import MainWindow


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


def _settings(path: Path) -> QSettings:
    return QSettings(str(path / "settings.ini"), QSettings.Format.IniFormat)


def _write_tts_file(tts_dir: Path, segment_id: int) -> Path:
    tts_dir.mkdir(parents=True, exist_ok=True)
    path = tts_segment_output_path(tts_dir, segment_id)
    path.write_bytes(b"placeholder")
    return path


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
    _write_tts_file(tmp_path, 10)
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"]
    khmer = widget._clips_by_clip_id["khmer:10"]

    original.setSelected(True)

    assert [clip.id for clip in widget.selected_timeline_clips] == ["original:10"]
    assert khmer.isSelected() is False


def test_reference_clips_show_lock_icon_and_remain_selectable(qapp, tmp_path):
    widget = TimelineWidget()
    _write_tts_file(tmp_path, 10)
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"]

    original.setSelected(True)

    assert original.locked is True
    assert original._lock_label is not None
    assert original.isSelected() is True


def test_reference_drag_and_trim_emit_read_only_feedback(qapp, tmp_path):
    widget = TimelineWidget()
    _write_tts_file(tmp_path, 10)
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"].timeline_clip
    assert original is not None
    messages = []
    widget.referenceClipActionBlocked.connect(lambda: messages.append("blocked"))

    widget.apply_timeline_clip_offset("original:10", 500)
    widget.apply_timeline_clip_trim("original:10", 1.1, 1.8)

    assert original.start_time == 1.0
    assert original.end_time == 2.0
    assert messages == ["blocked", "blocked"]


def test_moving_one_timeline_clip_does_not_move_sibling_track_clip(qapp, tmp_path):
    widget = TimelineWidget()
    _write_tts_file(tmp_path, 10)
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path)
    original = widget._clips_by_clip_id["original:10"]
    khmer = widget._clips_by_clip_id["khmer:10"]
    khmer_x = khmer.sceneBoundingRect().x()

    widget.apply_timeline_clip_offset("khmer:10", 500)

    assert original.timeline_clip.start_time == 1.0
    assert khmer.timeline_clip.start_time == 1.5
    assert original.sceneBoundingRect().x() == khmer_x


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
    first_clip = TimelineClip(
        id="khmer:0",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=0.0,
        end_time=1.0,
        source_path=first_path,
    )
    second_clip = TimelineClip(
        id="khmer:1",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=1.0,
        end_time=2.0,
        source_path=second_path,
    )
    controller.set_timeline(Timeline.from_clips([first_clip, second_clip]))

    first_player = controller._khmer_clip_players["khmer:0"][0]
    second_player = controller._khmer_clip_players["khmer:1"][0]

    assert first_player.source() == QUrl.fromLocalFile(str(first_path))
    assert second_player.source() == QUrl.fromLocalFile(str(second_path))
    controller._sync_timeline_audio(1200, start_playing=False)
    assert second_player.source() == QUrl.fromLocalFile(str(second_path))


def test_inspector_does_not_edit_read_only_original_clip(qapp, tmp_path):
    window = MainWindow(settings=_settings(tmp_path))
    _write_tts_file(tmp_path, 10)
    window.timeline.load_segments(
        [_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path
    )
    original = window.timeline._clips_by_clip_id["original:10"]
    khmer = window.timeline._clips_by_clip_id["khmer:10"]

    original.setSelected(True)
    window.inspector._volume_slider.setValue(25)

    assert original.timeline_clip.volume == 1.0
    assert khmer.timeline_clip.volume == 1.0


def test_inspector_opens_reference_clip_in_read_only_mode(qapp, tmp_path):
    window = MainWindow(settings=_settings(tmp_path))
    _write_tts_file(tmp_path, 10)
    window.timeline.load_segments(
        [_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path
    )
    original = window.timeline._clips_by_clip_id["original:10"]

    original.setSelected(True)

    assert window.inspector._timeline_clip is original.timeline_clip
    assert "Reference Clip" in window.inspector._reference_message_label.text()
    assert window.inspector._reference_message_label.isHidden() is False
    assert window.inspector._khmer_text_edit.isEnabled() is False
    assert window.inspector._save_translation_button.isEnabled() is False
    assert window.inspector._regenerate_button.isEnabled() is False
    assert window.inspector._delete_button.isEnabled() is False
    assert window.inspector._original_text_label.toPlainText() == "source"


def test_inspector_volume_changes_selected_khmer_clip_only(qapp, tmp_path):
    window = MainWindow(settings=_settings(tmp_path))
    _write_tts_file(tmp_path, 10)
    window.timeline.load_segments(
        [_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path
    )
    original = window.timeline._clips_by_clip_id["original:10"]
    khmer = window.timeline._clips_by_clip_id["khmer:10"]

    khmer.setSelected(True)
    window.inspector._volume_slider.setValue(40)

    assert khmer.timeline_clip.volume == 0.4
    assert original.timeline_clip.volume == 1.0


def test_inspector_does_not_edit_read_only_original_mute_state(qapp, tmp_path):
    window = MainWindow(settings=_settings(tmp_path))
    _write_tts_file(tmp_path, 10)
    window.timeline.load_segments(
        [_segment()], audio_path=tmp_path / "audio.wav", tts_directory=tmp_path
    )
    original = window.timeline._clips_by_clip_id["original:10"]
    khmer = window.timeline._clips_by_clip_id["khmer:10"]

    original.setSelected(True)
    window.inspector._muted_check.setChecked(True)

    assert original.timeline_clip.muted is False
    assert khmer.timeline_clip.muted is False


def test_playback_reads_muted_volume_and_timing_from_timeline_clip(qapp, tmp_path):
    audio_path = tmp_path / "audio.wav"
    tts_path = tmp_path / "0000.wav"
    audio_path.write_bytes(b"placeholder")
    tts_path.write_bytes(b"placeholder")
    original = TimelineClip(
        id="original:1",
        track_id=ORIGINAL_AUDIO_TRACK_ID,
        start_time=0.0,
        end_time=1.0,
        source_path=audio_path,
        volume=0.3,
        muted=True,
    )
    khmer = TimelineClip(
        id="khmer:1",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=0.5,
        end_time=1.5,
        source_path=tts_path,
        volume=0.7,
    )
    controller = PlaybackController(VideoPlayerWidget())
    controller.set_timeline_clips([original, khmer])

    controller._sync_audio_to_position(750, start_playing=False)

    assert controller._active_khmer_clip_ids == {"khmer:1"}
    assert controller._khmer_clip_players["khmer:1"][1].volume() == pytest.approx(0.7)
