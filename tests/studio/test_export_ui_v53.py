from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QSettings, QSize
from PySide6.QtWidgets import QDialogButtonBox, QRadioButton, QScrollArea

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportEncoderCapabilities,
    ExportResult,
    ExportStreamSummary,
    ExportSystemCapabilities,
)
from automatedub_studio.export.manager import (
    AudioMode,
    ExportCapabilityReport,
    ExportConfiguration,
    ExportEvent,
    ExportLifecycleState,
    ExportManager,
    ExportManagerError,
    ExportPipelineStage,
    ManagedExportResult,
    SubtitleMode,
    VideoEncodingPreset,
)
from automatedub_studio.project.models import Project, Segment
from automatedub_studio.timeline.timeline_clip import (
    VIDEO_TRACK_ID,
    Timeline,
    TimelineClip,
)
from automatedub_studio.ui.export_progress_window import ExportProgressWindow
from automatedub_studio.ui.export_wizard import ExportWizard


def test_export_wizard_builds_configuration(qapp, tmp_path):
    wizard = ExportWizard(tmp_path, "dubbed")
    wizard.audio_mode_combo.setCurrentIndex(0)
    wizard.subtitle_mode_combo.setCurrentIndex(1)

    config = wizard.configuration()

    assert config.output_folder == tmp_path
    assert config.filename == "dubbed"
    assert config.codec == "h264"
    assert config.video_preset == VideoEncodingPreset.COMPATIBLE_H264
    assert config.video_quality == "Balanced"
    assert config.audio_mode == AudioMode.KHMER_ONLY
    assert config.subtitle_mode == SubtitleMode.EXTERNAL_SRT


def test_export_wizard_keeps_action_buttons_outside_scrollable_content(qapp, tmp_path):
    wizard = ExportWizard(tmp_path, "dubbed")

    assert isinstance(wizard.content_scroll, QScrollArea)
    buttons = wizard.findChild(QDialogButtonBox)
    assert buttons is not None
    assert buttons.parentWidget() is wizard
    assert wizard.minimumHeight() <= wizard.height()

    wizard.resize(500, 420)
    wizard.show()
    QCoreApplication.processEvents()
    assert buttons.geometry().bottom() <= wizard.contentsRect().bottom()
    assert wizard.content_scroll.height() > 0


@pytest.mark.parametrize("size", [QSize(480, 420), QSize(640, 520), QSize(1000, 780)])
def test_export_wizard_reflows_content_and_keeps_footer_visible(qapp, tmp_path, size):
    wizard = ExportWizard(tmp_path, "a deliberately long export filename for layout testing")
    wizard.resize(size)
    wizard.show()
    QCoreApplication.processEvents()

    buttons = wizard.export_button.parentWidget()
    assert buttons.geometry().bottom() <= wizard.contentsRect().bottom()
    assert wizard.content_scroll.geometry().bottom() < buttons.geometry().top()
    assert wizard.output_folder_edit.width() > 0
    assert wizard.diagnostics_command_label.wordWrap() is True


def test_export_wizard_persists_last_used_preset(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    wizard = ExportWizard(tmp_path, "dubbed", settings=settings)
    h265_button = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.HIGH_COMPRESSION_H265.value}",
    )
    assert h265_button is not None
    assert not h265_button.isEnabled()
    wizard.quality_combo.setCurrentText("Small File")
    wizard.audio_mode_combo.setCurrentIndex(0)
    wizard.subtitle_mode_combo.setCurrentIndex(1)

    config = wizard.configuration()

    assert config.video_preset == VideoEncodingPreset.COMPATIBLE_H264
    assert config.codec == "h264"
    assert config.video_quality == "Small File"
    assert settings.value("export/video_preset") == "compatible_h264"
    assert settings.value("export/video_quality") == "Small File"

    restored = ExportWizard(tmp_path, "dubbed", settings=settings)

    assert restored._selected_preset() == VideoEncodingPreset.COMPATIBLE_H264
    assert restored._selected_quality() == "Small File"
    assert restored.audio_mode_combo.currentData() == AudioMode.KHMER_ONLY.value
    assert restored.subtitle_mode_combo.currentData() == SubtitleMode.EXTERNAL_SRT.value


def test_export_wizard_updates_live_estimates(qapp, tmp_path):
    wizard = ExportWizard(tmp_path, "dubbed")
    h265_button = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.HIGH_COMPRESSION_H265.value}",
    )
    assert h265_button is not None

    assert not h265_button.isEnabled()
    wizard.quality_combo.setCurrentText("Small File")

    assert wizard.codec_label.text() == "H.264"
    assert wizard.size_label.text() == "Small"
    assert "Excellent" in wizard.compatibility_label.text()
    assert h265_button.text() == "H.265 (HEVC)"


