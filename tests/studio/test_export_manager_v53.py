from __future__ import annotations

import json
from pathlib import Path

import pytest

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import ExportResult
from automatedub_studio.export.manager import (
    AudioMode,
    ExportConfiguration,
    ExportManager,
    ExportManagerError,
    ExportPipelineStage,
    SubtitleMode,
)
from automatedub_studio.project.models import Project, Segment


def _project(tmp_path: Path) -> Project:
    project_path = tmp_path / "project.autodub"
    project_path.mkdir()
    (project_path / "exports").mkdir()
    audio_path = project_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    video_path = project_path / "video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    tts_dir = project_path / "tts"
    tts_dir.mkdir()
    segments = [
        Segment(
            id=1,
            start=1.0,
            end=2.5,
            source_text="source",
            target_text="target subtitle",
        )
    ]
    return Project(
        project_path=project_path,
        audio_path=audio_path,
        translation_path=project_path / "translation.json",
        tts_directory=tts_dir,
        video_path=video_path,
        segments=segments,
    )


def _config(tmp_path: Path, **kwargs) -> ExportConfiguration:
    return ExportConfiguration(
        output_folder=tmp_path / "out",
        filename="dubbed",
        video_quality=kwargs.get("video_quality", "High"),
        codec=kwargs.get("codec", "h264"),
        audio_mode=kwargs.get("audio_mode", AudioMode.MIXED),
        subtitle_mode=kwargs.get("subtitle_mode", SubtitleMode.NONE),
    )


def _renderer(project, _editables, _tool_config, configuration):
    assert project.video_path is not None
    configuration.output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return ExportResult(output_path=configuration.output_path)


def test_export_configuration_builds_mp4_output_path(tmp_path):
    config = ExportConfiguration(output_folder=tmp_path, filename="movie")

    assert config.output_path == tmp_path / "movie.mp4"


def test_export_manager_reports_all_pipeline_stages_and_writes_metadata(qapp, tmp_path):
    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=_renderer,
    )
    events = []
    manager.eventEmitted.connect(events.append)

    result = manager.run_sync()

    assert result.output_path == tmp_path / "out" / "dubbed.mp4"
    assert result.output_path.is_file()
    assert result.metadata_path == tmp_path / "project.autodub" / "exports" / "dubbed.export.json"
    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert payload["configuration"]["audio_mode"] == "mixed"
    assert payload["configuration"]["codec"] == "h264"
    completed_stages = [event.stage for event in events if event.status == "completed"]
    assert completed_stages == list(ExportPipelineStage)


def test_export_manager_generates_external_subtitles(qapp, tmp_path):
    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path, subtitle_mode=SubtitleMode.EXTERNAL_SRT),
        renderer=_renderer,
    )

    result = manager.run_sync()

    assert result.subtitle_path == tmp_path / "out" / "dubbed.srt"
    assert result.subtitle_path.is_file()
    text = result.subtitle_path.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:02,500" in text
    assert "target subtitle" in text


def test_export_manager_stops_and_reports_failed_stage(qapp, tmp_path):
    def failing_renderer(_project, _editables, _tool_config, _configuration):
        raise RuntimeError("encode failed")

    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=failing_renderer,
    )

    with pytest.raises(ExportManagerError):
        manager.run_sync()

    assert manager.failure is not None
    assert manager.failure.stage == ExportPipelineStage.ENCODE_VIDEO
    assert "encode failed" in manager.failure.error
