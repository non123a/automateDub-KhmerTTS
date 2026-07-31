from __future__ import annotations

import json

from automatedub.config import ToolConfig
from automatedub_studio.pipeline.jobs import (
    CopySourceVideoJob,
    CreateProjectJob,
    PipelineContext,
    SpeechDetectionJob,
    TimelineGenerationJob,
)
from automatedub_studio.project.loader import load_project
from automatedub_studio.project.manager import NewProjectRequest, ProjectManager
from automatedub_studio.project.timeline_edits import load_timeline_edits


def _context(tmp_path) -> PipelineContext:
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    return PipelineContext(
        request=NewProjectRequest(
            project_name="Khmer Cut",
            project_location=tmp_path,
            video_file=video_file,
            source_language="Chinese",
            target_language="Khmer",
        ),
        project_manager=ProjectManager(),
        tool_config=ToolConfig(),
    )


def test_create_and_copy_jobs_populate_project_structure(tmp_path):
    context = _context(tmp_path)
    progress_events = []

    CreateProjectJob().run(context, lambda value, message="": progress_events.append(value))
    CopySourceVideoJob().run(context, lambda value, message="": progress_events.append(value))

    assert context.created_project is not None
    assert (context.project_path / "source" / "movie.mp4").read_bytes() == b"video"
    metadata = json.loads((context.project_path / "project.json").read_text(encoding="utf-8"))
    assert metadata["source_video"] == "source/movie.mp4"
    assert metadata["editor_video"] == "source/movie.mp4"
    assert progress_events[-1] == 100


def test_speech_detection_job_writes_timing_artifact(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    transcript_path = context.pipeline_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(
            {
                "segments": [
                    {"id": 1, "start": 0.5, "end": 1.25, "text": "你好"},
                    {"id": 2, "start": 2.0, "end": 3.0, "text": "再见"},
                ]
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["transcript"] = transcript_path

    SpeechDetectionJob().run(context, lambda _value, message="": None)

    output_path = context.pipeline_path / "speech_segments.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["segments"] == [
        {"id": 1, "start": 0.5, "end": 1.25},
        {"id": 2, "start": 2.0, "end": 3.0},
    ]


def test_timeline_generation_populates_timeline_directory_and_loader_uses_pipeline_paths(
    tmp_path,
):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    (context.project_path / "tts").mkdir(exist_ok=True)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    translation_path = context.pipeline_path / "translation.json"
    translation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "segments": [
                    {
                        "id": 1,
                        "start": 0.5,
                        "end": 1.25,
                        "source_language": "zh",
                        "target_language": "km",
                        "source_text": "你好",
                        "target_text": "សួស្តី",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["audio"] = audio_path
    context.artifacts["translation"] = translation_path

    TimelineGenerationJob().run(context, lambda _value, message="": None)

    timeline_path = context.project_path / "timeline" / "timeline.edited.json"
    assert timeline_path.is_file()
    timeline = load_timeline_edits(context.project_path)
    assert timeline is not None
    assert timeline.clip_by_id("original:1") is not None
    project = load_project(context.project_path)
    assert project.audio_path == audio_path
    assert project.translation_path == translation_path
