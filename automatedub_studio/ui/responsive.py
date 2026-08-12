"""Small cross-platform helpers for resizable Studio windows."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QScrollArea, QWidget


def scrollable_content(content: QWidget) -> QScrollArea:
    """Return a shrinkable scroll area that owns dialog body content.

    Keep primary actions outside this area so they remain reachable when a
    laptop display cannot accommodate the whole form at once.
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


def set_responsive_window_size(
    window: QWidget,
    *,
    minimum: QSize,
    preferred: QSize,
) -> None:
    """Set practical logical-pixel sizes without exceeding an active screen."""
    window.setMinimumSize(minimum)
    available = _available_geometry(window)
    width = min(preferred.width(), available.width())
    height = min(preferred.height(), available.height())
    window.resize(max(minimum.width(), width), max(minimum.height(), height))


def restore_visible_geometry(window: QWidget, geometry: object) -> bool:
    """Restore saved geometry only when it intersects a current display."""
    if not geometry or not window.restoreGeometry(geometry):
        return False
    frame = window.frameGeometry()
    screens = QGuiApplication.screens()
    if any(screen.availableGeometry().intersects(frame) for screen in screens):
        return True

    available = _available_geometry(window)
    width = min(max(window.minimumWidth(), window.width()), available.width())
    height = min(max(window.minimumHeight(), window.height()), available.height())
    window.resize(width, height)
    window.move(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )
    return False


def _available_geometry(window: QWidget) -> QRect:
    screen = QGuiApplication.screenAt(window.frameGeometry().center())
    if screen is None:
        screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None:  # pragma: no cover - Qt always supplies a primary screen
        return QRect(0, 0, 1280, 720)
    return screen.availableGeometry()
