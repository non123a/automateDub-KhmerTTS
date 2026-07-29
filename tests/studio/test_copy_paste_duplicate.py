from __future__ import annotations

from conftest import make_valid_project
from PySide6.QtCore import QSettings
from PySide6.QtGui import QUndoStack

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.edit.commands import ClipClipboard, PasteSegmentsCommand
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment
from automatedub_studio.ui.main_window import MainWindow


def _memory_settings() -> QSettings:
    return QSettings("automatedub-test", "CopyPasteDuplicateTest")


def _segment(
    segment_id: int,
    start: float,
    end: float,
    offset_ms: int = 0,
) -> Segment:
    return Segment(
        id=segment_id,
        start=start,
        end=end,
        source_text=f"source {segment_id}",
        target_text=f"target {segment_id}",
        offset_ms=offset_ms,
    )


def test_duplicate_selected_clip_preserves_properties_and_audio(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    window = MainWindow(settings=_memory_settings())
    window.open_project_path(project_dir)
    window._editables[0] = EditableSegment(
        id=0,
        speed=1.25,
        volume=0.7,
        fade_in_ms=120,
        fade_out_ms=240,
        locked=True,
        edited_text="edited",
        generated_duration=0.9,
    )
    source_audio = tts_segment_output_path(window.project.tts_directory, 0)
    source_audio.write_bytes(b"duplicated audio")
    window.timeline.select_segment_ids([0])

    window._duplicate_selected_clips()

    assert len(window.project.segments) == 3
    duplicate = window.project.segments[-1]
    assert duplicate.start == 1.0
    assert duplicate.end == 2.0
    assert duplicate.offset_ms == 0
    copied_editable = window._editables[duplicate.id]
    assert copied_editable.speed == 1.25
    assert copied_editable.volume == 0.7
    assert copied_editable.fade_in_ms == 120
    assert copied_editable.fade_out_ms == 240
    assert copied_editable.locked is True
    assert copied_editable.edited_text == "edited"
    assert tts_segment_output_path(window.project.tts_directory, duplicate.id).read_bytes() == (
        b"duplicated audio"
    )


def test_copy_and_paste_at_playhead_selects_new_clip(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    window = MainWindow(settings=_memory_settings())
    window.open_project_path(project_dir)
    window.timeline.select_segment_ids([0])
    window.timeline.set_playhead_position(5000)

    window._copy_selected_clips()
    window._paste_clipboard()

    pasted = window.project.segments[-1]
    assert pasted.start == 5.0
    assert pasted.end == 6.0
    assert [segment.id for segment in window.timeline.selected_segments] == [pasted.id]


def test_multi_clip_paste_preserves_relative_spacing(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=4)
    window = MainWindow(settings=_memory_settings())
    window.open_project_path(project_dir)
    window.timeline.select_segment_ids([0, 2])
    window._copy_selected_clips()
    window.timeline.set_playhead_position(10_000)

    window._paste_clipboard()

    pasted = window.project.segments[-2:]
    assert [(segment.start, segment.end) for segment in pasted] == [(10.0, 11.0), (12.0, 13.0)]
    assert [segment.id for segment in window.timeline.selected_segments] == [
        segment.id for segment in pasted
    ]


def test_paste_command_undo_redo_restores_segments_and_audio(qapp, tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    tts_segment_output_path(tts_dir, 1).write_bytes(b"tts")
    segments = [_segment(1, 0.0, 1.0)]
    editables = {1: EditableSegment(id=1, speed=1.4)}
    applied: list[tuple[list[int], bool]] = []
    stack = QUndoStack()
    command = PasteSegmentsCommand(
        segments,
        [segments[0]],
        paste_start_seconds=2.0,
        new_segment_ids=[2],
        editables=editables,
        source_editables={1: editables[1]},
        tts_directory=tts_dir,
        apply_cb=lambda ids, flash: applied.append((ids, flash)),
    )

    stack.push(command)
    assert [(segment.id, segment.start, segment.end) for segment in segments] == [
        (1, 0.0, 1.0),
        (2, 2.0, 3.0),
    ]
    assert editables[2].speed == 1.4
    assert tts_segment_output_path(tts_dir, 2).read_bytes() == b"tts"

    stack.undo()
    assert [(segment.id, segment.start, segment.end) for segment in segments] == [(1, 0.0, 1.0)]
    assert 2 not in editables
    assert not tts_segment_output_path(tts_dir, 2).exists()

    stack.redo()
    assert segments[-1].id == 2
    assert applied[-1] == ([2], True)


def test_clipboard_replacement_uses_latest_copy(qapp):
    clipboard = ClipClipboard()
    first = _segment(1, 0.0, 1.0)
    second = _segment(2, 4.0, 5.0)

    clipboard.replace([first], {})
    clipboard.replace([second], {})

    assert [segment.id for segment in clipboard.segments] == [2]
    assert clipboard.segments[0].source_text == "source 2"
