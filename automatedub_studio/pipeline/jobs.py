"""Processing pipeline jobs for Studio projects."""

from __future__ import annotations

import json
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
from automatedub_studio.pipeline.timeline_generation import build_initial_timeline
from automatedub_studio.project.manager import (
    CreatedProject,
    NewProjectRequest,
    ProjectManager,
)
from automatedub_studio.providers.manager import ProviderManager

STAGE_CREATE_PROJECT = "create_project"
STAGE_COPY_SOURCE_VIDEO = "copy_source_video"
STAGE_EXTRACT_AUDIO = "extract_audio"
STAGE_TRANSCRIPTION = "transcription"
STAGE_SPEECH_DETECTION = "speech_detection"
STAGE_TRANSLATION = "translation"
STAGE_TIMELINE_GENERATION = "timeline_generation"


@dataclass(frozen=True)
class PipelineStage:
    id: str
    label: str


@dataclass
class PipelineContext:
    request: NewProjectRequest
    project_manager: ProjectManager = field(default_factory=ProjectManager)
    tool_config: ToolConfig = field(default_factory=load_tool_config)
    provider_manager: ProviderManager | None = None
    created_project: CreatedProject | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)

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


class TimelineGenerationJob:
    stage = PipelineStage(STAGE_TIMELINE_GENERATION, "Timeline Generation")

    def run(self, context: PipelineContext, progress: ProgressCallback) -> None:
        progress(10, "Generating timeline")
        translation_path = context.artifacts.get(
            "translation",
            translation_output_path(context.pipeline_path),
        )
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


def default_pipeline_jobs() -> list[PipelineJob]:
    return [
        CreateProjectJob(),
        CopySourceVideoJob(),
        ExtractAudioJob(),
        TranscriptionJob(),
        SpeechDetectionJob(),
        TranslationJob(),
        TimelineGenerationJob(),
    ]


def _require_created_project(context: PipelineContext) -> CreatedProject:
    if context.created_project is None:
        raise RuntimeError("project has not been created")
    return context.created_project


def _update_metadata(context: PipelineContext, updates: dict[str, object]) -> None:
    created = _require_created_project(context)
    context.created_project = context.project_manager.write_project_metadata(created, updates)
