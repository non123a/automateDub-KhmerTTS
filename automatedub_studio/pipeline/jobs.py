"""Processing pipeline jobs for Studio projects."""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from automatedub.config import ToolConfig, load_tool_config
from automatedub.vertical_slice.audio import extract_audio
from automatedub.vertical_slice.paths import (
    audio_output_path,
    transcript_output_path,
    translation_output_path,
    translation_prompt_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.tts import (
    build_cambai_tts_payload,
    create_tts_provider,
    load_timed_translation_segments,
    tts_segment_output_path,
)
from automatedub_studio.backend.regeneration_service import (
    regenerate_segment,
)
from automatedub_studio.pipeline.timeline_generation import build_initial_timeline
from automatedub_studio.project.manager import (
    CreatedProject,
    NewProjectRequest,
    ProjectManager,
)
from automatedub_studio.project.models import Segment
from automatedub_studio.providers.manager import ProviderManager

STAGE_CREATE_PROJECT = "create_project"
STAGE_COPY_SOURCE_VIDEO = "copy_source_video"
STAGE_EXTRACT_AUDIO = "extract_audio"
STAGE_TRANSCRIPTION = "transcription"
STAGE_SPEECH_DETECTION = "speech_detection"
STAGE_TRANSLATION = "translation"
STAGE_TTS_GENERATION = "tts_generation"
STAGE_TIMELINE_GENERATION = "timeline_generation"
EXPECTED_PIPELINE_FLOW = [
    STAGE_CREATE_PROJECT,
    STAGE_COPY_SOURCE_VIDEO,
    STAGE_EXTRACT_AUDIO,
    STAGE_TRANSCRIPTION,
    STAGE_SPEECH_DETECTION,
    STAGE_TRANSLATION,
    STAGE_TTS_GENERATION,
    STAGE_TIMELINE_GENERATION,
]


@dataclass(frozen=True)
class PipelineStage:
    id: str
    label: str


class TTSGenerationFailedError(RuntimeError):
    """Raised when no usable initial Khmer audio was generated."""


@dataclass
class PipelineContext:
    request: NewProjectRequest
    project_manager: ProjectManager = field(default_factory=ProjectManager)
    tool_config: ToolConfig = field(default_factory=load_tool_config)
    provider_manager: ProviderManager | None = None
    tts_provider_factory: Callable[[ToolConfig], object] = create_tts_provider
    created_project: CreatedProject | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)
    scheduled_stages: list[str] = field(default_factory=list)
    scheduled_stage_details: list[dict[str, str]] = field(default_factory=list)
    tts_generation_completed: int | None = None
    tts_generation_total: int = 0
    tts_failed_segment_ids: list[int] = field(default_factory=list)
    tts_generation_summary: dict[str, object] = field(default_factory=dict)
    skip_tts: bool = False

    def __post_init__(self) -> None:
        if self.provider_manager is None:
            self.provider_manager = ProviderManager(self.tool_config)

    @property
    def project_path(self) -> Path:
        if self.created_project is None:
            raise RuntimeError("project has not been created")
        return self.created_project.project_path

    @property
    def pipeline_path(self) -> Path:
        return self.project_path / "pipeline"

    @property
    def timeline_path(self) -> Path:
        return self.project_path / "timeline"

    @property
    def tts_path(self) -> Path:
        return self.project_path / "tts"


class ProgressCallback(Protocol):
    def __call__(self, progress: int, message: str = "") -> None: ...


class PipelineJob(Protocol):
    stage: PipelineStage

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None: ...


class CreateProjectJob:
    stage = PipelineStage(STAGE_CREATE_PROJECT, "Create Project")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(5, "Creating project folder")
        context.created_project = context.project_manager.create_project_structure(
            context.request
        )
        if context.provider_manager is not None:
            _update_metadata(context, {"providers": context.provider_manager.project_metadata()})
        progress(100, "Project folder created")


class CopySourceVideoJob:
    stage = PipelineStage(STAGE_COPY_SOURCE_VIDEO, "Copy Source Video")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(10, "Copying source video")
        source_path = context.project_manager.copy_source_video(
            context.request,
            _require_created_project(context),
        )
        context.artifacts["source_video"] = source_path
        _update_metadata(
            context,
            {
                "source_video": source_path.relative_to(context.project_path).as_posix(),
                "editor_video": source_path.relative_to(context.project_path).as_posix(),
            },
        )
        progress(100, "Source video copied")


