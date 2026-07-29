"""Background job for preparing editor video proxies."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from automatedub.config import ToolConfig
from automatedub_studio.project.models import Project
from automatedub_studio.project.video_proxy import (
    VideoProxyError,
    VideoProxyResult,
    prepare_editor_video,
)


class VideoProxyJobSignals(QObject):
    progressChanged = Signal(str)
    finished = Signal(object)
    errorOccurred = Signal(str)


class VideoProxyJob(QRunnable):
    """Prepare the project's editor video path without blocking the GUI thread."""

    def __init__(self, project: Project, tool_config: ToolConfig):
        super().__init__()
        self.signals = VideoProxyJobSignals()
        self._project = project
        self._tool_config = tool_config

    def run(self) -> None:
        if self._project.video_path is None:
            self.signals.finished.emit(self._project)
            return
        try:
            result = prepare_editor_video(
                self._project.project_path,
                self._project.video_path,
                self._tool_config,
                on_progress=self.signals.progressChanged.emit,
            )
        except VideoProxyError as exc:
            self.signals.errorOccurred.emit(str(exc))
            return
        self._apply_result(result)
        self.signals.finished.emit(self._project)

    def _apply_result(self, result: VideoProxyResult) -> None:
        self._project.video_path = result.source_video
        self._project.editor_video_path = result.editor_video
        self._project.source_codec = result.source_codec
        self._project.editor_codec = result.editor_codec
