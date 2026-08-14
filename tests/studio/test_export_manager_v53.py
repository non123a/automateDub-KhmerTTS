from __future__ import annotations

import json
from pathlib import Path

import pytest

import automatedub_studio.export.manager as export_manager
from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportEncoderCapabilities,
    ExportResult,
    ExportStreamSummary,
)
from automatedub_studio.export.manager import (
    AudioMode,
    ExportConfiguration,
    ExportLifecycleState,
    ExportManager,
    ExportManagerError,
    ExportPipelineStage,
    SubtitleMode,
    VideoEncodingPreset,
    validate_export_presets,
    verify_export_output,
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
        video_preset=kwargs.get("video_preset", VideoEncodingPreset.COMPATIBLE_H264),
        audio_mode=kwargs.get("audio_mode", AudioMode.MIXED),
        subtitle_mode=kwargs.get("subtitle_mode", SubtitleMode.NONE),
    )


def _renderer(project, _editables, _tool_config, configuration):
    assert project.video_path is not None
    configuration.output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return ExportResult(output_path=configuration.output_path)


def _skip_verification(_tool_config: ToolConfig, _output_path: Path) -> None:
    """Keep orchestration tests independent from a real media fixture."""


def test_export_configuration_builds_mp4_output_path(tmp_path):
    config = ExportConfiguration(output_folder=tmp_path, filename="movie")

    assert config.output_path == tmp_path / "movie.mp4"


def test_export_validation_disables_fastest_for_av1_source(tmp_path):
    project = _project(tmp_path)
    project.source_codec = "av1"

    validations = validate_export_presets(project)

    fastest = validations[VideoEncodingPreset.FASTEST]
    assert not fastest.available
    assert "AV1" in fastest.message
    assert validations[VideoEncodingPreset.COMPATIBLE_H264].available
    assert not validations[VideoEncodingPreset.HIGH_COMPRESSION_H265].available
    assert "Coming Soon" in validations[VideoEncodingPreset.HIGH_COMPRESSION_H265].message


def test_export_validation_disables_original_av1_codec_for_mp4(tmp_path):
    project = _project(tmp_path)
    project.source_codec = "av1"

    validation = validate_export_presets(project)[VideoEncodingPreset.ORIGINAL_CODEC]

    assert not validation.available
    assert "Coming Soon" in validation.message


def test_original_codec_validation_is_unavailable_during_beta(tmp_path):
    project = _project(tmp_path)
    project.source_codec = "av1"
    report = export_manager.ExportCapabilityReport(
        source_video=project.video_path,
        source_streams=ExportStreamSummary(
            1,
            1,
            [{"codec_type": "video", "codec_name": "av1"}],
        ),
        source_container="mp4",
        system=export_manager.ExportSystemCapabilities(
            "ffmpeg test",
            frozenset({"libx264"}),
            frozenset({"mp4"}),
            "libx264",
            None,
        ),
        has_video_edits=False,
        has_audio_edits=False,
        subtitle_mode=SubtitleMode.NONE,
        stream_copy_supported=True,
        stream_copy_reason="FFmpeg verified -c:v copy for this source and MP4 output.",
    )

    validation = validate_export_presets(None, capability_report=report)[
        VideoEncodingPreset.ORIGINAL_CODEC
    ]

    assert not validation.available
    assert "Coming Soon" in validation.message


def test_export_validation_disables_h265_without_a_supported_encoder(tmp_path):
    validations = validate_export_presets(
        _project(tmp_path),
        encoder_capabilities=ExportEncoderCapabilities("libx264", None),
    )

    h265 = validations[VideoEncodingPreset.HIGH_COMPRESSION_H265]
    assert not h265.available
    assert "Coming Soon" in h265.message
    assert validations[VideoEncodingPreset.COMPATIBLE_H264].available


def test_export_manager_reports_all_pipeline_stages_and_writes_metadata(qapp, tmp_path):
    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=_renderer,
        verifier=_skip_verification,
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
    assert payload["configuration"]["video_preset"] == "compatible_h264"
    completed_stages = [event.stage for event in events if event.status == "completed"]
    assert completed_stages == list(ExportPipelineStage)


def test_export_manager_generates_external_subtitles(qapp, tmp_path):
    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path, subtitle_mode=SubtitleMode.EXTERNAL_SRT),
        renderer=_renderer,
        verifier=_skip_verification,
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


