"""QRunnable background job for the export pipeline."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportError,
    ExportOptions,
    ExportResult,
    export_project,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project


class ExportJobSignals(QObject):
    stageChanged = Signal(str)    # ExportStage.value string
    finished = Signal(object)     # ExportResult on success
    errorOccurred = Signal(str)   # error message on failure or cancel


class ExportJob(QRunnable):
    """Runs export_project() on a worker thread from the shared QThreadPool."""

    def __init__(
        self,
        project: Project,
        editables: dict[int, EditableSegment],
        tool_config: ToolConfig,
        options: ExportOptions,
    ):
        super().__init__()
        self.signals = ExportJobSignals()
        self._project = project
        self._editables = editables
        self._tool_config = tool_config
        self._options = options
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            result = export_project(
                project=self._project,
                editables=self._editables,
                tool_config=self._tool_config,
                options=self._options,
                on_stage=lambda s: self.signals.stageChanged.emit(s.value),
                is_cancelled=lambda: self._cancelled,
            )
            self.signals.finished.emit(result)
        except ExportError as exc:
            self.signals.errorOccurred.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.errorOccurred.emit(f"unexpected error: {exc}")


class ExportRunner:
    """Thin facade over QThreadPool for submitting ExportJob instances."""

    def __init__(self, thread_pool: QThreadPool | None = None):
        self._pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
        self._active_job: ExportJob | None = None

    @property
    def is_running(self) -> bool:
        return self._active_job is not None

    def submit(self, job: ExportJob) -> None:
        self._active_job = job
        job.signals.finished.connect(self._on_finished)
        job.signals.errorOccurred.connect(self._on_finished_with_error)
        self._pool.start(job)

    def cancel(self) -> None:
        if self._active_job is not None:
            self._active_job.cancel()

    def _on_finished(self, _result: ExportResult) -> None:
        self._active_job = None

    def _on_finished_with_error(self, _error: str) -> None:
        self._active_job = None
