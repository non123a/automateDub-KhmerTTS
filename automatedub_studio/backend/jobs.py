"""QThreadPool/QRunnable wrapper so regeneration never blocks the UI thread."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig
from automatedub_studio.backend.regeneration_service import (
    RegenerationOutcome,
    regenerate_segments,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment


class RegenerationJobSignals(QObject):
    started = Signal(int)              # segment_id about to be regenerated
    resultReady = Signal(object)        # RegenerationOutcome
    finished = Signal(list)             # list[RegenerationOutcome], emitted once at the end


class RegenerationJob(QRunnable):
    """Runs regenerate_segments() on a worker thread from the shared QThreadPool."""

    def __init__(
        self,
        segments: list[Segment],
        editables: dict[int, EditableSegment],
        tts_dir: Path,
        tool_config: ToolConfig,
        segment_ids: Iterable[int],
    ):
        super().__init__()
        self.signals = RegenerationJobSignals()
        self._segments = list(segments)
        self._editables = editables
        self._tts_dir = tts_dir
        self._tool_config = tool_config
        self._segment_ids = list(segment_ids)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        outcomes = regenerate_segments(
            self._segments,
            self._editables,
            self._tts_dir,
            self._tool_config,
            self._segment_ids,
            on_result=self.signals.resultReady.emit,
            on_start=self.signals.started.emit,
            is_cancelled=lambda: self._cancelled,
        )
        self.signals.finished.emit(outcomes)


class JobRunner:
    """Thin facade over a QThreadPool for submitting RegenerationJob instances."""

    def __init__(self, thread_pool: QThreadPool | None = None):
        self._pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
        self._active_job: RegenerationJob | None = None

    @property
    def is_running(self) -> bool:
        return self._active_job is not None

    def submit(self, job: RegenerationJob) -> None:
        self._active_job = job
        job.signals.finished.connect(self._on_finished)
        self._pool.start(job)

    def cancel(self) -> None:
        if self._active_job is not None:
            self._active_job.cancel()

    def _on_finished(self, _outcomes: list[RegenerationOutcome]) -> None:
        self._active_job = None
