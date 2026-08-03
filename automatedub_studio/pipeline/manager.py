"""Pipeline Manager observed by the Processing window."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig, load_tool_config
from automatedub_studio.pipeline.jobs import (
    STAGE_TTS_GENERATION,
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
    skipped_tts: bool = False


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
        self._context: PipelineContext | None = None
        self._failed_job_index: int | None = None
        self._stage_trace: list[dict[str, object]] = []

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
        self._context = None
        self._failed_job_index = None
        self._stage_trace = []
        self._start_worker()

    def retry(self) -> None:
        if not self.is_running:
            if self._context is not None and self._failed_job_index is not None:
                self._cancelled = False
                self.failure = None
                self._start_worker(
                    context=self._context,
                    start_index=self._failed_job_index,
                )
            else:
                self.start()

    def skip_tts_and_open_editor(self) -> None:
        if (
            self.is_running
            or self.failure is None
            or self.failure.stage_id != STAGE_TTS_GENERATION
            or self._context is None
            or self._failed_job_index is None
        ):
            return
        self._context.skip_tts = True
        self._cancelled = False
        self.failure = None
        self._start_worker(
            context=self._context,
            start_index=self._failed_job_index + 1,
        )

    def cancel(self) -> None:
        self._cancelled = True
        self.pipelineCancelled.emit()

    def run_sync(
        self,
        *,
        context: PipelineContext | None = None,
        start_index: int = 0,
    ) -> PipelineResult:
        if context is None:
            context = PipelineContext(
                request=self.request,
                project_manager=self.project_manager,
                tool_config=self.tool_config,
                provider_manager=self.provider_manager,
                scheduled_stages=[job.stage.id for job in self.jobs],
                scheduled_stage_details=_pipeline_description(self.jobs),
            )
            self._stage_trace = []
        self._context = context
        stage_trace = self._stage_trace
        for job_index, job in enumerate(self.jobs[start_index:], start=start_index):
            if self._cancelled:
                raise PipelineCancelledError("Pipeline cancelled")
            stage = job.stage
            self._emit_event(stage, "started", 0, "Started")
            started_at = datetime.now(UTC)
            started_clock = time.perf_counter()

            def progress(
                value: int,
                message: str = "",
                current_stage: PipelineStage = stage,
            ) -> None:
                self._emit_event(current_stage, "progress", value, message)

            try:
                job.run(context, progress)
            except Exception as exc:
                self._failed_job_index = job_index
                self._context = context
                _record_stage_trace(
                    context,
                    stage_trace,
                    job,
                    stage,
                    started_at,
                    started_clock,
                    status="failure",
                    error=str(exc),
                )
                event = self._emit_event(stage, "failed", 0, str(exc), error=str(exc))
                self.failure = event
                self.pipelineFailed.emit(event)
                raise PipelineFailedError(str(exc)) from exc
            stage_status = (
                "warning"
                if stage.id == STAGE_TTS_GENERATION
                and context.tts_generation_summary.get("failed")
                else "success"
            )
            _record_stage_trace(
                context,
                stage_trace,
                job,
                stage,
                started_at,
                started_clock,
                status=stage_status,
            )
            if stage.id == STAGE_TTS_GENERATION and context.tts_generation_summary.get("failed"):
                self._emit_event(
                    stage,
                    "warning",
                    100,
                    _tts_summary_message(context.tts_generation_summary),
                )
            else:
                self._emit_event(stage, "completed", 100, "Completed")

        if context.created_project is None:
            raise PipelineFailedError("Pipeline finished without creating a project")
        result = PipelineResult(
            project=context.created_project,
            artifacts=dict(context.artifacts),
            skipped_tts=context.skip_tts,
        )
        self.result = result
        self.failure = None
        self._failed_job_index = None
        self.pipelineCompleted.emit(result)
        return result

    def _start_worker(
        self,
        *,
        context: PipelineContext | None = None,
        start_index: int = 0,
    ) -> None:
        worker = _PipelineWorker(self, context=context, start_index=start_index)
        self._active_worker = worker
        self._pool.start(worker)

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
    def __init__(
        self,
        manager: PipelineManager,
        *,
        context: PipelineContext | None = None,
        start_index: int = 0,
    ):
        super().__init__()
        self._manager = manager
        self._context = context
        self._start_index = start_index

    def run(self) -> None:
        try:
            self._manager.run_sync(
                context=self._context,
                start_index=self._start_index,
            )
        except (PipelineFailedError, PipelineCancelledError):
            pass
        finally:
            self._manager._on_worker_finished()


def _record_stage_trace(
    context: PipelineContext,
    stage_trace: list[dict[str, object]],
    job: PipelineJob,
    stage: PipelineStage,
    started_at: datetime,
    started_clock: float,
    *,
    status: str,
    error: str | None = None,
) -> None:
    """Persist an inspectable trace after every stage boundary."""
    finished_at = datetime.now(UTC)
    event: dict[str, object] = {
        "stage_id": stage.id,
        "stage_name": stage.label,
        "job_class": type(job).__name__,
        "job_module": type(job).__module__,
        "start_time": started_at.isoformat(),
        "finish_time": finished_at.isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started_clock, 3),
        "status": status,
    }
    if error:
        event["error"] = error
    stage_trace.append(event)
    if context.created_project is None:
        return
    debug_dir = context.project_path / "pipeline" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "resolved_pipeline": context.scheduled_stages,
        "resolved_pipeline_jobs": context.scheduled_stage_details,
        "events": stage_trace,
    }
    (debug_dir / "pipeline_stage_trace.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

def _pipeline_description(jobs: list[PipelineJob]) -> list[dict[str, str]]:
    return [
        {
            "stage_id": job.stage.id,
            "stage_name": job.stage.label,
            "job_class": type(job).__name__,
            "job_module": type(job).__module__,
        }
        for job in jobs
    ]


def _tts_summary_message(summary: dict[str, object]) -> str:
    return (
        f"Generated: {summary.get('succeeded', 0)} · "
        f"Failed: {summary.get('failed', 0)} · "
        f"Skipped: {summary.get('skipped', 0)}"
    )
