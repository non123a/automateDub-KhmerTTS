from __future__ import annotations

from pathlib import Path

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
    Timeline,
)
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
        "Original Speech Segments",
        "Khmer TTS",
        "Draft Regeneration",
        "Audio Track 3",
        "Audio Track 4",
        "Original Movie Audio",
    )
    assert VIDEO_LANE == 0
    assert ORIGINAL_AUDIO_LANE == 1
    assert KHMER_TTS_LANE == 2
    assert ORIGINAL_MOVIE_AUDIO_LANE == 6


def test_default_timeline_has_no_original_movie_audio_track():
    timeline = Timeline.default()

    assert timeline.track_by_id(ORIGINAL_MOVIE_AUDIO_TRACK_ID) is None
    assert [track.name for track in timeline.tracks] == [
        "Video",
        "Original Speech Segments",
        "Khmer TTS",
        "Draft Regeneration",
    ]


def test_original_track_generation_uses_transcript_segments(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    tts_dir = tmp_path / "tts"
    widget = TimelineWidget()
    segments = _segments()

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tts_dir)

    assert len(widget._clips) == len(segments)
    movie_clips = [
        clip for clip in widget.timeline_clips
        if clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
    ]
    assert movie_clips == []
    assert widget.timeline.track_by_id(ORIGINAL_MOVIE_AUDIO_TRACK_ID) is None
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


def test_original_movie_clip_is_inserted_explicitly(qapp, tmp_path: Path):
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
    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None
    widget.add_timeline_clip(clip)

    assert widget.timeline.track_by_id(ORIGINAL_MOVIE_AUDIO_TRACK_ID) is not None
    movie_clips = [
        clip for clip in widget.timeline_clips
        if clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
    ]
    assert len(movie_clips) == 1
    movie = movie_clips[0]
    assert movie.segment_id is None
    assert movie.start_time == 0.0
    assert movie.end_time == 5.0
    assert movie.locked is False


def test_original_movie_audio_is_silent_until_inserted(qapp, tmp_path: Path):
    widget = TimelineWidget()
    widget.load_segments(_segments(), audio_path=tmp_path / "audio.wav")

    assert widget.timeline.active_audio_clips(0) == []

    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None
    widget.add_timeline_clip(clip)

    assert [
        active.track_id for active in widget.timeline.active_audio_clips(0)
    ] == [ORIGINAL_MOVIE_AUDIO_TRACK_ID]


def test_repeated_original_movie_insert_creates_exactly_one_track(qapp, tmp_path: Path):
    widget = TimelineWidget()
    widget.load_segments(_segments(), audio_path=tmp_path / "audio.wav")

    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None
    widget.add_timeline_clip(clip)

    assert widget.insert_original_movie_audio_clip() is None
    tracks = [
        track for track in widget.timeline.tracks
        if track.id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
    ]
    clips = [
        clip for clip in widget.timeline_clips
        if clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
    ]
    assert len(tracks) == 1
    assert len(clips) == 1


def test_inserted_original_movie_clip_is_editable(qapp, tmp_path: Path):
    audio_path = tmp_path / "audio.wav"
    widget = TimelineWidget()
    segments = [
        Segment(id=1, start=0.0, end=1.0, source_text="one", target_text="uno"),
        Segment(id=2, start=2.0, end=3.0, source_text="two", target_text="dos"),
    ]

    widget.load_segments(segments, audio_path=audio_path, tts_directory=tmp_path / "tts")
    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None
    widget.add_timeline_clip(clip)

    movie = next(
        clip for clip in widget.timeline_clips
        if clip.track_id == "original_movie_audio"
    )
    item = widget._clips_by_clip_id[movie.id]
    assert movie.segment_id is None
    assert movie.locked is False
    assert item._id_label is None
    widget.set_timeline_clip_volume(movie.id, 0.25)
    assert movie.volume == 0.25


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
    assert all(clip.track_id != "original_movie_audio" for clip in widget.timeline_clips)


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
