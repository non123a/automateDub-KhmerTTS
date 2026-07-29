"""Main window for AutomateDub Studio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from automatedub.config import ToolConfig, load_tool_config
from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.backend.export_service import (
    ExportError,
    ExportOptions,
    build_export_speech_tracks,
)
from automatedub_studio.backend.export_worker import ExportJob, ExportRunner
from automatedub_studio.backend.jobs import JobRunner, RegenerationJob
from automatedub_studio.backend.regeneration_service import (
    RegenerationOutcome,
    select_all_ids,
    select_changed_ids,
    select_failed_ids,
    select_selected_ids,
)
from automatedub_studio.edit.commands import (
    ClipClipboard,
    MultiOffsetChangeCommand,
    OffsetChangeCommand,
    PasteSegmentsCommand,
    PropertyChangeCommand,
    SplitSegmentCommand,
    TrimSegmentCommand,
)
from automatedub_studio.inspector.segment_inspector import SegmentInspectorWidget
from automatedub_studio.playback.playback_controller import PlaybackController, PlaybackMode
from automatedub_studio.playback.video_player import VideoPlayerWidget
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.edits import apply_edits, save_edits
from automatedub_studio.project.loader import (
    ProjectLoadError,
    count_tts_files,
    load_project,
    save_video_selection,
)
from automatedub_studio.project.models import Project
from automatedub_studio.timeline.clip_item import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_NEEDS_REGENERATION,
)
from automatedub_studio.timeline.ruler_widget import DEFAULT_SNAP_INTERVAL_MS
from automatedub_studio.timeline.timeline_widget import TimelineWidget
from automatedub_studio.ui.about_dialog import AboutDialog
from automatedub_studio.ui.export_dialog import ExportProgressDialog
from automatedub_studio.ui.project_info_panel import ProjectInfoPanel

WINDOW_TITLE = "AutomateDub Studio"
_GEOMETRY_KEY = "main_window/geometry"


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: QSettings | None = None,
        parent=None,
        tool_config: ToolConfig | None = None,
    ):
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings()
        self.project: Project | None = None
        self._editables: dict[int, EditableSegment] = {}
        self._undo_stack = QUndoStack(self)
        self._tool_config = tool_config if tool_config is not None else load_tool_config()
        self._job_runner = JobRunner()
        self._export_runner = ExportRunner()
        self._export_dialog: ExportProgressDialog | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._regen_completed = 0
        self._regen_total = 0
        self._regen_errors: list[str] = []
        self._clipboard = ClipClipboard()

        self.setWindowTitle(WINDOW_TITLE)
        self._build_menu_bar()
        self._build_toolbar()
        self._build_status_bar()
        self._build_central_widget()
        self._build_info_dock()
        self._build_inspector_dock()
        self._restore_geometry()
        self._update_regenerate_actions()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        self.open_project_action = QAction("Open Project...", self)
        self.open_project_action.triggered.connect(self._open_project)
        file_menu.addAction(self.open_project_action)

        self.save_project_action = QAction("Save Project", self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_action.setEnabled(False)
        self.save_project_action.triggered.connect(self._save_project)
        file_menu.addAction(self.save_project_action)

        file_menu.addSeparator()

        self.export_video_action = QAction("Export Video...", self)
        self.export_video_action.setEnabled(False)
        self.export_video_action.triggered.connect(self._export_video)
        file_menu.addAction(self.export_video_action)

        file_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        edit_menu = menu_bar.addMenu("&Edit")
        self.undo_action = self._undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = self._undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.copy_clip_action = QAction("Copy Clips", self)
        self.copy_clip_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_clip_action.triggered.connect(self._copy_selected_clips)
        edit_menu.addAction(self.copy_clip_action)

        self.paste_clip_action = QAction("Paste Clips", self)
        self.paste_clip_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.paste_clip_action.triggered.connect(self._paste_clipboard)
        edit_menu.addAction(self.paste_clip_action)

        self.duplicate_clip_action = QAction("Duplicate Clips", self)
        self.duplicate_clip_action.setShortcut("Ctrl+D")
        self.duplicate_clip_action.triggered.connect(self._duplicate_selected_clips)
        edit_menu.addAction(self.duplicate_clip_action)

        edit_menu.addSeparator()

        self.split_clip_action = QAction("Split Clip", self)
        self.split_clip_action.setShortcut("S")
        self.split_clip_action.triggered.connect(self._split_selected_clip)
        edit_menu.addAction(self.split_clip_action)

        help_menu = menu_bar.addMenu("&Help")
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Regenerate", self)
        toolbar.setObjectName("regenerate_toolbar")
        self.addToolBar(toolbar)

        self.regenerate_selected_action = QAction("Regenerate Selected", self)
        self.regenerate_selected_action.triggered.connect(self._regenerate_selected)
        toolbar.addAction(self.regenerate_selected_action)

        self.regenerate_changed_action = QAction("Regenerate Changed", self)
        self.regenerate_changed_action.triggered.connect(self._regenerate_selected_changed)
        toolbar.addAction(self.regenerate_changed_action)

        self.regenerate_failed_action = QAction("Regenerate Failed", self)
        self.regenerate_failed_action.triggered.connect(self._regenerate_failed)
        toolbar.addAction(self.regenerate_failed_action)

        self.regenerate_all_action = QAction("Regenerate All", self)
        self.regenerate_all_action.triggered.connect(self._regenerate_all)
        toolbar.addAction(self.regenerate_all_action)

        toolbar.addSeparator()

        self.snap_action = QAction("Snap: OFF", self)
        self.snap_action.setCheckable(True)
        self.snap_action.setToolTip(f"Snap clip drags to {DEFAULT_SNAP_INTERVAL_MS} ms")
        self.snap_action.toggled.connect(self._on_snap_toggled)
        toolbar.addAction(self.snap_action)

    def _build_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

    def _build_central_widget(self) -> None:
        self.video_player = VideoPlayerWidget()
        self.video_player.playbackStatusChanged.connect(self.statusBar().showMessage)
        self.playback_controller = PlaybackController(self.video_player, self)

        self.mode_selector = QComboBox()
        for mode, label in (
            (PlaybackMode.ORIGINAL, "Original"),
            (PlaybackMode.MIXED, "Mixed"),
            (PlaybackMode.KHMER_TTS, "Khmer TTS"),
            (PlaybackMode.TIMELINE_PREVIEW, "Timeline Preview"),
        ):
            self.mode_selector.addItem(label, mode)
        self.mode_selector.currentIndexChanged.connect(self._on_mode_selector_changed)

        mode_bar = QWidget()
        mode_bar_layout = QHBoxLayout(mode_bar)
        mode_bar_layout.setContentsMargins(4, 4, 4, 4)
        mode_bar_layout.addWidget(QLabel("Audio:"))
        mode_bar_layout.addWidget(self.mode_selector)
        mode_bar_layout.addStretch(1)

        self.timeline = TimelineWidget()
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(mode_bar)
        video_layout.addWidget(self.video_player, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(video_container)
        splitter.addWidget(self.timeline)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.video_player.videoPositionChanged.connect(self.timeline.set_playhead_position)
        self.timeline.segmentSelected.connect(self._on_segment_selected)
        self.timeline.segmentsSelected.connect(self._on_segments_selected)
        self.timeline.segmentOffsetChanged.connect(self._on_offset_live)
        self.timeline.segmentOffsetCommitted.connect(self._on_offset_committed)
        self.timeline.segmentsOffsetCommitted.connect(self._on_offsets_committed)
        self.timeline.segmentTrimChanged.connect(self._on_trim_live)
        self.timeline.segmentTrimCommitted.connect(self._on_trim_committed)
        self.timeline.clipPlayRequested.connect(self._on_clip_play_requested)

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
        self.inspector.speedChanged.connect(self._on_speed_changed)
        self.inspector.volumeChanged.connect(self._on_volume_changed)
        self.inspector.fadeInChanged.connect(self._on_fade_in_changed)
        self.inspector.fadeOutChanged.connect(self._on_fade_out_changed)
        self.inspector.lockedChanged.connect(self._on_locked_changed)
        self.inspector.regenerateRequested.connect(self._regenerate_ids)

        dock = QDockWidget("Segment Inspector", self)
        dock.setWidget(self.inspector)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # ------------------------------------------------------------------
    # Signal handlers — timeline
    # ------------------------------------------------------------------

    def _on_mode_selector_changed(self, index: int) -> None:
        mode = self.mode_selector.itemData(index)
        if mode is not None:
            self.playback_controller.set_mode(mode)

    def _on_snap_toggled(self, enabled: bool) -> None:
        self.snap_action.setText("Snap: ON" if enabled else "Snap: OFF")
        self.timeline.set_snap_enabled(enabled)

    def _on_clip_play_requested(self, segment_id: int) -> None:
        """Timeline double-click: audition a single TTS clip in isolation."""
        if self.project is None:
            return
        clip_path = tts_segment_output_path(self.project.tts_directory, segment_id)
        if clip_path.exists():
            self.playback_controller.play_clip(clip_path)

    def _on_segment_selected(self, segment) -> None:
        self._update_regenerate_actions()

    def _on_segments_selected(self, segments: list) -> None:
        self.inspector.set_segments(segments, self._editables)
        self._update_regenerate_actions()

    def _on_offset_live(self, _segment_id: int, offset_ms: int) -> None:
        selected = self.timeline.selected_segments
        if len(selected) > 1:
            self.inspector.set_segments(selected, self._editables)
        else:
            self.inspector.refresh_offset(offset_ms)

    def _on_offset_committed(
        self, segment_id: int, old_offset_ms: int, new_offset_ms: int
    ) -> None:
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        cmd = OffsetChangeCommand(
            segment, old_offset_ms, new_offset_ms, apply_cb=self._apply_offset
        )
        self._undo_stack.push(cmd)

    def _on_offsets_committed(
        self, old_offsets_ms: dict[int, int], new_offsets_ms: dict[int, int]
    ) -> None:
        segments = [
            segment
            for segment_id in new_offsets_ms
            if (segment := self._find_segment(segment_id)) is not None
        ]
        if not segments:
            return
        cmd = MultiOffsetChangeCommand(
            segments,
            old_offsets_ms,
            new_offsets_ms,
            apply_cb=self._apply_offset,
        )
        self._undo_stack.push(cmd)

    def _on_trim_live(
        self, _segment_id: int, _start_seconds: float, _end_seconds: float
    ) -> None:
        selected = self.timeline.selected_segments
        if len(selected) == 1:
            self.inspector.set_segment(selected[0], self._editables.get(selected[0].id))

    def _on_trim_committed(
        self,
        segment_id: int,
        old_start: float,
        old_end: float,
        new_start: float,
        new_end: float,
    ) -> None:
        if abs(old_start - new_start) < 1e-9 and abs(old_end - new_end) < 1e-9:
            return
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        cmd = TrimSegmentCommand(
            segment,
            old_start,
            old_end,
            new_start,
            new_end,
            apply_cb=self._apply_trim,
        )
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Signal handlers — inspector properties
    # ------------------------------------------------------------------

    def _on_speed_changed(self, old_val: float, new_val: float) -> None:
        self._push_property_command("speed", old_val, new_val)

    def _on_volume_changed(self, old_val: float, new_val: float) -> None:
        self._push_property_command("volume", old_val, new_val)

    def _on_fade_in_changed(self, old_val: int, new_val: int) -> None:
        self._push_property_command("fade_in_ms", old_val, new_val)

    def _on_fade_out_changed(self, old_val: int, new_val: int) -> None:
        self._push_property_command("fade_out_ms", old_val, new_val)

    def _on_locked_changed(self, old_val: bool, new_val: bool) -> None:
        self._push_property_command("locked", old_val, new_val)

    def _push_property_command(self, field: str, old_val: Any, new_val: Any) -> None:
        seg = self.timeline.selected_segment
        if seg is None:
            return
        cmd = PropertyChangeCommand(
            seg.id, field, old_val, new_val, apply_cb=self._apply_property
        )
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Apply callbacks
    # ------------------------------------------------------------------

    def _apply_offset(self, segment_id: int, offset_ms: int) -> None:
        self.timeline.apply_offset(segment_id, offset_ms)
        selected = self.timeline.selected_segments
        if len(selected) > 1 and any(segment.id == segment_id for segment in selected):
            self.inspector.set_segments(selected, self._editables)
        elif selected and selected[0].id == segment_id:
            self.inspector.refresh_offset(offset_ms)
        self._refresh_playback_sources()

    def _apply_property(self, segment_id: int, field: str, value: Any) -> None:
        es = self._editables.setdefault(segment_id, EditableSegment(id=segment_id))
        setattr(es, field, value)
        if field == "locked":
            self.timeline.apply_locked(segment_id, value)
            self._update_regenerate_actions()
        seg = self.timeline.selected_segment
        if seg is not None and seg.id == segment_id:
            self.inspector.refresh_property(field, value)
        self._refresh_playback_sources()

    def _apply_trim(self, segment_id: int, start_seconds: float, end_seconds: float) -> None:
        self.timeline.apply_trim(segment_id, start_seconds, end_seconds)
        selected = self.timeline.selected_segments
        if len(selected) == 1 and selected[0].id == segment_id:
            self.inspector.set_segment(selected[0], self._editables.get(segment_id))
        self._refresh_playback_sources()

    def _apply_structural_timeline_edit(
        self, selected_ids: list[int] | None = None, flash: bool = False
    ) -> None:
        if self.project is None:
            return
        self.timeline.load_segments(
            self.project.segments,
            audio_path=self.project.audio_path,
            tts_directory=self.project.tts_directory,
        )
        for seg_id, es in self._editables.items():
            if es.locked:
                self.timeline.apply_locked(seg_id, True)
            elif es.last_error is not None:
                self.timeline.apply_status(seg_id, STATUS_FAILED)
            elif es.needs_regeneration:
                self.timeline.apply_status(seg_id, STATUS_NEEDS_REGENERATION)
        selected_ids = selected_ids or []
        if selected_ids:
            self.timeline.select_segment_ids(selected_ids)
            if flash:
                self.timeline.flash_segment_ids(selected_ids)
        else:
            self.inspector.set_segment(None)
        self._update_regenerate_actions()
        self._refresh_playback_sources()

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------

    def _find_segment(self, segment_id: int):
        if self.project is None:
            return None
        for seg in self.project.segments:
            if seg.id == segment_id:
                return seg
        return None

    # ------------------------------------------------------------------
    # Regenerate actions
    # ------------------------------------------------------------------

    def _update_regenerate_actions(self) -> None:
        has_project = self.project is not None
        busy = self._job_runner.is_running
        selected_ids = self._selected_segment_ids()
        changed_ids = (
            select_changed_ids(self.project.segments, self._editables) if has_project else []
        )
        failed_ids = (
            select_failed_ids(self.project.segments, self._editables) if has_project else []
        )
        all_ids = select_all_ids(self.project.segments, self._editables) if has_project else []

        self.regenerate_selected_action.setEnabled(not busy and bool(selected_ids))
        self.regenerate_changed_action.setEnabled(not busy and bool(changed_ids))
        self.regenerate_failed_action.setEnabled(not busy and bool(failed_ids))
        self.regenerate_all_action.setEnabled(not busy and bool(all_ids))

    def _selected_segment_ids(self) -> list[int]:
        return select_selected_ids(
            [segment.id for segment in self.timeline.selected_segments], self._editables
        )

    def _regenerate_selected(self) -> None:
        self._start_regeneration(self._selected_segment_ids())

    def _regenerate_selected_changed(self) -> None:
        if self.project is None:
            return
        self._start_regeneration(select_changed_ids(self.project.segments, self._editables))

    def _regenerate_failed(self) -> None:
        if self.project is None:
            return
        self._start_regeneration(select_failed_ids(self.project.segments, self._editables))

    def _regenerate_all(self) -> None:
        if self.project is None:
            return
        ids = select_all_ids(self.project.segments, self._editables)
        if not ids:
            return
        confirm = QMessageBox.question(
            self,
            "Regenerate All",
            f"Regenerate all {len(ids)} segment(s)? This will call the TTS provider "
            "for every unlocked segment in the project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._start_regeneration(ids)

    def _regenerate_ids(self, *segment_ids: int) -> None:
        self._start_regeneration(list(segment_ids))

    def _copy_selected_clips(self) -> None:
        selected = self.timeline.selected_segments
        if not selected:
            return
        self._clipboard.replace(selected, self._editables)

    def _paste_clipboard(self) -> None:
        if self.project is None or self._clipboard.is_empty:
            return
        self._paste_segments(
            self._clipboard.segments,
            self._clipboard.editables,
            self.timeline.playhead_ms / 1000.0,
        )

    def _duplicate_selected_clips(self) -> None:
        if self.project is None:
            return
        selected = self.timeline.selected_segments
        if not selected:
            return
        source_editables = {
            segment.id: self._editables[segment.id]
            for segment in selected
            if segment.id in self._editables
        }
        paste_start = max(segment.end for segment in selected)
        self._paste_segments(selected, source_editables, paste_start)

    def _paste_segments(
        self,
        source_segments: list,
        source_editables: dict[int, EditableSegment],
        paste_start_seconds: float,
    ) -> None:
        if self.project is None or not source_segments:
            return
        new_ids = self._next_segment_ids(len(source_segments))
        cmd = PasteSegmentsCommand(
            self.project.segments,
            source_segments,
            paste_start_seconds,
            new_ids,
            self._editables,
            source_editables,
            self.project.tts_directory,
            apply_cb=self._apply_structural_timeline_edit,
        )
        self._undo_stack.push(cmd)

    def _split_selected_clip(self) -> None:
        if self.project is None:
            return
        selected = self.timeline.selected_segments
        if len(selected) != 1:
            return
        segment = selected[0]
        split_seconds = self.timeline.playhead_ms / 1000.0
        if not (segment.start < split_seconds < segment.end):
            return
        new_segment_id = max((item.id for item in self.project.segments), default=-1) + 1
        cmd = SplitSegmentCommand(
            self.project.segments,
            segment,
            split_seconds,
            new_segment_id,
            self._editables,
            apply_cb=self._apply_structural_timeline_edit,
        )
        self._undo_stack.push(cmd)

    def _next_segment_ids(self, count: int) -> list[int]:
        if self.project is None:
            return []
        start = max((item.id for item in self.project.segments), default=-1) + 1
        return list(range(start, start + count))

    def _start_regeneration(self, segment_ids: list[int]) -> None:
        if self.project is None or not segment_ids or self._job_runner.is_running:
            return

        for seg_id in segment_ids:
            self.timeline.apply_status(seg_id, STATUS_GENERATING)

        self._regen_completed = 0
        self._regen_total = len(segment_ids)
        self._regen_errors = []

        self._progress_dialog = QProgressDialog(
            "Regenerating segment...", "Cancel", 0, self._regen_total, self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.canceled.connect(self._cancel_regeneration)
        self._progress_dialog.setValue(0)

        job = RegenerationJob(
            self.project.segments,
            self._editables,
            self.project.tts_directory,
            self._tool_config,
            segment_ids,
        )
        job.signals.started.connect(self._on_regen_started)
        job.signals.resultReady.connect(self._on_regen_result)
        job.signals.finished.connect(self._on_regen_finished)
        self._job_runner.submit(job)
        self._update_regenerate_actions()

    def _cancel_regeneration(self) -> None:
        self._job_runner.cancel()

    def _on_regen_started(self, segment_id: int) -> None:
        if self._progress_dialog is not None:
            remaining = self._regen_total - self._regen_completed
            self._progress_dialog.setLabelText(
                f"Regenerating segment {segment_id}...  "
                f"Completed: {self._regen_completed}  Remaining: {remaining}"
            )
        seg = self.timeline.selected_segment
        if seg is not None and seg.id == segment_id:
            self.inspector.set_generating(True)

    def _on_regen_result(self, outcome: RegenerationOutcome) -> None:
        es = self._editables.setdefault(outcome.segment_id, EditableSegment(id=outcome.segment_id))
        if outcome.success:
            es.needs_regeneration = False
            es.last_error = None
            es.generated_duration = outcome.duration_seconds
            self.timeline.apply_status(outcome.segment_id, None)
        else:
            es.last_error = outcome.error
            self._regen_errors.append(f"Segment {outcome.segment_id}: {outcome.error}")
            self.timeline.apply_status(outcome.segment_id, STATUS_FAILED)

        self._regen_completed += 1
        if self._progress_dialog is not None:
            self._progress_dialog.setValue(self._regen_completed)

        seg = self.timeline.selected_segment
        if seg is not None and seg.id == outcome.segment_id:
            self.inspector.set_generating(False)
            self.inspector.refresh_status()

    def _on_regen_finished(self, outcomes: list[RegenerationOutcome]) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

        if self.project is not None:
            self.project.tts_file_count = count_tts_files(self.project.tts_directory)
            self.statusBar().showMessage(self._status_message(self.project))

        if self._regen_errors:
            QMessageBox.warning(
                self,
                "Regeneration Errors",
                f"{len(self._regen_errors)} segment(s) failed:\n"
                + "\n".join(self._regen_errors),
            )

        self._update_regenerate_actions()
        self._refresh_playback_sources()

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
        if project.video_candidates:
            names = [p.name for p in project.video_candidates]
            choice, ok = QInputDialog.getItem(
                self,
                "Choose Video File",
                "Multiple video files were found in this project. Choose which one to use:",
                names,
                0,
                False,
            )
            if ok and choice:
                chosen_path = project.project_path / choice
                save_video_selection(project.project_path, chosen_path)
                project.video_path = chosen_path
                project.video_candidates = []
        self._apply_loaded_project(project)

    def _apply_loaded_project(self, project: Project) -> None:
        self.project = project
        self._editables = {}
        apply_edits(project.segments, project.project_path, self._editables)
        self._undo_stack.clear()
        self.save_project_action.setEnabled(True)
        self.export_video_action.setEnabled(True)
        self.setWindowTitle(f"{WINDOW_TITLE} - {project.project_path.name}")
        self.info_panel.set_project(project)
        self.video_player.load_video(project.video_path)
        self.timeline.load_segments(
            project.segments,
            audio_path=project.audio_path,
            tts_directory=project.tts_directory,
        )
        for seg_id, es in self._editables.items():
            if es.locked:
                self.timeline.apply_locked(seg_id, True)
            elif es.last_error is not None:
                self.timeline.apply_status(seg_id, STATUS_FAILED)
            elif es.needs_regeneration:
                self.timeline.apply_status(seg_id, STATUS_NEEDS_REGENERATION)
        self.inspector.set_segment(None)
        self.statusBar().showMessage(self._status_message(project))
        self._update_regenerate_actions()
        self._refresh_playback_sources()

    def _refresh_playback_sources(self) -> None:
        """Recompute Timeline Preview tracks and mixed/Khmer sources.

        Called after loading a project and after any edit (offset/speed/
        volume/fade/regeneration) so Timeline Preview always reflects the
        current `EditableSegment` state without ever re-mixing or exporting.
        """
        if self.project is None:
            self.playback_controller.set_sources(None, None, [])
            return
        try:
            timeline_tracks = build_export_speech_tracks(
                self.project.segments,
                self._editables,
                self.project.tts_directory,
                self._tool_config,
            )
        except ExportError:
            timeline_tracks = []
        self.playback_controller.set_sources(
            self.project.mixed_audio_path, self.project.tts_combined_path, timeline_tracks
        )

    def _save_project(self) -> None:
        if self.project is None:
            return
        save_edits(self.project.segments, self.project.project_path, self._editables)
        self.statusBar().showMessage("Project saved.")

    def _export_video(self) -> None:
        if self.project is None:
            return
        default_name = f"{self.project.project_path.name}_dubbed.mp4"
        output_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Video",
            str(self.project.project_path / default_name),
            "MP4 Video (*.mp4)",
        )
        if not output_path_str:
            return
        output_path = Path(output_path_str)

        self._export_dialog = ExportProgressDialog(self)
        job = ExportJob(
            project=self.project,
            editables=self._editables,
            tool_config=self._tool_config,
            options=ExportOptions(output_path=output_path),
        )
        job.signals.stageChanged.connect(self._export_dialog.on_stage_changed)
        job.signals.finished.connect(self._on_export_finished)
        job.signals.errorOccurred.connect(self._on_export_error)
        self._export_runner.submit(job)

        self._export_dialog.exec()

    def _on_export_finished(self, result) -> None:
        if self._export_dialog is not None:
            self._export_dialog.on_finished(result)
        self.statusBar().showMessage(f"Export complete: {result.output_path.name}")

    def _on_export_error(self, message: str) -> None:
        if self._export_dialog is not None:
            self._export_dialog.on_error(message)
        self.statusBar().showMessage(f"Export failed: {message}")

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
