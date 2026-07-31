"""Centralized application notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Notification:
    level: str
    message: str
    created_at: str


class NotificationCenter(QObject):
    notificationPosted = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notifications: list[Notification] = []

    def post(self, level: str, message: str) -> Notification:
        notification = Notification(
            level=level,
            message=message,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        self.notifications.append(notification)
        self.notificationPosted.emit(notification)
        return notification

    def info(self, message: str) -> Notification:
        return self.post("info", message)

    def warning(self, message: str) -> Notification:
        return self.post("warning", message)

    def error(self, message: str) -> Notification:
        return self.post("error", message)