class ExtractAudioJob:
    stage = PipelineStage(STAGE_EXTRACT_AUDIO, "Extract Audio")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(5, "Extracting audio")
        source_video = context.artifacts.get("source_video")
        if source_video is None:
            source_video = _require_created_project(context).source_video_path
        audio_path = extract_audio(
            input_path=source_video,
            output_dir=context.pipeline_path,
            tool_config=context.tool_config,
        )
        context.artifacts["audio"] = audio_path
        _update_metadata(
            context,
            {"audio": audio_path.relative_to(context.project_path).as_posix()},
        )
        progress(100, "Audio extracted")


class TranscriptionJob:
    stage = PipelineStage(STAGE_TRANSCRIPTION, "Transcription")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(5, "Transcribing audio")
        audio_path = context.artifacts.get("audio", audio_output_path(context.pipeline_path))
        transcript_path = transcript_output_path(context.pipeline_path)
        if context.provider_manager is None:
            raise RuntimeError("provider manager is not configured")
        provider = context.provider_manager.stt_provider()
        provider.validate()
        provider.transcribe(audio_path=audio_path, transcript_path=transcript_path)
        context.artifacts["transcript"] = transcript_path
        _update_metadata(
            context,
            {"transcript": transcript_path.relative_to(context.project_path).as_posix()},
        )
        progress(100, "Transcription complete")


class SpeechDetectionJob:
    stage = PipelineStage(STAGE_SPEECH_DETECTION, "Speech Detection")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(10, "Writing detected speech segments")
        transcript_path = context.artifacts.get(
            "transcript",
            transcript_output_path(context.pipeline_path),
        )
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        segments = transcript.get("segments", [])
        speech_segments = [
            {
                "id": segment.get("id"),
                "start": segment.get("start"),
                "end": segment.get("end"),
            }
            for segment in segments
            if isinstance(segment, dict)
        ]
        output_path = context.pipeline_path / "speech_segments.json"
        output_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_transcript": transcript_path.name,
                    "segments": speech_segments,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["speech_segments"] = output_path
        _update_metadata(
            context,
            {"speech_segments": output_path.relative_to(context.project_path).as_posix()},
        )
        progress(100, f"Detected {len(speech_segments)} speech segments")


class TranslationJob:
    stage = PipelineStage(STAGE_TRANSLATION, "Translation")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(5, "Translating transcript")
        transcript_path = context.artifacts.get(
            "transcript",
            transcript_output_path(context.pipeline_path),
        )
        translation_path = translation_output_path(context.pipeline_path)
        prompt_path = translation_prompt_output_path(context.pipeline_path)
        if context.provider_manager is None:
            raise RuntimeError("provider manager is not configured")
        provider = context.provider_manager.translation_provider()
        provider.validate()
        trace = translation_provider_trace(context.provider_manager, provider)
        debug_dir = context.pipeline_path / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "translation_provider_trace.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        progress(
            10,
            f"Translation provider: {trace['provider_id']} "
            f"({trace['provider_class']})",
        )
        provider.translate(
            transcript_path=transcript_path,
            translation_path=translation_path,
            prompt_path=prompt_path,
        )
        context.artifacts["translation"] = translation_path
        context.artifacts["translation_prompt"] = prompt_path
        _update_metadata(
            context,
            {
                "translation": translation_path.relative_to(context.project_path).as_posix(),
                "translation_prompt": prompt_path.relative_to(context.project_path).as_posix(),
            },
        )
        progress(100, "Translation complete")


