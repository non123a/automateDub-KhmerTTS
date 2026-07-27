"""Timeline widget: QGraphicsView-based visualization of segment timing.

Two lanes (Original Transcript, Khmer TTS) display the same timing until
a future milestone separates them. Ctrl+Wheel zooms horizontally; the
playhead tracks the video player's position.
"""

from __future__ import annotations

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


def _lane_y(lane: int) -> float:
    """Top y-coordinate (scene space) for the given lane index."""
    return SCENE_MARGIN_V + lane * (LANE_HEIGHT + LANE_GAP)


def _scene_height() -> float:
    return SCENE_MARGIN_V * 2 + LANE_COUNT * LANE_HEIGHT + (LANE_COUNT - 1) * LANE_GAP


class _TimelineView(QGraphicsView):
    """QGraphicsView that intercepts Ctrl+Wheel for horizontal zoom."""

    zoomRequested = Signal(float)  # emits zoom multiplier (>1 = in, <1 = out)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
            self.zoomRequested.emit(factor)
            event.accept()
        else:
            super().wheelEvent(event)


class TimelineWidget(QWidget):
    """Horizontal timeline showing segment clips across two lanes.

    Owns the QGraphicsScene. Exposes:
    - ``load_segments(segments)`` — rebuild from a new segment list.
    - ``set_playhead_position(ms)`` — move the playhead (called by MainWindow
      whenever the video player position changes).
    - ``selected_segment`` property — the currently selected Segment, or None.
    """

    segmentSelected = Signal(object)  # emits Segment | None

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom = 1.0
        self._duration_ms = 0
        self._clips: list[ClipItem] = []

        self._scene = QGraphicsScene(self)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._view = _TimelineView()
        self._view.setScene(self._scene)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setRenderHint(self._view.renderHints())
        self._view.zoomRequested.connect(self._apply_zoom)
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
        self._clips = []
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
            x = self._time_to_x(segment.start)

            for lane in range(LANE_COUNT):
                y = _lane_y(lane)
                clip = ClipItem(segment, x, y + 4, width, LANE_HEIGHT - 8, lane)
                self._scene.addItem(clip)
                self._clips.append(clip)

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
