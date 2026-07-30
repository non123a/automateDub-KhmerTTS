from __future__ import annotations

import json
from pathlib import Path

from conftest import make_valid_project
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from automatedub.config import ToolConfig
from automatedub.vertical_slice.tts import GeneratedSpeech
from automatedub_studio.backend.regeneration_service import (
    ClipRegenerationOutcome,
    clip_tts_output_path,
    regenerate_timeline_clip,
)
from automatedub_studio.inspector.segment_inspector import (
    _STATUS_GENERATING,
    _STATUS_MODIFIED,
    SegmentInspectorWidget,
)
from automatedub_studio.project.timeline_edits import (
    load_timeline_edits,
    save_timeline_edits,
)
from automatedub_studio.timeline.timeline_clip import (
    DRAFT_REGENERATION_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    Timeline,
    TimelineClip,
)
from automatedub_studio.ui.main_window import MainWindow


def _wav_bytes(seconds: float = 0.1, frame_rate: int = 16000) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * int(frame_rate * seconds))
    return buffer.getvalue()


def _clip(tmp_path: Path) -> TimelineClip:
    return TimelineClip(
        id="khmer:1",
        track_id=KHMER_TTS_TRACK_ID,
        start_time=1.0,
        end_time=2.0,
        source_path=tmp_path / "0001.wav",
        source_offset=0.0,
        segment_id=1,
        chinese_text="source text",
        khmer_text="old khmer",
        voice_model="voice-a",
        speaking_rate=1.1,
    )


def test_timeline_clip_metadata_serializes_roundtrip(tmp_path):
    clip = _clip(tmp_path)
    restored = TimelineClip.from_dict(clip.to_dict())

    assert restored.chinese_text == "source text"
    assert restored.khmer_text == "old khmer"
    assert restored.voice_model == "voice-a"
    assert restored.speaking_rate == 1.1


