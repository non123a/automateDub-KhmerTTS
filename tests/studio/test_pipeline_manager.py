from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from automatedub.config import ToolConfig
from automatedub_studio.pipeline.jobs import (
    EXPECTED_PIPELINE_FLOW,
    STAGE_TIMELINE_GENERATION,
    STAGE_TTS_GENERATION,
    PipelineContext,
    PipelineStage,
    TTSGenerationFailedError,
)
from automatedub_studio.pipeline.manager import (
    PipelineFailedError,
    PipelineManager,
)
from automatedub_studio.project.manager import NewProjectRequest
from automatedub_studio.ui.processing_window import ProcessingWindow


@dataclass
class FakeJob:
    stage_id: str
    label: str
    fail: bool = False

    @property
    def stage(self) -> PipelineStage:
        return PipelineStage(self.stage_id, self.label)

    def run(self, context: PipelineContext, progress) -> None:
        progress(50, f"{self.label} halfway")
        if self.fail:
            raise RuntimeError(f"{self.label} failed")
        progress(100, f"{self.label} done")


class FakeProjectJob:
    stage = PipelineStage("create_project", "Create Project")

    def run(self, context: PipelineContext, progress) -> None:
        progress(50, "creating")
        context.created_project = context.project_manager.create_project_structure(
            context.request
        )
        progress(100, "created")


class FakeAllTTSFailedJob:
    stage = PipelineStage(STAGE_TTS_GENERATION, "Generating Khmer Speech")

    def run(self, context: PipelineContext, progress) -> None:
        context.tts_generation_completed = 0
        context.tts_generation_total = 2
        context.tts_failed_segment_ids = [0, 1]
        context.tts_generation_summary = {
            "translation_segments_loaded": 2,
            "segments_attempted": 2,
            "succeeded": 0,
            "failed": 2,
            "skipped": 0,
            "failed_segment_ids": [0, 1],
            "common_failure_reason": "provider rejected request",
        }
        progress(100, "Generated: 0 · Failed: 2 · Skipped: 0")
        raise TTSGenerationFailedError("All 2 Khmer speech generation requests failed")


class FakePartialTTSJob:
    stage = PipelineStage(STAGE_TTS_GENERATION, "Generating Khmer Speech")

    def run(self, context: PipelineContext, progress) -> None:
        context.tts_generation_completed = 1
        context.tts_generation_total = 2
        context.tts_failed_segment_ids = [1]
        context.tts_generation_summary = {
            "translation_segments_loaded": 2,
            "segments_attempted": 2,
            "succeeded": 1,
            "failed": 1,
            "skipped": 0,
            "failed_segment_ids": [1],
            "common_failure_reason": "segment failed",
        }
        progress(100, "Generated: 1 · Failed: 1 · Skipped: 0")


def _request(tmp_path) -> NewProjectRequest:
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    return NewProjectRequest(
        project_name="Khmer Cut",
        project_location=tmp_path,
        video_file=video_file,
        source_language="Chinese",
        target_language="Khmer",
    )


def test_pipeline_manager_emits_started_progress_completed(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob()],
    )
    events = []
    manager.eventEmitted.connect(events.append)

    result = manager.run_sync()

    assert result.project.project_path == tmp_path / "Khmer Cut.autodub"
    assert [event.status for event in events] == ["started", "progress", "progress", "completed"]
    assert events[0].label == "Create Project"
    assert events[-1].progress == 100
    trace_path = result.project.project_path / "pipeline" / "debug" / "pipeline_stage_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["resolved_pipeline"] == ["create_project"]
    assert trace["resolved_pipeline_jobs"][0]["job_class"] == "FakeProjectJob"
    assert trace["events"][0]["stage_id"] == "create_project"
    assert trace["events"][0]["status"] == "success"
    assert "elapsed_seconds" in trace["events"][0]


def test_pipeline_manager_default_runtime_pipeline_contains_bulk_tts(qapp, tmp_path):
    manager = PipelineManager(_request(tmp_path), tool_config=ToolConfig())
    stages = [stage.id for stage in manager.stages]

    assert stages == EXPECTED_PIPELINE_FLOW
    assert stages.index(STAGE_TTS_GENERATION) < stages.index(STAGE_TIMELINE_GENERATION)


