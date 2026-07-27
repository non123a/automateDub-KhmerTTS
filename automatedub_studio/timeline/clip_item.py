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

SELECTED_PEN_COLOR = QColor("#FF8800")
SELECTED_PEN_WIDTH = 3
NORMAL_PEN_WIDTH = 1

CLIP_CORNER_RADIUS = 3.0


class ClipItem(QGraphicsRectItem):
    """A single segment rectangle on the timeline.

    Shows the segment ID as text and provides a tooltip with full details.
    Can be selected by clicking (highlight border changes).
    """

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

        if lane == 1:
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(LANE_COLORS.get(lane, QColor("#888888"))))
        self.setPen(QPen(QColor("#333333"), NORMAL_PEN_WIDTH))

        self._id_label = QGraphicsTextItem(str(segment.id), self)
        self._id_label.setDefaultTextColor(Qt.GlobalColor.white)
        self._center_label()
        self.setToolTip(self._build_tooltip(segment))

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
            if value:
                self.setPen(QPen(SELECTED_PEN_COLOR, SELECTED_PEN_WIDTH))
            else:
                self.setPen(QPen(QColor("#333333"), NORMAL_PEN_WIDTH))
        return super().itemChange(change, value)
