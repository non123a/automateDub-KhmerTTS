"""Tests for SegmentInspectorWidget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from automatedub_studio.inspector.segment_inspector import (
    _NO_SELECTION_TEXT,
    _PLACEHOLDER,
    _STATUS_DEFAULT,
    SegmentInspectorWidget,
)
from automatedub_studio.project.models import Segment


# ---------------------------------------------------------------------------
# Construction / empty state
# ---------------------------------------------------------------------------


def test_inspector_creates(qapp):
    inspector = SegmentInspectorWidget()
    assert inspector is not None


def test_inspector_shows_no_selection_initially(qapp):
    inspector = SegmentInspectorWidget()
    assert inspector._stack.currentWidget() is inspector._empty_label


def test_inspector_empty_label_text(qapp):
    inspector = SegmentInspectorWidget()
    assert inspector._empty_label.text() == _NO_SELECTION_TEXT


# ---------------------------------------------------------------------------
# set_segment(None) - clearing
# ---------------------------------------------------------------------------


def test_set_segment_none_shows_empty_state(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="src", target_text="tgt")

    inspector.set_segment(seg)
    inspector.set_segment(None)

    assert inspector._stack.currentWidget() is inspector._empty_label


# ---------------------------------------------------------------------------
# set_segment(segment) - showing details
# ---------------------------------------------------------------------------


def test_set_segment_shows_detail_widget(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=42, start=1.0, end=2.0, source_text="hello", target_text="world")

    inspector.set_segment(seg)

    assert inspector._stack.currentWidget() is inspector._detail_widget


def test_set_segment_displays_id(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=99, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._id_label.text() == "99"


def test_set_segment_displays_status(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._status_label.text() == _STATUS_DEFAULT


def test_set_segment_displays_original_text(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="Original", target_text="Khmer")

    inspector.set_segment(seg)

    assert inspector._original_text_label.text() == "Original"


def test_set_segment_displays_khmer_text(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="src", target_text="Khmer Text")

    inspector.set_segment(seg)

    assert inspector._khmer_text_label.text() == "Khmer Text"


def test_set_segment_displays_timing(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=1.5, end=3.2, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert "1.500" in inspector._start_label.text()
    assert "3.200" in inspector._end_label.text()
    assert "1.700" in inspector._duration_label.text()


def test_set_segment_empty_source_text_shows_placeholder(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="", target_text="tgt")

    inspector.set_segment(seg)

    assert inspector._original_text_label.text() == _PLACEHOLDER


def test_set_segment_displays_default_offset(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._offset_label.text() == "0 ms"


def test_set_segment_displays_default_speed(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._speed_label.text() == "1.00"


def test_set_segment_displays_default_volume(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._volume_label.text() == "100%"


def test_set_segment_displays_default_voice(qapp):
    inspector = SegmentInspectorWidget()
    seg = Segment(id=1, start=0.0, end=1.0, source_text="s", target_text="t")

    inspector.set_segment(seg)

    assert inspector._voice_label.text() == "Default Voice"


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def test_play_original_button_is_disabled(qapp):
    inspector = SegmentInspectorWidget()
    assert not inspector._play_original_button.isEnabled()


def test_play_khmer_button_is_disabled(qapp):
    inspector = SegmentInspectorWidget()
    assert not inspector._play_khmer_button.isEnabled()


def test_compare_button_is_disabled(qapp):
    inspector = SegmentInspectorWidget()
    assert not inspector._compare_button.isEnabled()