def test_export_manager_rechecks_encoder_availability_before_rendering(
    qapp, tmp_path, monkeypatch
):
    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(
            tmp_path,
            codec="h265",
            video_preset=VideoEncodingPreset.HIGH_COMPRESSION_H265,
        ),
        renderer=_renderer,
        verifier=_skip_verification,
    )
    report = export_manager.inspect_export_capabilities(
        manager.project,
        manager.timeline,
        manager.tool_config,
    )
    report = export_manager.ExportCapabilityReport(
        source_video=report.source_video,
        source_streams=report.source_streams,
        source_container=report.source_container,
        system=export_manager.ExportSystemCapabilities(
            "ffmpeg test",
            frozenset({"libx264"}),
            frozenset({"mp4"}),
            "libx264",
            None,
        ),
        has_video_edits=report.has_video_edits,
        has_audio_edits=report.has_audio_edits,
        subtitle_mode=SubtitleMode.NONE,
    )
    monkeypatch.setattr(export_manager, "inspect_export_capabilities", lambda *_args: report)

    with pytest.raises(ExportManagerError, match="Coming Soon"):
        manager.run_sync()

    assert manager.failure is not None
    assert manager.failure.stage == ExportPipelineStage.PREPARE_TIMELINE


def test_verify_export_output_requires_nonempty_file_and_one_video_and_audio_stream(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "dubbed.mp4"
    output_path.write_bytes(b"media")
    monkeypatch.setattr(export_manager, "_resolve_ffprobe", lambda _config: "ffprobe")
    monkeypatch.setattr(
        export_manager,
        "validate_export_streams",
        lambda _ffprobe, _path: ExportStreamSummary(
            1,
            1,
            [{"codec_type": "video"}, {"codec_type": "audio"}],
        ),
    )

    verify_export_output(ToolConfig(), output_path)


@pytest.mark.parametrize("video_streams,audio_streams", [(0, 1), (1, 0), (2, 1), (1, 2)])
def test_verify_export_output_rejects_anything_but_one_video_and_audio_stream(
    tmp_path, monkeypatch, video_streams, audio_streams
):
    output_path = tmp_path / "dubbed.mp4"
    output_path.write_bytes(b"media")
    monkeypatch.setattr(export_manager, "_resolve_ffprobe", lambda _config: "ffprobe")
    monkeypatch.setattr(
        export_manager,
        "validate_export_streams",
        lambda _ffprobe, _path: ExportStreamSummary(video_streams, audio_streams, []),
    )

    with pytest.raises(ExportManagerError, match="verification failed"):
        verify_export_output(ToolConfig(), output_path)


def test_verify_export_output_rejects_missing_or_empty_output(tmp_path):
    output_path = tmp_path / "dubbed.mp4"

    with pytest.raises(ExportManagerError, match="did not produce"):
        verify_export_output(ToolConfig(), output_path)

    output_path.touch()
    with pytest.raises(ExportManagerError, match="empty"):
        verify_export_output(ToolConfig(), output_path)


def test_export_manager_fails_at_verification_before_completion(qapp, tmp_path):
    def failed_verification(_tool_config: ToolConfig, _output_path: Path) -> None:
        raise ExportManagerError("unreadable MP4")

    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=_renderer,
        verifier=failed_verification,
    )
    events = []
    manager.eventEmitted.connect(events.append)

    with pytest.raises(ExportManagerError, match="unreadable MP4"):
        manager.run_sync()

    assert manager.failure is not None
    assert manager.failure.stage == ExportPipelineStage.VERIFY_OUTPUT
    assert not any(
        event.stage == ExportPipelineStage.VERIFY_OUTPUT and event.status == "completed"
        for event in events
    )


def test_cancelled_export_removes_partial_output(qapp, tmp_path):
    manager: ExportManager

    def cancelling_renderer(_project, _editables, _tool_config, configuration):
        configuration.output_path.write_bytes(b"partial")
        manager.cancel()
        raise RuntimeError("ffmpeg stopped")

    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=cancelling_renderer,
    )
    cancelled = []
    manager.exportCancelled.connect(lambda: cancelled.append(True))

    with pytest.raises(ExportManagerError, match="ffmpeg stopped"):
        manager.run_sync()

    assert cancelled == [True]
    assert not manager.configuration.output_path.exists()
    assert manager.state == ExportLifecycleState.CANCELLED


def test_cancel_is_idempotent_and_retry_can_follow_cancel(qapp, tmp_path):
    calls: list[str] = []

    def cancelling_renderer(_project, _editables, _tool_config, _configuration):
        calls.append("cancelled")
        manager.cancel()
        manager.cancel()
        raise RuntimeError("ffmpeg stopped")

    manager = ExportManager(
        project=_project(tmp_path),
        editables={},
        tool_config=ToolConfig(),
        configuration=_config(tmp_path),
        renderer=cancelling_renderer,
    )

    with pytest.raises(ExportManagerError, match="ffmpeg stopped"):
        manager.run_sync()

    assert manager.state == ExportLifecycleState.CANCELLED
    assert calls == ["cancelled"]
