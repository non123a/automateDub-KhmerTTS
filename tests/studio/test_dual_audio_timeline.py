from __future__ import annotations

from pathlib import Path

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_widget import (
    AUDIO_TRACK_COUNT,
    BASE_PIXELS_PER_SECOND,
    KHMER_TTS_LANE,
    LANE_NAMES,
    ORIGINAL_AUDIO_LANE,
    VIDEO_LANE,
    TimelineWidget,
)


def _segments() -> list[Segment]:
    return [
        Segment(
            id=10,
            start=1.25,
            end=2.50,
            source_text="source 10",
            target_text="target 10",
        ),
        Segment(
            id=11,
            start=3.00,
            end=4.25,
            source_text="source 11",
            target_text="target 11",
        ),
    ]


def test_timeline_displays_video_original_audio_and_khmer_tracks(qapp):
    assert LANE_NAMES == ("Video", "Original Audio", "Khmer TTS")
    assert VIDEO_LANE == 0
    assert ORIGINAL_AUDIO_LANE == 1
    assert KHMER_TTS_LANE == 2


def test_original_track_generation_uses_transcript_segments(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    widget = TimelineWidget()
    segments = _segments()

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tts_dir)

    assert len(widget._clips) == len(segments) * AUDIO_TRACK_COUNT
    original_clips = [
        clip for clips in widget._clips_by_segment.values() for clip in clips
        if clip.lane == ORIGINAL_AUDIO_LANE
    ]
    assert [clip.segment.id for clip in original_clips] == [10, 11]


def test_original_clip_timing_matches_transcript(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    widget = TimelineWidget()
    segment = _segments()[0]

    widget.load_segments([segment], audio_path=audio_path)

    original_clip = next(
        clip for clip in widget._clips_by_segment[segment.id]
        if clip.lane == ORIGINAL_AUDIO_LANE
    )
    assert original_clip.segment.start == segment.start
    assert original_clip.segment.end == segment.end
    assert abs(original_clip.rect().width() - 1.25 * BASE_PIXELS_PER_SECOND) < 0.1


def test_original_clip_references_source_audio_window(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    widget = TimelineWidget()
    segment = _segments()[0]

    widget.load_segments([segment], audio_path=audio_path)

    original_clip = next(
        clip for clip in widget._clips_by_segment[segment.id]
        if clip.lane == ORIGINAL_AUDIO_LANE
    )
    assert original_clip._wav_path == audio_path
    assert original_clip._wav_start_seconds == segment.start
    assert original_clip._wav_end_seconds == segment.end


def test_khmer_track_uses_existing_tts_clip_path(qapp, tmp_path: Path):
    tts_dir = tmp_path / "tts"
    widget = TimelineWidget()
    segment = _segments()[0]

    widget.load_segments([segment], tts_directory=tts_dir)

    khmer_clip = next(
        clip for clip in widget._clips_by_segment[segment.id]
        if clip.lane == KHMER_TTS_LANE
    )
    assert khmer_clip._wav_path == tts_segment_output_path(tts_dir, segment.id)
    assert khmer_clip._wav_start_seconds == 0.0
    assert khmer_clip._wav_end_seconds is None


def test_audio_tracks_stay_synchronized_with_transcript(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    widget = TimelineWidget()
    segment = _segments()[1]

    widget.load_segments([segment], audio_path=audio_path, tts_directory=tts_dir)

    original_clip = next(
        clip for clip in widget._clips_by_segment[segment.id]
        if clip.lane == ORIGINAL_AUDIO_LANE
    )
    khmer_clip = next(
        clip for clip in widget._clips_by_segment[segment.id]
        if clip.lane == KHMER_TTS_LANE
    )
    assert original_clip.rect().x() == khmer_clip.rect().x()
    assert original_clip.rect().width() == khmer_clip.rect().width()
