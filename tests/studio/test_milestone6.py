"""Tests for Milestone 6: editable clip timing (offset_ms)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from automatedub_studio.edit.commands import OffsetChangeCommand
from automatedub_studio.inspector.segment_inspector import SegmentInspectorWidget
from automatedub_studio.project.edits import apply_edits, load_edits, save_edits
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_widget import (
    KHMER_TTS_LANE,
    ORIGINAL_AUDIO_LANE,
    VIDEO_LANE,
    TimelineWidget,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_segment(seg_id: int = 1, start: float = 1.0, end: float = 2.0) -> Segment:
    return Segment(id=seg_id, start=start, end=end, source_text="src", target_text="tgt")


# ===========================================================================
# Segment model — offset_ms
# ===========================================================================


def test_segment_default_offset_ms():
    seg = make_segment()
    assert seg.offset_ms == 0


def test_segment_offset_ms_is_mutable():
    seg = make_segment()
    seg.offset_ms = 250
    assert seg.offset_ms == 250


# ===========================================================================
# edits.py — save / load / apply
# ===========================================================================


def test_save_edits_writes_only_modified_segments():
    segs = [
        Segment(id=1, start=0.0, end=1.0, source_text="", target_text="a"),
        Segment(id=2, start=1.0, end=2.0, source_text="", target_text="b", offset_ms=300),
        Segment(id=3, start=2.0, end=3.0, source_text="", target_text="c"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits(segs, path)
        data = json.loads((path / "translation.edited.json").read_text())

    assert data["version"] == 1
    assert len(data["segments"]) == 1
    assert data["segments"][0] == {"id": 2, "offset_ms": 300}


def test_save_edits_writes_empty_segments_when_nothing_modified():
    segs = [make_segment(1), make_segment(2)]
    with tempfile.TemporaryDirectory() as tmp:
        save_edits(segs, Path(tmp))
        data = json.loads((Path(tmp) / "translation.edited.json").read_text())
    assert data["segments"] == []


def test_load_edits_returns_empty_dict_when_file_missing():
    with tempfile.TemporaryDirectory() as tmp:
        result = load_edits(Path(tmp))
    assert result == {}


def test_load_edits_returns_offset_map():
    payload = {"version": 1, "segments": [{"id": 5, "offset_ms": -100}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        result = load_edits(path)
    assert result == {5: {"offset_ms": -100}}


def test_load_edits_ignores_malformed_entries():
    payload = {
        "version": 1,
        "segments": [{"id": "bad", "offset_ms": 10}, {"id": 1, "offset_ms": 50}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        result = load_edits(path)
    assert result == {1: {"offset_ms": 50}}


def test_apply_edits_updates_segment_offset_ms():
    segs = [make_segment(3)]
    segs[0].offset_ms = 0
    payload = {"version": 1, "segments": [{"id": 3, "offset_ms": 750}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits(segs, path)
    assert segs[0].offset_ms == 750


def test_apply_edits_no_op_when_file_absent():
    segs = [make_segment(1)]
    with tempfile.TemporaryDirectory() as tmp:
        apply_edits(segs, Path(tmp))
    assert segs[0].offset_ms == 0


def test_save_then_load_roundtrip():
    segs = [
        Segment(id=10, start=0.0, end=1.0, source_text="", target_text="a", offset_ms=200),
        Segment(id=11, start=1.0, end=2.0, source_text="", target_text="b", offset_ms=-50),
        Segment(id=12, start=2.0, end=3.0, source_text="", target_text="c"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        save_edits(segs, path)
        result = load_edits(path)
    assert result == {10: {"offset_ms": 200}, 11: {"offset_ms": -50}}


# ===========================================================================
# OffsetChangeCommand — undo / redo
# ===========================================================================


def test_offset_command_redo_applies_new_offset():
    seg = make_segment()
    calls = []
    cmd = OffsetChangeCommand(
        seg, old_offset_ms=0, new_offset_ms=300, apply_cb=lambda i, o: calls.append((i, o))
    )
    cmd.redo()
    assert seg.offset_ms == 300
    assert calls == [(seg.id, 300)]


def test_offset_command_undo_restores_old_offset():
    seg = make_segment()
    seg.offset_ms = 300
    calls = []
    cmd = OffsetChangeCommand(
        seg, old_offset_ms=0, new_offset_ms=300, apply_cb=lambda i, o: calls.append((i, o))
    )
    cmd.undo()
    assert seg.offset_ms == 0
    assert calls == [(seg.id, 0)]


def test_offset_command_text():
    seg = make_segment(42)
    cmd = OffsetChangeCommand(seg, 0, 100, apply_cb=lambda i, o: None)
    assert "42" in cmd.text()


# ===========================================================================
# SegmentInspectorWidget — offset formatting
# ===========================================================================


def test_inspector_set_segment_shows_zero_offset(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    inspector.set_segment(seg)
    assert inspector._offset_label.text() == "0 ms"


def test_inspector_set_segment_shows_positive_offset(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    seg.offset_ms = 250
    inspector.set_segment(seg)
    assert inspector._offset_label.text() == "+250 ms"


def test_inspector_set_segment_shows_negative_offset(qapp):
    inspector = SegmentInspectorWidget()
    seg = make_segment()
    seg.offset_ms = -120
    inspector.set_segment(seg)
    assert inspector._offset_label.text() == "-120 ms"


def test_inspector_refresh_offset_updates_label(qapp):
    inspector = SegmentInspectorWidget()
    inspector.set_segment(make_segment())
    inspector.refresh_offset(500)
    assert inspector._offset_label.text() == "+500 ms"


def test_inspector_refresh_offset_no_op_when_empty(qapp):
    inspector = SegmentInspectorWidget()
    inspector.refresh_offset(999)
    assert inspector._stack.currentWidget() is inspector._empty_label


# ===========================================================================
# TimelineWidget — apply_offset repositions clips
# ===========================================================================


def test_timeline_apply_offset_updates_segment(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=1.0, end=2.0)
    tl.load_segments([seg])

    tl.apply_offset(seg.id, 500)

    assert seg.offset_ms == 500


def test_timeline_apply_offset_unknown_segment_is_safe(qapp):
    tl = TimelineWidget()
    tl.load_segments([make_segment(1)])
    tl.apply_offset(999, 100)  # should not raise


def test_timeline_load_segments_positions_clips_with_existing_offset(qapp):
    from automatedub_studio.timeline.timeline_widget import (
        BASE_PIXELS_PER_SECOND,
        LANE_LABEL_WIDTH,
        SCENE_MARGIN_H,
    )

    tl = TimelineWidget()
    seg = Segment(id=1, start=2.0, end=3.0, source_text="", target_text="t", offset_ms=1000)
    tl.load_segments([seg])

    clips = tl._clips_by_segment.get(1, [])
    assert len(clips) > 0
    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + 3.0 * BASE_PIXELS_PER_SECOND
    actual_x = clips[0].x() + clips[0].rect().x()
    assert abs(actual_x - expected_x) < 0.5


# ===========================================================================
# TimelineWidget — segmentOffsetCommitted signal on drag end
# ===========================================================================


def test_timeline_segment_offset_committed_signal_fires(qapp):
    tl = TimelineWidget()
    seg = make_segment(7, start=0.0, end=1.0)
    tl.load_segments([seg])

    received = []
    tl.segmentOffsetCommitted.connect(lambda sid, old, new: received.append((sid, old, new)))
    tl._view.clipDragEnded.emit("khmer:7", 0, 400)

    assert received == [("khmer:7", 0, 400)]


# ===========================================================================
# EditableSegment model
# ===========================================================================


def test_editable_segment_defaults():
    from automatedub_studio.project.editable_project import EditableSegment

    es = EditableSegment(id=1)
    assert es.offset_ms == 0
    assert es.speed == 1.0
    assert es.volume == 1.0
    assert es.fade_in_ms == 0
    assert es.fade_out_ms == 0
    assert es.voice_id is None
    assert es.edited_text is None
    assert es.locked is False
    assert es.needs_regeneration is False


def test_editable_segment_is_modified_false_by_default():
    from automatedub_studio.project.editable_project import EditableSegment

    assert EditableSegment(id=1).is_modified is False


def test_editable_segment_is_modified_true_when_offset_nonzero():
    from automatedub_studio.project.editable_project import EditableSegment

    es = EditableSegment(id=1, offset_ms=50)
    assert es.is_modified is True


def test_editable_segment_fields_mutable():
    from automatedub_studio.project.editable_project import EditableSegment

    es = EditableSegment(id=5)
    es.offset_ms = 200
    es.locked = True
    assert es.offset_ms == 200
    assert es.locked is True


# ===========================================================================
# ClipItem — lane selection
# ===========================================================================


def test_lane0_clip_is_selectable(qapp):
    from automatedub_studio.timeline.clip_item import ClipItem

    seg = make_segment()
    clip = ClipItem(seg, 0, 0, 100, 40, lane=0)
    flag = ClipItem.GraphicsItemFlag.ItemIsSelectable
    assert clip.flags() & flag


def test_lane1_clip_is_selectable(qapp):
    from automatedub_studio.timeline.clip_item import ClipItem

    seg = make_segment()
    clip = ClipItem(seg, 0, 0, 100, 40, lane=1)
    flag = ClipItem.GraphicsItemFlag.ItemIsSelectable
    assert clip.flags() & flag


def test_timeline_video_lane_has_no_segment_clips(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=0.0, end=1.0)
    tl.load_segments([seg])
    clips = tl._clips_by_segment[seg.id]
    assert all(c.lane != VIDEO_LANE for c in clips)


def test_timeline_audio_track_clips_selectable(qapp):
    tl = TimelineWidget()
    seg = make_segment(1, start=0.0, end=1.0)
    tl.load_segments([seg])
    clips = tl._clips_by_segment[seg.id]
    for lane in (ORIGINAL_AUDIO_LANE, KHMER_TTS_LANE):
        clip = next(c for c in clips if c.lane == lane)
        flag = clip.GraphicsItemFlag.ItemIsSelectable
        assert clip.flags() & flag


# ===========================================================================
# Snap behavior
# ===========================================================================


def test_snap_rounds_to_10ms():
    from automatedub_studio.timeline.timeline_widget import _snap

    assert _snap(0) == 0
    assert _snap(5) == 10
    assert _snap(4) == 0
    assert _snap(14) == 10
    assert _snap(15) == 20
    assert _snap(-5) == 0
    assert _snap(-6) == -10
    assert _snap(250) == 250
    assert _snap(253) == 250
    assert _snap(256) == 260


# ===========================================================================
# Inspector status "Edited"
# ===========================================================================


def test_inspector_status_generated_when_offset_zero(qapp):
    from automatedub_studio.inspector.segment_inspector import _STATUS_GENERATED

    inspector = SegmentInspectorWidget()
    seg = make_segment()
    inspector.set_segment(seg)
    assert inspector._status_label.text() == _STATUS_GENERATED


def test_inspector_status_edited_when_offset_nonzero(qapp):
    from automatedub_studio.inspector.segment_inspector import _STATUS_EDITED

    inspector = SegmentInspectorWidget()
    seg = make_segment()
    seg.offset_ms = 100
    inspector.set_segment(seg)
    assert inspector._status_label.text() == _STATUS_EDITED


def test_inspector_refresh_offset_updates_status_to_edited(qapp):
    from automatedub_studio.inspector.segment_inspector import _STATUS_EDITED

    inspector = SegmentInspectorWidget()
    inspector.set_segment(make_segment())
    inspector.refresh_offset(300)
    assert inspector._status_label.text() == _STATUS_EDITED


def test_inspector_refresh_offset_resets_status_to_generated(qapp):
    from automatedub_studio.inspector.segment_inspector import _STATUS_GENERATED

    inspector = SegmentInspectorWidget()
    seg = make_segment()
    seg.offset_ms = 100
    inspector.set_segment(seg)
    inspector.refresh_offset(0)
    assert inspector._status_label.text() == _STATUS_GENERATED


# ===========================================================================
# apply_offset — correct scene position after move
# ===========================================================================


def test_apply_offset_positions_clip_correctly(qapp):
    """After apply_offset the clip's scene-x must equal _time_to_x(start + offset/1000)."""
    from automatedub_studio.timeline.timeline_widget import (
        BASE_PIXELS_PER_SECOND,
        LANE_LABEL_WIDTH,
        SCENE_MARGIN_H,
    )

    tl = TimelineWidget()
    seg = make_segment(1, start=2.0, end=3.0)
    tl.load_segments([seg])
    tl.apply_offset(seg.id, 500)  # +500 ms → effective start 2.5 s

    clips = tl._clips_by_segment[seg.id]
    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + 2.5 * BASE_PIXELS_PER_SECOND
    for clip in clips:
        actual_x = clip.pos().x() + clip.rect().x()
        assert abs(actual_x - expected_x) < 0.5


def test_apply_offset_then_reset_positions_clip_at_origin(qapp):
    from automatedub_studio.timeline.timeline_widget import (
        BASE_PIXELS_PER_SECOND,
        LANE_LABEL_WIDTH,
        SCENE_MARGIN_H,
    )

    tl = TimelineWidget()
    seg = make_segment(1, start=1.0, end=2.0)
    tl.load_segments([seg])
    tl.apply_offset(seg.id, 1000)
    tl.apply_offset(seg.id, 0)

    clips = tl._clips_by_segment[seg.id]
    expected_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + 1.0 * BASE_PIXELS_PER_SECOND
    for clip in clips:
        actual_x = clip.pos().x() + clip.rect().x()
        assert abs(actual_x - expected_x) < 0.5
