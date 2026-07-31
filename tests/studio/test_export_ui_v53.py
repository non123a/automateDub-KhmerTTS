from __future__ import annotations

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import ExportResult
from automatedub_studio.export.manager import (
    AudioMode,
    ExportConfiguration,
    ExportManager,
    SubtitleMode,
)
from automatedub_studio.project.models import Project, Segment
from automatedub_studio.ui.export_progress_window import ExportProgressWindow
from automatedub_studio.ui.export_wizard import ExportWizard


def test_export_wizard_builds_configuration(qapp, tmp_path):
    wizard = ExportWizard(tmp_path, "dubbed")
    wizard.audio_mode_combo.setCurrentIndex(0)
    wizard.subtitle_mode_combo.setCurrentIndex(2)

    config = wizard.configuration()

    assert config.output_folder == tmp_path
    assert config.filename == "dubbed"
    assert config.codec == "h264"
    assert config.audio_mode == AudioMode.KHMER_ONLY
    assert config.subtitle_mode == SubtitleMode.EXTERNAL_SRT


def test_export_progress_window_observes_completion(qapp, tmp_path):
    project_path = tmp_path / "project.autodub"
    project_path.mkdir()
    (project_path / "exports").mkdir()
    audio_path = project_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    video_path = project_path / "video.mp4"
    video_path.write_bytes(b"video")

    def renderer(_project, _editables, _tool_config, configuration):
        configuration.output_path.write_bytes(b"video")
        return ExportResult(output_path=configuration.output_path)

    manager = ExportManager(
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
    )
    window = ExportProgressWindow(manager)

    result = manager.run_sync()

    assert window.status_label.text() == "Export Complete"
    assert window.progress.value() == 100
    assert window.output_path == result.output_path
    assert window.open_folder_button.isEnabled()
