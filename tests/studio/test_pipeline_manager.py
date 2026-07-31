from __future__ import annotations

from dataclasses import dataclass

import pytest

from automatedub.config import ToolConfig
from automatedub_studio.pipeline.jobs import PipelineContext, PipelineStage
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
    assert window.cancel_button.isEnabled()
    assert not window.open_editor_button.isEnabled()
