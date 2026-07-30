"""Tests for Milestone 7 — Inspector property editor, persistence, undo/redo, locked drag."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from automatedub_studio.edit.commands import PropertyChangeCommand
from automatedub_studio.inspector.segment_inspector import (
    _STATUS_EDITED,
    _STATUS_GENERATED,
    SegmentInspectorWidget,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.edits import apply_edits, load_edits, save_edits
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem
from automatedub_studio.timeline.timeline_widget import TimelineWidget


def make_segment(seg_id: int = 1, start: float = 0.0, end: float = 1.0) -> Segment:
    return Segment(id=seg_id, start=start, end=end, source_text="src", target_text="tgt")


def make_editable(**kwargs) -> EditableSegment:
    return EditableSegment(id=kwargs.pop("id", 1), **kwargs)


# ===========================================================================
# EditableSegment.is_modified — extended for M7 fields
# ===========================================================================


def test_is_modified_false_by_default():
    assert EditableSegment(id=1).is_modified is False


def test_is_modified_true_when_speed_changed():
    assert EditableSegment(id=1, speed=1.5).is_modified is True


def test_is_modified_true_when_volume_changed():
    assert EditableSegment(id=1, volume=0.8).is_modified is True


def test_is_modified_true_when_fade_in_set():
    assert EditableSegment(id=1, fade_in_ms=100).is_modified is True


def test_is_modified_true_when_fade_out_set():
    assert EditableSegment(id=1, fade_out_ms=200).is_modified is True


def test_is_modified_true_when_locked():
    assert EditableSegment(id=1, locked=True).is_modified is True


# ===========================================================================
# edits.py — save / load / apply with M7 fields
# ===========================================================================


def test_save_edits_includes_speed():
    seg = make_segment(1)
    es = EditableSegment(id=1, speed=1.5)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    record = data["segments"][0]
    assert record["speed"] == 1.5


def test_save_edits_includes_volume():
    seg = make_segment(1)
    es = EditableSegment(id=1, volume=0.5)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    record = data["segments"][0]
    assert record["volume"] == 0.5


def test_save_edits_includes_fades():
    seg = make_segment(1)
    es = EditableSegment(id=1, fade_in_ms=100, fade_out_ms=200)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    record = data["segments"][0]
    assert record["fade_in_ms"] == 100
    assert record["fade_out_ms"] == 200


def test_save_edits_includes_locked():
    seg = make_segment(1)
    es = EditableSegment(id=1, locked=True)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    record = data["segments"][0]
    assert record["locked"] is True


def test_save_edits_omits_default_fields():
    seg = make_segment(1)
    seg.offset_ms = 100  # only offset is non-default
    es = EditableSegment(id=1)  # all defaults
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    record = data["segments"][0]
    assert "speed" not in record
    assert "volume" not in record
    assert "locked" not in record


def test_load_edits_returns_speed():
    payload = {"version": 1, "segments": [{"id": 3, "speed": 1.25}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        result = load_edits(path)
    assert result == {3: {"speed": 1.25}}


def test_load_edits_returns_locked():
    payload = {"version": 1, "segments": [{"id": 7, "locked": True}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        result = load_edits(path)
    assert result == {7: {"locked": True}}


def test_apply_edits_restores_speed():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {"version": 1, "segments": [{"id": 1, "speed": 1.75}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert editables[1].speed == 1.75


def test_apply_edits_restores_volume():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {"version": 1, "segments": [{"id": 1, "volume": 0.6}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert abs(editables[1].volume - 0.6) < 1e-6


def test_apply_edits_restores_fades():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {"version": 1, "segments": [{"id": 1, "fade_in_ms": 50, "fade_out_ms": 80}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert editables[1].fade_in_ms == 50
    assert editables[1].fade_out_ms == 80


def test_apply_edits_restores_locked():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {"version": 1, "segments": [{"id": 1, "locked": True}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert editables[1].locked is True


def test_speed_save_load_roundtrip():
    seg = make_segment(1)
    es = EditableSegment(id=1, speed=0.75)
    editables_out = {1: es}
    editables_in: dict[int, EditableSegment] = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, editables_out)
        apply_edits([seg], path, editables_in)
    assert abs(editables_in[1].speed - 0.75) < 1e-6


def test_locked_save_load_roundtrip():
    seg = make_segment(1)
    es = EditableSegment(id=1, locked=True)
    editables_in: dict[int, EditableSegment] = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits([seg], path, {1: es})
        apply_edits([seg], path, editables_in)
    assert editables_in[1].locked is True


# ===========================================================================
# PropertyChangeCommand — undo / redo
# ===========================================================================


def test_property_command_redo_applies_new_value():
    calls = []
    cmd = PropertyChangeCommand(
        5, "speed", 1.0, 1.5, apply_cb=lambda sid, f, v: calls.append((sid, f, v))
    )
    cmd.redo()
    assert calls == [(5, "speed", 1.5)]


def test_property_command_undo_restores_old_value():
    calls = []
    cmd = PropertyChangeCommand(
        5, "speed", 1.0, 1.5, apply_cb=lambda sid, f, v: calls.append((sid, f, v))
    )
    cmd.undo()
    assert calls == [(5, "speed", 1.0)]


def test_property_command_text():
    cmd = PropertyChangeCommand(3, "volume", 1.0, 0.5, apply_cb=lambda *a: None)
    assert "volume" in cmd.text()
    assert "3" in cmd.text()


def test_property_command_undo_locked():
    calls = []
    cmd = PropertyChangeCommand(
        2, "locked", False, True, apply_cb=lambda sid, f, v: calls.append((sid, f, v))
    )
    cmd.redo()
    cmd.undo()
    assert calls[-1] == (2, "locked", False)


# ===========================================================================
# ClipItem — locked visuals
# ===========================================================================


def test_clip_set_locked_shows_lock_label(qapp):
    seg = make_segment()
    clip = ClipItem(seg, 0, 0, 100, 40, lane=1)
    assert clip._lock_label is None
    clip.set_locked(True)
    assert clip._lock_label is not None


def test_clip_set_locked_removes_lock_label_on_unlock(qapp):
    seg = make_segment()
    clip = ClipItem(seg, 0, 0, 100, 40, lane=1)
    clip.set_locked(True)
    clip.set_locked(False)
    assert clip._lock_label is None


def test_clip_locked_flag_set(qapp):
    seg = make_segment()
    clip = ClipItem(seg, 0, 0, 100, 40, lane=1)
    clip.set_locked(True)
    assert clip.locked is True


# ===========================================================================
# Timeline — locked drag prevention
# ===========================================================================


def test_locked_clip_does_not_start_drag(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=0.0, end=2.0)
    tl.load_segments([seg])
    tl.apply_locked(seg.id, True)

    clips = tl._clips_by_segment[seg.id]
    lane1_clip = next(c for c in clips if c.lane == 2)
    assert lane1_clip.locked is True


def test_apply_locked_sets_clip_locked(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=0.0, end=2.0)
    tl.load_segments([seg])
    tl.apply_locked(seg.id, True)

    clips = tl._clips_by_segment[seg.id]
    for clip in clips:
        assert clip.locked is True


def test_apply_locked_false_clears_lock(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=0.0, end=2.0)
    tl.load_segments([seg])
    tl.apply_locked(seg.id, True)
    tl.apply_locked(seg.id, False)

    clips = tl._clips_by_segment[seg.id]
    original_clip = next(clip for clip in clips if clip.lane == 2)
    khmer_clip = next(clip for clip in clips if clip.lane == 3)
    assert original_clip.locked is True
    assert khmer_clip.locked is False


# ===========================================================================
# Inspector — property controls + status
# ===========================================================================


def test_inspector_set_segment_shows_editable_speed(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, speed=1.5)
    inspector.set_segment(seg, es)
    assert abs(inspector._speed_spin.value() - 1.5) < 1e-6


def test_inspector_set_segment_shows_editable_volume(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, volume=0.5)
    inspector.set_segment(seg, es)
    assert inspector._volume_slider.value() == 50
    assert inspector._volume_display.text() == "50%"


def test_inspector_set_segment_shows_fades(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, fade_in_ms=300, fade_out_ms=400)
    inspector.set_segment(seg, es)
    assert inspector._fade_in_spin.value() == 300
    assert inspector._fade_out_spin.value() == 400


def test_inspector_set_segment_shows_locked(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, locked=True)
    inspector.set_segment(seg, es)
    assert inspector._locked_check.isChecked() is True


def test_inspector_status_edited_when_speed_changed(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, speed=1.5)
    inspector.set_segment(seg, es)
    assert inspector._status_label.text() == _STATUS_EDITED


def test_inspector_status_edited_when_locked(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1, locked=True)
    inspector.set_segment(seg, es)
    assert inspector._status_label.text() == _STATUS_EDITED


def test_inspector_status_generated_when_all_defaults(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    inspector.set_segment(seg)
    assert inspector._status_label.text() == _STATUS_GENERATED


def test_inspector_refresh_property_speed(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1)
    inspector.set_segment(seg, es)
    inspector.refresh_property("speed", 1.75)
    assert abs(inspector._speed_spin.value() - 1.75) < 1e-6


def test_inspector_refresh_property_locked(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1)
    inspector.set_segment(seg, es)
    inspector.refresh_property("locked", True)
    assert inspector._locked_check.isChecked() is True


def test_inspector_speed_signal_emitted_on_change(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1)
    inspector.set_segment(seg, es)

    received = []
    inspector.speedChanged.connect(lambda old, new: received.append((old, new)))
    inspector._speed_spin.setValue(1.5)
    assert len(received) == 1
    assert abs(received[0][1] - 1.5) < 1e-6


def test_inspector_locked_signal_emitted_on_check(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    es = EditableSegment(id=1)
    inspector.set_segment(seg, es)

    received = []
    inspector.lockedChanged.connect(lambda old, new: received.append((old, new)))
    inspector._locked_check.setChecked(True)
    assert received == [(False, True)]