class BulkKhmerTTSGenerationJob:
    stage = PipelineStage(STAGE_TTS_GENERATION, "Generating Khmer Speech")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(0, "Preparing Khmer speech generation")
        translation_path = context.artifacts.get(
            "translation",
            translation_output_path(context.pipeline_path),
        )
        timed_segments = load_timed_translation_segments(translation_path)
        segments = [
            Segment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                source_text="",
                target_text=segment.target_text,
            )
            for segment in timed_segments
        ]
        debug_dir = context.pipeline_path / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        tts_dir = tts_output_dir_path(context.project_path)
        tts_dir.mkdir(parents=True, exist_ok=True)
        total = len(segments)
        outputs: list[dict[str, object]] = []
        failures: list[int] = []
        skipped: list[int] = []
        started_at = time.monotonic()
        generation_trace = {
            "version": 1,
            "entered": True,
            "skipped": False,
            "skip_reason": None,
            "translation_path": str(translation_path),
            "translation_segments_loaded": total,
            "synthesis_requests_queued": total,
            "completed": 0,
            "failed": 0,
            "failed_segment_ids": failures,
            "output_directory": str(tts_dir),
            "output_files_written": [],
            "provider_called": False,
        }
        _write_json(debug_dir / "tts_generation_trace.json", generation_trace)
        if context.provider_manager is None:
            raise RuntimeError("provider manager is not configured")
        provider = None
        request_entries: list[dict[str, object]] = []
        try:
            tool_config = context.provider_manager.tool_config
            if tool_config.tts_provider.strip().lower() != "cambai":
                raise TTSGenerationFailedError(
                    "Initial Khmer TTS requires the Camb.ai provider."
                )
            provider = context.tts_provider_factory(context.provider_manager.tool_config)
            provider_trace = tts_provider_trace(
                context.provider_manager,
                provider,
                executed=True,
            )
            _write_json(debug_dir / "tts_provider_trace.json", provider_trace)
            _write_json(debug_dir / "tts_provider.json", provider_trace)
            _write_json(debug_dir / "tts_requests.json", {"version": 1, "requests": []})
            validate = getattr(provider, "validate", None)
            if callable(validate):
                validate()
        except Exception as exc:
            provider_trace = tts_provider_trace(
                context.provider_manager,
                provider,
                executed=False,
                error=str(exc),
            )
            _write_json(debug_dir / "tts_provider_trace.json", provider_trace)
            _write_json(debug_dir / "tts_provider.json", provider_trace)
            outputs = [
                _failed_tts_result(
                    segment,
                    tts_segment_output_path(tts_dir, segment.id),
                    provider_trace,
                    str(exc),
                )
                for segment in segments
            ]
            summary = {
                "translation_segments_loaded": total,
                "segments_attempted": 0,
                "succeeded": 0,
                "failed": total,
                "skipped": 0,
                "failed_segment_ids": [segment.id for segment in segments],
                "common_failure_reason": str(exc),
            }
            _write_tts_results(
                debug_dir,
                tts_dir,
                provider_trace,
                summary,
                outputs,
            )
            context.tts_generation_completed = 0
            context.tts_generation_total = total
            context.tts_failed_segment_ids = list(summary["failed_segment_ids"])
            context.tts_generation_summary = summary
            raise TTSGenerationFailedError(
                f"Khmer speech provider validation failed: {exc}"
            ) from exc
        for index, segment in enumerate(segments, start=1):
            elapsed = time.monotonic() - started_at
            average = elapsed / max(index - 1, 1)
            remaining = max(total - index + 1, 0) * average
            progress(
                _bulk_tts_progress(index - 1, total),
                (
                    f"Segment {segment.id} ({index}/{total}) · "
                    f"{index - 1} completed · ~{round(remaining)}s remaining"
                ),
            )
            output_path = tts_segment_output_path(tts_dir, segment.id)
            request_entry = {
                "segment_id": segment.id,
                "text": segment.target_text,
                "output_path": str(output_path),
                "request_payload": _tts_request_payload(
                    context.provider_manager.tool_config,
                    segment.target_text,
                ),
                "request_started": False,
            }
            request_entries.append(request_entry)
            _write_json(
                debug_dir / "tts_requests.json",
                {"version": 1, "requests": request_entries},
            )
            outcome = regenerate_segment(
                segment,
                None,
                tts_dir,
                context.provider_manager.tool_config,
                provider_factory=context.tts_provider_factory,
            )
            if not outcome.success:
                failures.append(segment.id)
            else:
                generation_trace["completed"] = int(generation_trace["completed"]) + 1
                generation_trace["output_files_written"].append(str(output_path))
            generation_trace["failed"] = len(failures)
            generation_trace["provider_called"] = True
            generation_trace["failed_segment_ids"] = list(failures)
            _write_json(debug_dir / "tts_generation_trace.json", generation_trace)
            outputs.append(
                _regeneration_result_payload(
                    segment_id=segment.id,
                    khmer_text=segment.target_text,
                    output_filename=output_path.name,
                    output_path=str(output_path),
                    success=outcome.success,
                    failure=outcome.error,
                    queued=True,
                    outcome=outcome,
                    request_payload=_tts_request_payload(
                        context.provider_manager.tool_config,
                        segment.target_text,
                    ),
                )
            )
            request_entry.update(
                {
                    "request_started": outcome.request_started,
                    "request_started_at": outcome.request_started_at,
                    "request_finished_at": outcome.request_finished_at,
                    "http_status": outcome.http_status,
                    "response_body": outcome.response_body,
                }
            )
            _write_json(
                debug_dir / "tts_requests.json",
                {"version": 1, "requests": request_entries},
            )
            progress(
                _bulk_tts_progress(index, total),
                f"Segment {segment.id} complete · {index}/{total} processed",
            )

        generation_trace["output_files_written"] = [
            str(path) for path in sorted(tts_dir.glob("*.wav"))
        ]
        generation_trace["completed"] = total - len(failures)
        generation_trace["failed"] = len(failures)
        generation_trace["failed_segment_ids"] = list(failures)
        _write_json(debug_dir / "tts_generation_trace.json", generation_trace)
        failure_reasons = Counter(
            str(item["failure"])
            for item in outputs
            if not item["success"] and item["failure"]
        )
        summary = {
            "translation_segments_loaded": total,
            "segments_attempted": total,
            "succeeded": total - len(failures),
            "failed": len(failures),
            "skipped": len(skipped),
            "failed_segment_ids": failures,
            "common_failure_reason": failure_reasons.most_common(1)[0][0]
            if failure_reasons
            else None,
        }
        _write_tts_results(
            debug_dir,
            tts_dir,
            provider_trace,
            summary,
            outputs,
        )
        context.artifacts["tts"] = tts_dir
        context.tts_generation_completed = total - len(failures)
        context.tts_generation_total = total
        context.tts_failed_segment_ids = list(failures)
        context.tts_generation_summary = summary
        _update_metadata(
            context,
            {
                "tts": tts_dir.relative_to(context.project_path).as_posix(),
                "tts_generation": {
                    "generated_count": total - len(failures),
                    "failed_segment_ids": failures,
                },
            },
        )
        progress(
            100,
            _tts_summary_message(summary),
        )

        if total and not context.tts_generation_completed:
            raise TTSGenerationFailedError(
                f"All {total} Khmer speech generation requests failed. "
                f"Common reason: {summary['common_failure_reason'] or 'unknown'}"
            )


