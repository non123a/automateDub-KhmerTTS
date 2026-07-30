from __future__ import annotations

from pathlib import Path

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_widget import (
    BASE_PIXELS_PER_SECOND,
    KHMER_TTS_LANE,
    LANE_NAMES,
    ORIGINAL_AUDIO_LANE,
    ORIGINAL_MOVIE_AUDIO_LANE,
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


def _write_tts_file(tts_dir: Path, segment_id: int) -> Path:
    tts_dir.mkdir(parents=True, exist_ok=True)
    path = tts_segment_output_path(tts_dir, segment_id)
    path.write_bytes(b"RIFF....WAVEfmt ")
    return path


def test_timeline_displays_reference_and_editable_audio_tracks(qapp):
    assert LANE_NAMES == (
        "Video",
        "Original Movie Audio",
        "Original Speech Segments",
        "Khmer TTS",
        "Draft Regeneration",
        "Audio Track 3",
        "Audio Track 4",
    )
    assert VIDEO_LANE == 0
    assert ORIGINAL_MOVIE_AUDIO_LANE == 1
    assert ORIGINAL_AUDIO_LANE == 2
    assert KHMER_TTS_LANE == 3


def test_original_track_generation_uses_transcript_segments(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    widget = TimelineWidget()
    segments = _segments()

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tts_dir)

    assert len(widget._clips) == len(segments) + 1
    movie_clips = [
        clip for clip in widget.timeline_clips
        if clip.track_id == "original_movie_audio"
    ]
    assert len(movie_clips) == 1
    assert movie_clips[0].start_time == 0.0
    assert movie_clips[0].end_time == max(segment.end for segment in segments)
    assert movie_clips[0].locked is True
    original_clips = [
        clip for clips in widget._clips_by_segment.values() for clip in clips
        if clip.lane == ORIGINAL_AUDIO_LANE
    ]
    assert [clip.segment.id for clip in original_clips] == [10, 11]


def test_original_clips_exist_for_segments_without_khmer_tts(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    segments = _segments()
    _write_tts_file(tts_dir, segments[0].id)
    widget = TimelineWidget()

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tts_dir)

    original_ids = [
        clip.timeline_clip.segment_id
        for clip in widget._clips
        if clip.timeline_clip.track_id == "original_audio"
        and not clip.timeline_clip.is_background
    ]
    khmer_ids = [
        clip.timeline_clip.segment_id
        for clip in widget._clips
        if clip.timeline_clip.track_id == "khmer_tts"
    ]

    assert original_ids == [10, 11]
    assert khmer_ids == [10]


def test_continuous_original_movie_clip_fills_timing_gaps(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    segments = [
        Segment(id=1, start=1.0, end=2.0, source_text="one", target_text="uno"),
        Segment(id=2, start=2.6, end=5.0,
                source_text="two", target_text="dos"),
    ]
    _write_tts_file(tts_dir, 1)
    _write_tts_file(tts_dir, 2)
    widget = TimelineWidget()

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tts_dir)

    references = [
        clip for clip in widget.timeline_clips
        if clip.track_id == "original_movie_audio"
    ]
    assert len(references) == 1
    reference = references[0]
    assert reference.segment_id is None
    assert reference.start_time == 0.0
    assert reference.end_time == 5.0
    assert reference.locked is True


def test_continuous_original_movie_clip_is_read_only(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    widget = TimelineWidget()
    segments = [
        Segment(id=1, start=0.0, end=1.0, source_text="one", target_text="uno"),
        Segment(id=2, start=2.0, end=3.0, source_text="two", target_text="dos"),
    ]

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tmp_path / "tts")

    reference = next(
        clip for clip in widget.timeline_clips
        if clip.track_id == "original_movie_audio"
    )
    item = widget._clips_by_clip_id[reference.id]
    assert reference.segment_id is None
    assert reference.locked is True
    assert item._id_label is None
    old_volume = reference.volume
    widget.set_timeline_clip_volume(reference.id, 0.25)
    widget.set_timeline_clip_translation(reference.id, "must not edit")
    assert reference.volume == old_volume
    assert reference.khmer_text == ""


def test_reference_clip_never_creates_khmer_clip(qapp, tmp_path: Path):
    widget = TimelineWidget()
    segments = [
        Segment(id=1, start=0.0, end=1.0, source_text="one", target_text="uno"),
        Segment(id=2, start=3.0, end=4.0, source_text="two", target_text="dos"),
    ]
    _write_tts_file(tmp_path / "tts", 1)
    _write_tts_file(tmp_path / "tts", 2)

    widget.load_segments(segments, tts_directory=tmp_path / "tts")

    assert [
        clip.id
        for clip in widget.timeline_clips
        if clip.track_id == "khmer_tts"
    ] == ["khmer:1", "khmer:2"]
    assert all(
        clip.track_id != "khmer_tts"
        for clip in widget.timeline_clips
        if clip.track_id == "original_movie_audio"
    )


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
    _write_tts_file(tts_dir, segment.id)

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
    _write_tts_file(tts_dir, segment.id)

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