def test_inspector_original_text_is_reference_only(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    inspector.set_timeline_clip(_clip(tmp_path))
    original = inspector._original_text_label

    assert original.toPlainText() == "source text"
    assert original.isReadOnly() is True
    assert (
        original.textInteractionFlags()
        & Qt.TextInteractionFlag.TextSelectableByMouse
    )
    original.setFocus()
    original.moveCursor(original.textCursor().MoveOperation.End)
    QTest.keyClicks(original, " changed")
    assert original.toPlainText() == "source text"

    original.selectAll()
    original.copy()
    assert qapp.clipboard().text() == "source text"
    assert "reference_text_label" == original.objectName()


def test_inspector_khmer_translation_is_editable_with_generation_helper(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    inspector.set_timeline_clip(_clip(tmp_path))

    assert inspector._khmer_text_edit.isReadOnly() is False
    assert (
        inspector._translation_helper_label.text()
        == "Only the Khmer Translation is used when generating speech."
    )


def test_timeline_edits_persist_clip_translation(tmp_path):
    timeline = Timeline.from_clips([_clip(tmp_path)])
    timeline.clip_by_id("khmer:1").khmer_text = "saved khmer"

    save_timeline_edits(timeline, tmp_path)
    restored = load_timeline_edits(tmp_path)

    assert restored is not None
    assert restored.clip_by_id("khmer:1").khmer_text == "saved khmer"


def test_inspector_loads_timeline_clip_and_saves_translation(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    clip = _clip(tmp_path)
    saved: list[tuple[str, str]] = []
    inspector.clipTranslationSaveRequested.connect(
        lambda clip_id, text: saved.append((clip_id, text))
    )

    inspector.set_timeline_clip(clip)
    inspector._khmer_text_edit.setPlainText("new khmer")

    assert inspector.has_unsaved_changes is True
    assert inspector._status_label.text() == _STATUS_MODIFIED

    inspector.save_translation()

    assert clip.khmer_text == "new khmer"
    assert saved == [("khmer:1", "new khmer")]
    assert inspector.has_unsaved_changes is False


def test_editing_speaking_rate_enables_save_and_disables_regenerate(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    inspector.set_timeline_clip(_clip(tmp_path))

    inspector._speaking_rate_spin.setValue(1.25)

    assert inspector.has_unsaved_changes is True
    assert inspector._save_translation_button.isEnabled() is True
    assert inspector._regenerate_button.isEnabled() is False


def test_inspector_disables_regenerate_until_translation_is_saved(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    clip = _clip(tmp_path)

    inspector.set_timeline_clip(clip)
    assert inspector._regenerate_button.isEnabled() is True

    inspector._khmer_text_edit.setPlainText("draft khmer")

    assert inspector._status_label.text() == _STATUS_MODIFIED
    assert inspector._save_translation_button.isEnabled() is True
    assert inspector._regenerate_button.isEnabled() is False

    inspector.save_translation()

    assert inspector._save_translation_button.isEnabled() is False
    assert inspector._regenerate_button.isEnabled() is True


def test_inspector_save_emits_translation_and_speaking_rate(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    clip = _clip(tmp_path)
    saved: list[tuple[str, str, float]] = []
    inspector.clipSaveRequested.connect(
        lambda clip_id, text, rate: saved.append((clip_id, text, rate))
    )

    inspector.set_timeline_clip(clip)
    inspector._khmer_text_edit.setPlainText("new khmer")
    inspector._speaking_rate_spin.setValue(1.35)
    inspector.save_translation()

    assert clip.khmer_text == "new khmer"
    assert clip.speaking_rate == 1.35
    assert saved == [("khmer:1", "new khmer", 1.35)]


def test_inspector_reverts_unsaved_translation(qapp, tmp_path):
    inspector = SegmentInspectorWidget()
    clip = _clip(tmp_path)

    inspector.set_timeline_clip(clip)
    inspector._khmer_text_edit.setPlainText("draft")
    inspector.revert_translation()

    assert inspector._khmer_text_edit.toPlainText() == "old khmer"
    assert clip.khmer_text == "old khmer"
    assert inspector.has_unsaved_changes is False


def test_main_window_save_and_reload_persists_clip_translation(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    clip = window.timeline._clips_by_clip_id["khmer:0"].timeline_clip
    window.inspector.set_timeline_clip(clip)
    window.inspector._khmer_text_edit.setPlainText("persisted khmer")
    window.inspector.save_translation()

    window._save_project()

    reloaded = MainWindow()
    reloaded.open_project_path(project_dir)

    assert reloaded.timeline.timeline.clip_by_id("khmer:0").khmer_text == "persisted khmer"


def test_clip_save_immediately_persists_text_and_speaking_rate_without_changing_translation_json(
    qapp, tmp_path
):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    translation_path = project_dir / "translation.json"
    original_translation = json.loads(translation_path.read_text(encoding="utf-8"))
    window = MainWindow()
    window.open_project_path(project_dir)
    clip = window.timeline.timeline.clip_by_id("khmer:0")
    window.inspector.set_timeline_clip(clip)

    window.inspector._khmer_text_edit.setPlainText("edited khmer")
    window.inspector._speaking_rate_spin.setValue(1.45)
    window.inspector.save_translation()

    edited = load_timeline_edits(project_dir)
    unchanged_translation = json.loads(translation_path.read_text(encoding="utf-8"))

    assert edited is not None
    edited_clip = edited.clip_by_id("khmer:0")
    assert edited_clip.khmer_text == "edited khmer"
    assert edited_clip.speaking_rate == 1.45
    assert unchanged_translation == original_translation


def test_regenerate_timeline_clip_writes_clip_specific_audio(tmp_path):
    clip = _clip(tmp_path)
    calls: list[str] = []

    class Provider:
        def describe(self):
            raise AssertionError("unused")

        def generate(self, text: str) -> GeneratedSpeech:
            calls.append(text)
            return GeneratedSpeech(audio=_wav_bytes())

    outcome = regenerate_timeline_clip(
        clip,
        tmp_path,
        ToolConfig(),
        provider_factory=lambda _config: Provider(),
    )

    expected = clip_tts_output_path(tmp_path, clip.id)
    assert outcome.success is True
    assert outcome.wav_path == expected
    assert expected.exists()
    assert calls == ["old khmer"]


def test_regenerate_timeline_clip_uses_only_timeline_clip_khmer_text(tmp_path):
    clip = _clip(tmp_path)
    clip.khmer_text = "edited khmer"
    clip.target_text = "old target"
    clip.source_text = "original chinese"
    calls: list[str] = []

    class Provider:
        def describe(self):
            raise AssertionError("unused")

        def generate(self, text: str) -> GeneratedSpeech:
            calls.append(text)
            return GeneratedSpeech(audio=_wav_bytes())

    outcome = regenerate_timeline_clip(
        clip,
        tmp_path,
        ToolConfig(),
        provider_factory=lambda _config: Provider(),
    )

    assert outcome.success is True
    assert calls == ["edited khmer"]


def test_regenerate_timeline_clip_uses_clip_speaking_rate(tmp_path):
    clip = _clip(tmp_path)
    clip.speaking_rate = 1.55
    speeds: list[float] = []

    class Provider:
        def describe(self):
            raise AssertionError("unused")

        def generate(self, text: str) -> GeneratedSpeech:
            return GeneratedSpeech(audio=_wav_bytes())

    def provider_factory(config: ToolConfig) -> Provider:
        speeds.append(config.tts_speed)
        return Provider()

    outcome = regenerate_timeline_clip(
        clip,
        tmp_path,
        ToolConfig(tts_speed=1.0),
        provider_factory=provider_factory,
    )

    assert outcome.success is True
    assert speeds == [1.55]


def test_main_window_clip_regen_result_creates_draft_clip_without_touching_original(
    qapp, tmp_path
):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    original = window.timeline.timeline.clip_by_id("original:0")
    khmer = window.timeline.timeline.clip_by_id("khmer:0")
    old_original_path = original.source_path
    new_path = project_dir / "tts" / "clips" / "khmer_0.wav"
    new_path.parent.mkdir()
    new_path.write_bytes(_wav_bytes())

    from automatedub_studio.backend.regeneration_service import ClipRegenerationOutcome

    window._on_clip_regen_result(
        ClipRegenerationOutcome(clip_id="khmer:0", success=True, wav_path=new_path)
    )

    draft = next(
        clip
        for clip in window.timeline.timeline_clips
        if clip.track_id == DRAFT_REGENERATION_TRACK_ID and clip.source_path == new_path
    )

    assert khmer.source_path != new_path
    assert original.source_path == old_original_path
    assert draft.khmer_text == khmer.khmer_text
    assert draft.voice_model == khmer.voice_model
    assert draft.speaking_rate == khmer.speaking_rate
    assert draft.source_offset == khmer.source_offset
    assert draft.segment_id == khmer.segment_id
    assert window.playback_controller._timeline.clip_by_id(draft.id).source_path == new_path


def test_multiple_regenerations_create_multiple_draft_clips(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    new_path_1 = project_dir / "tts" / "clips" / "khmer_0_v1.wav"
    new_path_1.parent.mkdir()
    new_path_1.write_bytes(_wav_bytes())
    new_path_2 = project_dir / "tts" / "clips" / "khmer_0_v2.wav"
    new_path_2.write_bytes(_wav_bytes())

    window._on_clip_regen_result(
        ClipRegenerationOutcome(clip_id="khmer:0", success=True, wav_path=new_path_1)
    )
    window._on_clip_regen_result(
        ClipRegenerationOutcome(clip_id="khmer:0", success=True, wav_path=new_path_2)
    )

    drafts = [
        clip
        for clip in window.timeline.timeline_clips
        if clip.track_id == DRAFT_REGENERATION_TRACK_ID
    ]

    assert [clip.source_path for clip in drafts] == [new_path_1, new_path_2]


def test_reopen_restores_edited_text_rate_regenerated_source_and_playback(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    clip = window.timeline.timeline.clip_by_id("khmer:0")
    window.inspector.set_timeline_clip(clip)
    window.inspector._khmer_text_edit.setPlainText("reopened khmer")
    window.inspector._speaking_rate_spin.setValue(1.65)
    window.inspector.save_translation()
    new_path = project_dir / "tts" / "clips" / "khmer_0.wav"
    new_path.parent.mkdir()
    new_path.write_bytes(_wav_bytes())

    window._on_clip_regen_result(
        ClipRegenerationOutcome(clip_id="khmer:0", success=True, wav_path=new_path)
    )

    reloaded = MainWindow()
    reloaded.open_project_path(project_dir)
    reloaded_clip = reloaded.timeline.timeline.clip_by_id("khmer:0")
    reloaded_draft = next(
        clip
        for clip in reloaded.timeline.timeline_clips
        if clip.track_id == DRAFT_REGENERATION_TRACK_ID and clip.source_path == new_path
    )

    assert reloaded_clip.khmer_text == "reopened khmer"
    assert reloaded_clip.speaking_rate == 1.65
    assert reloaded_clip.source_path != new_path
    assert reloaded_draft.khmer_text == "reopened khmer"
    assert reloaded_draft.speaking_rate == 1.65
    assert reloaded_draft.source_path == new_path
    assert (
        reloaded.playback_controller._timeline.clip_by_id(reloaded_draft.id).source_path
        == new_path
    )


def test_main_window_clip_regen_completion_updates_inspector_status(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    khmer = window.timeline.timeline.clip_by_id("khmer:0")
    window.inspector.set_timeline_clip(khmer)
    window.inspector.set_generating(True)
    assert window.inspector._status_label.text() == _STATUS_GENERATING
    new_path = project_dir / "tts" / "clips" / "khmer_0.wav"
    new_path.parent.mkdir()
    new_path.write_bytes(_wav_bytes())

    from automatedub_studio.backend.regeneration_service import ClipRegenerationOutcome

    window._on_clip_regen_result(
        ClipRegenerationOutcome(clip_id="khmer:0", success=True, wav_path=new_path)
    )

    assert window.inspector._status_label.text() == "Regeneration completed"


def test_regenerate_selected_single_khmer_clip_uses_clip_regeneration_path(
    qapp, tmp_path, monkeypatch
):
    project_dir = make_valid_project(tmp_path, segment_count=1)
    window = MainWindow()
    window.open_project_path(project_dir)
    window.timeline.select_timeline_clip_ids(["khmer:0"])
    clip_calls: list[str] = []
    legacy_calls: list[list[int]] = []
    monkeypatch.setattr(window, "_regenerate_timeline_clip", clip_calls.append)
    monkeypatch.setattr(window, "_start_regeneration", legacy_calls.append)

    window.regenerate_selected_action.trigger()

    assert clip_calls == ["khmer:0"]
    assert legacy_calls == []