def test_export_wizard_disables_fastest_for_av1_and_explains_why(qapp, tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"video")
    project = Project(
        project_path=tmp_path,
        audio_path=tmp_path / "audio.wav",
        translation_path=tmp_path / "translation.json",
        tts_directory=tmp_path / "tts",
        video_path=video_path,
        source_codec="av1",
    )

    wizard = ExportWizard(
        tmp_path,
        "dubbed",
        project=project,
        timeline=Timeline.default(),
    )
    fastest = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.FASTEST.value}",
    )
    compatible = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.COMPATIBLE_H264.value}",
    )

    assert fastest is not None
    assert compatible is not None
    assert not fastest.isEnabled()
    assert compatible.isEnabled()
    assert "AV1" in wizard.validation_label.text()


def test_export_wizard_disables_stream_copy_when_video_track_has_edits(qapp, tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"video")
    project = Project(
        project_path=tmp_path,
        audio_path=tmp_path / "audio.wav",
        translation_path=tmp_path / "translation.json",
        tts_directory=tmp_path / "tts",
        video_path=video_path,
        source_codec="h264",
    )
    timeline = Timeline.default()
    timeline.add_clip(
        TimelineClip(
            id="video:edit",
            track_id=VIDEO_TRACK_ID,
            start_time=0.0,
            end_time=1.0,
            source_path=video_path,
        )
    )

    wizard = ExportWizard(tmp_path, "dubbed", project=project, timeline=timeline)
    fastest = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.FASTEST.value}",
    )

    assert fastest is not None
    assert not fastest.isEnabled()
    assert "Video edits require re-encoding" in wizard.validation_label.text()


def test_export_wizard_disables_h265_without_an_encoder_and_shows_preview(qapp, tmp_path):
    wizard = ExportWizard(
        tmp_path,
        "dubbed",
        encoder_capabilities=ExportEncoderCapabilities("libx264", None),
    )
    h265 = wizard.findChild(
        QRadioButton,
        f"export_preset_{VideoEncodingPreset.HIGH_COMPRESSION_H265.value}",
    )

    assert h265 is not None
    assert not h265.isEnabled()
    assert "Coming Soon" in wizard.validation_label.text()
    assert wizard.audio_codec_label.text() == "AAC"
    assert wizard.subtitle_preview_label.text() == "None"


def test_export_wizard_explains_subtitle_modes(qapp, tmp_path):
    wizard = ExportWizard(tmp_path, "dubbed")

    wizard.subtitle_mode_combo.setCurrentIndex(1)
    assert "separate subtitle file" in wizard.subtitle_description.text()
    wizard.subtitle_mode_combo.setCurrentIndex(2)
    assert "inside the MP4" in wizard.subtitle_description.text()
    wizard.subtitle_mode_combo.setCurrentIndex(3)
    assert "cannot be disabled" in wizard.subtitle_description.text()


def test_export_wizard_displays_capability_diagnostics(qapp, tmp_path):
    source_video = tmp_path / "source.mp4"
    report = ExportCapabilityReport(
        source_video=source_video,
        source_streams=ExportStreamSummary(
            1,
            1,
            [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "pix_fmt": "yuv420p",
                    "avg_frame_rate": "30000/1001",
                }
            ],
        ),
        source_container="mp4",
        system=ExportSystemCapabilities(
            "ffmpeg version test",
            frozenset({"libx264", "libx265", "h264_videotoolbox"}),
            frozenset({"mp4", "mov"}),
            "h264_videotoolbox",
            "libx265",
        ),
        has_video_edits=False,
        has_audio_edits=True,
        subtitle_mode=SubtitleMode.NONE,
    )

    wizard = ExportWizard(tmp_path, "dubbed", capability_report=report)

    assert "1920x1080" in wizard.diagnostics_source_label.text()
    assert "h264_videotoolbox: available" in wizard.diagnostics_system_label.text()
    assert "H.264 ⭐ Recommended: Available" in wizard.diagnostics_presets_label.text()
    assert "Actual encoder: h264_videotoolbox" in wizard.diagnostics_selected_label.text()
    assert "-c:v h264_videotoolbox" in wizard.diagnostics_command_label.text()


def test_export_wizard_lists_available_and_unavailable_preset_reasons(qapp, tmp_path):
    report = ExportCapabilityReport(
        source_video=tmp_path / "source.mp4",
        source_streams=ExportStreamSummary(
            1,
            1,
            [{"codec_type": "video", "codec_name": "av1"}],
        ),
        source_container="mp4",
        system=ExportSystemCapabilities(
            "ffmpeg version test",
            frozenset({"libx264"}),
            frozenset({"mp4"}),
            "libx264",
            None,
        ),
        has_video_edits=False,
        has_audio_edits=False,
        subtitle_mode=SubtitleMode.NONE,
    )

    wizard = ExportWizard(tmp_path, "dubbed", capability_report=report)

    assert "Available:" in wizard._preset_descriptions[VideoEncodingPreset.COMPATIBLE_H264].text()
    assert "Coming Soon\nComing Soon. H.265" in (
        wizard._preset_descriptions[VideoEncodingPreset.HIGH_COMPRESSION_H265].text()
    )
    assert "Unavailable\n" in wizard._preset_descriptions[VideoEncodingPreset.FASTEST].text()
    assert "Coming Soon" in (
        wizard._preset_descriptions[VideoEncodingPreset.ORIGINAL_CODEC].text()
    )
    assert "Copy Original: Unavailable" in wizard.diagnostics_presets_label.text()
    assert "H.265 (HEVC): Unavailable" in wizard.diagnostics_presets_label.text()


