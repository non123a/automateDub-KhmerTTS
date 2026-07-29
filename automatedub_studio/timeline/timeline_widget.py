"""Timeline widget: QGraphicsView-based visualization of segment timing.

The timeline displays generic tracks owned by a Timeline model. Ctrl+Wheel
zooms horizontally; the playhead tracks the video player's position. Selected
clips can be dragged horizontally to adjust offset_ms.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem
from automatedub_studio.timeline.ruler_widget import (
    DEFAULT_SNAP_INTERVAL_MS,
    TimelineRulerWidget,
    snap_offset,
)
from automatedub_studio.timeline.state import TimelineState
from automatedub_studio.timeline.timeline_clip import (
    AUDIO_TRACK_3_ID,
    AUDIO_TRACK_4_ID,
    AUDIO_TRACK_IDS,
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)
from automatedub_studio.timeline.waveform_cache import WaveformCache

# ---------------------------------------------------------------------------
# Layout constants (scene coordinates, zoom=1.0)
# ---------------------------------------------------------------------------
BASE_PIXELS_PER_SECOND = 100.0
LANE_HEIGHT = 55
LANE_GAP = 10
LANE_LABEL_WIDTH = 140
SCENE_MARGIN_H = 8
SCENE_MARGIN_V = 10
VIDEO_LANE = 0
ORIGINAL_AUDIO_LANE = 1
KHMER_TTS_LANE = 2
AUDIO_TRACK_3_LANE = 3
AUDIO_TRACK_4_LANE = 4
AUDIO_LANES = (
    ORIGINAL_AUDIO_LANE,
    KHMER_TTS_LANE,
    AUDIO_TRACK_3_LANE,
    AUDIO_TRACK_4_LANE,
)
LANE_NAMES = ("Video", "Original Audio", "Khmer TTS", "Audio Track 3", "Audio Track 4")
LANE_COUNT = len(LANE_NAMES)
AUDIO_TRACK_COUNT = 2

HEADER_BG_COLOR = QColor("#2D2D2D")
LANE_BG_COLORS = [
    QColor("#242832"),
    QColor("#1E2A3A"),
    QColor("#1A2E1A"),
    QColor("#2A2535"),
    QColor("#302A24"),
]
PLAYHEAD_COLOR = QColor("#FF4444")
PASTE_FLASH_MS = 650

_MIN_ZOOM = 0.05
_MAX_ZOOM = 20.0
_ZOOM_STEP = 1.18
_DRAG_THRESHOLD_PX = 3
_SNAP_MS = 10
MIN_CLIP_DURATION_SECONDS = 0.001


def _snap(offset_ms: int) -> int:
    return snap_offset(offset_ms, _SNAP_MS)


def _lane_y(lane: int) -> float:
    return SCENE_MARGIN_V + lane * (LANE_HEIGHT + LANE_GAP)


def _scene_height() -> float:
    return SCENE_MARGIN_V * 2 + LANE_COUNT * LANE_HEIGHT + (LANE_COUNT - 1) * LANE_GAP


TRACK_IDS_BY_LANE = (
    "video",
    ORIGINAL_AUDIO_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    AUDIO_TRACK_3_ID,
    AUDIO_TRACK_4_ID,
)
LANE_BY_TRACK_ID = {track_id: lane for lane, track_id in enumerate(TRACK_IDS_BY_LANE)}


class _TimelineView(QGraphicsView):
    """QGraphicsView with Ctrl+Wheel zoom and horizontal clip dragging."""

    zoomRequested = Signal(float)
    clipDragMoved = Signal(str, int)  # (clip_id, live_offset_ms)
    clipDragEnded = Signal(str, int, int)  # (clip_id, old_ms, new_ms)
    clipsDragEnded = Signal(dict, dict)  # old_offsets_by_segment_id, new_offsets_by_segment_id
    clipTrimMoved = Signal(str, float, float)  # clip_id, start_seconds, end_seconds
    # clip_id, old_start, old_end, new_start, new_end
    clipTrimEnded = Signal(str, float, float, float, float)
    clipPlayRequested = Signal(int)       # segment_id, from double-clicking a clip
    clipMutePaintRequested = Signal(str)
    clipTrackChangeRequested = Signal(str, float)
    timelineSeekRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self._drag_clip: ClipItem | None = None
        self._drag_press_scene_x: float = 0.0
        self._drag_start_offset_ms: int = 0
        self._drag_start_offsets_ms: dict[str, int] = {}
        self._dragging: bool = False
        self._drag_label: QGraphicsTextItem | None = None
        self._trim_clip: ClipItem | None = None
        self._trim_handle: str | None = None
        self._trim_press_scene_x: float = 0.0
        self._trim_start_seconds: float = 0.0
        self._trim_end_seconds: float = 0.0
        self._trimming: bool = False
        self._snap_enabled = False
        self._snap_interval_ms = DEFAULT_SNAP_INTERVAL_MS
        self._mute_paint_mode = False
        self._last_clicked_clip: ClipItem | None = None
        self._playhead_ms = 0
        self._playhead_dragging = False
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)

    def set_playhead_position(self, position_ms: int) -> None:
        self._playhead_ms = max(0, position_ms)

    def set_mute_paint_mode(self, enabled: bool) -> None:
        self._mute_paint_mode = enabled

    def set_snap_enabled(self, enabled: bool) -> None:
        self._snap_enabled = enabled

    def set_snap_interval_ms(self, interval_ms: int) -> None:
        self._snap_interval_ms = max(1, interval_ms)

    def _offset_for_drag_delta(self, delta_ms: int, start_offset_ms: int | None = None) -> int:
        raw_offset = (self._drag_start_offset_ms if start_offset_ms is None else start_offset_ms)
        raw_offset += delta_ms
        if not self._snap_enabled:
            return raw_offset
        return snap_offset(raw_offset, self._snap_interval_ms)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
            self.zoomRequested.emit(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self.scene().itemAt(scene_pos, self.transform())
        if self._is_over_playhead(scene_pos.x()):
            self._playhead_dragging = True
            self.timelineSeekRequested.emit(self._scene_x_to_time_ms(scene_pos.x()))
            event.accept()
            return
        if self._mute_paint_mode and isinstance(item, ClipItem):
            self.clipMutePaintRequested.emit(self._clip_key(item))
            event.accept()
            return
        if item is None and scene_pos.x() >= LANE_LABEL_WIDTH + SCENE_MARGIN_H:
            self.timelineSeekRequested.emit(self._scene_x_to_time_ms(scene_pos.x()))
            event.accept()
            return
        if isinstance(item, ClipItem) and not item.locked:
            handle = item.trim_handle_at(item.mapFromScene(scene_pos))
            if handle is not None:
                self._trim_clip = item
                self._trim_handle = handle
                self._trim_press_scene_x = scene_pos.x()
                self._trim_start_seconds = (
                    item.timeline_clip.start_time if item.timeline_clip else item.segment.start
                )
                self._trim_end_seconds = (
                    item.timeline_clip.end_time if item.timeline_clip else item.segment.end
                )
                self._trimming = False
                item.setSelected(True)
                event.accept()
                return
        if isinstance(item, ClipItem) and self._is_additive_modifier(event.modifiers()):
            self._toggle_clip_selection(item)
            self._last_clicked_clip = item
            event.accept()
            return
        if isinstance(item, ClipItem) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._select_range(item)
            self._last_clicked_clip = item
            event.accept()
            return

        was_selected_clip = isinstance(item, ClipItem) and item.isSelected()
        if not was_selected_clip or event.modifiers():
            super().mousePressEvent(event)

        if (
            isinstance(item, ClipItem)
            and item.isSelected()
            and not item.locked
        ):
            self._drag_clip = item
            self._drag_press_scene_x = scene_pos.x()
            self._drag_start_offset_ms = self._clip_offset_ms(item)
            self._drag_start_offsets_ms = self._selected_unlocked_clip_offsets()
            self._dragging = False
            self._last_clicked_clip = item
        elif isinstance(item, ClipItem):
            self._last_clicked_clip = item

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self.scene().itemAt(scene_pos, self.transform())
        if isinstance(item, ClipItem) and item.lane == KHMER_TTS_LANE:
            self.clipPlayRequested.emit(item.segment.id)

    def mouseMoveEvent(self, event) -> None:
        if self._playhead_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.timelineSeekRequested.emit(self._scene_x_to_time_ms(scene_pos.x()))
            event.accept()
            return
        if self._trim_clip is not None and event.buttons() & Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            dx = scene_pos.x() - self._trim_press_scene_x
            if not self._trimming and abs(dx) > _DRAG_THRESHOLD_PX:
                self._trimming = True
            if self._trimming:
                delta_seconds = dx / BASE_PIXELS_PER_SECOND
                if self._trim_handle == "left":
                    start = self._trim_start_seconds + delta_seconds
                    end = self._trim_end_seconds
                else:
                    start = self._trim_start_seconds
                    end = self._trim_end_seconds + delta_seconds
                self.clipTrimMoved.emit(self._clip_key(self._trim_clip), start, end)
                event.accept()
                return
        if self._drag_clip is not None and event.buttons() & Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            dx = scene_pos.x() - self._drag_press_scene_x
            if not self._dragging and abs(dx) > _DRAG_THRESHOLD_PX:
                self._dragging = True
            if self._dragging:
                delta_ms = round(dx / BASE_PIXELS_PER_SECOND * 1000)
                moved_offsets = self._moved_offsets(delta_ms)
                for segment_id, offset_ms in moved_offsets.items():
                    self.clipDragMoved.emit(segment_id, offset_ms)
                self._update_drag_label(
                    self._drag_clip, moved_offsets[self._clip_key(self._drag_clip)]
                )
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._playhead_dragging and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.timelineSeekRequested.emit(self._scene_x_to_time_ms(scene_pos.x()))
            self._playhead_dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._trim_clip is not None and event.button() == Qt.MouseButton.LeftButton:
            if self._trimming:
                scene_pos = self.mapToScene(event.position().toPoint())
                dx = scene_pos.x() - self._trim_press_scene_x
                delta_seconds = dx / BASE_PIXELS_PER_SECOND
                if self._trim_handle == "left":
                    start = self._trim_start_seconds + delta_seconds
                    end = self._trim_end_seconds
                else:
                    start = self._trim_start_seconds
                    end = self._trim_end_seconds + delta_seconds
                    self.clipTrimEnded.emit(
                        self._clip_key(self._trim_clip),
                    self._trim_start_seconds,
                    self._trim_end_seconds,
                    start,
                    end,
                )
            self._trim_clip = None
            self._trim_handle = None
            self._trimming = False
            return
        if self._drag_clip is not None and event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                scene_pos = self.mapToScene(event.position().toPoint())
                dx = scene_pos.x() - self._drag_press_scene_x
                delta_ms = round(dx / BASE_PIXELS_PER_SECOND * 1000)
                new_offsets_ms = self._moved_offsets(delta_ms)
                changed_new_offsets = {
                    segment_id: offset_ms
                    for segment_id, offset_ms in new_offsets_ms.items()
                    if offset_ms != self._drag_start_offsets_ms.get(segment_id)
                }
                if len(changed_new_offsets) == 1:
                    segment_id, new_offset_ms = next(iter(changed_new_offsets.items()))
                    self.clipDragEnded.emit(
                        segment_id,
                        self._drag_start_offsets_ms[segment_id],
                        new_offset_ms,
                    )
                elif changed_new_offsets:
                    old_offsets_ms = {
                        segment_id: self._drag_start_offsets_ms[segment_id]
                        for segment_id in changed_new_offsets
                    }
                    self.clipsDragEnded.emit(old_offsets_ms, changed_new_offsets)
                self.clipTrackChangeRequested.emit(self._clip_key(self._drag_clip), scene_pos.y())
            self._remove_drag_label()
        self._drag_clip = None
        self._drag_start_offsets_ms = {}
        self._dragging = False

    def _update_drag_label(self, clip: ClipItem, offset_ms: int) -> None:
        text = f"{'+' if offset_ms > 0 else ''}{offset_ms} ms"
        rect = clip.rect()
        label_x = clip.pos().x() + rect.x() + rect.width() / 2
        label_y = clip.pos().y() + rect.y() - 18
        if self._drag_label is None:
            self._drag_label = QGraphicsTextItem(text)
            self._drag_label.setDefaultTextColor(QColor("#FFFFFF"))
            self._drag_label.setZValue(2000)
            self.scene().addItem(self._drag_label)
        else:
            self._drag_label.setPlainText(text)
        self._drag_label.setPos(label_x - self._drag_label.boundingRect().width() / 2, label_y)

    def _remove_drag_label(self) -> None:
        if self._drag_label is not None:
            self.scene().removeItem(self._drag_label)
            self._drag_label = None

    def _selected_unlocked_clip_offsets(self) -> dict[str, int]:
        offsets: dict[str, int] = {}
        for item in self.scene().selectedItems():
            if isinstance(item, ClipItem) and not item.locked:
                offsets.setdefault(self._clip_key(item), self._clip_offset_ms(item))
        if self._drag_clip is not None and not self._drag_clip.locked:
            offsets.setdefault(
                self._clip_key(self._drag_clip), self._clip_offset_ms(self._drag_clip)
            )
        return offsets

    def _moved_offsets(self, delta_ms: int) -> dict[str, int]:
        return {
            segment_id: self._offset_for_drag_delta(delta_ms, start_offset)
            for segment_id, start_offset in self._drag_start_offsets_ms.items()
        }

    @staticmethod
    def _clip_key(item: ClipItem) -> str:
        return item.timeline_clip.id if item.timeline_clip is not None else str(item.segment.id)

    @staticmethod
    def _clip_offset_ms(item: ClipItem) -> int:
        if item.timeline_clip is None:
            return item.segment.offset_ms
        return round((item.timeline_clip.start_time - item.segment.start) * 1000)

    def _select_range(self, item: ClipItem) -> None:
        if self._last_clicked_clip is None or self._last_clicked_clip.lane != item.lane:
            self.scene().clearSelection()
            item.setSelected(True)
            return
        lane_items = sorted(
            (
                scene_item
                for scene_item in self.scene().items()
                if isinstance(scene_item, ClipItem) and scene_item.lane == item.lane
            ),
            key=lambda clip: (clip.segment.start, clip.segment.id),
        )
        try:
            start_index = lane_items.index(self._last_clicked_clip)
            end_index = lane_items.index(item)
        except ValueError:
            self.scene().clearSelection()
            item.setSelected(True)
            return
        lower, upper = sorted((start_index, end_index))
        self.scene().clearSelection()
        for clip in lane_items[lower : upper + 1]:
            clip.setSelected(True)

    @staticmethod
    def _is_additive_modifier(modifiers: Qt.KeyboardModifier) -> bool:
        return bool(
            modifiers
            & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        )

    def _toggle_clip_selection(self, item: ClipItem) -> None:
        item.setSelected(not item.isSelected())

    def _is_over_playhead(self, scene_x: float) -> bool:
        playhead_x = LANE_LABEL_WIDTH + SCENE_MARGIN_H + (
            self._playhead_ms / 1000.0 * BASE_PIXELS_PER_SECOND
        )
        return abs(scene_x - playhead_x) <= 6.0 / max(self.transform().m11(), 0.001)

    @staticmethod
    def _scene_x_to_time_ms(scene_x: float) -> int:
        seconds = (scene_x - (LANE_LABEL_WIDTH + SCENE_MARGIN_H)) / BASE_PIXELS_PER_SECOND
        return max(0, round(seconds * 1000))


class TimelineWidget(QWidget):
    """Horizontal timeline showing segment clips across two lanes.

    Owns the QGraphicsScene. Exposes:
    - ``load_segments(segments)`` — rebuild from a new segment list.
    - ``set_playhead_position(ms)`` — move the playhead.
    - ``selected_segment`` property — the currently selected Segment, or None.
    - ``apply_offset(segment_id, offset_ms)`` — reposition clips for a segment.
    """

    segmentSelected = Signal(object)  # emits Segment | None
    segmentsSelected = Signal(list)  # emits selected Segment list
    timelineClipSelected = Signal(object)  # emits TimelineClip | None
    timelineClipsSelected = Signal(list)  # emits selected TimelineClip list
    segmentOffsetChanged = Signal(str, int)   # (clip_id, offset_ms) live during drag
    segmentOffsetCommitted = Signal(str, int, int)  # (clip_id, old_ms, new_ms) on drag end
    segmentsOffsetCommitted = Signal(dict, dict)  # old_offsets, new_offsets
    segmentTrimChanged = Signal(str, float, float)  # live trim
    segmentTrimCommitted = Signal(str, float, float, float, float)
    clipPlayRequested = Signal(int)  # segment_id, from double-clicking a clip
    clipMutePaintRequested = Signal(str)
    timelineSeekRequested = Signal(int)
    timelineChanged = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom = 1.0
        self._duration_ms = 0
        self._playhead_ms = 0
        self._state = TimelineState()
        self._segments: list[Segment] = []
        self._clips_by_segment: dict[int, list[ClipItem]] = {}
        self._timeline = Timeline.default()
        self._timeline_clips: list[TimelineClip] = []
        self._clips_by_clip_id: dict[str, ClipItem] = {}
        self._waveform_cache = WaveformCache()
        self._audio_path: Path | None = None
        self._tts_directory: Path | None = None

        self._scene = QGraphicsScene(self)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._ruler = TimelineRulerWidget(
            pixels_per_second=BASE_PIXELS_PER_SECOND,
            time_origin_x=LANE_LABEL_WIDTH + SCENE_MARGIN_H,
        )
        self._ruler.seekRequested.connect(self._on_seek_requested)

        self._view = _TimelineView()
        self._view.setScene(self._scene)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setRenderHint(self._view.renderHints())
        self._view.zoomRequested.connect(self._apply_zoom)
        self._view.clipDragMoved.connect(self._on_clip_drag_moved)
        self._view.clipDragEnded.connect(self._on_clip_drag_ended)
        self._view.clipsDragEnded.connect(self._on_clips_drag_ended)
        self._view.clipTrimMoved.connect(self._on_clip_trim_moved)
        self._view.clipTrimEnded.connect(self._on_clip_trim_ended)
        self._view.clipPlayRequested.connect(self.clipPlayRequested.emit)
        self._view.clipMutePaintRequested.connect(self.clipMutePaintRequested.emit)
        self._view.clipTrackChangeRequested.connect(self._on_clip_track_change_requested)
        self._view.timelineSeekRequested.connect(self._on_seek_requested)
        self._view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._view.horizontalScrollBar().valueChanged.connect(self._ruler.set_scroll_value)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._ruler)
        layout.addWidget(self._view)

        self._playhead: QGraphicsLineItem | None = None
        self._draw_static_lanes(duration_ms=0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_segments(
        self,
        segments: list[Segment],
        duration_ms: int = 0,
        audio_path: Path | None = None,
        tts_directory: Path | None = None,
    ) -> None:
        self._duration_ms = max(
            duration_ms,
            int(max((s.end for s in segments), default=0.0) * 1000),
        )
        self._segments = segments
        self._audio_path = audio_path
        self._tts_directory = tts_directory
        self._timeline = self._build_timeline(segments)
        self._timeline_clips = self._timeline.all_clips()
        self._rebuild_scene(segments)
        self._ruler.set_duration(self._duration_ms)

    def set_playhead_position(self, position_ms: int) -> None:
        self._playhead_ms = max(0, position_ms)
        x = self._time_to_x(self._playhead_ms / 1000.0)
        self._state.set_current_time(self._playhead_ms)
        self._view.set_playhead_position(self._playhead_ms)
        if self._playhead is not None:
            self._playhead.setLine(x, 0, x, _scene_height())
        self._ensure_scene_rect_covers_time(position_ms / 1000.0)
        self._ruler.set_playhead_position(position_ms)

    @property
    def selected_segment(self) -> Segment | None:
        selected = self.selected_segments
        return selected[0] if len(selected) == 1 else None

    @property
    def selected_timeline_clip(self) -> TimelineClip | None:
        selected = self.selected_timeline_clips
        return selected[0] if len(selected) == 1 else None

    @property
    def selected_segments(self) -> list[Segment]:
        by_id: dict[int, Segment] = {}
        for item in self._scene.selectedItems():
            if isinstance(item, ClipItem):
                by_id.setdefault(item.segment.id, item.segment)
        return sorted(by_id.values(), key=lambda segment: (segment.start, segment.id))

    @property
    def selected_timeline_clips(self) -> list[TimelineClip]:
        clips = [
            item.timeline_clip
            for item in self._scene.selectedItems()
            if isinstance(item, ClipItem) and item.timeline_clip is not None
        ]
        for clip in self._timeline_clips:
            clip.selected = clip in clips
        return sorted(clips, key=lambda clip: (clip.start_time, clip.track_id, clip.id))

    @property
    def timeline_clips(self) -> list[TimelineClip]:
        return list(self._timeline.all_clips())

    @property
    def timeline(self) -> Timeline:
        return self._timeline

    @property
    def _clips(self) -> list[ClipItem]:
        return [clip for clips in self._clips_by_segment.values() for clip in clips]

    def apply_offset(self, segment_id: int, offset_ms: int) -> None:
        """Reposition all clips for the given segment to reflect new offset_ms."""
        clips = self._clips_by_segment.get(segment_id, [])
        if not clips:
            return
        segment = clips[0].segment
        segment.offset_ms = offset_ms
        effective_start = segment.start + offset_ms / 1000.0
        new_x = self._time_to_x(effective_start)
        for clip in clips:
            # rect().x() is the fixed scene-x set at construction; pos() is the delta
            clip.setX(new_x - clip.rect().x())

    def apply_timeline_clip_offset(self, clip_id: str, offset_ms: int) -> None:
        """Move one independent timeline clip without moving its sibling track clip."""
        item = self._clips_by_clip_id.get(clip_id)
        if item is None or item.timeline_clip is None:
            return
        segment = item.segment
        timeline_clip = item.timeline_clip
        if timeline_clip.locked or self._track_is_locked(timeline_clip.track_id):
            return
        duration = timeline_clip.duration
        start_time = segment.start + offset_ms / 1000.0
        timeline_clip.start_time = start_time
        timeline_clip.end_time = start_time + duration
        new_x = self._time_to_x(start_time)
        item.setX(new_x - item.rect().x())
        self._ensure_scene_rect_covers_time(timeline_clip.end_time)

    def set_timeline_clip_muted(self, clip_id: str, muted: bool) -> None:
        clip = self._find_timeline_clip(clip_id)
        item = self._clips_by_clip_id.get(clip_id)
        if clip is not None:
            clip.muted = muted
        if item is not None:
            item.update()

    def set_mute_paint_mode(self, enabled: bool) -> None:
        self._view.set_mute_paint_mode(enabled)

    def set_timeline_clip_volume(self, clip_id: str, volume: float) -> None:
        clip = self._find_timeline_clip(clip_id)
        if clip is not None:
            clip.volume = max(0.0, volume)

    def set_timeline_clip_fade_in(self, clip_id: str, fade_in_ms: int) -> None:
        clip = self._find_timeline_clip(clip_id)
        if clip is not None:
            clip.fade_in = max(0, fade_in_ms) / 1000.0

    def set_timeline_clip_fade_out(self, clip_id: str, fade_out_ms: int) -> None:
        clip = self._find_timeline_clip(clip_id)
        if clip is not None:
            clip.fade_out = max(0, fade_out_ms) / 1000.0

    def set_timeline_clip_locked(self, clip_id: str, locked: bool) -> None:
        clip = self._find_timeline_clip(clip_id)
        item = self._clips_by_clip_id.get(clip_id)
        if clip is not None:
            clip.locked = locked
        if item is not None:
            item.set_locked(locked or (clip is not None and self._track_is_locked(clip.track_id)))

    def set_track_muted(self, track_id: str, muted: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.muted = muted
            self.timelineChanged.emit()

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is not None:
            track.solo = solo
            self.timelineChanged.emit()

    def set_track_locked(self, track_id: str, locked: bool) -> None:
        track = self._timeline.track_by_id(track_id)
        if track is None:
            return
        track.locked = locked
        for clip in track.clips:
            item = self._clips_by_clip_id.get(clip.id)
            if item is not None:
                item.set_locked(locked or clip.locked)
                item.update()
        self.timelineChanged.emit()

    def move_timeline_clip_to_track(self, clip_id: str, track_id: str) -> bool:
        clip = self._find_timeline_clip(clip_id)
        if clip is None:
            return False
        old_track_id = clip.track_id
        moved = self._timeline.move_clip_to_track(clip_id, track_id)
        if not moved:
            return False
        lane = self._lane_for_track_id(track_id)
        item = self._clips_by_clip_id.get(clip_id)
        if item is not None and lane is not None:
            item.lane = lane
            rect = item.rect()
            item.setRect(rect.x(), _lane_y(lane) + 4, rect.width(), rect.height())
            item.setX(0)
            item.setY(0)
            item.update()
        if old_track_id != track_id:
            self._timeline_clips = self._timeline.all_clips()
            self.timelineChanged.emit()
        return True

    def set_timeline_clip_status(self, clip_id: str, status: str | None) -> None:
        item = self._clips_by_clip_id.get(clip_id)
        if item is not None:
            item.set_status(status)

    def apply_timeline_clip_trim(
        self, clip_id: str, start_seconds: float, end_seconds: float
    ) -> None:
        """Apply trim to one independent timeline clip."""
        item = self._clips_by_clip_id.get(clip_id)
        if item is None or item.timeline_clip is None:
            return
        timeline_clip = item.timeline_clip
        if timeline_clip.locked or self._track_is_locked(timeline_clip.track_id):
            return
        start_seconds, end_seconds = self.constrain_timeline_clip_trim(
            clip_id, start_seconds, end_seconds
        )
        timeline_clip.start_time = start_seconds
        timeline_clip.end_time = end_seconds
        width = max(0.0, timeline_clip.duration * BASE_PIXELS_PER_SECOND)
        x = self._time_to_x(timeline_clip.start_time)
        rect = item.rect()
        item.setRect(x, rect.y(), width, rect.height())
        item.setX(0)
        item.update()
        self._ensure_scene_rect_covers_time(timeline_clip.end_time)

    def constrain_timeline_clip_trim(
        self, clip_id: str, start_seconds: float, end_seconds: float
    ) -> tuple[float, float]:
        clip = self._find_timeline_clip(clip_id)
        if clip is None:
            return start_seconds, end_seconds
        track_clips = sorted(
            [item for item in self._timeline_clips if item.track_id == clip.track_id],
            key=lambda item: (item.start_time, item.id),
        )
        index = track_clips.index(clip)
        previous_end = track_clips[index - 1].end_time if index > 0 else 0.0
        source_end = self._duration_ms / 1000.0 if self._duration_ms > 0 else clip.end_time
        next_start = (
            track_clips[index + 1].start_time if index < len(track_clips) - 1 else source_end
        )
        constrained_start = max(0.0, previous_end, start_seconds)
        constrained_end = min(source_end, next_start, end_seconds)
        if constrained_end - constrained_start < MIN_CLIP_DURATION_SECONDS:
            if abs(start_seconds - clip.start_time) > abs(end_seconds - clip.end_time):
                constrained_start = constrained_end - MIN_CLIP_DURATION_SECONDS
            else:
                constrained_end = constrained_start + MIN_CLIP_DURATION_SECONDS
        constrained_start = max(0.0, previous_end, constrained_start)
        constrained_end = min(source_end, next_start, constrained_end)
        if constrained_end <= constrained_start:
            return clip.start_time, clip.end_time
        return constrained_start, constrained_end

    def apply_locked(self, segment_id: int, locked: bool) -> None:
        """Update locked state on all clips for a segment."""
        for clip in self._clips_by_segment.get(segment_id, []):
            clip.set_locked(locked)

    def apply_status(self, segment_id: int, status: str | None) -> None:
        """Update the regeneration status badge on all clips for a segment."""
        for clip in self._clips_by_segment.get(segment_id, []):
            clip.set_status(status)

    def select_segment_ids(self, segment_ids: list[int]) -> None:
        """Select all clip items belonging to the given segment IDs."""
        wanted = set(segment_ids)
        self._scene.blockSignals(True)
        self._scene.clearSelection()
        for segment_id in wanted:
            for clip in self._clips_by_segment.get(segment_id, []):
                clip.setSelected(True)
        self._scene.blockSignals(False)
        self._on_selection_changed()

    def flash_segment_ids(self, segment_ids: list[int]) -> None:
        """Briefly highlight newly pasted/duplicated clips."""
        wanted = set(segment_ids)
        clips = [
            clip
            for segment_id in wanted
            for clip in self._clips_by_segment.get(segment_id, [])
        ]
        for clip in clips:
            clip.set_flash(True)
        if clips:
            QTimer.singleShot(PASTE_FLASH_MS, lambda: self._clear_flash(clips))

    def apply_trim(self, segment_id: int, start_seconds: float, end_seconds: float) -> None:
        """Apply a constrained trim to a segment and redraw its clips."""
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        start_seconds, end_seconds = self.constrain_trim(segment_id, start_seconds, end_seconds)
        segment.start = start_seconds
        segment.end = end_seconds
        clips = self._clips_by_segment.get(segment_id, [])
        width = max(0.0, (segment.end - segment.start) * BASE_PIXELS_PER_SECOND)
        x = self._time_to_x(segment.start + segment.offset_ms / 1000.0)
        for clip in clips:
            rect = clip.rect()
            clip.setRect(x, rect.y(), width, rect.height())
            clip.setX(0)
            clip.update()
        self._ensure_scene_rect_covers_time(segment.end)

    def constrain_trim(
        self, segment_id: int, start_seconds: float, end_seconds: float
    ) -> tuple[float, float]:
        """Clamp trim timing to duration, neighbors, and source length constraints."""
        segment = self._find_segment(segment_id)
        if segment is None:
            return start_seconds, end_seconds
        previous_end, next_start = self._neighbor_bounds(segment)
        source_end = self._duration_ms / 1000.0 if self._duration_ms > 0 else segment.end
        constrained_start = max(0.0, previous_end, start_seconds)
        constrained_end = min(source_end, next_start, end_seconds)
        if constrained_end - constrained_start < MIN_CLIP_DURATION_SECONDS:
            if abs(start_seconds - segment.start) > abs(end_seconds - segment.end):
                constrained_start = constrained_end - MIN_CLIP_DURATION_SECONDS
            else:
                constrained_end = constrained_start + MIN_CLIP_DURATION_SECONDS
        constrained_start = max(0.0, previous_end, constrained_start)
        constrained_end = min(source_end, next_start, constrained_end)
        if constrained_end <= constrained_start:
            return segment.start, segment.end
        return constrained_start, constrained_end

    def set_snap_enabled(self, enabled: bool) -> None:
        """Enable or disable grid snapping for clip drag edits."""
        self._view.set_snap_enabled(enabled)

    def set_snap_interval_ms(self, interval_ms: int) -> None:
        """Set the snap interval used by clip drag edits."""
        self._view.set_snap_interval_ms(interval_ms)

    @property
    def playhead_ms(self) -> int:
        return self._playhead_ms

    @property
    def state(self) -> TimelineState:
        return self._state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _time_to_x(self, seconds: float) -> float:
        return LANE_LABEL_WIDTH + SCENE_MARGIN_H + seconds * BASE_PIXELS_PER_SECOND

    def _apply_zoom(self, factor: float) -> None:
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        self._view.setTransform(QTransform().scale(self._zoom, 1.0))
        self._ruler.set_zoom(self._zoom)
        self._ruler.set_scroll_value(self._view.horizontalScrollBar().value())

    def _rebuild_scene(self, segments: list[Segment]) -> None:
        self._scene.clear()
        self._clips_by_segment = {}
        self._clips_by_clip_id = {}
        self._playhead = None
        self._draw_static_lanes(self._duration_ms)
        self._draw_clips(segments)
        self._draw_playhead()

    def _find_segment(self, segment_id: int) -> Segment | None:
        for segment in self._segments:
            if segment.id == segment_id:
                return segment
        return None

    def _find_timeline_clip(self, clip_id: str) -> TimelineClip | None:
        return self._timeline.clip_by_id(clip_id)

    def _track_is_locked(self, track_id: str) -> bool:
        track = self._timeline.track_by_id(track_id)
        return bool(track and track.locked)

    @staticmethod
    def _clear_flash(clips: list[ClipItem]) -> None:
        for clip in clips:
            clip.set_flash(False)

    def _neighbor_bounds(self, segment: Segment) -> tuple[float, float]:
        lane_segments = sorted(self._segments, key=lambda item: (item.start, item.id))
        index = lane_segments.index(segment)
        previous_end = lane_segments[index - 1].end if index > 0 else 0.0
        source_end = self._duration_ms / 1000.0 if self._duration_ms > 0 else segment.end
        next_start = (
            lane_segments[index + 1].start
            if index < len(lane_segments) - 1
            else source_end
        )
        return previous_end, next_start

    def _draw_static_lanes(self, duration_ms: int) -> None:
        scene_w = self._time_to_x(max(duration_ms / 1000.0, 30.0)) + SCENE_MARGIN_H
        scene_h = _scene_height()
        self._scene.setSceneRect(0, 0, scene_w, scene_h)

        for lane, track in enumerate(self._timeline.tracks):
            y = _lane_y(lane)
            bg = QGraphicsRectItem(0, y, scene_w, LANE_HEIGHT)
            bg.setBrush(QBrush(LANE_BG_COLORS[lane % len(LANE_BG_COLORS)]))
            bg.setPen(QPen(Qt.PenStyle.NoPen))
            self._scene.addItem(bg)

            header = QGraphicsRectItem(0, y, LANE_LABEL_WIDTH, LANE_HEIGHT)
            header.setBrush(QBrush(HEADER_BG_COLOR))
            header.setPen(QPen(Qt.PenStyle.NoPen))
            self._scene.addItem(header)

            label = QGraphicsTextItem(track.name)
            label.setDefaultTextColor(QColor("#CCCCCC"))
            label.setPos(6, y + 8)
            self._scene.addItem(label)

            controls = QGraphicsTextItem(
                f"M:{'ON' if track.muted else 'OFF'}  "
                f"S:{'ON' if track.solo else 'OFF'}  "
                f"L:{'ON' if track.locked else 'OFF'}"
            )
            controls.setDefaultTextColor(QColor("#AAAAAA"))
            controls.setPos(6, y + 29)
            self._scene.addItem(controls)

    def _draw_clips(self, segments: list[Segment]) -> None:
        segment_by_id = {segment.id: segment for segment in segments}
        for timeline_clip in self._timeline_clips:
            if timeline_clip.segment_id is None:
                continue
            segment = segment_by_id.get(timeline_clip.segment_id)
            if segment is None:
                continue
            lane = self._lane_for_track_id(timeline_clip.track_id)
            if lane is None:
                continue
            width = timeline_clip.duration * BASE_PIXELS_PER_SECOND
            x = self._time_to_x(timeline_clip.start_time)
            y = _lane_y(lane)
            wav_path, wav_start, wav_end = self._wav_context_for_timeline_clip(timeline_clip)
            clip = ClipItem(
                segment,
                x,
                y + 4,
                width,
                LANE_HEIGHT - 8,
                lane,
                wav_path=wav_path,
                waveform_cache=self._waveform_cache,
                wav_start_seconds=wav_start,
                wav_end_seconds=wav_end,
                timeline_clip=timeline_clip,
            )
            self._scene.addItem(clip)
            self._clips_by_segment.setdefault(segment.id, []).append(clip)
            self._clips_by_clip_id[timeline_clip.id] = clip

    def _build_timeline(self, segments: list[Segment]) -> Timeline:
        timeline = Timeline.default()
        original_track = timeline.track_by_id(ORIGINAL_AUDIO_TRACK_ID)
        khmer_track = timeline.track_by_id(KHMER_TTS_TRACK_ID)
        if original_track is None or khmer_track is None:
            return timeline
        original_track.clips = []
        khmer_track.clips = []
        clips: list[TimelineClip] = []
        for segment in segments:
            duration = max(0.0, segment.end - segment.start)
            start_time = segment.start + segment.offset_ms / 1000.0
            clips.append(
                TimelineClip(
                    id=f"original:{segment.id}",
                    track_id=ORIGINAL_AUDIO_TRACK_ID,
                    start_time=start_time,
                    end_time=start_time + duration,
                    source_path=self._audio_path,
                    source_offset=segment.start,
                    segment_id=segment.id,
                    source_text=segment.source_text,
                    target_text=segment.target_text,
                )
            )
            clips.append(
                TimelineClip(
                    id=f"khmer:{segment.id}",
                    track_id=KHMER_TTS_TRACK_ID,
                    start_time=start_time,
                    end_time=start_time + duration,
                    source_path=(
                        tts_segment_output_path(self._tts_directory, segment.id)
                        if self._tts_directory is not None
                        else None
                    ),
                    source_offset=0.0,
                    segment_id=segment.id,
                    source_text=segment.source_text,
                    target_text=segment.target_text,
                )
            )
        original_track.clips = [
            clip for clip in clips if clip.track_id == ORIGINAL_AUDIO_TRACK_ID
        ]
        khmer_track.clips = [clip for clip in clips if clip.track_id == KHMER_TTS_TRACK_ID]
        return timeline

    @staticmethod
    def _lane_for_track_id(track_id: str) -> int | None:
        return LANE_BY_TRACK_ID.get(track_id)

    @staticmethod
    def _track_id_for_scene_y(scene_y: float) -> str | None:
        for lane, track_id in enumerate(TRACK_IDS_BY_LANE):
            y = _lane_y(lane)
            if y <= scene_y <= y + LANE_HEIGHT:
                return track_id
        return None

    def _wav_context_for_timeline_clip(
        self, timeline_clip: TimelineClip
    ) -> tuple[Path | None, float, float | None]:
        if timeline_clip.track_id == ORIGINAL_AUDIO_TRACK_ID:
            return timeline_clip.source_path, timeline_clip.source_offset, (
                timeline_clip.source_offset + timeline_clip.duration
            )
        if timeline_clip.track_id == KHMER_TTS_TRACK_ID:
            return timeline_clip.source_path, timeline_clip.source_offset, None
        return None, 0.0, None

    def _wav_context_for_lane(
        self, lane: int, segment: Segment
    ) -> tuple[Path | None, float, float | None]:
        """Return (wav_path, start_seconds, end_seconds) for a clip's waveform.

        Original Audio slices the shared project audio to this segment's
        window; Khmer TTS uses the segment's own WAV file
        in full.
        """
        if lane == ORIGINAL_AUDIO_LANE:
            if self._audio_path is None:
                return None, 0.0, None
            return self._audio_path, segment.start, segment.end
        if lane == KHMER_TTS_LANE and self._tts_directory is not None:
            return tts_segment_output_path(self._tts_directory, segment.id), 0.0, None
        return None, 0.0, None


    def _draw_playhead(self) -> None:
        self._playhead = QGraphicsLineItem(0, 0, 0, _scene_height())
        self._playhead.setPen(QPen(PLAYHEAD_COLOR, 2))
        self._playhead.setZValue(1000)
        self._scene.addItem(self._playhead)

    def _ensure_scene_rect_covers_time(self, seconds: float) -> None:
        current_rect = self._scene.sceneRect()
        needed_x = self._time_to_x(seconds) + SCENE_MARGIN_H
        if needed_x > current_rect.right():
            self._scene.setSceneRect(0, 0, needed_x, current_rect.height())

    def _on_selection_changed(self) -> None:
        self._state.selected_clip_ids = {clip.id for clip in self.selected_timeline_clips}
        self.segmentSelected.emit(self.selected_segment)
        self.segmentsSelected.emit(self.selected_segments)
        self.timelineClipSelected.emit(self.selected_timeline_clip)
        self.timelineClipsSelected.emit(self.selected_timeline_clips)

    def _on_seek_requested(self, position_ms: int) -> None:
        self.set_playhead_position(position_ms)
        self.timelineSeekRequested.emit(self._playhead_ms)

    def _on_clip_drag_moved(self, segment_id: str, offset_ms: int) -> None:
        self.apply_timeline_clip_offset(segment_id, offset_ms)
        self.segmentOffsetChanged.emit(segment_id, offset_ms)

    def _on_clip_drag_ended(
        self, segment_id: str, old_offset_ms: int, new_offset_ms: int
    ) -> None:
        self.segmentOffsetCommitted.emit(segment_id, old_offset_ms, new_offset_ms)

    def _on_clips_drag_ended(
        self, old_offsets_ms: dict[str, int], new_offsets_ms: dict[str, int]
    ) -> None:
        self.segmentsOffsetCommitted.emit(old_offsets_ms, new_offsets_ms)

    def _on_clip_track_change_requested(self, clip_id: str, scene_y: float) -> None:
        track_id = self._track_id_for_scene_y(scene_y)
        if track_id is None or track_id not in AUDIO_TRACK_IDS:
            return
        self.move_timeline_clip_to_track(clip_id, track_id)

    def _on_clip_trim_moved(
        self, segment_id: str, start_seconds: float, end_seconds: float
    ) -> None:
        constrained_start, constrained_end = self.constrain_timeline_clip_trim(
            segment_id, start_seconds, end_seconds
        )
        self.apply_timeline_clip_trim(segment_id, constrained_start, constrained_end)
        self.segmentTrimChanged.emit(segment_id, constrained_start, constrained_end)

    def _on_clip_trim_ended(
        self,
        segment_id: str,
        old_start: float,
        old_end: float,
        new_start: float,
        new_end: float,
    ) -> None:
        constrained_start, constrained_end = self.constrain_timeline_clip_trim(
            segment_id, new_start, new_end
        )
        self.segmentTrimCommitted.emit(
            segment_id, old_start, old_end, constrained_start, constrained_end
        )