class TimelineGenerationJob:
    stage = PipelineStage(STAGE_TIMELINE_GENERATION, "Timeline Generation")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        translation_path = context.artifacts.get(
            "translation",
            translation_output_path(context.pipeline_path),
        )
        timed_segments = load_timed_translation_segments(translation_path)
        if not context.skip_tts:
            _assert_tts_outputs_ready(
                context,
                translation_segments=timed_segments,
                tts_dir=tts_output_dir_path(context.project_path),
            )
        progress(10, "Generating timeline")
        audio_path = context.artifacts.get("audio", audio_output_path(context.pipeline_path))
        timeline = build_initial_timeline(
            project_path=context.project_path,
            translation_path=translation_path,
            audio_path=audio_path,
            tts_directory=tts_output_dir_path(context.project_path),
        )
        timeline_path = context.timeline_path / "timeline.edited.json"
        context.artifacts["timeline"] = timeline_path
        _update_metadata(
            context,
            {
                "timeline": timeline_path.relative_to(context.project_path).as_posix(),
                "pipeline": {
                    "status": "ready",
                    "stages": [job.stage.id for job in default_pipeline_jobs()],
                },
            },
        )
        progress(100, f"Generated {len(timeline.all_clips())} timeline clips")


def translation_provider_trace(
    provider_manager: ProviderManager,
    provider,
) -> dict[str, object]:
    tool_config = provider_manager.tool_config
    provider_class = type(provider)
    return {
        "provider_id": getattr(provider, "id", provider_manager.selection.translation_provider_id),
        "provider_class": provider_class.__name__,
        "provider_module": provider_class.__module__,
        "selected_provider_id": provider_manager.selection.translation_provider_id,
        "model": tool_config.localization_model,
        "base_url": tool_config.nbw_base_url,
        "wire_api": tool_config.translation_wire_api,
    }


def default_pipeline_jobs() -> list[PipelineJob]:
    return [
        CreateProjectJob(),
        CopySourceVideoJob(),
        ExtractAudioJob(),
        TranscriptionJob(),
        SpeechDetectionJob(),
        TranslationJob(),
        BulkKhmerTTSGenerationJob(),
        TimelineGenerationJob(),
    ]


