"""Reusable video player widget.

Wraps a single QMediaPlayer + QVideoWidget behind a small widget with its
own transport controls (Play/Pause/Stop/seek). Kept independent of
MainWindow and the project layer: it only knows about a video Path (or the
absence of one), never about Project, translation.json, or the timeline.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

NO_VIDEO_MESSAGE = "No video available"
_DEFAULT_TIME_LABEL = "00:00:00 / 00:00:00"

_STATUS_BY_PLAYBACK_STATE = {
    QMediaPlayer.PlaybackState.PlayingState: "Playing",
    QMediaPlayer.PlaybackState.PausedState: "Paused",
    QMediaPlayer.PlaybackState.StoppedState: "Stopped",
}


def format_time(milliseconds: int) -> str:
    """Format a millisecond position as HH:MM:SS."""
    total_seconds = max(0, milliseconds) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class VideoPlayerWidget(QWidget):
    """Video preview surface with Play/Pause/Stop/seek controls.

    Emits `playbackStatusChanged` with "Playing" / "Paused" / "Stopped" so a
    host window can mirror playback state in its own status bar without
    reaching into QMediaPlayer directly.
    """

    playbackStatusChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._slider_pressed = False
        self._has_video = False

        self._media_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._media_player.setAudioOutput(self._audio_output)

        self._video_widget = QVideoWidget()
        self._media_player.setVideoOutput(self._video_widget)

        self._message_label = QLabel(NO_VIDEO_MESSAGE)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._video_widget)
        self._stack.addWidget(self._message_label)
        self._stack.setCurrentWidget(self._message_label)

        self._play_button = QPushButton("Play")
        self._pause_button = QPushButton("Pause")
        self._stop_button = QPushButton("Stop")
        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._time_label = QLabel(_DEFAULT_TIME_LABEL)

        self._build_layout()
        self._wire_signals()
        self._set_controls_enabled(False)

    def _build_layout(self) -> None:
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._play_button)
        controls_layout.addWidget(self._pause_button)
        controls_layout.addWidget(self._stop_button)
        controls_layout.addWidget(self._seek_slider, 1)
        controls_layout.addWidget(self._time_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack, 1)
        layout.addLayout(controls_layout)

    def _wire_signals(self) -> None:
        self._play_button.clicked.connect(self.play)
        self._pause_button.clicked.connect(self.pause)
        self._stop_button.clicked.connect(self.stop)

        self._seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self._seek_slider.sliderReleased.connect(self._on_slider_released)
        self._seek_slider.sliderMoved.connect(self._on_slider_moved)

        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.durationChanged.connect(self._on_duration_changed)
        self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._media_player.errorOccurred.connect(self._on_error_occurred)

    def load_video(self, video_path: Path | None) -> None:
        """Load `video_path` for preview, or show the "no video" state.

        Never autoplays and never raises: a missing/corrupted/unsupported
        file surfaces as a friendly in-place message instead.
        """
        self._media_player.stop()

        if video_path is None:
            self._has_video = False
            self._show_message(NO_VIDEO_MESSAGE)
            self._set_controls_enabled(False)
            return

        self._has_video = True
        self._stack.setCurrentWidget(self._video_widget)
        self._set_controls_enabled(True)
        self._seek_slider.setRange(0, 0)
        self._time_label.setText(_DEFAULT_TIME_LABEL)
        self._media_player.setSource(QUrl.fromLocalFile(str(video_path)))

    def play(self) -> None:
        if self._has_video:
            self._media_player.play()

    def pause(self) -> None:
        if self._has_video:
            self._media_player.pause()

    def stop(self) -> None:
        if self._has_video:
            self._media_player.stop()

    def _show_message(self, message: str) -> None:
        self._message_label.setText(message)
        self._stack.setCurrentWidget(self._message_label)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._play_button.setEnabled(enabled)
        self._pause_button.setEnabled(enabled)
        self._stop_button.setEnabled(enabled)
        self._seek_slider.setEnabled(enabled)

    def _on_slider_pressed(self) -> None:
        self._slider_pressed = True

    def _on_slider_released(self) -> None:
        self._slider_pressed = False
        self._media_player.setPosition(self._seek_slider.value())

    def _on_slider_moved(self, position: int) -> None:
        self._media_player.setPosition(position)
        self._update_time_label(position, self._media_player.duration())

    def _on_position_changed(self, position: int) -> None:
        if not self._slider_pressed:
            self._seek_slider.setValue(position)
        self._update_time_label(position, self._media_player.duration())

    def _on_duration_changed(self, duration: int) -> None:
        self._seek_slider.setRange(0, duration)
        self._update_time_label(self._media_player.position(), duration)

    def _update_time_label(self, position: int, duration: int) -> None:
        self._time_label.setText(f"{format_time(position)} / {format_time(duration)}")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        status = _STATUS_BY_PLAYBACK_STATE.get(state)
        if status is not None:
            self.playbackStatusChanged.emit(status)

    def _on_error_occurred(
        self, error: QMediaPlayer.Error, error_string: str
    ) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        self._has_video = False
        self._set_controls_enabled(False)
        message = error_string or "Unable to play this video."
        self._show_message(f"Unable to play video:\n{message}")
