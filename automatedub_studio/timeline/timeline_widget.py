"""Timeline widget: QGraphicsView-based visualization of segment timing.

Two lanes (Original Transcript, Khmer TTS) display the same timing until
a future milestone separates them. Ctrl+Wheel zooms horizontally; the
playhead tracks the video player's position. Selected clips can be dragged
horizontally to adjust offset_ms.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QWidget,
)

from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.clip_item import ClipItem

# ---------------------------------------------------------------------------
# Layout constants (scene coordinates, zoom=1.0)
# ---------------------------------------------------------------------------
BASE_PIXELS_PER_SECOND = 100.0
LANE_HEIGHT = 55
LANE_GAP = 10
LANE_LABEL_WIDTH = 140
SCENE_MARGIN_H = 8
SCENE_MARGIN_V = 10
LANE_NAMES = ("Original Transcript", "Khmer TTS")
LANE_COUNT = 2

HEADER_BG_COLOR = QColor("#2D2D2D")
LANE_BG_COLORS = [QColor("#1E2A3A"), QColor("#1A2E1A")]
PLAYHEAD_COLOR = QColor("#FF4444")

_MIN_ZOOM = 0.05
_MAX_ZOOM = 20.0
_ZOOM_STEP = 1.18
_DRAG_THRESHOLD_PX = 3
_SNAP_MS = 10


def _snap(offset_ms: int) -> int:
    return math.floor(offset_ms / _SNAP_MS + 0.5) * _SNAP_MS


def _lane_y(lane: int) -> float:
    return SCENE_MARGIN_V + lane * (LANE_HEIGHT + LANE_GAP)


def _scene_height() -> float:
    return SCENE_MARGIN_V * 2 + LANE_COUNT * LANE_HEIGHT + (LANE_COUNT - 1) * LANE_GAP


class _TimelineView(QGraphicsView):
    """QGraphicsView with Ctrl+Wheel zoom and horizontal clip dragging."""

    zoomRequested = Signal(float)
    clipDragMoved = Signal(int, int)      # (segment_id, live_offset_ms)
    clipDragEnded = Signal(int, int, int) # (segment_id, old_offset_ms, new_offset_ms)

    def __init__(self):
        super().__init__()
        self._drag_clip: ClipItem | None = None
        self._drag_press_scene_x: float = 0.0
        self._drag_start_offset_ms: int = 0
        self._dragging: bool = False
        self._drag_label: QGraphicsTextItem | None = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
            self.zoomRequested.emit(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self.scene().itemAt(scene_pos, self.transform())
        if (
            isinstance(item, ClipItem)
            and item.isSelected()
            and item.lane == 1
            and not item.locked
        ):
            self._drag_clip = item
            self._drag_press_scene_x = scene_pos.x()
            self._drag_start_offset_ms = item.segment.offset_ms
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._drag_clip is not None and event.buttons() & Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            dx = scene_pos.x() - self._drag_press_scene_x
            if not self._dragging and abs(dx) > _DRAG_THRESHOLD_PX:
                self._dragging = True
            if self._dragging:
                delta_ms = round(dx / BASE_PIXELS_PER_SECOND * 1000)
                snapped = _snap(self._drag_start_offset_ms + delta_ms)
                self.clipDragMoved.emit(self._drag_clip.segment.id, snapped)
                self._update_drag_label(self._drag_clip, snapped)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_clip is not None and event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                scene_pos = self.mapToScene(event.position().toPoint())
                dx = scene_pos.x() - self._drag_press_scene_x
                new_offset_ms = _snap(
                    self._drag_start_offset_ms + round(dx / BASE_PIXELS_PER_SECOND * 1000)
                )
                if new_offset_ms != self._drag_start_offset_ms:
                    self.clipDragEnded.emit(
                        self._drag_clip.segment.id,
                        self._drag_start_offset_ms,
                        new_offset_ms,
                    )
            self._remove_drag_label()
        self._drag_clip = None
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


class TimelineWidget(QWidget):
    """Horizontal timeline showing segment clips across two lanes.

    Owns the QGraphicsScene. Exposes:
    - ``load_segments(segments)`` — rebuild from a new segment list.
    - ``set_playhead_position(ms)`` — move the playhead.
    - ``selected_segment`` property — the currently selected Segment, or None.
    - ``apply_offset(segment_id, offset_ms)`` — reposition clips for a segment.
    """

    segmentSelected = Signal(object)  # emits Segment | None
    segmentOffsetChanged = Signal(int, int)   # (segment_id, offset_ms) live during drag
    segmentOffsetCommitted = Signal(int, int, int)  # (segment_id, old_ms, new_ms) on drag end

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom = 1.0
        self._duration_ms = 0
        self._clips_by_segment: dict[int, list[ClipItem]] = {}

        self._scene = QGraphicsScene(self)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._view = _TimelineView()
        self._view.setScene(self._scene)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setRenderHint(self._view.renderHints())
        self._view.zoomRequested.connect(self._apply_zoom)
        self._view.clipDragMoved.connect(self._on_clip_drag_moved)
        self._view.clipDragEnded.connect(self._on_clip_drag_ended)
        self._view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._playhead: QGraphicsLineItem | None = None
        self._draw_static_lanes(duration_ms=0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_segments(self, segments: list[Segment], duration_ms: int = 0) -> None:
        self._duration_ms = max(
            duration_ms,
            int(max((s.end for s in segments), default=0.0) * 1000),
        )
        self._rebuild_scene(segments)

    def set_playhead_position(self, position_ms: int) -> None:
        x = self._time_to_x(position_ms / 1000.0)
        if self._playhead is not None:
            self._playhead.setLine(x, 0, x, _scene_height())
        self._ensure_scene_rect_covers_time(position_ms / 1000.0)

    @property
    def selected_segment(self) -> Segment | None:
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, ClipItem):
                return item.segment
        return None

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

    def apply_locked(self, segment_id: int, locked: bool) -> None:
        """Update locked state on all clips for a segment."""
        for clip in self._clips_by_segment.get(segment_id, []):
            clip.set_locked(locked)

    def apply_status(self, segment_id: int, status: str | None) -> None:
        """Update the regeneration status badge on all clips for a segment."""
        for clip in self._clips_by_segment.get(segment_id, []):
            clip.set_status(status)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _time_to_x(self, seconds: float) -> float:
        return LANE_LABEL_WIDTH + SCENE_MARGIN_H + seconds * BASE_PIXELS_PER_SECOND

    def _apply_zoom(self, factor: float) -> None:
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        self._view.setTransform(QTransform().scale(self._zoom, 1.0))

    def _rebuild_scene(self, segments: list[Segment]) -> None:
        self._scene.clear()
        self._clips_by_segment = {}
        self._playhead = None
        self._draw_static_lanes(self._duration_ms)
        self._draw_clips(segments)
        self._draw_playhead()

    def _draw_static_lanes(self, duration_ms: int) -> None:
        scene_w = self._time_to_x(max(duration_ms / 1000.0, 30.0)) + SCENE_MARGIN_H
        scene_h = _scene_height()
        self._scene.setSceneRect(0, 0, scene_w, scene_h)

        for lane in range(LANE_COUNT):
            y = _lane_y(lane)
            bg = QGraphicsRectItem(0, y, scene_w, LANE_HEIGHT)
            bg.setBrush(QBrush(LANE_BG_COLORS[lane]))
            bg.setPen(QPen(Qt.PenStyle.NoPen))
            self._scene.addItem(bg)

            header = QGraphicsRectItem(0, y, LANE_LABEL_WIDTH, LANE_HEIGHT)
            header.setBrush(QBrush(HEADER_BG_COLOR))
            header.setPen(QPen(Qt.PenStyle.NoPen))
            self._scene.addItem(header)

            label = QGraphicsTextItem(LANE_NAMES[lane])
            label.setDefaultTextColor(QColor("#CCCCCC"))
            label.setPos(6, y + (LANE_HEIGHT - label.boundingRect().height()) / 2)
            self._scene.addItem(label)

    def _draw_clips(self, segments: list[Segment]) -> None:
        for segment in segments:
            duration = segment.end - segment.start
            width = duration * BASE_PIXELS_PER_SECOND
            effective_start = segment.start + segment.offset_ms / 1000.0
            x = self._time_to_x(effective_start)

            clips_for_segment = []
            for lane in range(LANE_COUNT):
                y = _lane_y(lane)
                clip = ClipItem(segment, x, y + 4, width, LANE_HEIGHT - 8, lane)
                self._scene.addItem(clip)
                clips_for_segment.append(clip)

            self._clips_by_segment[segment.id] = clips_for_segment

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
        self.segmentSelected.emit(self.selected_segment)

    def _on_clip_drag_moved(self, segment_id: int, offset_ms: int) -> None:
        self.apply_offset(segment_id, offset_ms)
        self.segmentOffsetChanged.emit(segment_id, offset_ms)

    def _on_clip_drag_ended(self, segment_id: int, old_offset_ms: int, new_offset_ms: int) -> None:
        self.segmentOffsetCommitted.emit(segment_id, old_offset_ms, new_offset_ms)

