from __future__ import annotations

from automatedub_studio.app import create_initial_window
from automatedub_studio.pipeline.manager import PipelineManager
from automatedub_studio.project.manager import NewProjectRequest
from automatedub_studio.ui.home_window import HomeWindow
from automatedub_studio.ui.main_window import MainWindow
from automatedub_studio.ui.new_project_wizard import NewProjectWizard
from automatedub_studio.ui.processing_window import ProcessingWindow


def test_initial_window_is_home_window(qapp):
    window = create_initial_window()

    assert isinstance(window, HomeWindow)
    assert not isinstance(window, MainWindow)
    assert window.new_project_button.text() == "New Project"
    assert window.open_project_button.text() == "Open Project"
    assert window.settings_button.text() == "Settings"
    assert window.about_button.text() == "About"
    assert "Recent Projects" in window.recent_projects_label.text()


def test_new_project_wizard_collects_project_request(qapp, tmp_path):
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    wizard = NewProjectWizard()
    page = wizard.details_page

    page.project_name_edit.setText("Khmer Cut")
    page.location_edit.setText(str(tmp_path))
    page.video_file_edit.setText(str(video_file))
    page.source_language_combo.setCurrentText("Chinese")
    page.target_language_combo.setCurrentText("Khmer")

    request = wizard.request()

    assert page.isComplete()
    assert request.project_name == "Khmer Cut"
    assert request.project_location == tmp_path
    assert request.video_file == video_file
    assert request.source_language == "Chinese"
    assert request.target_language == "Khmer"


def test_new_project_wizard_summary_page(qapp, tmp_path):
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    wizard = NewProjectWizard()
    wizard.details_page.project_name_edit.setText("Khmer Cut")
    wizard.details_page.location_edit.setText(str(tmp_path))
    wizard.details_page.video_file_edit.setText(str(video_file))

    wizard.summary_page.initializePage()

    summary = wizard.summary_page.summary_label.text()
    assert "Project Name: Khmer Cut" in summary
    assert f"Project Folder: {tmp_path / 'Khmer Cut.autodub'}" in summary
    assert f"Video File: {video_file}" in summary


def test_processing_window_shows_placeholder_stages(qapp, tmp_path):
    manager = PipelineManager(
        NewProjectRequest(
            project_name="Khmer Cut",
            project_location=tmp_path,
            video_file=tmp_path / "movie.mp4",
            source_language="Chinese",
            target_language="Khmer",
        )
    )
    window = ProcessingWindow(manager)

    stage_text = [label.text() for label in window.stage_labels.values()]

    assert stage_text == [
        "Create Project",
        "Copy Source Video",
        "Extract Audio",
        "Transcription",
        "Speech Detection",
        "Translation",
        "Generating Khmer Speech",
        "Timeline Generation",
    ]
