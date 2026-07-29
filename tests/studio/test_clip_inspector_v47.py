from __future__ import annotations

from pathlib import Path

from conftest import make_valid_project

from automatedub.config import ToolConfig
from automatedub.vertical_slice.tts import GeneratedSpeech
from automatedub_studio.backend.regeneration_service import (
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


def test_main_window_clip_regen_result_replaces_only_selected_clip_source(qapp, tmp_path):
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

    assert khmer.source_path == new_path
    assert original.source_path == old_original_path
    assert window.playback_controller._timeline.clip_by_id("khmer:0").source_path == new_path


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
