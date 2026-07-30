"""Main window for AutomateDub Studio."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
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
from automatedub_studio.backend.export_service import ExportOptions
from automatedub_studio.backend.export_worker import ExportJob, ExportRunner
from automatedub_studio.backend.jobs import ClipRegenerationJob, JobRunner, RegenerationJob
from automatedub_studio.backend.regeneration_service import (
    ClipRegenerationOutcome,
    RegenerationOutcome,
    select_all_ids,
    select_changed_ids,
    select_failed_ids,
    select_selected_ids,
)
from automatedub_studio.backend.video_proxy_job import VideoProxyJob
from automatedub_studio.edit.commands import (
    ClipClipboard,
    MultiTimelineClipOffsetChangeCommand,
    MultiTimelineClipPropertyChangeCommand,
    PasteSegmentsCommand,
    SplitSegmentCommand,
    TimelineClipOffsetChangeCommand,
    TimelineClipPropertyChangeCommand,
    TimelineClipTrimCommand,
)
from automatedub_studio.inspector.segment_inspector import SegmentInspectorWidget
from automatedub_studio.playback.playback_controller import PlaybackController
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
from automatedub_studio.project.timeline_edits import (
    load_timeline_edits,
    save_timeline_edits,
)
from automatedub_studio.project.video_proxy import PROXY_REQUIRED_CODECS
from automatedub_studio.timeline.clip_item import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_NEEDS_REGENERATION,
)
from automatedub_studio.timeline.ruler_widget import DEFAULT_SNAP_INTERVAL_MS
from automatedub_studio.timeline.state import TimelinePlaybackState
from automatedub_studio.timeline.timeline_clip import (
    DRAFT_REGENERATION_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    TimelineClip,
)
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
        self._video_proxy_dialog: QProgressDialog | None = None
        self._video_proxy_job: VideoProxyJob | None = None
        self._regen_completed = 0
        self._regen_total = 0
        self._regen_errors: list[str] = []
        self._clipboard = ClipClipboard()
        self._restoring_inspector_selection = False

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

        edit_menu.addSeparator()

        self.play_pause_action = QAction("Play/Pause", self)
        self.play_pause_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self.play_pause_action.triggered.connect(self._toggle_play_pause)
        edit_menu.addAction(self.play_pause_action)

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

        toolbar.addSeparator()

        self.mute_original_track_action = QAction("Mute Original Audio", self)
        self.mute_original_track_action.setCheckable(True)
        self.mute_original_track_action.toggled.connect(self._on_mute_original_track_toggled)
        toolbar.addAction(self.mute_original_track_action)

        self.mute_khmer_track_action = QAction("Mute Khmer TTS", self)
        self.mute_khmer_track_action.setCheckable(True)
        self.mute_khmer_track_action.toggled.connect(self._on_mute_khmer_track_toggled)
        toolbar.addAction(self.mute_khmer_track_action)

        self.mute_selected_action = QAction("Mute Selected", self)
        self.mute_selected_action.triggered.connect(self._mute_selected_clips)
        toolbar.addAction(self.mute_selected_action)

        self.mute_paint_action = QAction("Mute Paint Mode", self)
        self.mute_paint_action.setCheckable(True)
        self.mute_paint_action.toggled.connect(self._on_mute_paint_toggled)
        toolbar.addAction(self.mute_paint_action)

    def _build_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

    def _build_central_widget(self) -> None:
        self.video_player = VideoPlayerWidget()
        self.video_player.playbackStatusChanged.connect(self._on_playback_status_changed)
        self.playback_controller = PlaybackController(self.video_player, self)

        self.timeline = TimelineWidget()
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self.video_player, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(video_container)
        splitter.addWidget(self.timeline)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.video_player.videoPositionChanged.connect(self.timeline.set_playhead_position)
        self.timeline.timelineSeekRequested.connect(self._on_timeline_seek_requested)
        self.timeline.segmentSelected.connect(self._on_segment_selected)
        self.timeline.segmentsSelected.connect(self._on_segments_selected)
        self.timeline.timelineClipsSelected.connect(self._on_timeline_clips_selected)
        self.timeline.segmentOffsetChanged.connect(self._on_offset_live)
        self.timeline.segmentOffsetCommitted.connect(self._on_offset_committed)
        self.timeline.segmentsOffsetCommitted.connect(self._on_offsets_committed)
        self.timeline.segmentTrimChanged.connect(self._on_trim_live)
        self.timeline.segmentTrimCommitted.connect(self._on_trim_committed)
        self.timeline.clipPlayRequested.connect(self._on_clip_play_requested)
        self.timeline.clipMutePaintRequested.connect(self._on_clip_mute_paint_requested)
        self.timeline.timelineChanged.connect(self._refresh_playback_sources)

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
        self.inspector.regenerateRequested.connect(self._regenerate_ids)
        self.inspector.clipVolumeChanged.connect(self._on_clip_volume_changed)
        self.inspector.clipMutedChanged.connect(self._on_clip_muted_changed)
        self.inspector.clipFadeInChanged.connect(self._on_clip_fade_in_changed)
        self.inspector.clipFadeOutChanged.connect(self._on_clip_fade_out_changed)
        self.inspector.clipLockedChanged.connect(self._on_clip_locked_changed)
        self.inspector.clipTranslationSaveRequested.connect(
            self._on_clip_translation_save_requested
        )
        self.inspector.clipSaveRequested.connect(self._on_clip_save_requested)
        self.inspector.clipRegenerateRequested.connect(self._regenerate_timeline_clip)

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

    def _on_snap_toggled(self, enabled: bool) -> None:
        self.snap_action.setText("Snap: ON" if enabled else "Snap: OFF")
        self.timeline.set_snap_enabled(enabled)

    def _toggle_play_pause(self) -> None:
        self.playback_controller.toggle_play_pause()

    def _on_timeline_seek_requested(self, position_ms: int) -> None:
        self.playback_controller.seek(position_ms)

    def _on_playback_status_changed(self, status: str) -> None:
        if status == "Playing":
            self.timeline.state.playback_state = TimelinePlaybackState.PLAYING
        elif status == "Paused":
            self.timeline.state.playback_state = TimelinePlaybackState.PAUSED
        elif status == "Stopped":
            self.timeline.state.playback_state = TimelinePlaybackState.STOPPED
        self.statusBar().showMessage(status)

    def _on_mute_original_track_toggled(self, muted: bool) -> None:
        self.timeline.set_track_muted(ORIGINAL_AUDIO_TRACK_ID, muted)
        self.playback_controller.set_original_muted(muted)

    def _on_mute_khmer_track_toggled(self, muted: bool) -> None:
        self.timeline.set_track_muted(KHMER_TTS_TRACK_ID, muted)
        self.playback_controller.set_khmer_muted(muted)

    def _on_mute_paint_toggled(self, enabled: bool) -> None:
        self.timeline.set_mute_paint_mode(enabled)

    def _on_clip_mute_paint_requested(self, clip_id: str) -> None:
        clip = next((item for item in self.timeline.timeline_clips if item.id == clip_id), None)
        if clip is None:
            return
        self._push_clip_property_command(clip.id, "muted", clip.muted, not clip.muted)

    def _mute_selected_clips(self) -> None:
        selected = self.timeline.selected_timeline_clips
        if not selected:
            return
        old_values = {clip.id: clip.muted for clip in selected}
        new_values = {clip.id: not clip.muted for clip in selected}
        cmd = MultiTimelineClipPropertyChangeCommand(
            "muted", old_values, new_values, apply_cb=self._apply_clip_property
        )
        self._undo_stack.push(cmd)

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
        self._update_regenerate_actions()

    def _on_timeline_clips_selected(self, clips: list) -> None:
        if not hasattr(self.inspector, "_stack"):
            return
        if self._restoring_inspector_selection:
            self._restoring_inspector_selection = False
        elif not self._resolve_pending_inspector_edits():
            previous = self.inspector._timeline_clip
            if previous is not None:
                self._restoring_inspector_selection = True
                self.timeline.select_timeline_clip_ids([previous.id])
            return
        try:
            self.inspector.set_timeline_clips(clips)
        except RuntimeError:
            return

    def _on_offset_live(self, _clip_id: str, offset_ms: int) -> None:
        selected = self.timeline.selected_timeline_clips
        if len(selected) > 1:
            self.inspector.set_timeline_clips(selected)
        else:
            self.inspector.refresh_offset(offset_ms)

    def _on_offset_committed(
        self, segment_id: str, old_offset_ms: int, new_offset_ms: int
    ) -> None:
        cmd = TimelineClipOffsetChangeCommand(
            segment_id, old_offset_ms, new_offset_ms, apply_cb=self._apply_clip_offset
        )
        self._undo_stack.push(cmd)

    def _on_offsets_committed(
        self, old_offsets_ms: dict[str, int], new_offsets_ms: dict[str, int]
    ) -> None:
        if not new_offsets_ms:
            return
        cmd = MultiTimelineClipOffsetChangeCommand(
            old_offsets_ms,
            new_offsets_ms,
            apply_cb=self._apply_clip_offset,
        )
        self._undo_stack.push(cmd)

    def _on_trim_live(
        self, _clip_id: str, _start_seconds: float, _end_seconds: float
    ) -> None:
        selected = self.timeline.selected_timeline_clips
        if len(selected) == 1:
            self.inspector.set_timeline_clip(selected[0])

    def _on_trim_committed(
        self,
        segment_id: str,
        old_start: float,
        old_end: float,
        new_start: float,
        new_end: float,
    ) -> None:
        if abs(old_start - new_start) < 1e-9 and abs(old_end - new_end) < 1e-9:
            return
        cmd = TimelineClipTrimCommand(
            segment_id,
            old_start,
            old_end,
            new_start,
            new_end,
            apply_cb=self._apply_clip_trim,
        )
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Signal handlers — inspector properties
    # ------------------------------------------------------------------

    def _on_clip_volume_changed(self, clip_id: str, old_val: float, new_val: float) -> None:
        self._push_clip_property_command(clip_id, "volume", old_val, new_val)

    def _on_clip_muted_changed(self, clip_id: str, old_val: bool, new_val: bool) -> None:
        self._push_clip_property_command(clip_id, "muted", old_val, new_val)

    def _on_clip_fade_in_changed(self, clip_id: str, old_val: int, new_val: int) -> None:
        self._push_clip_property_command(clip_id, "fade_in_ms", old_val, new_val)

    def _on_clip_fade_out_changed(self, clip_id: str, old_val: int, new_val: int) -> None:
        self._push_clip_property_command(clip_id, "fade_out_ms", old_val, new_val)

    def _on_clip_locked_changed(self, clip_id: str, old_val: bool, new_val: bool) -> None:
        self._push_clip_property_command(clip_id, "locked", old_val, new_val)

    def _on_clip_translation_save_requested(self, clip_id: str, khmer_text: str) -> None:
        self.timeline.set_timeline_clip_translation(clip_id, khmer_text)
        self._refresh_playback_sources()

    def _on_clip_save_requested(
        self, clip_id: str, khmer_text: str, speaking_rate: float
    ) -> None:
        self.timeline.set_timeline_clip_translation(clip_id, khmer_text)
        self.timeline.set_timeline_clip_speaking_rate(clip_id, speaking_rate)
        if self.project is not None:
            save_timeline_edits(self.timeline.timeline, self.project.project_path)
        self._refresh_playback_sources()

    def _push_clip_property_command(
        self, clip_id: str, field: str, old_val: Any, new_val: Any
    ) -> None:
        cmd = TimelineClipPropertyChangeCommand(
            clip_id, field, old_val, new_val, apply_cb=self._apply_clip_property
        )
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Apply callbacks
    # ------------------------------------------------------------------

    def _apply_clip_offset(self, clip_id: str, offset_ms: int) -> None:
        self.timeline.apply_timeline_clip_offset(clip_id, offset_ms)
        selected = self.timeline.selected_timeline_clips
        if len(selected) > 1 and any(clip.id == clip_id for clip in selected):
            self.inspector.set_timeline_clips(selected)
        elif selected and selected[0].id == clip_id:
            self.inspector.refresh_offset(offset_ms)
        self._refresh_playback_sources()

    def _apply_clip_property(self, clip_id: str, field: str, value: Any) -> None:
        refresh_field = field
        refresh_value = value
        if field == "volume":
            self.timeline.set_timeline_clip_volume(clip_id, value)
        elif field == "muted":
            self.timeline.set_timeline_clip_muted(clip_id, value)
        elif field == "fade_in_ms":
            self.timeline.set_timeline_clip_fade_in(clip_id, value)
            refresh_field = "fade_in"
            refresh_value = value / 1000.0
        elif field == "fade_out_ms":
            self.timeline.set_timeline_clip_fade_out(clip_id, value)
            refresh_field = "fade_out"
            refresh_value = value / 1000.0
        elif field == "locked":
            self.timeline.set_timeline_clip_locked(clip_id, value)
            self._update_regenerate_actions()
        else:
            return
        selected = self.timeline.selected_timeline_clips
        if len(selected) > 1 and any(clip.id == clip_id for clip in selected):
            self.inspector.set_timeline_clips(selected)
        elif len(selected) == 1 and selected[0].id == clip_id:
            self.inspector.refresh_timeline_clip_property(refresh_field, refresh_value)
        self._refresh_playback_sources()

    def _apply_clip_trim(self, clip_id: str, start_seconds: float, end_seconds: float) -> None:
        self.timeline.apply_timeline_clip_trim(clip_id, start_seconds, end_seconds)
        selected = self.timeline.selected_timeline_clips
        if len(selected) == 1 and selected[0].id == clip_id:
            self.inspector.set_timeline_clip(selected[0])
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
        self._seed_timeline_clips_from_import_editables()
        selected_ids = selected_ids or []
        if selected_ids:
            self.timeline.select_segment_ids(selected_ids)
            if flash:
                self.timeline.flash_segment_ids(selected_ids)
        else:
            self.inspector.set_timeline_clip(None)
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
        has_project = self.project is not None and hasattr(self.project, "segments")
        busy = self._job_runner.is_running
        selected_ids = self._selected_segment_ids()
        changed_ids = (
            select_changed_ids(self.project.segments, self._editables) if has_project else []
        )
        failed_ids = (
            select_failed_ids(self.project.segments, self._editables) if has_project else []
        )
        all_ids = select_all_ids(self.project.segments, self._editables) if has_project else []

        self.regenerate_selected_action.setEnabled(
            not busy and bool(selected_ids) and not self.inspector.has_unsaved_changes
        )
        self.regenerate_changed_action.setEnabled(not busy and bool(changed_ids))
        self.regenerate_failed_action.setEnabled(not busy and bool(failed_ids))
        self.regenerate_all_action.setEnabled(not busy and bool(all_ids))

    def _selected_segment_ids(self) -> list[int]:
        selected_ids = [
            clip.segment_id
            for clip in self.timeline.selected_timeline_clips
            if clip.segment_id is not None
        ]
        return select_selected_ids(
            list(dict.fromkeys(selected_ids)), self._editables
        )

    def _regenerate_selected(self) -> None:
        selected_clips = self.timeline.selected_timeline_clips
        if len(selected_clips) == 1 and selected_clips[0].track_id == KHMER_TTS_TRACK_ID:
            self._regenerate_timeline_clip(selected_clips[0].id)
            return
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

    def _regenerate_timeline_clip(self, clip_id: str) -> None:
        if self.project is None or self._job_runner.is_running:
            return
        if self.inspector.has_unsaved_changes:
            return
        clip = next((item for item in self.timeline.timeline_clips if item.id == clip_id), None)
        if clip is None or clip.locked or clip.source_path is None:
            return
        self.timeline.set_timeline_clip_status(clip.id, STATUS_GENERATING)
        self.inspector.set_generating(True)
        job = ClipRegenerationJob(clip, self.project.tts_directory, self._tool_config)
        job.signals.resultReady.connect(self._on_clip_regen_result)
        job.signals.finished.connect(self._on_clip_regen_finished)
        self._job_runner.submit(job)
        self._update_regenerate_actions()

    def _copy_selected_clips(self) -> None:
        selected = self._selected_segments_from_timeline_clips()
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
        selected = self._selected_segments_from_timeline_clips()
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
        selected = self._selected_segments_from_timeline_clips()
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

    def _selected_segments_from_timeline_clips(self) -> list:
        if self.project is None:
            return []
        selected_ids = [
            clip.segment_id
            for clip in self.timeline.selected_timeline_clips
            if clip.segment_id is not None
        ]
        unique_ids = set(selected_ids)
        return [
            segment for segment in self.project.segments
            if segment.id in unique_ids
        ]

    def _start_regeneration(self, segment_ids: list[int]) -> None:
        if self.project is None or not segment_ids or self._job_runner.is_running:
            return

        for seg_id in segment_ids:
            self.timeline.set_timeline_clip_status(f"khmer:{seg_id}", STATUS_GENERATING)

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
        clip = self.timeline.selected_timeline_clip
        if clip is not None and clip.segment_id == segment_id:
            self.inspector.set_generating(True)

    def _on_regen_result(self, outcome: RegenerationOutcome) -> None:
        es = self._editables.setdefault(outcome.segment_id, EditableSegment(id=outcome.segment_id))
        if outcome.success:
            es.needs_regeneration = False
            es.last_error = None
            es.generated_duration = outcome.duration_seconds
            if outcome.wav_path is not None:
                self._ensure_khmer_clip_for_regenerated_segment(
                    outcome.segment_id, outcome.wav_path
                )
            self.timeline.set_timeline_clip_status(f"khmer:{outcome.segment_id}", None)
        else:
            es.last_error = outcome.error
            self._regen_errors.append(f"Segment {outcome.segment_id}: {outcome.error}")
            self.timeline.set_timeline_clip_status(
                f"khmer:{outcome.segment_id}", STATUS_FAILED
            )

        self._regen_completed += 1
        if self._progress_dialog is not None:
            self._progress_dialog.setValue(self._regen_completed)

        clip = self.timeline.selected_timeline_clip
        if clip is not None and clip.segment_id == outcome.segment_id:
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

    def _on_clip_regen_result(self, outcome: ClipRegenerationOutcome) -> None:
        if outcome.success and outcome.wav_path is not None:
            source_clip = next(
                (item for item in self.timeline.timeline_clips if item.id == outcome.clip_id),
                None,
            )
            if source_clip is not None:
                draft_clip = self._build_draft_regeneration_clip(source_clip, outcome.wav_path)
                self.timeline.add_timeline_clip(draft_clip)
            if self.project is not None:
                save_timeline_edits(self.timeline.timeline, self.project.project_path)
            self.inspector.show_regeneration_completed()
            self.statusBar().showMessage(
                f"Regeneration completed: draft created for {outcome.clip_id}"
            )
        else:
            self.timeline.set_timeline_clip_status(outcome.clip_id, STATUS_FAILED)
            self.inspector.show_regeneration_error(outcome.error or "Unknown error")
            QMessageBox.warning(
                self,
                "Regeneration Error",
                f"Clip {outcome.clip_id}: {outcome.error}",
            )

    def _on_clip_regen_finished(self, _outcome: ClipRegenerationOutcome) -> None:
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
        self._prepare_video_and_apply_project(project)

    def _prepare_video_and_apply_project(self, project: Project) -> None:
        if project.video_path is None:
            self._apply_loaded_project(project)
            return
        if self._project_video_metadata_is_current(project):
            self._apply_loaded_project(project)
            return

        self._video_proxy_dialog = QProgressDialog(
            "Preparing video for editing...", "", 0, 0, self
        )
        self._video_proxy_dialog.setCancelButton(None)
        self._video_proxy_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._video_proxy_job = VideoProxyJob(project, self._tool_config)
        self._video_proxy_job.signals.progressChanged.connect(self._on_video_proxy_progress)
        self._video_proxy_job.signals.finished.connect(self._on_video_proxy_finished)
        self._video_proxy_job.signals.errorOccurred.connect(self._on_video_proxy_error)
        QThreadPool.globalInstance().start(self._video_proxy_job)
        self._video_proxy_dialog.exec()

    @staticmethod
    def _project_video_metadata_is_current(project: Project) -> bool:
        if (
            project.editor_video_path is None
            or project.source_codec is None
            or project.editor_codec is None
            or not project.editor_video_path.is_file()
        ):
            return False
        if project.source_codec.lower() in PROXY_REQUIRED_CODECS:
            return project.editor_video_path.stat().st_mtime >= project.video_path.stat().st_mtime
        return True

    def _on_video_proxy_progress(self, message: str) -> None:
        if self._video_proxy_dialog is not None:
            self._video_proxy_dialog.setLabelText(message)

    def _on_video_proxy_finished(self, project: Project) -> None:
        if self._video_proxy_dialog is not None:
            self._video_proxy_dialog.setLabelText("Loading project...")
            self._video_proxy_dialog.close()
            self._video_proxy_dialog = None
        self._video_proxy_job = None
        self._apply_loaded_project(project)

    def _on_video_proxy_error(self, message: str) -> None:
        if self._video_proxy_dialog is not None:
            self._video_proxy_dialog.close()
            self._video_proxy_dialog = None
        self._video_proxy_job = None
        QMessageBox.critical(self, "Failed to Prepare Video", message)

    def _apply_loaded_project(self, project: Project) -> None:
        self.project = project
        self._editables = {}
        apply_edits(project.segments, project.project_path, self._editables)
        self._undo_stack.clear()
        self.save_project_action.setEnabled(True)
        self.export_video_action.setEnabled(True)
        self.setWindowTitle(f"{WINDOW_TITLE} - {project.project_path.name}")
        self.info_panel.set_project(project)
        self.video_player.load_video(project.editor_video_path or project.video_path)
        self.timeline.load_segments(
            project.segments,
            audio_path=project.audio_path,
            tts_directory=project.tts_directory,
        )
        if edited_timeline := load_timeline_edits(project.project_path):
            self.timeline.load_timeline(edited_timeline)
        self._seed_timeline_clips_from_import_editables()
        self.inspector.set_timeline_clip(None)
        self.statusBar().showMessage(self._status_message(project))
        self._update_regenerate_actions()
        self._refresh_playback_sources()

    def _seed_timeline_clips_from_import_editables(self) -> None:
        """Seed TimelineClip state from legacy import/export metadata."""
        for clip in self.timeline.timeline_clips:
            if clip.track_id != KHMER_TTS_TRACK_ID or clip.segment_id is None:
                continue
            es = self._editables.get(clip.segment_id)
            if es is None:
                continue
            clip.volume = es.volume
            clip.fade_in = es.fade_in_ms / 1000.0
            clip.fade_out = es.fade_out_ms / 1000.0
            clip.locked = es.locked
            self.timeline.set_timeline_clip_locked(clip.id, es.locked)
            if es.last_error is not None:
                self.timeline.set_timeline_clip_status(clip.id, STATUS_FAILED)
            elif es.needs_regeneration:
                self.timeline.set_timeline_clip_status(clip.id, STATUS_NEEDS_REGENERATION)

    def _refresh_playback_sources(self) -> None:
        """Publish the editor TimelineClip model to playback."""
        if self.project is None:
            self.playback_controller.set_timeline_clips([])
            return
        self.playback_controller.set_timeline(self.timeline.timeline)

    def _save_project(self) -> None:
        if self.project is None:
            return
        if not self._resolve_pending_inspector_edits():
            return
        save_edits(self.project.segments, self.project.project_path, self._editables)
        save_timeline_edits(self.timeline.timeline, self.project.project_path)
        self.statusBar().showMessage("Project saved.")

    def _resolve_pending_inspector_edits(self) -> bool:
        if not self.inspector.has_unsaved_changes:
            return True
        response = QMessageBox.question(
            self,
            "Unsaved Translation",
            "You have unsaved changes.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if response == QMessageBox.StandardButton.Save:
            self.inspector.save_translation()
            return True
        if response == QMessageBox.StandardButton.Discard:
            self.inspector.revert_translation()
            return True
        return False

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

    def _ensure_khmer_clip_for_regenerated_segment(
        self, segment_id: int, wav_path: Path
    ) -> None:
        if self.timeline.timeline.clip_by_id(f"khmer:{segment_id}") is not None:
            return
        if self.project is None:
            return
        segment = next((item for item in self.project.segments if item.id == segment_id), None)
        if segment is None:
            return
        original_clip = self.timeline.timeline.clip_by_id(f"original:{segment_id}")
        start_time = (
            original_clip.start_time
            if original_clip is not None
            else segment.start + segment.offset_ms / 1000.0
        )
        duration = (
            original_clip.duration
            if original_clip is not None
            else max(0.0, segment.end - segment.start)
        )
        clip = TimelineClip(
            id=f"khmer:{segment.id}",
            track_id=KHMER_TTS_TRACK_ID,
            start_time=start_time,
            end_time=start_time + duration,
            source_path=wav_path,
            source_offset=0.0,
            segment_id=segment.id,
            source_text=segment.source_text,
            target_text=segment.target_text,
            chinese_text=segment.source_text,
            khmer_text=segment.target_text,
        )
        self.timeline.add_timeline_clip(clip)
        save_timeline_edits(self.timeline.timeline, self.project.project_path)

    @staticmethod
    def _build_draft_regeneration_clip(source_clip, wav_path: Path):
        return replace(
            source_clip,
            id=f"draft:{source_clip.id}:{wav_path.stem}",
            track_id=DRAFT_REGENERATION_TRACK_ID,
            source_path=wav_path,
            selected=False,
        )

    def _restore_geometry(self) -> None:
        geometry = self._settings.value(_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)