def tts_provider_trace(
    provider_manager: ProviderManager,
    provider,
    *,
    executed: bool,
    error: str | None = None,
) -> dict[str, object]:
    selection = provider_manager.selection
    tool_config = provider_manager.tool_config
    provider_class = type(provider) if provider is not None else None
    return {
        "version": 1,
        "resolved": provider is not None,
        "executed": executed,
        "provider_id": getattr(provider, "id", selection.tts_provider_id)
        if provider is not None
        else selection.tts_provider_id,
        "provider": getattr(provider, "id", selection.tts_provider_id)
        if provider is not None
        else selection.tts_provider_id,
        "provider_class": provider_class.__name__ if provider_class is not None else None,
        "provider_module": provider_class.__module__ if provider_class is not None else None,
        "underlying_provider_class": _underlying_provider_class(provider)
        if provider is not None
        else None,
        "selected_provider_id": selection.tts_provider_id,
        "voice_id": selection.selected_voice,
        "voice": selection.selected_voice,
        "model": tool_config.tts_model,
        "speech_model": tool_config.tts_model,
        "language": tool_config.camb_language,
        "speaking_rate": tool_config.tts_speed,
        "speed": tool_config.tts_speed,
        "sync_offset": tool_config.tts_sync_offset_ms,
        "offset": tool_config.tts_sync_offset_ms,
        "api_base_url": tool_config.camb_api_base_url,
        "api_endpoint": "text_to_speech.tts",
        "request_payload_template": _tts_request_payload(tool_config, "<segment text>"),
        "error": error,
    }


def _underlying_provider_class(provider) -> str | None:
    underlying = getattr(provider, "provider", None)
    if underlying is None:
        return None
    return f"{type(underlying).__module__}.{type(underlying).__name__}"


def _tts_request_payload(tool_config: ToolConfig, text: str) -> dict[str, object]:
    if tool_config.tts_provider.strip().lower() == "cambai":
        try:
            payload = build_cambai_tts_payload(tool_config, text)
        except Exception:
            payload = {
                "text": text,
                "voice_id": tool_config.camb_voice_id,
                "language": tool_config.camb_language,
                "speech_model": tool_config.tts_model,
            }
        return {
            **payload,
            "output_format": "wav",
            "speaking_rate": tool_config.tts_speed,
        }
    return {
        "text": text,
        "model": tool_config.tts_model,
        "output_format": "wav",
        "speaking_rate": tool_config.tts_speed,
    }


def _bulk_tts_progress(completed: int, total: int) -> int:
    if total <= 0:
        return 100
    return min(99, int((completed / total) * 100))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _regeneration_result_payload(
    *,
    segment_id: int,
    khmer_text: str,
    output_filename: str,
    output_path: str,
    success: bool,
    failure: str | None,
    queued: bool,
    outcome,
    request_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "khmer_text": khmer_text,
        "provider": outcome.provider_id,
        "provider_class": outcome.provider_class,
        "voice_id": outcome.voice_id,
        "model": outcome.model,
        "speaking_rate": outcome.speaking_rate,
        "request_payload": request_payload,
        "request_started": outcome.request_started,
        "request_started_at": outcome.request_started_at,
        "request_finished_at": outcome.request_finished_at,
        "http_status": outcome.http_status,
        "response_body": outcome.response_body,
        "output_filename": output_filename,
        "output_path": output_path,
        "file_exists": outcome.file_exists,
        "file_size": outcome.file_size,
        "audio_duration": outcome.duration_seconds,
        "validation_result": outcome.validation_result,
        "success": success,
        "failure": failure,
        "queued": queued,
    }


def _failed_tts_result(
    segment: Segment,
    output_path: Path,
    provider_trace: dict[str, object],
    error: str,
) -> dict[str, object]:
    return {
        "segment_id": segment.id,
        "khmer_text": segment.target_text,
        "provider": provider_trace.get("provider_id"),
        "provider_class": provider_trace.get("provider_class"),
        "voice_id": provider_trace.get("voice_id"),
        "model": provider_trace.get("model"),
        "speaking_rate": provider_trace.get("speaking_rate"),
        "request_started": False,
        "request_started_at": None,
        "request_finished_at": None,
        "http_status": None,
        "response_body": error,
        "output_filename": output_path.name,
        "output_path": str(output_path),
        "file_exists": output_path.is_file(),
        "file_size": output_path.stat().st_size if output_path.is_file() else 0,
        "audio_duration": None,
        "validation_result": "not_run",
        "success": False,
        "failure": error,
        "queued": False,
    }


