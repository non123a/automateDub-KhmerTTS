"""Pipeline Manager observed by the Processing window."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig, load_tool_config
from automatedub_studio.pipeline.jobs import (
    PipelineContext,
    PipelineJob,
    PipelineStage,
    default_pipeline_jobs,
)
from automatedub_studio.project.manager import CreatedProject, NewProjectRequest, ProjectManager
from automatedub_studio.providers.manager import ProviderManager


@dataclass(frozen=True)
class PipelineEvent:
    stage_id: str
    label: str
    status: str
    progress: int = 0
    message: str = ""
    error: str = ""


@dataclass(frozen=True)
class PipelineResult:
    project: CreatedProject
    artifacts: dict[str, object]


class PipelineManager(QObject):
    """Coordinates project processing jobs and emits observable state changes."""

    eventEmitted = Signal(object)
    pipelineCompleted = Signal(object)
    pipelineFailed = Signal(object)
    pipelineCancelled = Signal()

    def __init__(
        self,
        request: NewProjectRequest,
        *,
        project_manager: ProjectManager | None = None,
        provider_manager: ProviderManager | None = None,
        tool_config: ToolConfig | None = None,
        jobs: list[PipelineJob] | None = None,
        thread_pool: QThreadPool | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.request = request
        self.project_manager = project_manager if project_manager is not None else ProjectManager()
        self.tool_config = tool_config if tool_config is not None else load_tool_config()
        self.provider_manager = (
            provider_manager
            if provider_manager is not None
            else ProviderManager(self.tool_config)
        )
        self.jobs = jobs if jobs is not None else default_pipeline_jobs()
        self._pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
        self._active_worker: _PipelineWorker | None = None
        self._cancelled = False
        self.result: PipelineResult | None = None
        self.failure: PipelineEvent | None = None

    @property
    def stages(self) -> list[PipelineStage]:
        return [job.stage for job in self.jobs]

    @property
    def is_running(self) -> bool:
        return self._active_worker is not None

    def start(self) -> None:
        if self.is_running:
            return
        self._cancelled = False
        self.result = None
        self.failure = None
        worker = _PipelineWorker(self)
        self._active_worker = worker
        self._pool.start(worker)

    def retry(self) -> None:
        if not self.is_running:
            self.start()

    def cancel(self) -> None:
        self._cancelled = True
        self.pipelineCancelled.emit()

    def run_sync(self) -> PipelineResult:
        context = PipelineContext(
            request=self.request,
            project_manager=self.project_manager,
            tool_config=self.tool_config,
            provider_manager=self.provider_manager,
        )
        for job in self.jobs:
            if self._cancelled:
                raise PipelineCancelledError("Pipeline cancelled")
            stage = job.stage
            self._emit_event(stage, "started", 0, "Started")

            def progress(
                value: int,
                message: str = "",
                current_stage: PipelineStage = stage,
            ) -> None:
                self._emit_event(current_stage, "progress", value, message)

            try:
                job.run(context, progress)
            except Exception as exc:
                event = self._emit_event(stage, "failed", 0, str(exc), error=str(exc))
                self.failure = event
                self.pipelineFailed.emit(event)
                raise PipelineFailedError(str(exc)) from exc
            self._emit_event(stage, "completed", 100, "Completed")

        if context.created_project is None:
            raise PipelineFailedError("Pipeline finished without creating a project")
        result = PipelineResult(
            project=context.created_project,
            artifacts=dict(context.artifacts),
        )
        self.result = result
        self.pipelineCompleted.emit(result)
        return result

    def _on_worker_finished(self) -> None:
        self._active_worker = None

    def _emit_event(
        self,
        stage: PipelineStage,
        status: str,
        progress: int = 0,
        message: str = "",
        *,
        error: str = "",
    ) -> PipelineEvent:
        event = PipelineEvent(
            stage_id=stage.id,
            label=stage.label,
            status=status,
            progress=progress,
            message=message,
            error=error,
        )
        self.eventEmitted.emit(event)
        return event


class PipelineFailedError(RuntimeError):
    """Raised when a pipeline stage fails."""


class PipelineCancelledError(RuntimeError):
    """Raised when the pipeline is cancelled."""


class _PipelineWorker(QRunnable):
    def __init__(self, manager: PipelineManager):
        super().__init__()
        self._manager = manager

    def run(self) -> None:
        try:
            self._manager.run_sync()
        except (PipelineFailedError, PipelineCancelledError):
            pass
        finally:
            self._manager._on_worker_finished()
