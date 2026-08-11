from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

from automatedub_studio.app import startup_paths
from automatedub_studio.project.assets import MissingAssetRecovery
from automatedub_studio.project.browser import ProjectBrowser
from automatedub_studio.project.recent_projects import RecentProjectsManager
from automatedub_studio.project.session import SessionRecoveryManager
from automatedub_studio.settings.manager import SettingsManager
from automatedub_studio.ui.home_window import HomeWindow
from automatedub_studio.ui.new_project_wizard import NewProjectWizard


def _project(path: Path, name: str = "Demo", source_video: str = "source/movie.mp4") -> Path:
    path.mkdir()
    (path / "source").mkdir()
    (path / "exports").mkdir()
    metadata = {
        "project_name": name,
        "created_at": "2026-01-01T00:00:00Z",
        "source_video": source_video,
        "editor_video": source_video,
        "pipeline": {"status": "ready"},
    }
    (path / "project.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_recent_project_persistence_pin_remove_and_folder(tmp_path):
    project_a = _project(tmp_path / "a.autodub", "A")
    project_b = _project(tmp_path / "b.autodub", "B")
    manager = RecentProjectsManager(tmp_path / "recent.json")

    manager.add_project(project_a, opened_at="2026-01-01T00:00:00Z")
    manager.add_project(project_b, opened_at="2026-01-02T00:00:00Z")
    manager.pin_project(project_a, True)

    reloaded = RecentProjectsManager(tmp_path / "recent.json")
    projects = reloaded.list_projects()

    assert [project.name for project in projects] == ["A", "B"]
    assert projects[0].pinned
    assert projects[0].status == "ready"
    assert reloaded.containing_folder(project_a) == tmp_path

    reloaded.remove_project(project_a)

    assert [project.project_path for project in reloaded.list_projects()] == [project_b]


def test_home_recent_project_actions_disable_until_selected(qapp, tmp_path):
    project = _project(tmp_path / "recent.autodub", "Recent")
    recent_manager = RecentProjectsManager(tmp_path / "recent.json")
    recent_manager.add_project(project, opened_at="2026-01-01T00:00:00Z")
    window = HomeWindow(
        settings_manager=SettingsManager(settings_path=tmp_path / "settings.json"),
        recent_projects_manager=recent_manager,
        session_recovery_manager=SessionRecoveryManager(tmp_path / "session.json"),
    )

    window.recent_projects_list.setCurrentRow(-1)
    window._update_recent_action_state()

    assert not window.pin_recent_button.isEnabled()
    assert not window.remove_recent_button.isEnabled()
    assert not window.open_recent_folder_button.isEnabled()
    assert not window.project_browser_button.isEnabled()
    assert window.recent_selected_label.text() == "Select a recent project to manage it."

    window.recent_projects_list.setCurrentRow(0)
    window._update_recent_action_state()

    assert window.pin_recent_button.isEnabled()
    assert window.remove_recent_button.isEnabled()
    assert window.open_recent_folder_button.isEnabled()
    assert window.project_browser_button.isEnabled()
    assert "Selected project:" in window.recent_selected_label.text()


def test_home_shows_empty_recent_state(qapp, tmp_path):
    window = HomeWindow(
        settings_manager=SettingsManager(settings_path=tmp_path / "settings.json"),
        recent_projects_manager=RecentProjectsManager(tmp_path / "recent.json"),
        session_recovery_manager=SessionRecoveryManager(tmp_path / "session.json"),
    )

    assert window.recent_empty_label.text() == (
        "No recent projects yet. Create a project or open an existing project to begin."
    )
    assert not window.pin_recent_button.isEnabled()
    assert not window.recent_actions_widget.isVisible()
    assert not window.recent_projects_list.isVisible()


def test_home_opens_dropped_autodub_project(qapp, tmp_path):
    project = _project(tmp_path / "drop.autodub")
    window = HomeWindow(
        settings_manager=SettingsManager(settings_path=tmp_path / "settings.json"),
        recent_projects_manager=RecentProjectsManager(tmp_path / "recent.json"),
        session_recovery_manager=SessionRecoveryManager(tmp_path / "session.json"),
    )
    opened: list[Path] = []
    window.openProjectRequested.connect(opened.append)

    event = _DropEvent(project)
    window.dropEvent(event)

    assert event.accepted
    assert opened == [project]
    assert window.recent_projects_manager.list_projects()[0].project_path == project


def test_home_drop_video_starts_new_project_workflow(qapp, tmp_path):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"video")
    window = HomeWindow(
        settings_manager=SettingsManager(settings_path=tmp_path / "settings.json"),
        recent_projects_manager=RecentProjectsManager(tmp_path / "recent.json"),
        session_recovery_manager=SessionRecoveryManager(tmp_path / "session.json"),
    )
    requested: list[Path] = []
    window.newProjectFromVideoRequested.connect(requested.append)
    window._new_project = lambda video_path=None: None

    event = _DropEvent(video)
    window.dropEvent(event)

    assert event.accepted
    assert requested == [video]


