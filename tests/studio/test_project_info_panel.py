from __future__ import annotations

from conftest import make_valid_project

from automatedub_studio.project.loader import load_project
from automatedub_studio.ui.project_info_panel import ProjectInfoPanel


def test_info_panel_starts_with_placeholders(qapp):
    panel = ProjectInfoPanel()

    assert panel.project_path_label.text() == "—"
    assert panel.segment_count_label.text() == "—"


def test_info_panel_displays_loaded_project(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=6, with_video=True)
    project = load_project(project_dir)
    panel = ProjectInfoPanel()

    panel.set_project(project)

    assert panel.project_path_label.text() == str(project_dir)
    assert panel.audio_label.text() == str(project.audio_path)
    assert panel.translation_label.text() == str(project.translation_path)
    assert panel.tts_directory_label.text() == str(project.tts_directory)
    assert panel.segment_count_label.text() == "6"
    assert panel.tts_count_label.text() == "6"
    assert panel.video_label.text() == str(project.video_path)


def test_info_panel_reset_to_placeholders(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path)
    project = load_project(project_dir)
    panel = ProjectInfoPanel()
    panel.set_project(project)

    panel.set_project(None)

    assert panel.project_path_label.text() == "—"
    assert panel.video_label.text() == "—"
