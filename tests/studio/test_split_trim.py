from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QUndoStack

from automatedub_studio.edit.commands import (
    DeleteTimelineClipsCommand,
    InsertTimelineClipCommand,
    SplitTimelineClipCommand,
    TimelineClipMoveCommand,
    TimelineClipTrimCommand,
)
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import (
    DRAFT_REGENERATION_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
    TimelineClip,
)
from automatedub_studio.timeline.timeline_widget import (
    BASE_PIXELS_PER_SECOND,
    MIN_CLIP_DURATION_SECONDS,
    TimelineWidget,
)


def _segment(
    segment_id: int = 1,
    start: float = 1.0,
    end: float = 3.0,
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


def _timeline_clip(
    clip_id: str = "clip:1",
    track_id: str = KHMER_TTS_TRACK_ID,
    start: float = 1.0,
    end: float = 3.0,
    source_offset: float = 0.25,
    source_path: Path | None = None,
    segment_id: int | None = 1,
) -> TimelineClip:
    return TimelineClip(
        id=clip_id,
        track_id=track_id,
        start_time=start,
        end_time=end,
        source_path=source_path if source_path is not None else Path("clip.wav"),
        source_offset=source_offset,
        segment_id=segment_id,
        source_text="source",
        target_text="target",
        khmer_text="target",
    )


def test_insert_original_movie_audio_track(qapp, tmp_path: Path):
    widget = TimelineWidget()
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav")

    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None

    widget.add_timeline_clip(clip)

    movie_clips = [
        timeline_clip
        for timeline_clip in widget.timeline_clips
        if timeline_clip.track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
    ]
    assert len(movie_clips) == 1
    movie = movie_clips[0]
    assert movie.start_time == 0.0
    assert movie.end_time == 3.0
    assert movie.locked is False
    assert movie.source_path == tmp_path / "audio.wav"


def test_prevent_duplicate_movie_audio_track(qapp, tmp_path: Path):
    widget = TimelineWidget()
    widget.load_segments([_segment()], audio_path=tmp_path / "audio.wav")

    clip = widget.insert_original_movie_audio_clip()
    assert clip is not None

    stack = QUndoStack()
    stack.push(
        InsertTimelineClipCommand(
            clip,
            add_cb=widget.add_timeline_clip,
            remove_cb=widget.remove_timeline_clip,
        )
    )

    assert widget.insert_original_movie_audio_clip() is None

    stack.undo()
    assert widget.timeline.clip_by_id(clip.id) is None


def test_split_timeline_clip_command(qapp):
    original = _timeline_clip(
        clip_id="clip:1",
        track_id=KHMER_TTS_TRACK_ID,
        start=1.0,
        end=3.0,
        source_offset=0.5,
    )
    clips = [original]
    calls: list[tuple[list[str], list[TimelineClip]]] = []

    def replace_cb(remove_ids: list[str], add_clips: list[TimelineClip]) -> None:
        calls.append((list(remove_ids), list(add_clips)))
        for clip_id in remove_ids:
            clips[:] = [clip for clip in clips if clip.id != clip_id]
        clips.extend(add_clips)

    command = SplitTimelineClipCommand(
        original,
        split_seconds=2.0,
        replace_cb=replace_cb,
    )

    command.redo()

    left, right = calls[-1][1]
    assert calls[-1][0] == ["clip:1"]
    assert left.id == "clip:1:left"
    assert right.id == "clip:1:right"
    assert left.start_time == 1.0
    assert left.end_time == 2.0
    assert right.start_time == 2.0
    assert right.end_time == 3.0
    assert right.source_offset == 1.5
    assert {clip.id for clip in clips} == {"clip:1:left", "clip:1:right"}


def test_split_timeline_clip_undo_redo(qapp):
    original = _timeline_clip(clip_id="clip:1", start=1.0, end=3.0)
    target = [original]
    history: list[tuple[list[str], list[TimelineClip]]] = []

    def replace_cb(remove_ids: list[str], add_clips: list[TimelineClip]) -> None:
        history.append((list(remove_ids), [clip for clip in add_clips]))
        for clip_id in remove_ids:
            target[:] = [clip for clip in target if clip.id != clip_id]
        target.extend(add_clips)

    stack = QUndoStack()
    stack.push(SplitTimelineClipCommand(original, 2.0, replace_cb=replace_cb))

    assert {clip.id for clip in target} == {"clip:1:left", "clip:1:right"}

    stack.undo()
    assert [clip.id for clip in target] == ["clip:1"]

    stack.redo()
    assert {clip.id for clip in target} == {"clip:1:left", "clip:1:right"}
    assert history[0][0] == ["clip:1"]


def test_left_trim_changes_start_and_source_offset(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(
        clip_id="movie:1",
        track_id=ORIGINAL_MOVIE_AUDIO_TRACK_ID,
        start=1.0,
        end=3.0,
        source_offset=0.25,
        source_path=Path("audio.wav"),
        segment_id=None,
    )
    widget.timeline.add_clip(clip)
    widget.load_timeline(widget.timeline)

    widget.apply_timeline_clip_trim(clip.id, 1.5, 3.0)

    assert clip.start_time == 1.5
    assert clip.end_time == 3.0
    assert clip.source_offset == 0.75
    item = widget._clips_by_clip_id[clip.id]
    assert abs(item.rect().width() - 1.5 * BASE_PIXELS_PER_SECOND) < 0.1


def test_right_trim_changes_end_and_preserves_source_offset(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(
        clip_id="movie:1",
        track_id=ORIGINAL_MOVIE_AUDIO_TRACK_ID,
        start=1.0,
        end=3.0,
        source_offset=0.25,
        source_path=Path("audio.wav"),
        segment_id=None,
    )
    widget.timeline.add_clip(clip)
    widget.load_timeline(widget.timeline)

    widget.apply_timeline_clip_trim(clip.id, 1.0, 2.25)

    assert clip.start_time == 1.0
    assert clip.end_time == 2.25
    assert clip.source_offset == 0.25
    item = widget._clips_by_clip_id[clip.id]
    assert abs(item.rect().width() - 1.25 * BASE_PIXELS_PER_SECOND) < 0.1


def test_trim_command_undo_redo(qapp):
    clip = _timeline_clip(clip_id="clip:1", start=1.0, end=3.0)
    calls: list[tuple[str, float, float]] = []
    stack = QUndoStack()
    command = TimelineClipTrimCommand(
        clip.id,
        old_start=1.0,
        old_end=3.0,
        new_start=1.5,
        new_end=2.5,
        apply_cb=lambda clip_id, start, end: calls.append((clip_id, start, end)),
    )

    stack.push(command)
    assert calls[-1] == ("clip:1", 1.5, 2.5)

    stack.undo()
    assert calls[-1] == ("clip:1", 1.0, 3.0)

    stack.redo()
    assert calls[-1] == ("clip:1", 1.5, 2.5)


def test_move_timeline_clip_command(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(
        clip_id="clip:1",
        track_id=KHMER_TTS_TRACK_ID,
        start=1.0,
        end=3.0,
        segment_id=1,
    )
    widget.timeline.add_clip(clip)
    widget.load_timeline(widget.timeline)

    command = TimelineClipMoveCommand(
        clip.id,
        clip.track_id,
        clip.start_time,
        DRAFT_REGENERATION_TRACK_ID,
        4.0,
        apply_cb=lambda clip_id, track_id, start_time: widget.move_timeline_clip(
            clip_id, track_id, start_time
        ),
    )
    stack = QUndoStack()
    stack.push(command)

    assert clip.track_id == DRAFT_REGENERATION_TRACK_ID
    assert clip.start_time == 4.0

    stack.undo()
    assert clip.track_id == KHMER_TTS_TRACK_ID
    assert clip.start_time == 1.0


def test_insert_timeline_clip_command_undo_redo(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(
        clip_id="movie:1",
        track_id=ORIGINAL_MOVIE_AUDIO_TRACK_ID,
        start=0.0,
        end=3.0,
        source_path=Path("audio.wav"),
        segment_id=None,
    )

    stack = QUndoStack()
    stack.push(
        InsertTimelineClipCommand(
            clip,
            add_cb=widget.add_timeline_clip,
            remove_cb=widget.remove_timeline_clip,
        )
    )
    assert widget.timeline.clip_by_id(clip.id) is not None

    stack.undo()
    assert widget.timeline.clip_by_id(clip.id) is None

    stack.redo()
    assert widget.timeline.clip_by_id(clip.id) is not None


def test_delete_timeline_clip_command_undo_redo(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(
        clip_id="clip:1",
        track_id=KHMER_TTS_TRACK_ID,
        start=1.0,
        end=3.0,
        segment_id=1,
    )
    widget.timeline.add_clip(clip)
    widget.load_timeline(widget.timeline)

    stack = QUndoStack()
    stack.push(
        DeleteTimelineClipsCommand(
            [clip.id],
            remove_cb=widget.remove_timeline_clip,
            restore_cb=widget.add_timeline_clip,
        )
    )
    assert widget.timeline.clip_by_id(clip.id) is None

    stack.undo()
    assert widget.timeline.clip_by_id(clip.id) is clip

    stack.redo()
    assert widget.timeline.clip_by_id(clip.id) is None


def test_invalid_trim_cannot_cross_zero_duration(qapp):
    widget = TimelineWidget()
    clip = _timeline_clip(start=1.0, end=3.0)
    widget.timeline.add_clip(clip)
    widget.load_timeline(widget.timeline)

    start, end = widget.constrain_timeline_clip_trim(clip.id, 3.5, 3.0)

    assert end - start >= MIN_CLIP_DURATION_SECONDS - 1e-9
    assert start < end