def test_new_project_button_ignores_qt_checked_payload(qapp, tmp_path):
    window = HomeWindow(
        settings_manager=SettingsManager(settings_path=tmp_path / "settings.json"),
        recent_projects_manager=RecentProjectsManager(tmp_path / "recent.json"),
        session_recovery_manager=SessionRecoveryManager(tmp_path / "session.json"),
    )
    called: list[bool] = []

    def fake_new_project() -> None:
        called.append(True)

    window._new_project = fake_new_project

    window.new_project_button.click()

    assert called == [True]


def test_new_project_wizard_emits_complete_changed_without_warning(qapp):
    wizard = NewProjectWizard()
    spy = _SignalSpy(wizard.details_page.completeChanged)

    wizard.details_page.project_name_edit.setText("Demo")
    wizard.details_page.location_edit.setText("/tmp")
    wizard.details_page.video_file_edit.setText("/tmp/video.mp4")

    assert spy.count >= 3


def test_session_recovery_detects_unclean_session(tmp_path):
    manager = SessionRecoveryManager(tmp_path / "session.json")
    project = tmp_path / "project.autodub"
    autosave = tmp_path / "autosave.json"

    manager.mark_open(project, autosave)

    assert manager.has_unclean_session()
    snapshot = manager.recoverable_session()
    assert snapshot is not None
    assert snapshot.project_path == project
    assert snapshot.autosave_path == autosave

    manager.mark_clean()

    assert not manager.has_unclean_session()
    assert manager.recoverable_session() is None


def test_missing_asset_recovery_detects_and_relinks_source(tmp_path):
    project = _project(tmp_path / "missing.autodub", source_video="source/missing.mp4")
    recovery = MissingAssetRecovery()
    replacement = project / "source" / "replacement.mp4"
    replacement.write_bytes(b"video")

    missing = recovery.missing_assets(project)

    assert [item.key for item in missing] == ["source_video", "editor_video"]

    recovery.relink_source_video(project, replacement)
    metadata = json.loads((project / "project.json").read_text(encoding="utf-8"))

    assert recovery.missing_assets(project) == []
    assert metadata["source_video"] == "source/replacement.mp4"
    assert metadata["editor_video"] == "source/replacement.mp4"


def test_project_browser_details_and_actions(tmp_path):
    project = _project(tmp_path / "browser.autodub", "Browser")
    (project / "exports" / "export.json").write_text("{}", encoding="utf-8")
    browser = ProjectBrowser()

    details = browser.details(project)

    assert details.name == "Browser"
    assert details.status == "ready"
    assert len(details.export_history) == 1

    renamed = browser.rename_project(project, "Renamed")
    duplicated = browser.duplicate_project(renamed, new_name="Copy")
    archived = browser.archive_project(duplicated, archive_root=tmp_path / "archive")

    assert renamed.name == "Renamed.autodub"
    assert archived.parent == tmp_path / "archive"
    assert browser.details(renamed).name == "Renamed"
    assert browser.details(archived).name == "Copy"

    browser.delete_project(archived)

    assert not archived.exists()


def test_startup_paths_exposes_file_association_arguments():
    paths = startup_paths(["studio", "/tmp/project.autodub", "--flag", "/tmp/movie.mp4"])

    assert paths == [Path("/tmp/project.autodub"), Path("/tmp/movie.mp4")]


class _DropEvent:
    def __init__(self, path: Path):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        self._mime = mime
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _SignalSpy:
    def __init__(self, signal):
        self.count = 0
        signal.connect(self._increment)

    def _increment(self, *_args) -> None:
        self.count += 1