def test_export_progress_window_observes_completion(qapp, tmp_path):
    manager = _export_manager(tmp_path)
    window = ExportProgressWindow(manager)

    result = manager.run_sync()

    assert window.status_label.text() == "Export Complete"
    assert window.progress.value() == 100
    assert window.output_path == result.output_path
    assert window.open_file_button.isEnabled()
    assert window.open_folder_button.isEnabled()
    assert not window.cancel_button.isVisible()
    assert not window.cancel_button.isEnabled()
    assert manager.state == ExportLifecycleState.COMPLETED


def _export_manager(tmp_path) -> ExportManager:
    project_path = tmp_path / "project.autodub"
    project_path.mkdir(exist_ok=True)
    (project_path / "exports").mkdir(exist_ok=True)
    audio_path = project_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    video_path = project_path / "video.mp4"
    video_path.write_bytes(b"video")

    def renderer(_project, _editables, _tool_config, configuration):
        configuration.output_path.write_bytes(b"video")
        return ExportResult(output_path=configuration.output_path)

    return ExportManager(
        project=Project(
            project_path=project_path,
            audio_path=audio_path,
            translation_path=project_path / "translation.json",
            tts_directory=project_path / "tts",
            video_path=video_path,
            segments=[Segment(1, 0.0, 1.0, "source", "target")],
        ),
        editables={},
        tool_config=ToolConfig(),
        configuration=ExportConfiguration(output_folder=tmp_path / "out", filename="dubbed"),
        renderer=renderer,
        verifier=lambda _tool_config, _output_path: None,
    )


def test_export_progress_window_shows_failure_and_allows_retry(qapp, tmp_path):
    project_path = tmp_path / "project.autodub"
    project_path.mkdir()
    (project_path / "exports").mkdir()
    video_path = project_path / "video.mp4"
    video_path.write_bytes(b"video")

    def renderer(_project, _editables, _tool_config, configuration):
        configuration.output_path.write_bytes(b"media")
        return ExportResult(output_path=configuration.output_path)

    def failed_verification(_tool_config, _output_path):
        raise RuntimeError("ffprobe could not read output")

    manager = ExportManager(
        project=Project(
            project_path=project_path,
            audio_path=project_path / "audio.wav",
            translation_path=project_path / "translation.json",
            tts_directory=project_path / "tts",
            video_path=video_path,
        ),
        editables={},
        tool_config=ToolConfig(),
        configuration=ExportConfiguration(output_folder=tmp_path / "out", filename="dubbed"),
        renderer=renderer,
        verifier=failed_verification,
    )
    window = ExportProgressWindow(manager)

    with pytest.raises(ExportManagerError, match="ffprobe could not read output"):
        manager.run_sync()

    assert window.status_label.text() == "Export Failed"
    assert window.retry_button.isEnabled()
    assert window.close_button.isEnabled()
    assert not window.open_file_button.isEnabled()
    assert not window.open_folder_button.isEnabled()
    assert not window.cancel_button.isVisible()


def test_export_progress_window_ignores_stale_run_events(qapp, tmp_path):
    manager = _export_manager(tmp_path)
    window = ExportProgressWindow(manager)
    manager.run_sync()
    completed_job_id = manager._active_job_id
    manager.retry()
    current_job_id = manager._active_job_id
    assert current_job_id > completed_job_id

    window._on_event(
        ExportEvent(
            ExportPipelineStage.ENCODE_VIDEO,
            "progress",
            25,
            "stale update",
            job_id=completed_job_id,
        )
    )

    assert window.status_label.text() == "Starting export..."
    assert window.progress.value() == 0

    window._on_completed(
        ManagedExportResult(
            output_path=tmp_path / "stale.mp4",
            metadata_path=tmp_path / "stale.export.json",
            job_id=completed_job_id,
        )
    )
    assert window.status_label.text() == "Starting export..."


def test_export_progress_window_cancelling_state_disables_cancel(qapp, tmp_path):
    manager = _export_manager(tmp_path)
    window = ExportProgressWindow(manager)
    manager._begin_run()
    manager._set_state(ExportLifecycleState.EXPORTING)
    manager.cancel()

    assert window.status_label.text() == "Cancelling export..."
    assert not window.cancel_button.isEnabled()
    assert window.cancel_button.text() == "Cancelling..."


@pytest.mark.parametrize("size", [QSize(480, 320), QSize(620, 440), QSize(1000, 720)])
def test_export_progress_window_reflows_and_keeps_cancel_visible(qapp, tmp_path, size):
    manager = _export_manager(tmp_path)
    window = ExportProgressWindow(manager)
    window.resize(size)
    window.show()
    QCoreApplication.processEvents()

    assert window.cancel_button.geometry().bottom() <= window.contentsRect().bottom()
    assert window.content_scroll.geometry().bottom() < window.cancel_button.geometry().top()
    assert window.status_label.wordWrap() is True
