"""Export manager and render-pipeline coordination."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportOptions,
    ExportResult,
    build_mux_command,
    export_project,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project


class AudioMode(StrEnum):
    KHMER_ONLY = "khmer_only"
    ORIGINAL_ONLY = "original_only"
    MIXED = "mixed"


class SubtitleMode(StrEnum):
    NONE = "none"
    BURNED_IN = "burned_in"
    EXTERNAL_SRT = "external_srt"


class ExportPipelineStage(StrEnum):
    PREPARE_TIMELINE = "Prepare Timeline"
    RENDER_AUDIO = "Render Audio"
    MIX_AUDIO = "Mix Audio"
    GENERATE_SUBTITLES = "Generate Subtitles"
    ENCODE_VIDEO = "Encode Video"
    FINALIZE_EXPORT = "Finalize Export"


@dataclass(frozen=True)
class ExportConfiguration:
    output_folder: Path
    filename: str
    video_quality: str = "High"
    codec: str = "h264"
    audio_mode: AudioMode = AudioMode.MIXED
    subtitle_mode: SubtitleMode = SubtitleMode.NONE

    @property
    def output_path(self) -> Path:
        filename = self.filename if self.filename.endswith(".mp4") else f"{self.filename}.mp4"
        return self.output_folder / filename


@dataclass(frozen=True)
class ExportEvent:
    stage: ExportPipelineStage
    status: str
    progress: int = 0
    message: str = ""
    error: str = ""


@dataclass(frozen=True)
class ManagedExportResult:
    output_path: Path
    metadata_path: Path
    subtitle_path: Path | None = None


ExportRenderer = Callable[
    [Project, dict[int, EditableSegment], ToolConfig, ExportConfiguration],
    ExportResult,
]


class ExportManager(QObject):
    """Coordinates export stages and background render execution."""

    eventEmitted = Signal(object)
    exportCompleted = Signal(object)
    exportFailed = Signal(object)
    exportCancelled = Signal()

    def __init__(
        self,
        project: Project,
        editables: dict[int, EditableSegment],
        tool_config: ToolConfig,
        configuration: ExportConfiguration,
        *,
        renderer: ExportRenderer | None = None,
        thread_pool: QThreadPool | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.editables = editables
        self.tool_config = tool_config
        self.configuration = configuration
        self.renderer = renderer if renderer is not None else _default_renderer
        self._pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
        self._active_worker: _ExportWorker | None = None
        self._cancelled = False
        self.result: ManagedExportResult | None = None
        self.failure: ExportEvent | None = None
        self._current_stage = ExportPipelineStage.PREPARE_TIMELINE

    @property
    def is_running(self) -> bool:
        return self._active_worker is not None

    @property
    def stages(self) -> list[ExportPipelineStage]:
        return list(ExportPipelineStage)

    def start(self) -> None:
        if self.is_running:
            return
        self._cancelled = False
        worker = _ExportWorker(self)
        self._active_worker = worker
        self._pool.start(worker)

    def retry(self) -> None:
        if not self.is_running:
            self.start()

    def cancel(self) -> None:
        self._cancelled = True
        self.exportCancelled.emit()

    def run_sync(self) -> ManagedExportResult:
        output_path = self.configuration.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        exports_dir = self.project.project_path / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = exports_dir / f"{output_path.stem}.export.json"
        subtitle_path: Path | None = None

        try:
            self._run_stage(ExportPipelineStage.PREPARE_TIMELINE, "Timeline ready")
            self._run_stage(ExportPipelineStage.RENDER_AUDIO, "Audio render plan ready")
            self._run_stage(ExportPipelineStage.MIX_AUDIO, "Audio mix ready")
            subtitle_path = self._generate_subtitles(output_path)
            self._run_stage(
                ExportPipelineStage.GENERATE_SUBTITLES,
                "Subtitles generated" if subtitle_path else "Subtitles skipped",
            )
            self._ensure_not_cancelled()
            self._emit_event(ExportPipelineStage.ENCODE_VIDEO, "started", 0, "Encoding video")
            rendered = self.renderer(
                self.project,
                self.editables,
                self.tool_config,
                self.configuration,
            )
            self._emit_event(
                ExportPipelineStage.ENCODE_VIDEO,
                "completed",
                100,
                "Video encoded",
            )
            self._write_metadata(metadata_path, rendered.output_path, subtitle_path)
            self._run_stage(ExportPipelineStage.FINALIZE_EXPORT, "Export finalized")
        except Exception as exc:
            stage = self._current_stage_for_failure()
            event = self._emit_event(stage, "failed", 0, str(exc), error=str(exc))
            self.failure = event
            self.exportFailed.emit(event)
            raise ExportManagerError(str(exc)) from exc

        result = ManagedExportResult(
            output_path=output_path,
            metadata_path=metadata_path,
            subtitle_path=subtitle_path,
        )
        self.result = result
        self.exportCompleted.emit(result)
        return result

    def _run_stage(self, stage: ExportPipelineStage, message: str) -> None:
        self._ensure_not_cancelled()
        self._emit_event(stage, "started", 0, stage.value)
        self._emit_event(stage, "progress", 50, message)
        self._ensure_not_cancelled()
        self._emit_event(stage, "completed", 100, message)

    def _generate_subtitles(self, output_path: Path) -> Path | None:
        if self.configuration.subtitle_mode == SubtitleMode.NONE:
            return None
        subtitle_path = output_path.with_suffix(".srt")
        subtitle_path.write_text(_build_srt(self.project), encoding="utf-8")
        return subtitle_path

    def _write_metadata(
        self,
        metadata_path: Path,
        output_path: Path,
        subtitle_path: Path | None,
    ) -> None:
        payload = {
            "version": 1,
            "output_path": str(output_path),
            "subtitle_path": str(subtitle_path) if subtitle_path is not None else None,
            "configuration": _configuration_payload(self.configuration),
            "stages": [stage.value for stage in self.stages],
        }
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _ensure_not_cancelled(self) -> None:
        if self._cancelled:
            raise ExportManagerError("export cancelled")

    def _current_stage_for_failure(self) -> ExportPipelineStage:
        return self._current_stage

    def _on_worker_finished(self) -> None:
        self._active_worker = None

    def _emit_event(
        self,
        stage: ExportPipelineStage,
        status: str,
        progress: int = 0,
        message: str = "",
        *,
        error: str = "",
    ) -> ExportEvent:
        event = ExportEvent(stage, status, progress, message, error)
        self._current_stage = stage
        self.eventEmitted.emit(event)
        return event


class ExportManagerError(RuntimeError):
    """Raised when managed export fails."""


class _ExportWorker(QRunnable):
    def __init__(self, manager: ExportManager):
        super().__init__()
        self._manager = manager

    def run(self) -> None:
        try:
            self._manager.run_sync()
        except ExportManagerError:
            pass
        finally:
            self._manager._on_worker_finished()


def _default_renderer(
    project: Project,
    editables: dict[int, EditableSegment],
    tool_config: ToolConfig,
    configuration: ExportConfiguration,
) -> ExportResult:
    if configuration.audio_mode == AudioMode.MIXED:
        return export_project(
            project=project,
            editables=editables,
            tool_config=tool_config,
            options=ExportOptions(output_path=configuration.output_path),
        )
    audio_path = _audio_path_for_mode(project, configuration.audio_mode)
    ffmpeg = _resolve_ffmpeg(tool_config)
    configuration.output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_mux_command(
        ffmpeg=ffmpeg,
        video_path=_require_video(project),
        mixed_audio_path=audio_path,
        output_path=configuration.output_path,
    )
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
        raise ExportManagerError(f"video render failed: {message}") from exc
    if not configuration.output_path.exists():
        raise ExportManagerError(
            f"export did not produce expected file: {configuration.output_path}"
        )
    return ExportResult(output_path=configuration.output_path)


def _audio_path_for_mode(project: Project, audio_mode: AudioMode) -> Path:
    if audio_mode == AudioMode.ORIGINAL_ONLY:
        if not project.audio_path.exists():
            raise ExportManagerError(f"source audio not found: {project.audio_path}")
        return project.audio_path
    if audio_mode == AudioMode.KHMER_ONLY:
        if project.tts_combined_path is not None and project.tts_combined_path.exists():
            return project.tts_combined_path
        raise ExportManagerError("Khmer-only export requires tts_combined.wav")
    raise ExportManagerError(f"unsupported audio mode: {audio_mode.value}")


def _require_video(project: Project) -> Path:
    if project.video_path is None or not project.video_path.exists():
        raise ExportManagerError(f"source video not found: {project.video_path}")
    return project.video_path


def _resolve_ffmpeg(tool_config: ToolConfig) -> str:
    try:
        from automatedub.vertical_slice.mix import validate_ffmpeg

        return validate_ffmpeg(tool_config)
    except Exception as exc:  # noqa: BLE001
        raise ExportManagerError(str(exc)) from exc


def _configuration_payload(configuration: ExportConfiguration) -> dict[str, object]:
    payload = asdict(configuration)
    payload["output_folder"] = str(configuration.output_folder)
    payload["audio_mode"] = configuration.audio_mode.value
    payload["subtitle_mode"] = configuration.subtitle_mode.value
    return payload


def _build_srt(project: Project) -> str:
    blocks = []
    for index, segment in enumerate(project.segments, start=1):
        blocks.append(
            "\n".join(
                (
                    str(index),
                    f"{_srt_time(segment.start)} --> {_srt_time(segment.end)}",
                    segment.target_text,
                    "",
                )
            )
        )
    return "\n".join(blocks)


def _srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
