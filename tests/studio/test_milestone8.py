"""Tests for Milestone 8 — selective TTS regeneration."""

from __future__ import annotations

import io
import json
import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from automatedub.config import ToolConfig
from automatedub_studio.backend.jobs import JobRunner, RegenerationJob
from automatedub_studio.backend.regeneration_service import (
    RegenerationOutcome,
    regenerate_segment,
    regenerate_segments,
    resolve_text,
    resolve_tool_config,
    select_all_ids,
    select_changed_ids,
    select_failed_ids,
    select_selected_ids,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.edits import apply_edits, save_edits
from automatedub_studio.project.models import Segment


def make_valid_wav_bytes(seconds: float = 0.5, frame_rate: int = 16000) -> bytes:
    frame_count = int(round(seconds * frame_rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


class GeneratedSpeechStub:
    def __init__(self, audio: bytes):
        self.audio = audio
        self.metadata = None


class FakeProvider:
    """Records every call so tests can assert exactly which segments were hit."""

    def __init__(self, tool_config: ToolConfig, audio: bytes | None = None, fail_ids=None):
        self.tool_config = tool_config
        self._audio = audio if audio is not None else make_valid_wav_bytes()
        self._fail_ids = fail_ids or set()
        self.calls: list[str] = []

    def describe(self):
        return None

    def generate(self, text: str):
        self.calls.append(text)
        return GeneratedSpeechStub(self._audio)


def make_provider_factory(fail_texts: set[str] | None = None, audio: bytes | None = None):
    calls: list[tuple[str, ToolConfig]] = []
    fail_texts = fail_texts or set()

    def factory(tool_config: ToolConfig):
        provider = FailingProvider(tool_config, audio, fail_texts, calls)
        return provider

    return factory, calls


class FailingProvider:
    def __init__(self, tool_config, audio, fail_texts, calls):
        self.tool_config = tool_config
        self._audio = audio if audio is not None else make_valid_wav_bytes()
        self._fail_texts = fail_texts
        self._calls = calls

    def describe(self):
        return None

    def generate(self, text: str):
        self._calls.append((text, self.tool_config))
        if text in self._fail_texts:
            raise RuntimeError(f"provider error for {text!r}")
        return GeneratedSpeechStub(self._audio)


def make_segment(seg_id: int, text: str = "target text") -> Segment:
    return Segment(id=seg_id, start=0.0, end=1.0, source_text="src", target_text=text)


def make_tool_config() -> ToolConfig:
    return ToolConfig(camb_api_key="key", camb_voice_id="100")


# ===========================================================================
# resolve_text / resolve_tool_config
# ===========================================================================


def test_resolve_text_uses_target_text_by_default():
    seg = make_segment(1, text="original target")
    assert resolve_text(seg, None) == "original target"


def test_resolve_text_prefers_edited_text():
    seg = make_segment(1, text="original target")
    es = EditableSegment(id=1, edited_text="edited version")
    assert resolve_text(seg, es) == "edited version"


def test_resolve_text_falls_back_when_edited_text_empty():
    seg = make_segment(1, text="original target")
    es = EditableSegment(id=1, edited_text=None)
    assert resolve_text(seg, es) == "original target"


def test_resolve_tool_config_uses_project_default_voice():
    config = make_tool_config()
    result = resolve_tool_config(config, None)
    assert result.camb_voice_id == "100"


def test_resolve_tool_config_uses_segment_voice_override():
    config = make_tool_config()
    es = EditableSegment(id=1, voice_id="999")
    result = resolve_tool_config(config, es)
    assert result.camb_voice_id == "999"


# ===========================================================================
# regenerate_segment — single regeneration
# ===========================================================================


def test_regenerate_segment_writes_wav(tmp_path):
    seg = make_segment(5)
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    provider_factory, calls = make_provider_factory()

    outcome = regenerate_segment(seg, None, tts_dir, make_tool_config(), provider_factory)

    assert outcome.success is True
    assert outcome.segment_id == 5
    assert (tts_dir / "0005.wav").exists()
    assert outcome.duration_seconds is not None
    assert calls == [("target text", make_tool_config())]


def test_regenerate_segment_overwrites_previous_wav(tmp_path):
    seg = make_segment(5)
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    wav_path = tts_dir / "0005.wav"
    wav_path.write_bytes(b"old content")
    provider_factory, _ = make_provider_factory()

    regenerate_segment(seg, None, tts_dir, make_tool_config(), provider_factory)

    assert wav_path.read_bytes() != b"old content"


def test_regenerate_segment_uses_edited_text():
    seg = make_segment(5, text="original")
    es = EditableSegment(id=5, edited_text="new text")
    provider_factory, calls = make_provider_factory()

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tts_dir = Path(tmp)
        regenerate_segment(seg, es, tts_dir, make_tool_config(), provider_factory)

    assert calls[0][0] == "new text"


def test_regenerate_segment_uses_voice_override(tmp_path):
    seg = make_segment(5)
    es = EditableSegment(id=5, voice_id="777")
    provider_factory, calls = make_provider_factory()

    regenerate_segment(seg, es, tmp_path, make_tool_config(), provider_factory)

    assert calls[0][1].camb_voice_id == "777"


def test_regenerate_segment_uses_default_voice_without_override(tmp_path):
    seg = make_segment(5)
    provider_factory, calls = make_provider_factory()

    regenerate_segment(seg, None, tmp_path, make_tool_config(), provider_factory)

    assert calls[0][1].camb_voice_id == "100"


# ===========================================================================
# Failed regeneration — leaves previous WAV untouched, stores error
# ===========================================================================


def test_regenerate_segment_failure_leaves_previous_wav_untouched(tmp_path):
    seg = make_segment(5)
    wav_path = tmp_path / "0005.wav"
    wav_path.write_bytes(b"previous audio")
    provider_factory, _ = make_provider_factory(fail_texts={"target text"})

    outcome = regenerate_segment(seg, None, tmp_path, make_tool_config(), provider_factory)

    assert outcome.success is False
    assert outcome.error is not None
    assert wav_path.read_bytes() == b"previous audio"


def test_regenerate_segment_failure_on_invalid_wav_bytes(tmp_path):
    seg = make_segment(5)
    provider_factory, _ = make_provider_factory(audio=b"not a wav file")

    outcome = regenerate_segment(seg, None, tmp_path, make_tool_config(), provider_factory)

    assert outcome.success is False
    assert not (tmp_path / "0005.wav").exists()


# ===========================================================================
# Multi regeneration — only requested ids are ever generated
# ===========================================================================


def test_regenerate_segments_only_calls_provider_for_requested_ids(tmp_path):
    segments = [make_segment(1, "one"), make_segment(2, "two"), make_segment(3, "three")]
    provider_factory, calls = make_provider_factory()

    outcomes = regenerate_segments(
        segments, {}, tmp_path, make_tool_config(), [1, 3], provider_factory=provider_factory
    )

    assert {o.segment_id for o in outcomes} == {1, 3}
    assert sorted(text for text, _ in calls) == ["one", "three"]
    assert not (tmp_path / "0002.wav").exists()


def test_regenerate_segments_continues_after_failure(tmp_path):
    segments = [make_segment(1, "one"), make_segment(2, "two"), make_segment(3, "three")]
    provider_factory, calls = make_provider_factory(fail_texts={"two"})

    outcomes = regenerate_segments(
        segments, {}, tmp_path, make_tool_config(), [1, 2, 3], provider_factory=provider_factory
    )

    assert [o.success for o in outcomes] == [True, False, True]
    assert len(calls) == 3


def test_regenerate_segments_calls_on_result_per_segment(tmp_path):
    segments = [make_segment(1), make_segment(2)]
    provider_factory, _ = make_provider_factory()
    results: list[RegenerationOutcome] = []

    regenerate_segments(
        segments,
        {},
        tmp_path,
        make_tool_config(),
        [1, 2],
        on_result=results.append,
        provider_factory=provider_factory,
    )

    assert len(results) == 2


def test_regenerate_segments_calls_on_start_before_generating(tmp_path):
    segments = [make_segment(1)]
    provider_factory, _ = make_provider_factory()
    started: list[int] = []

    regenerate_segments(
        segments,
        {},
        tmp_path,
        make_tool_config(),
        [1],
        on_start=started.append,
        provider_factory=provider_factory,
    )

    assert started == [1]


# ===========================================================================
# Cancel
# ===========================================================================


def test_regenerate_segments_stops_when_cancelled(tmp_path):
    segments = [make_segment(1), make_segment(2), make_segment(3)]
    provider_factory, calls = make_provider_factory()

    outcomes = regenerate_segments(
        segments,
        {},
        tmp_path,
        make_tool_config(),
        [1, 2, 3],
        is_cancelled=lambda: len(calls) >= 1,
        provider_factory=provider_factory,
    )

    assert len(outcomes) == 1
    assert len(calls) == 1


def test_job_runner_cancel_stops_remaining_segments(qapp, tmp_path):
    segments = [make_segment(i) for i in range(1, 6)]
    provider_factory, calls = make_provider_factory()

    job = RegenerationJob(segments, {}, tmp_path, make_tool_config(), [1, 2, 3, 4, 5])

    def cancel_after_first(segment_id):
        job.cancel()

    job.signals.started.connect(cancel_after_first)

    finished_outcomes = []
    job.signals.finished.connect(finished_outcomes.append)

    # Patch the module-level factory the job actually uses via monkeypatched service call.
    import automatedub_studio.backend.jobs as jobs_module

    original = jobs_module.regenerate_segments

    def patched(*args, **kwargs):
        kwargs["provider_factory"] = provider_factory
        return original(*args, **kwargs)

    jobs_module.regenerate_segments = patched
    try:
        job.run()
    finally:
        jobs_module.regenerate_segments = original

    assert len(finished_outcomes[0]) == 1


# ===========================================================================
# Selection helpers — the four regenerate actions
# ===========================================================================


def test_select_selected_ids_excludes_locked():
    editables = {1: EditableSegment(id=1, locked=True)}
    assert select_selected_ids([1, 2], editables) == [2]


def test_select_changed_ids_returns_needs_regeneration_only():
    editables = {
        1: EditableSegment(id=1, needs_regeneration=True),
        2: EditableSegment(id=2, needs_regeneration=False),
    }
    segments = [make_segment(1), make_segment(2)]
    assert select_changed_ids(segments, editables) == [1]


def test_select_changed_ids_excludes_locked():
    editables = {1: EditableSegment(id=1, needs_regeneration=True, locked=True)}
    segments = [make_segment(1)]
    assert select_changed_ids(segments, editables) == []


def test_select_failed_ids_returns_last_error_only():
    editables = {
        1: EditableSegment(id=1, last_error="boom"),
        2: EditableSegment(id=2, last_error=None),
    }
    segments = [make_segment(1), make_segment(2)]
    assert select_failed_ids(segments, editables) == [1]


def test_select_all_ids_excludes_locked():
    editables = {2: EditableSegment(id=2, locked=True)}
    segments = [make_segment(1), make_segment(2), make_segment(3)]
    assert select_all_ids(segments, editables) == [1, 3]


def test_select_all_ids_includes_unedited_segments():
    segments = [make_segment(1), make_segment(2)]
    assert select_all_ids(segments, {}) == [1, 2]


# ===========================================================================
# Status transitions
# ===========================================================================


def test_editable_segment_defaults_have_no_error_or_regen_flag():
    es = EditableSegment(id=1)
    assert es.last_error is None
    assert es.needs_regeneration is False


def test_is_modified_true_when_needs_regeneration():
    assert EditableSegment(id=1, needs_regeneration=True).is_modified is True


def test_is_modified_true_when_voice_id_set():
    assert EditableSegment(id=1, voice_id="42").is_modified is True


def test_is_modified_true_when_edited_text_set():
    assert EditableSegment(id=1, edited_text="hello").is_modified is True


def test_successful_outcome_clears_error_and_sets_duration(tmp_path):
    seg = make_segment(1)
    provider_factory, _ = make_provider_factory()
    es = EditableSegment(id=1, last_error="old failure", needs_regeneration=True)

    outcome = regenerate_segment(seg, es, tmp_path, make_tool_config(), provider_factory)

    assert outcome.success is True
    assert outcome.duration_seconds is not None
    # The service returns an outcome; applying it onto EditableSegment is the
    # caller's job (main_window._on_regen_result) — verify the outcome itself
    # carries what the caller needs to clear last_error/needs_regeneration.
    assert outcome.error is None


def test_failed_outcome_carries_error_message(tmp_path):
    seg = make_segment(1)
    provider_factory, _ = make_provider_factory(fail_texts={"target text"})

    outcome = regenerate_segment(seg, None, tmp_path, make_tool_config(), provider_factory)

    assert outcome.success is False
    assert "provider error" in outcome.error


# ===========================================================================
# Persistence — edited_text / voice_id / needs_regeneration roundtrip
# ===========================================================================


def test_save_edits_includes_edited_text():
    seg = make_segment(1)
    es = EditableSegment(id=1, edited_text="new khmer text")
    with _tmp_project_dir() as path:
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    assert data["segments"][0]["edited_text"] == "new khmer text"


def test_save_edits_includes_voice_id():
    seg = make_segment(1)
    es = EditableSegment(id=1, voice_id="42")
    with _tmp_project_dir() as path:
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    assert data["segments"][0]["voice_id"] == "42"


def test_save_edits_includes_needs_regeneration():
    seg = make_segment(1)
    es = EditableSegment(id=1, needs_regeneration=True)
    with _tmp_project_dir() as path:
        save_edits([seg], path, {1: es})
        data = json.loads((path / "translation.edited.json").read_text())
    assert data["segments"][0]["needs_regeneration"] is True


def test_apply_edits_restores_edited_text_and_voice():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {
        "version": 1,
        "segments": [{"id": 1, "edited_text": "restored text", "voice_id": "55"}],
    }
    with _tmp_project_dir() as path:
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert editables[1].edited_text == "restored text"
    assert editables[1].voice_id == "55"


def test_apply_edits_restores_needs_regeneration():
    seg = make_segment(1)
    editables: dict[int, EditableSegment] = {}
    payload = {"version": 1, "segments": [{"id": 1, "needs_regeneration": True}]}
    with _tmp_project_dir() as path:
        (path / "translation.edited.json").write_text(json.dumps(payload))
        apply_edits([seg], path, editables)
    assert editables[1].needs_regeneration is True


def _tmp_project_dir():
    import tempfile

    class _Ctx:
        def __enter__(self):
            self._tmpdir = tempfile.TemporaryDirectory()
            return Path(self._tmpdir.name)

        def __exit__(self, *exc):
            self._tmpdir.cleanup()

    return _Ctx()


# ===========================================================================
# Background worker — JobRunner / RegenerationJob run via QThreadPool
# ===========================================================================


def test_job_runner_submits_to_thread_pool_and_emits_finished(qapp, tmp_path):
    from PySide6.QtCore import QEventLoop

    segments = [make_segment(1), make_segment(2)]
    provider_factory, calls = make_provider_factory()

    job = RegenerationJob(segments, {}, tmp_path, make_tool_config(), [1, 2])

    import automatedub_studio.backend.jobs as jobs_module

    original = jobs_module.regenerate_segments

    def patched(*args, **kwargs):
        kwargs["provider_factory"] = provider_factory
        return original(*args, **kwargs)

    jobs_module.regenerate_segments = patched

    runner = JobRunner()
    loop = QEventLoop()
    results: list[list[RegenerationOutcome]] = []

    def on_finished(outcomes):
        results.append(outcomes)
        loop.quit()

    job.signals.finished.connect(on_finished)
    try:
        runner.submit(job)
        loop.exec()
    finally:
        jobs_module.regenerate_segments = original

    assert len(results) == 1
    assert len(results[0]) == 2
    assert runner.is_running is False


def test_job_runner_is_running_true_while_active(qapp, tmp_path):
    from PySide6.QtCore import QEventLoop, QThreadPool

    provider_factory, _ = make_provider_factory()
    segments = [make_segment(1)]
    job = RegenerationJob(segments, {}, tmp_path, make_tool_config(), [1])

    import automatedub_studio.backend.jobs as jobs_module

    original = jobs_module.regenerate_segments

    def patched(*args, **kwargs):
        kwargs["provider_factory"] = provider_factory
        return original(*args, **kwargs)

    jobs_module.regenerate_segments = patched

    runner = JobRunner()
    loop = QEventLoop()
    job.signals.finished.connect(lambda _: loop.quit())

    try:
        runner.submit(job)
        assert runner.is_running is True
        loop.exec()
    finally:
        QThreadPool.globalInstance().waitForDone()
        jobs_module.regenerate_segments = original

    assert runner.is_running is False
