"""Export manager and render-pipeline coordination."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportEncoderCapabilities,
    ExportOptions,
    ExportResult,
    ExportStreamSummary,
    ExportSystemCapabilities,
    FFmpegProgress,
    build_mux_command,
    choose_export_video_encoder,
    export_project,
    probe_export_encoder_capabilities,
    probe_export_system_capabilities,
    probe_source_streams_for_export,
    probe_stream_copy_capability,
    stream_copy_safety,
    validate_export_streams,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project
from automatedub_studio.timeline.timeline_clip import (
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
    VIDEO_TRACK_ID,
    Timeline,
)


class AudioMode(StrEnum):
    KHMER_ONLY = "khmer_only"
    ORIGINAL_ONLY = "original_only"
    MIXED = "mixed"


class SubtitleMode(StrEnum):
    NONE = "none"
    EXTERNAL_SRT = "external_srt"
    EMBEDDED = "embedded"
    BURNED_IN = "burned_in"


class VideoEncodingPreset(StrEnum):
    FASTEST = "fastest"
    COMPATIBLE_H264 = "compatible_h264"
    HIGH_COMPRESSION_H265 = "high_compression_h265"
    ORIGINAL_CODEC = "original_codec"


BETA_UNAVAILABLE_PRESETS = {
    VideoEncodingPreset.HIGH_COMPRESSION_H265: (
        "Coming Soon. H.265 (HEVC) export is under development and is unavailable in the beta."
    ),
    VideoEncodingPreset.ORIGINAL_CODEC: (
        "Coming Soon. Original Codec export is under development and is temporarily unavailable "
        "in the beta."
    ),
}


class ExportPipelineStage(StrEnum):
    PREPARE_TIMELINE = "Preparing Project"
    RENDER_AUDIO = "Rendering Audio"
    ENCODE_VIDEO = "Encoding Video"
    FINALIZE_EXPORT = "Finalizing MP4"
    VERIFY_OUTPUT = "Verifying Output"


class ExportLifecycleState(StrEnum):
    """The one authoritative lifecycle for a managed export run."""

    IDLE = "idle"
    STARTING = "starting"
    EXPORTING = "exporting"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExportConfiguration:
    output_folder: Path
    filename: str
    video_quality: str = "High"
    codec: str = "h264"
    video_preset: VideoEncodingPreset = VideoEncodingPreset.COMPATIBLE_H264
    include_original_movie_audio: bool = False
    audio_mode: AudioMode = AudioMode.MIXED
    subtitle_mode: SubtitleMode = SubtitleMode.NONE

    @property
    def output_path(self) -> Path:
        filename = self.filename if self.filename.endswith(".mp4") else f"{self.filename}.mp4"
        return self.output_folder / filename


@dataclass(frozen=True)
class ExportPresetValidation:
    preset: VideoEncodingPreset
    available: bool
    message: str
    warning: str = ""


@dataclass(frozen=True)
class ExportCapabilityReport:
    """The source, system, and timeline facts behind preset availability."""

    source_video: Path | None
    source_streams: ExportStreamSummary
    source_container: str
    system: ExportSystemCapabilities
    has_video_edits: bool
    has_audio_edits: bool
    subtitle_mode: SubtitleMode
    stream_copy_supported: bool = False
    stream_copy_reason: str = "Stream-copy capability has not been checked."

    @property
    def source_codec(self) -> str | None:
        return self.source_streams.first_video_codec

    @property
    def source_video_stream(self) -> dict[str, object]:
        return next(
            (
                stream
                for stream in self.source_streams.raw_streams
                if stream.get("codec_type") == "video"
            ),
            {},
        )

    @property
    def source_resolution(self) -> str:
        stream = self.source_video_stream
        width, height = stream.get("width"), stream.get("height")
        return f"{width}x{height}" if width and height else "Unknown"

    @property
    def source_pixel_format(self) -> str:
        return str(self.source_video_stream.get("pix_fmt") or "Unknown")

    @property
    def source_frame_rate(self) -> str:
        return str(self.source_video_stream.get("avg_frame_rate") or "Unknown")


def inspect_export_capabilities(
    project: Project | None,
    timeline: Timeline | None,
    tool_config: ToolConfig,
    subtitle_mode: SubtitleMode = SubtitleMode.NONE,
) -> ExportCapabilityReport:
    source_video = project.export_video_path if project is not None else None
    source_streams = ExportStreamSummary(0, 0, [])
    if source_video is not None:
        try:
            source_streams = probe_source_streams_for_export(
                _resolve_ffprobe(tool_config),
                source_video,
                known_source_codec=project.source_codec if project is not None else None,
            )
        except ExportManagerError:
            source_codec = project.source_codec if project is not None else None
            source_streams = ExportStreamSummary(
                1 if source_codec else 0,
                0,
                [{"codec_type": "video", "codec_name": source_codec}] if source_codec else [],
            )
    ffmpeg: str | None = None
    try:
        ffmpeg = _resolve_ffmpeg(tool_config)
        system = probe_export_system_capabilities(ffmpeg)
    except ExportManagerError:
        system = ExportSystemCapabilities(
            "FFmpeg unavailable",
            frozenset(),
            frozenset(),
            None,
            None,
        )
    if source_video is not None and ffmpeg is not None:
        stream_copy_supported, stream_copy_reason = probe_stream_copy_capability(
            ffmpeg, source_video
        )
    elif source_video is not None:
        stream_copy_supported, stream_copy_reason = (
            False,
            "FFmpeg is unavailable for stream-copy capability checking.",
        )
    else:
        stream_copy_supported, stream_copy_reason = (
            False,
            "A source video is required for stream copy.",
        )
    return ExportCapabilityReport(
        source_video=source_video,
        source_streams=source_streams,
        source_container=(
            source_streams.container_name
            or (source_video.suffix.lower().lstrip(".") if source_video else "")
        ),
        system=system,
        has_video_edits=_timeline_has_video_edits(timeline),
        has_audio_edits=_timeline_has_audio_edits(timeline),
        subtitle_mode=subtitle_mode,
        stream_copy_supported=stream_copy_supported,
        stream_copy_reason=stream_copy_reason,
    )


def validate_export_presets(
    project: Project | None,
    timeline: Timeline | None = None,
    encoder_capabilities: ExportEncoderCapabilities | None = None,
    capability_report: ExportCapabilityReport | None = None,
) -> dict[VideoEncodingPreset, ExportPresetValidation]:
    """Describe which export strategies are safe for the current project."""
    source_video = project.export_video_path if project is not None else None
    source_codec = project.source_codec.lower() if project and project.source_codec else None
    has_video_edits = _timeline_has_video_edits(timeline)
    if capability_report is not None:
        source_video = capability_report.source_video
        source_codec = capability_report.source_codec
        has_video_edits = capability_report.has_video_edits
        encoder_capabilities = ExportEncoderCapabilities(
            capability_report.system.h264_encoder,
            capability_report.system.h265_encoder,
        )

    validations = {
        VideoEncodingPreset.COMPATIBLE_H264: ExportPresetValidation(
            VideoEncodingPreset.COMPATIBLE_H264,
            True,
            "Re-encodes the source video to broadly compatible H.264 MP4.",
        ),
        VideoEncodingPreset.HIGH_COMPRESSION_H265: ExportPresetValidation(
            VideoEncodingPreset.HIGH_COMPRESSION_H265,
            encoder_capabilities is None or encoder_capabilities.h265_encoder is not None,
            (
                "Re-encodes the source video to playable H.265 MP4."
                if encoder_capabilities is None or encoder_capabilities.h265_encoder is not None
                else "No supported H.265 encoder is available on this computer."
            ),
        ),
    }
    if encoder_capabilities is not None and encoder_capabilities.h264_encoder is None:
        validations[VideoEncodingPreset.COMPATIBLE_H264] = ExportPresetValidation(
            VideoEncodingPreset.COMPATIBLE_H264,
            False,
            "No supported H.264 encoder is available on this computer.",
        )

    if capability_report is not None and not capability_report.system.supports_mp4_muxing:
        unavailable = "FFmpeg does not provide the MP4 muxer required for this export."
        for preset in (
            VideoEncodingPreset.COMPATIBLE_H264,
            VideoEncodingPreset.HIGH_COMPRESSION_H265,
        ):
            validations[preset] = ExportPresetValidation(preset, False, unavailable)

    if has_video_edits:
        copy_message = "Video edits require re-encoding and cannot use stream copy."
        validations[VideoEncodingPreset.FASTEST] = ExportPresetValidation(
            VideoEncodingPreset.FASTEST,
            False,
            copy_message,
        )
        validations[VideoEncodingPreset.ORIGINAL_CODEC] = ExportPresetValidation(
            VideoEncodingPreset.ORIGINAL_CODEC, False, copy_message
        )
        return _apply_beta_export_policy(validations)

    if capability_report is not None:
        can_stream_copy, stream_copy_message = (
            capability_report.stream_copy_supported,
            capability_report.stream_copy_reason,
        )
    else:
        can_stream_copy = False
        stream_copy_message = (
            f"Source codec {(source_codec or 'unknown').upper()} requires an actual FFmpeg "
            "stream-copy capability check before this preset can be used."
        )
    validations[VideoEncodingPreset.FASTEST] = ExportPresetValidation(
        VideoEncodingPreset.FASTEST,
        can_stream_copy,
        stream_copy_message,
    )

    if source_video is None:
        validations[VideoEncodingPreset.ORIGINAL_CODEC] = ExportPresetValidation(
            VideoEncodingPreset.ORIGINAL_CODEC,
            False,
            "A source video is required to preserve the original codec.",
        )
    elif not can_stream_copy:
        validations[VideoEncodingPreset.ORIGINAL_CODEC] = ExportPresetValidation(
            VideoEncodingPreset.ORIGINAL_CODEC,
            False,
            "Original codec is not compatible with current MP4 export settings: "
            f"{stream_copy_message}",
        )
    else:
        validations[VideoEncodingPreset.ORIGINAL_CODEC] = ExportPresetValidation(
            VideoEncodingPreset.ORIGINAL_CODEC,
            True,
            "Copies the original video codec into the MP4 output.",
            (
                f"{source_codec.upper()} is verified by FFmpeg but may require an AV1-capable "
                "player on this device."
                if source_codec == "av1"
                else ""
            ),
        )
    return _apply_beta_export_policy(validations)


def _apply_beta_export_policy(
    validations: dict[VideoEncodingPreset, ExportPresetValidation],
) -> dict[VideoEncodingPreset, ExportPresetValidation]:
    """Keep experimental codecs visible but unavailable during the external beta."""
    for preset, message in BETA_UNAVAILABLE_PRESETS.items():
        validations[preset] = ExportPresetValidation(preset, False, message)
    return validations


def validate_export_preset(
    project: Project | None,
    preset: VideoEncodingPreset,
    timeline: Timeline | None = None,
    encoder_capabilities: ExportEncoderCapabilities | None = None,
    capability_report: ExportCapabilityReport | None = None,
) -> ExportPresetValidation:
    return validate_export_presets(
        project,
        timeline,
        encoder_capabilities,
        capability_report,
    )[preset]


def _timeline_has_video_edits(timeline: Timeline | None) -> bool:
    if timeline is None:
        return False
    video_track = timeline.track_by_id(VIDEO_TRACK_ID)
    return bool(video_track and video_track.clips)


def _timeline_has_audio_edits(timeline: Timeline | None) -> bool:
    if timeline is None:
        return False
    return any(track.is_audio and track.clips for track in timeline.tracks)


def timeline_has_original_movie_audio(timeline: Timeline | None) -> bool:
    if timeline is None:
        return False
    track = timeline.track_by_id(ORIGINAL_MOVIE_AUDIO_TRACK_ID)
    return bool(track and track.clips)


def detect_export_encoder_capabilities(
    tool_config: ToolConfig,
) -> ExportEncoderCapabilities:
    try:
        return probe_export_encoder_capabilities(_resolve_ffmpeg(tool_config))
    except ExportManagerError:
        return ExportEncoderCapabilities(None, None)


@dataclass(frozen=True)
class ExportEvent:
    stage: ExportPipelineStage
    status: str
    progress: int = 0
    message: str = ""
    error: str = ""
    frame: int | None = None
    fps: float | None = None
    encoded_time_seconds: float | None = None
    elapsed_seconds: float | None = None
    remaining_seconds: float | None = None
    output_size_bytes: int | None = None
    speed: float | None = None
    command: tuple[str, ...] = ()
    job_id: int = 0


@dataclass(frozen=True)
class ManagedExportResult:
    output_path: Path
    metadata_path: Path
    subtitle_path: Path | None = None
    job_id: int = 0


ExportRenderer = Callable[
    [Project, dict[int, EditableSegment], ToolConfig, ExportConfiguration],
    ExportResult,
]
ExportVerifier = Callable[[ToolConfig, Path], None]


class ExportManager(QObject):
    """Coordinates export stages and background render execution."""

    eventEmitted = Signal(object)
    exportCompleted = Signal(object)
    exportFailed = Signal(object)
    exportCancelled = Signal()
    stateChanged = Signal(object, int)

    def __init__(
        self,
        project: Project,
        editables: dict[int, EditableSegment],
        tool_config: ToolConfig,
        configuration: ExportConfiguration,
        *,
        timeline: Timeline | None = None,
        renderer: ExportRenderer | None = None,
        verifier: ExportVerifier | None = None,
        thread_pool: QThreadPool | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.editables = editables
        self.tool_config = tool_config
        self.configuration = configuration
        self.timeline = timeline
        self.renderer = (
            renderer
            if renderer is not None
            else lambda project, editables, config, configuration: _default_renderer(
                project,
                editables,
                config,
                configuration,
                timeline=self.timeline,
                on_progress=self._on_ffmpeg_progress,
            )
        )
        self.verifier = verifier if verifier is not None else verify_export_output
        self._pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
        self._active_worker: _ExportWorker | None = None
        self._cancelled = False
        self._job_id = 0
        self._active_job_id = 0
        self.state = ExportLifecycleState.IDLE
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
        self._begin_run()
        worker = _ExportWorker(self)
        self._active_worker = worker
        self._pool.start(worker)

    def retry(self) -> None:
        if not self.is_running:
            self.start()

    def cancel(self) -> None:
        if self.state not in (ExportLifecycleState.STARTING, ExportLifecycleState.EXPORTING):
            return
        self._cancelled = True
        self._set_state(ExportLifecycleState.CANCELLING)

    def run_sync(self) -> ManagedExportResult:
        if self.state in (
            ExportLifecycleState.IDLE,
            ExportLifecycleState.COMPLETED,
            ExportLifecycleState.FAILED,
        ):
            self._begin_run()
        output_path = self.configuration.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        exports_dir = self.project.project_path / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = exports_dir / f"{output_path.stem}.export.json"
        subtitle_path: Path | None = None

        try:
            self._set_state(ExportLifecycleState.EXPORTING)
            capability_report = inspect_export_capabilities(
                self.project,
                self.timeline,
                self.tool_config,
                self.configuration.subtitle_mode,
            )
            validation = validate_export_preset(
                None,
                self.configuration.video_preset,
                capability_report=capability_report,
            )
            if not validation.available:
                raise ExportManagerError(validation.message)
            if (
                self.configuration.subtitle_mode == SubtitleMode.BURNED_IN
                and self.configuration.video_preset
                in (VideoEncodingPreset.FASTEST, VideoEncodingPreset.ORIGINAL_CODEC)
            ):
                raise ExportManagerError(
                    "Burned Into Video requires re-encoding. Select H.264 or H.265."
            )
            self._run_stage(ExportPipelineStage.PREPARE_TIMELINE, "Timeline ready")
            subtitle_path = self._generate_subtitles(output_path)
            self._run_stage(
                ExportPipelineStage.RENDER_AUDIO,
                "Audio rendered; subtitles generated" if subtitle_path else "Audio rendered",
            )
            self._ensure_not_cancelled()
            self._emit_event(ExportPipelineStage.ENCODE_VIDEO, "started", 0, "Encoding video")
            render_configuration = replace(
                self.configuration,
                include_original_movie_audio=timeline_has_original_movie_audio(self.timeline),
            )
            rendered = self.renderer(
                self.project,
                self.editables,
                self.tool_config,
                render_configuration,
            )
            if subtitle_path is not None and self.configuration.subtitle_mode in (
                SubtitleMode.EMBEDDED,
                SubtitleMode.BURNED_IN,
            ):
                self._apply_subtitles(rendered.output_path, subtitle_path)
                subtitle_path.unlink(missing_ok=True)
                subtitle_path = None
            self._emit_event(
                ExportPipelineStage.ENCODE_VIDEO,
                "completed",
                100,
                "Video encoded",
            )
            self._run_stage(ExportPipelineStage.FINALIZE_EXPORT, "MP4 finalized")
            self._emit_event(ExportPipelineStage.VERIFY_OUTPUT, "started", 0, "Verifying output")
            self.verifier(self.tool_config, rendered.output_path)
            self._emit_event(ExportPipelineStage.VERIFY_OUTPUT, "completed", 100, "Output verified")
            self._write_metadata(metadata_path, rendered.output_path, subtitle_path)
        except Exception as exc:
            stage = self._current_stage_for_failure()
            if self._cancelled:
                output_path.unlink(missing_ok=True)
                self._emit_event(stage, "cancelled", 0, "Export cancelled", error=str(exc))
                self.exportCancelled.emit()
                self._set_state(ExportLifecycleState.IDLE)
                raise ExportManagerError(str(exc)) from exc
            event = self._emit_event(stage, "failed", 0, str(exc), error=str(exc))
            self.failure = event
            self.exportFailed.emit(event)
            self._set_state(ExportLifecycleState.FAILED)
            raise ExportManagerError(str(exc)) from exc

        result = ManagedExportResult(
            output_path=output_path,
            metadata_path=metadata_path,
            subtitle_path=subtitle_path,
            job_id=self._active_job_id,
        )
        self.result = result
        self._set_state(ExportLifecycleState.COMPLETED)
        self.exportCompleted.emit(result)
        return result

    def _begin_run(self) -> None:
        self._cancelled = False
        self.failure = None
        self.result = None
        self._job_id += 1
        self._active_job_id = self._job_id
        self._set_state(ExportLifecycleState.STARTING)

    def _set_state(self, state: ExportLifecycleState) -> None:
        self.state = state
        self.stateChanged.emit(state, self._active_job_id)

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

    def _apply_subtitles(self, output_path: Path, subtitle_path: Path) -> None:
        ffmpeg = _resolve_ffmpeg(self.tool_config)
        temporary_output = output_path.with_name(f"{output_path.stem}.subtitled.mp4")
        if self.configuration.subtitle_mode == SubtitleMode.EMBEDDED:
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(output_path),
                "-i",
                str(subtitle_path),
                "-map",
                "0",
                "-map",
                "1:0",
                "-c",
                "copy",
                "-c:s",
                "mov_text",
                str(temporary_output),
            ]
        else:
            source_summary = probe_source_streams_for_export(
                _resolve_ffprobe(self.tool_config),
                output_path,
            )
            encoder, _reason = choose_export_video_encoder(
                source_summary,
                self.configuration.codec,
                video_preset=self.configuration.video_preset.value,
                encoder_capabilities=probe_export_encoder_capabilities(ffmpeg),
            )
            subtitle_filter = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(output_path),
                "-vf",
                f"subtitles=filename='{subtitle_filter}'",
                "-c:v",
                encoder,
                "-c:a",
                "copy",
                str(temporary_output),
            ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            message = (
                exc.stderr.strip()
                or exc.stdout.strip()
                or f"ffmpeg exited with {exc.returncode}"
            )
            raise ExportManagerError(f"subtitle render failed: {message}") from exc
        if not temporary_output.exists():
            raise ExportManagerError("subtitle render did not produce an MP4")
        temporary_output.replace(output_path)

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

    def _on_ffmpeg_progress(self, progress: FFmpegProgress) -> None:
        message_parts = []
        if progress.frame is not None:
            message_parts.append(f"frame {progress.frame}")
        if progress.fps is not None:
            message_parts.append(f"{progress.fps:.1f} fps")
        if progress.encoded_time_seconds is not None:
            message_parts.append(f"encoded {_format_seconds(progress.encoded_time_seconds)}")
        if progress.elapsed_seconds is not None:
            message_parts.append(f"elapsed {_format_seconds(progress.elapsed_seconds)}")
        if progress.remaining_seconds is not None:
            message_parts.append(f"remaining {_format_seconds(progress.remaining_seconds)}")
        if progress.output_size_bytes is not None:
            message_parts.append(f"{_format_bytes(progress.output_size_bytes)}")
        if progress.speed is not None:
            message_parts.append(f"{progress.speed:.2f}x")
        self._emit_event(
            ExportPipelineStage.ENCODE_VIDEO,
            "progress",
            progress.percent,
            f"{progress.percent}% · " + (" · ".join(message_parts) or "Encoding video"),
            frame=progress.frame,
            fps=progress.fps,
            encoded_time_seconds=progress.encoded_time_seconds,
            elapsed_seconds=progress.elapsed_seconds,
            remaining_seconds=progress.remaining_seconds,
            output_size_bytes=progress.output_size_bytes,
            speed=progress.speed,
            command=progress.command,
        )

    def _emit_event(
        self,
        stage: ExportPipelineStage,
        status: str,
        progress: int = 0,
        message: str = "",
        *,
        error: str = "",
        frame: int | None = None,
        fps: float | None = None,
        encoded_time_seconds: float | None = None,
        elapsed_seconds: float | None = None,
        remaining_seconds: float | None = None,
        output_size_bytes: int | None = None,
        speed: float | None = None,
        command: tuple[str, ...] = (),
    ) -> ExportEvent:
        event = ExportEvent(
            stage,
            status,
            progress,
            message,
            error,
            frame,
            fps,
            encoded_time_seconds,
            elapsed_seconds,
            remaining_seconds,
            output_size_bytes,
            speed,
            command,
            self._active_job_id,
        )
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
    *,
    timeline: Timeline | None = None,
    on_progress: Callable[[FFmpegProgress], None] | None = None,
) -> ExportResult:
    # Both dubbed modes must render the editable TimelineClip model.  The
    # legacy precombined TTS WAV cannot represent moves, duplicates, mutes,
    # fades, or overlaps made in the editor.
    if configuration.audio_mode != AudioMode.ORIGINAL_ONLY:
        return export_project(
            project=project,
            editables=editables,
            tool_config=tool_config,
            options=ExportOptions(
                output_path=configuration.output_path,
                video_codec=configuration.codec,
                video_quality=configuration.video_quality,
                video_preset=configuration.video_preset.value,
                include_original_movie_audio=configuration.include_original_movie_audio,
            ),
            timeline=timeline,
            on_progress=on_progress,
        )
    audio_path = _audio_path_for_mode(project, configuration.audio_mode)
    ffmpeg = _resolve_ffmpeg(tool_config)
    ffprobe = _resolve_ffprobe(tool_config)
    source_video = _require_video(project)
    source_summary = probe_source_streams_for_export(
        ffprobe,
        source_video,
        known_source_codec=project.source_codec,
    )
    encoder_capabilities = probe_export_encoder_capabilities(ffmpeg)
    if configuration.video_preset == VideoEncodingPreset.FASTEST:
        can_stream_copy, reason = stream_copy_safety(source_summary, source_video)
        if not can_stream_copy:
            raise ExportManagerError(f"Fastest preset unavailable: {reason}")
    video_encoder, _reason = choose_export_video_encoder(
        source_summary,
        configuration.codec,
        video_preset=configuration.video_preset.value,
        encoder_capabilities=encoder_capabilities,
    )
    configuration.output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_mux_command(
        ffmpeg=ffmpeg,
        video_path=source_video,
        mixed_audio_path=audio_path,
        output_path=configuration.output_path,
        video_encoder=video_encoder,
        video_quality=configuration.video_quality,
        source_video_bitrate=_source_video_bitrate(source_summary),
        loglevel="info",
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
    try:
        validate_export_streams(
            ffprobe=ffprobe,
            output_path=configuration.output_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise ExportManagerError(str(exc)) from exc
    return ExportResult(output_path=configuration.output_path)


def verify_export_output(tool_config: ToolConfig, output_path: Path) -> None:
    """Reject incomplete or unreadable media before presenting success to the user."""
    if not output_path.is_file():
        raise ExportManagerError(f"export did not produce expected file: {output_path}")
    if output_path.stat().st_size <= 0:
        raise ExportManagerError("export output is empty")
    try:
        summary = validate_export_streams(_resolve_ffprobe(tool_config), output_path)
    except Exception as exc:  # noqa: BLE001
        raise ExportManagerError(f"export output verification failed: {exc}") from exc
    if summary.video_streams != 1 or summary.audio_streams != 1:
        raise ExportManagerError(
            "export output verification failed: expected exactly one video stream "
            "and one audio stream"
        )


def _audio_path_for_mode(project: Project, audio_mode: AudioMode) -> Path:
    if audio_mode == AudioMode.ORIGINAL_ONLY:
        source_audio = project.extracted_audio_path
        if not source_audio.exists():
            raise ExportManagerError(f"source audio not found: {source_audio}")
        return source_audio
    if audio_mode == AudioMode.KHMER_ONLY:
        if project.tts_combined_path is not None and project.tts_combined_path.exists():
            return project.tts_combined_path
        raise ExportManagerError("Khmer-only export requires tts_combined.wav")
    raise ExportManagerError(f"unsupported audio mode: {audio_mode.value}")


def _require_video(project: Project) -> Path:
    source_video = project.export_video_path
    if source_video is None or not source_video.exists():
        raise ExportManagerError(f"source video not found: {source_video}")
    return source_video


def _resolve_ffmpeg(tool_config: ToolConfig) -> str:
    try:
        from automatedub.vertical_slice.mix import validate_ffmpeg

        return validate_ffmpeg(tool_config)
    except Exception as exc:  # noqa: BLE001
        raise ExportManagerError(str(exc)) from exc


def _resolve_ffprobe(tool_config: ToolConfig) -> str:
    try:
        from automatedub.vertical_slice.mix import validate_ffprobe

        return validate_ffprobe(tool_config)
    except Exception as exc:  # noqa: BLE001
        raise ExportManagerError(str(exc)) from exc


def _source_video_bitrate(summary: ExportStreamSummary) -> int | None:
    for stream in summary.raw_streams:
        if stream.get("codec_type") == "video":
            try:
                value = int(str(stream.get("bit_rate")))
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
    return None


def _format_seconds(value: float) -> str:
    minutes, seconds = divmod(max(0, int(value)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    return f"{value / 1024:.0f} KB"


def _configuration_payload(configuration: ExportConfiguration) -> dict[str, object]:
    payload = asdict(configuration)
    payload["output_folder"] = str(configuration.output_folder)
    payload["audio_mode"] = configuration.audio_mode.value
    payload["subtitle_mode"] = configuration.subtitle_mode.value
    payload["video_preset"] = configuration.video_preset.value
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
