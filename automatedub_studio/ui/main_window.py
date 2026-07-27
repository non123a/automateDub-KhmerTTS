"""Main window for AutomateDub Studio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMainWindow, QMessageBox, QSplitter

from automatedub_studio.inspector.segment_inspector import SegmentInspectorWidget
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.loader import ProjectLoadError, load_project
from automatedub_studio.project.models import Project
from automatedub_studio.timeline.timeline_widget import TimelineWidget
from automatedub_studio.ui.about_dialog import AboutDialog
from automatedub_studio.ui.project_info_panel import ProjectInfoPanel

WINDOW_TITLE = "AutomateDub Studio"
_GEOMETRY_KEY = "main_window/geometry"


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings()
        self.project: Project | None = None

        self.setWindowTitle(WINDOW_TITLE)
        self._build_menu_bar()
        self._build_status_bar()
        self._build_central_widget()
        self._build_info_dock()
        self._build_inspector_dock()
        self._restore_geometry()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        self.open_project_action = QAction("Open Project...", self)
        self.open_project_action.triggered.connect(self._open_project)
        file_menu.addAction(self.open_project_action)

        file_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        help_menu = menu_bar.addMenu("&Help")

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.about_action)

    def _build_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

    def _build_central_widget(self) -> None:
        self.video_player = VideoPlayerWidget()
        self.video_player.playbackStatusChanged.connect(self.statusBar().showMessage)

        self.timeline = TimelineWidget()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.video_player)
        splitter.addWidget(self.timeline)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.video_player.videoPositionChanged.connect(self.timeline.set_playhead_position)
        self.timeline.segmentSelected.connect(self._on_segment_selected)

        self.setCentralWidget(splitter)

    def _build_info_dock(self) -> None:
        self.info_panel = ProjectInfoPanel()

        dock = QDockWidget("Project Info", self)
        dock.setWidget(self.info_panel)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_inspector_dock(self) -> None:
        self.inspector = SegmentInspectorWidget()

        dock = QDockWidget("Segment Inspector", self)
        dock.setWidget(self.inspector)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _on_segment_selected(self, segment) -> None:
        self.inspector.set_segment(segment)

    def _show_about_dialog(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()

    def _open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Project")
        if not directory:
            return
        self.open_project_path(Path(directory))

    def open_project_path(self, project_dir: Path) -> None:
        try:
            project = load_project(project_dir)
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Failed to Open Project", str(exc))
            return

        self._apply_loaded_project(project)

    def _apply_loaded_project(self, project: Project) -> None:
        self.project = project
        self.setWindowTitle(f"{WINDOW_TITLE} - {project.project_path.name}")
        self.info_panel.set_project(project)
        self.video_player.load_video(project.video_path)
        self.timeline.load_segments(project.segments)
        self.inspector.set_segment(None)
        self.statusBar().showMessage(self._status_message(project))

    @staticmethod
    def _status_message(project: Project) -> str:
        video_status = "Found" if project.has_video else "Missing"
        return (
            "Project Loaded  |  "
            f"Segments: {project.segment_count}  |  "
            f"TTS Files: {project.tts_file_count}  |  "
            "Audio: ✓  |  "
            f"Video: {video_status}"
        )

    def _restore_geometry(self) -> None:
        geometry = self._settings.value(_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)
