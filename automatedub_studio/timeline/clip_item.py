"""ClipItem: QGraphicsRectItem representing one segment on the timeline."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

from automatedub_studio.project.models import Segment

LANE_COLORS = {
    0: QColor("#5094D9"),
    1: QColor("#60C080"),
}
LOCKED_COLOR = QColor("#8888AA")

SELECTED_PEN_COLOR = QColor("#FF8800")
SELECTED_PEN_WIDTH = 3
NORMAL_PEN_WIDTH = 1

CLIP_CORNER_RADIUS = 3.0


class ClipItem(QGraphicsRectItem):
    """A single segment rectangle on the timeline."""

    def __init__(
        self,
        segment: Segment,
        x: float,
        y: float,
        width: float,
        height: float,
        lane: int,
    ):
        super().__init__(x, y, width, height)
        self.segment = segment
        self.lane = lane
        self.locked = False

        if lane == 1:
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(LANE_COLORS.get(lane, QColor("#888888"))))
        self.setPen(QPen(QColor("#333333"), NORMAL_PEN_WIDTH))

        self._id_label = QGraphicsTextItem(str(segment.id), self)
        self._id_label.setDefaultTextColor(Qt.GlobalColor.white)
        self._center_label()

        self._lock_label: QGraphicsTextItem | None = None

        self.setToolTip(self._build_tooltip(segment))

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        base_color = LOCKED_COLOR if locked else LANE_COLORS.get(self.lane, QColor("#888888"))
        self.setBrush(QBrush(base_color))
        if locked and self._lock_label is None:
            self._lock_label = QGraphicsTextItem("\U0001f512", self)
            self._lock_label.setDefaultTextColor(Qt.GlobalColor.white)
            r = self.rect()
            self._lock_label.setPos(r.x() + r.width() - 18, r.y() + 2)
        elif not locked and self._lock_label is not None:
            self._lock_label.setParentItem(None)
            self._lock_label = None

    def _center_label(self) -> None:
        rect = self.rect()
        label_rect = self._id_label.boundingRect()
        self._id_label.setPos(
            rect.x() + (rect.width() - label_rect.width()) / 2,
            rect.y() + (rect.height() - label_rect.height()) / 2,
        )

    @staticmethod
    def _build_tooltip(segment: Segment) -> str:
        duration = segment.end - segment.start
        lines = [
            f"ID: {segment.id}",
            f"Start: {segment.start:.3f}s",
            f"End:   {segment.end:.3f}s",
            f"Duration: {duration:.3f}s",
        ]
        if segment.source_text:
            lines.insert(1, f"Source: {segment.source_text}")
        lines.append(f"Target: {segment.target_text}")
        return "\n".join(lines)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemSelectedHasChanged:
            pen_color = SELECTED_PEN_COLOR if value else QColor("#333333")
            self.setPen(QPen(pen_color, SELECTED_PEN_WIDTH if value else NORMAL_PEN_WIDTH))
        return super().itemChange(change, value)
