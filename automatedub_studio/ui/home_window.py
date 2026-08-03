"""Home window for AutomateDub Studio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.pipeline.manager import PipelineManager
from automatedub_studio.project.assets import MissingAssetRecovery
from automatedub_studio.project.loader import VIDEO_EXTENSIONS
from automatedub_studio.project.manager import ProjectManager
from automatedub_studio.project.recent_projects import (
    RecentProjectsManager,
    default_recent_projects_path,
)
from automatedub_studio.project.session import (
    SessionRecoveryManager,
    default_session_state_path,
)
from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.settings.manager import SettingsManager
from automatedub_studio.ui.about_dialog import AboutDialog
from automatedub_studio.ui.first_run_wizard import FirstRunWizard
from automatedub_studio.ui.new_project_wizard import NewProjectWizard
from automatedub_studio.ui.notifications import NotificationCenter
from automatedub_studio.ui.processing_window import ProcessingWindow
from automatedub_studio.ui.project_browser import ProjectBrowserWindow
from automatedub_studio.ui.settings_window import SettingsWindow


class HomeWindow(QMainWindow):
    """Application entry window for Studio workflows."""

    openProjectRequested = Signal(object)
    newProjectFromVideoRequested = Signal(object)

    def __init__(
        self,
        project_manager: ProjectManager | None = None,
        settings_manager: SettingsManager | None = None,
        recent_projects_manager: RecentProjectsManager | None = None,
        session_recovery_manager: SessionRecoveryManager | None = None,
        notification_center: NotificationCenter | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_manager = project_manager if project_manager is not None else ProjectManager()
        self.settings_manager = (
            settings_manager if settings_manager is not None else SettingsManager()
        )
        self.recent_projects_manager = recent_projects_manager or RecentProjectsManager(
            default_recent_projects_path()
        )
        self.session_recovery_manager = session_recovery_manager or SessionRecoveryManager(
            default_session_state_path()
        )
        self.notification_center = notification_center or NotificationCenter(self)
        self.asset_recovery = MissingAssetRecovery()
        self.processing_windows: list[ProcessingWindow] = []
        self.pipeline_managers: list[PipelineManager] = []
        self.settings_windows: list[SettingsWindow] = []
        self.project_browser_windows: list[ProjectBrowserWindow] = []

        self.setWindowTitle("AutomateDub Studio")
        self.setAcceptDrops(True)
        central = QWidget(self)
        layout = QVBoxLayout(central)

        title = QLabel("<b>AutomateDub Studio</b>")
        title.setObjectName("home_title")
        layout.addWidget(title)

        self.new_project_button = QPushButton("New Project")
        self.new_project_button.setObjectName("new_project_button")
        self.new_project_button.clicked.connect(lambda _checked=False: self._new_project())
        layout.addWidget(self.new_project_button)

        self.open_project_button = QPushButton("Open Project")
        self.open_project_button.setObjectName("open_project_button")
        self.open_project_button.clicked.connect(self._open_project)
        layout.addWidget(self.open_project_button)

        self.recent_projects_label = QLabel("Recent Projects")
        self.recent_projects_label.setObjectName("recent_projects_placeholder")
        layout.addWidget(self.recent_projects_label)
        self.recent_selected_label = QLabel("Select a recent project to manage it.")
        self.recent_selected_label.setObjectName("recent_selected_label")
        layout.addWidget(self.recent_selected_label)
        self.recent_projects_list = QListWidget()
        self.recent_projects_list.setObjectName("recent_projects_list")
        self.recent_projects_list.itemDoubleClicked.connect(self._open_recent_project)
        self.recent_projects_list.itemSelectionChanged.connect(self._update_recent_action_state)
        self.recent_projects_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.recent_projects_list)

        self.recent_empty_label = QLabel("No recent projects yet.")
        self.recent_empty_label.setObjectName("recent_empty_label")
        layout.addWidget(self.recent_empty_label)

        self.recent_actions_widget = QWidget()
        recent_actions = QHBoxLayout(self.recent_actions_widget)
        recent_actions.setContentsMargins(0, 0, 0, 0)
        self.pin_recent_button = QPushButton("Pin")
        self.pin_recent_button.clicked.connect(self._pin_selected_recent_project)
        recent_actions.addWidget(self.pin_recent_button)
        self.remove_recent_button = QPushButton("Remove")
        self.remove_recent_button.clicked.connect(self._remove_selected_recent_project)
        recent_actions.addWidget(self.remove_recent_button)
        self.open_recent_folder_button = QPushButton("Open Folder")
        self.open_recent_folder_button.clicked.connect(self._open_selected_recent_folder)
        recent_actions.addWidget(self.open_recent_folder_button)
        self.project_browser_button = QPushButton("Project Browser")
        self.project_browser_button.clicked.connect(self._show_project_browser)
        recent_actions.addWidget(self.project_browser_button)
        layout.addWidget(self.recent_actions_widget)

        self.session_recovery_label = QLabel("")
        self.session_recovery_label.setObjectName("session_recovery_label")
        layout.addWidget(self.session_recovery_label)

        self.notification_label = QLabel("")
        self.notification_label.setObjectName("notification_label")
        layout.addWidget(self.notification_label)
        self.notification_center.notificationPosted.connect(self._show_notification)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("settings_button")
        self.settings_button.clicked.connect(self._show_settings)
        layout.addWidget(self.settings_button)

        self.about_button = QPushButton("About")
        self.about_button.setObjectName("about_button")
        self.about_button.clicked.connect(self._show_about)
        layout.addWidget(self.about_button)
        layout.addStretch(1)

        self.setCentralWidget(central)
        self._refresh_recent_projects()
        self._refresh_session_recovery()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        path = self._first_dropped_path(event.mimeData())
        if path is not None and self._is_supported_drop(path):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        path = self._first_dropped_path(event.mimeData())
        if path is None:
            event.ignore()
            return
        if path.suffix.lower() == ".autodub":
            self._open_project_path(path)
            event.acceptProposedAction()
            return
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self.newProjectFromVideoRequested.emit(path)
            self._new_project(video_path=path)
            event.acceptProposedAction()
            return
        event.ignore()

    def open_path(self, path: Path) -> bool:
        path = Path(path).expanduser()
        if path.suffix.lower() == ".autodub":
            self._open_project_path(path)
            return True
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self._new_project(video_path=path)
            return True
        return False

    def maybe_show_first_run_wizard(self) -> None:
        if self.settings_manager.data.first_run_completed:
            return
        wizard = FirstRunWizard(self.settings_manager, self)
        wizard.exec()

    def _new_project(self, video_path: Path | None = None) -> None:
        wizard = NewProjectWizard(self)
        if video_path is not None:
            wizard.details_page.video_file_edit.setText(str(video_path))
            if not wizard.details_page.project_name_edit.text().strip():
                wizard.details_page.project_name_edit.setText(video_path.stem)
            default_folder = self.settings_manager.data.default_project_folder
            if default_folder and not wizard.details_page.location_edit.text().strip():
                wizard.details_page.location_edit.setText(default_folder)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return

        pipeline_manager = PipelineManager(
            wizard.request(),
            project_manager=self.project_manager,
            provider_manager=ProviderManager(self.settings_manager.tool_config()),
            tool_config=self.settings_manager.tool_config(),
        )
        processing_window = ProcessingWindow(pipeline_manager)
        processing_window.openEditorRequested.connect(self.openProjectRequested.emit)
        self.pipeline_managers.append(pipeline_manager)
        self.processing_windows.append(processing_window)
        processing_window.show()
        pipeline_manager.start()

    def _open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Project")
        if directory:
            self._open_project_path(Path(directory))

    def _show_settings(self) -> None:
        window = SettingsWindow(self.settings_manager, parent=self)
        self.settings_windows.append(window)
        window.show()

    def _show_about(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()

    def _open_project_path(self, project_path: Path) -> None:
        self.recent_projects_manager.add_project(project_path)
        self.session_recovery_manager.mark_open(project_path)
        missing = self.asset_recovery.missing_assets(project_path)
        if missing:
            self.notification_center.warning(
                f"Missing asset: {missing[0].description} ({missing[0].path})"
            )
        self._refresh_recent_projects()
        self.openProjectRequested.emit(project_path)

    def _refresh_recent_projects(self) -> None:
        self.recent_projects_list.clear()
        projects = self.recent_projects_manager.list_projects()
        if not projects:
            self.recent_projects_label.setText("Recent Projects")
            self.recent_selected_label.setText("No recent projects selected.")
            self.recent_projects_list.setVisible(False)
            self.recent_empty_label.setVisible(True)
            self.recent_actions_widget.setVisible(False)
            self._set_recent_action_enabled(False)
            return
        self.recent_projects_label.setText("Recent Projects")
        self.recent_projects_list.setVisible(True)
        self.recent_empty_label.setVisible(False)
        self.recent_actions_widget.setVisible(True)
        for project in projects:
            prefix = "Pinned - " if project.pinned else ""
            item = QListWidgetItem(
                f"{prefix}{project.name} | {project.status} | Last opened: {project.last_opened}"
            )
            item.setToolTip(str(project.project_path))
            item.setData(0x0100, str(project.project_path))
            self.recent_projects_list.addItem(item)
        self.recent_projects_list.setCurrentRow(0)
        self._update_recent_action_state()

    def _selected_recent_path(self) -> Path | None:
        item = self.recent_projects_list.currentItem()
        if item is None:
            return None
        value = item.data(0x0100)
        return Path(value) if isinstance(value, str) else None

    def _open_recent_project(self, _item=None) -> None:
        path = self._selected_recent_path()
        if path is not None:
            self._open_project_path(path)

    def _pin_selected_recent_project(self) -> None:
        path = self._selected_recent_path()
        if path is None:
            return
        self.recent_projects_manager.pin_project(path, True)
        self._refresh_recent_projects()

    def _remove_selected_recent_project(self) -> None:
        path = self._selected_recent_path()
        if path is None:
            return
        self.recent_projects_manager.remove_project(path)
        self._refresh_recent_projects()

    def _open_selected_recent_folder(self) -> None:
        path = self._selected_recent_path()
        if path is None:
            return
        folder = self.recent_projects_manager.containing_folder(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_project_browser(self) -> None:
        path = self._selected_recent_path()
        if path is None:
            return
        window = ProjectBrowserWindow(path, parent=self)
        self.project_browser_windows.append(window)
        window.show()

    def _refresh_session_recovery(self) -> None:
        snapshot = self.session_recovery_manager.recoverable_session()
        if snapshot is None:
            self.session_recovery_label.setText("")
            return
        self.session_recovery_label.setText(
            f"Recover previous session: {snapshot.project_path}"
        )

    def _show_notification(self, notification) -> None:
        self.notification_label.setText(f"{notification.level}: {notification.message}")

    def _update_recent_action_state(self) -> None:
        has_selection = self._selected_recent_path() is not None
        self._set_recent_action_enabled(has_selection)
        if has_selection:
            item = self.recent_projects_list.currentItem()
            if item is not None:
                self.recent_selected_label.setText(f"Selected project: {item.text()}")
            return
        if self.recent_projects_list.count() == 0:
            self.recent_selected_label.setText("No recent projects yet.")
        else:
            self.recent_selected_label.setText("Select a recent project to manage it.")

    def _set_recent_action_enabled(self, enabled: bool) -> None:
        self.pin_recent_button.setEnabled(enabled)
        self.remove_recent_button.setEnabled(enabled)
        self.open_recent_folder_button.setEnabled(enabled)
        self.project_browser_button.setEnabled(enabled)

    @staticmethod
    def _first_dropped_path(mime_data) -> Path | None:
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if url.isLocalFile():
                return Path(url.toLocalFile())
        return None

    @staticmethod
    def _is_supported_drop(path: Path) -> bool:
        return path.suffix.lower() == ".autodub" or path.suffix.lower() in VIDEO_EXTENSIONS