def _write_tts_results(
    debug_dir: Path,
    tts_dir: Path,
    provider_trace: dict[str, object],
    summary: dict[str, object],
    outputs: list[dict[str, object]],
) -> None:
    _write_json(
        debug_dir / "tts_generation_results.json",
        {
            "version": 1,
            "provider": provider_trace,
            "comparison_with_inspector_regenerate": _bulk_vs_regenerate_comparison(),
            "output_directory": str(tts_dir),
            "summary": summary,
            "segments": outputs,
        },
    )
    _write_json(
        debug_dir / "tts_results.json",
        {
            "version": 1,
            "provider": provider_trace,
            "output_directory": str(tts_dir),
            "summary": summary,
            "segments": outputs,
        },
    )
    _write_json(
        debug_dir / "tts_outputs.json",
        {
            "version": 1,
            "tts_directory": str(tts_dir),
            "tts_directory_created": tts_dir.is_dir(),
            "translation_segments_loaded": summary["translation_segments_loaded"],
            "synthesis_requests_queued": sum(
                1 for item in outputs if item["queued"]
            ),
            "provider_called": any(item["request_started"] for item in outputs),
            "failed_segment_ids": summary["failed_segment_ids"],
            "segments": outputs,
        },
    )


def _tts_summary_message(summary: dict[str, object]) -> str:
    return (
        f"Generated: {summary['succeeded']} · "
        f"Failed: {summary['failed']} · "
        f"Skipped: {summary['skipped']}"
    )


def _bulk_vs_regenerate_comparison() -> dict[str, object]:
    return {
        "bulk_function": (
            "automatedub_studio.pipeline.jobs.BulkKhmerTTSGenerationJob.run"
        ),
        "bulk_service": (
            "automatedub_studio.backend.regeneration_service.regenerate_segment"
        ),
        "inspector_service": (
            "automatedub_studio.backend.regeneration_service.regenerate_timeline_clip"
        ),
        "provider_method": "provider.generate(text)",
        "output_format": "wav",
        "validation": "automatedub.vertical_slice.tts.validate_wav_audio",
        "file_write": "Path.write_bytes(speech.audio)",
        "same_provider_manager_selection": True,
        "remaining_differences": [
            "bulk reads Segment.target_text from translation.json",
            "inspector reads TimelineClip.khmer_text from timeline.edited.json/runtime model",
            "bulk writes tts/####.wav",
            "inspector writes tts/clips/<clip_id>.wav",
        ],
    }


def _assert_tts_outputs_ready(
    context: PipelineContext,
    *,
    translation_segments,
    tts_dir: Path,
) -> None:
    if context.tts_generation_completed is None:
        raise RuntimeError(
            "TTS generation did not complete before Timeline Generation. "
            "The editor will not open with an unverified Khmer track."
        )
    if not tts_dir.is_dir():
        raise RuntimeError(f"TTS output directory is missing: {tts_dir}")

    failed_ids = set(context.tts_failed_segment_ids)
    expected_ids = {
        segment.id for segment in translation_segments if segment.id not in failed_ids
    }
    actual_paths = {
        path for path in tts_dir.glob("*.wav") if path.is_file()
    }
    actual_ids = {
        int(path.stem)
        for path in actual_paths
        if path.stem.isdigit()
    }
    if len(actual_paths) != len(expected_ids) or actual_ids != expected_ids:
        raise RuntimeError(
            "TTS output validation failed before Timeline Generation: "
            f"expected {len(expected_ids)} WAV file(s), found {len(actual_paths)}"
        )
    if translation_segments and not expected_ids:
        raise RuntimeError(
            "TTS generation produced no usable audio."
        )


def _require_created_project(context: PipelineContext) -> CreatedProject:
    if context.created_project is None:
        raise RuntimeError("project has not been created")
    return context.created_project


def _update_metadata(context: PipelineContext, updates: dict[str, object]) -> None:
    created = _require_created_project(context)
    context.created_project = context.project_manager.write_project_metadata(created, updates)