def test_pipeline_manager_stops_remaining_jobs_on_failure(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[
            FakeProjectJob(),
            FakeJob("extract_audio", "Extract Audio", fail=True),
            FakeJob("translation", "Translation"),
        ],
    )
    events = []
    manager.eventEmitted.connect(events.append)

    with pytest.raises(PipelineFailedError):
        manager.run_sync()

    assert manager.failure is not None
    assert manager.failure.stage_id == "extract_audio"
    assert "Extract Audio failed" in manager.failure.error
    assert not any(event.stage_id == "translation" for event in events)
    project_path = tmp_path / "Khmer Cut.autodub"
    trace = json.loads(
        (project_path / "pipeline" / "debug" / "pipeline_stage_trace.json").read_text(
            encoding="utf-8"
        )
    )
    assert [event["stage_id"] for event in trace["events"]] == [
        "create_project",
        "extract_audio",
    ]
    assert trace["events"][-1]["status"] == "failure"
    assert trace["events"][-1]["error"] == "Extract Audio failed"


def test_processing_window_observes_pipeline_events(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob()],
    )
    window = ProcessingWindow(manager)

    manager.run_sync()

    assert window.status_label.text() == "Project Ready"
    assert window.open_editor_button.isEnabled()
    assert window.close_button.isEnabled()
    assert not window.retry_button.isEnabled()


def test_processing_window_shows_failure_actions(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeJob("extract_audio", "Extract Audio", fail=True)],
    )
    window = ProcessingWindow(manager)

    with pytest.raises(PipelineFailedError):
        manager.run_sync()

    assert window.status_label.text() == "Extract Audio failed"
    assert window.error_label.text() == "Extract Audio failed"
    assert window.retry_button.isEnabled()
    assert not window.skip_tts_button.isEnabled()
    assert window.cancel_button.isEnabled()
    assert not window.open_editor_button.isEnabled()


def test_processing_window_enables_skip_tts_only_for_tts_failure(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob(), FakeAllTTSFailedJob(), FakeJob("timeline", "Timeline")],
    )
    window = ProcessingWindow(manager)

    with pytest.raises(PipelineFailedError):
        manager.run_sync()

    assert window.status_label.text() == "Generating Khmer Speech failed"
    assert window.retry_button.isEnabled()
    assert window.skip_tts_button.isEnabled()
    assert not window.open_editor_button.isEnabled()


def test_skip_tts_resumes_after_failed_tts_stage(qapp, tmp_path, monkeypatch):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob(), FakeAllTTSFailedJob(), FakeJob("timeline", "Timeline")],
    )
    with pytest.raises(PipelineFailedError):
        manager.run_sync()

    starts = []

    def capture_start(*, context=None, start_index=0):
        starts.append((context, start_index))

    monkeypatch.setattr(manager, "_start_worker", capture_start)

    manager.skip_tts_and_open_editor()

    assert starts == [(manager._context, 2)]
    assert manager._context is not None
    assert manager._context.skip_tts is True


def test_pipeline_manager_marks_partial_tts_as_warning(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob(), FakePartialTTSJob()],
    )
    events = []
    manager.eventEmitted.connect(events.append)

    manager.run_sync()

    warning = events[-1]
    assert warning.stage_id == STAGE_TTS_GENERATION
    assert warning.status == "warning"
    assert warning.message == "Generated: 1 · Failed: 1 · Skipped: 0"


def test_processing_window_renders_tts_warning_summary(qapp, tmp_path):
    manager = PipelineManager(
        _request(tmp_path),
        tool_config=ToolConfig(),
        jobs=[FakeProjectJob(), FakePartialTTSJob()],
    )
    window = ProcessingWindow(manager)

    manager.run_sync()

    label = window.stage_labels[STAGE_TTS_GENERATION]
    assert label.text() == "⚠ Generating Khmer Speech — Generated: 1 · Failed: 1 · Skipped: 0"
    assert window.status_label.text() == "Project Ready"
