"""Generate initial Studio timeline artifacts from pipeline outputs."""

from __future__ import annotations

from pathlib import Path

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.loader import load_segments
from automatedub_studio.project.models import Segment
from automatedub_studio.project.timeline_edits import save_timeline_edits
from automatedub_studio.timeline.timeline_clip import (
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)


def build_initial_timeline(
    *,
    project_path: Path,
    translation_path: Path,
    audio_path: Path,
    tts_directory: Path | None = None,
) -> Timeline:
    segments = load_segments(translation_path)
    timeline = Timeline.default()
    original_track = timeline.track_by_id(ORIGINAL_AUDIO_TRACK_ID)
    khmer_track = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    if original_track is None or khmer_track is None:
        return timeline

    ordered_segments = sorted(segments, key=lambda item: (item.start, item.id))
    original_track.clips = _build_original_speech_clips(ordered_segments, audio_path)
    khmer_track.clips = _build_existing_khmer_clips(
        ordered_segments,
        tts_directory,
    )
    save_timeline_edits(timeline, project_path / "timeline")
    return timeline


def _build_original_speech_clips(
    segments: list[Segment],
    audio_path: Path,
) -> list[TimelineClip]:
    return [
        TimelineClip(
            id=f"original:{segment.id}",
            track_id=ORIGINAL_AUDIO_TRACK_ID,
            start_time=segment.start,
            end_time=segment.end,
            source_path=audio_path,
            source_offset=segment.start,
            segment_id=segment.id,
            source_text=segment.source_text,
            target_text=segment.target_text,
            chinese_text=segment.source_text,
            khmer_text=segment.target_text,
            locked=True,
        )
        for segment in segments
    ]


def _build_existing_khmer_clips(
    segments: list[Segment],
    tts_directory: Path | None,
) -> list[TimelineClip]:
    if tts_directory is None:
        return []
    clips: list[TimelineClip] = []
    for segment in segments:
        source_path = tts_segment_output_path(tts_directory, segment.id)
        if not source_path.is_file():
            continue
        clips.append(
            TimelineClip(
                id=f"khmer:{segment.id}",
                track_id=KHMER_TTS_TRACK_ID,
                start_time=segment.start,
                end_time=segment.end,
                source_path=source_path,
                source_offset=0.0,
                segment_id=segment.id,
                source_text=segment.source_text,
                target_text=segment.target_text,
                chinese_text=segment.source_text,
                khmer_text=segment.target_text,
            )
        )
    return clips
