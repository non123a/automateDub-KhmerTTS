"""Tests for VideoPlayerWidget."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtMultimedia import QMediaPlayer

from automatedub_studio.playback.video_player import (
    NO_VIDEO_MESSAGE,
    VideoPlayerWidget,
    format_time,
)

# ---------------------------------------------------------------------------
# format_time
# ---------------------------------------------------------------------------


def test_format_time_zero():
    assert format_time(0) == "00:00:00"


def test_format_time_seconds():
    assert format_time(90_000) == "00:01:30"


def test_format_time_hours():
    assert format_time(3_723_000) == "01:02:03"


def test_format_time_negative_clamps_to_zero():
    assert format_time(-500) == "00:00:00"


# ---------------------------------------------------------------------------
# Widget construction
# ---------------------------------------------------------------------------


def test_video_player_widget_creates(qapp):
    widget = VideoPlayerWidget()
    assert widget is not None


def test_video_player_controls_disabled_on_creation(qapp):
    widget = VideoPlayerWidget()
    assert not widget._play_button.isEnabled()
    assert not widget._pause_button.isEnabled()
    assert not widget._stop_button.isEnabled()
    assert not widget._seek_slider.isEnabled()


def test_video_player_shows_no_video_message_on_creation(qapp):
    widget = VideoPlayerWidget()
    assert widget._message_label.text() == NO_VIDEO_MESSAGE
    assert widget._stack.currentWidget() is widget._message_label


def test_video_player_has_video_is_false_on_creation(qapp):
    widget = VideoPlayerWidget()
    assert widget._has_video is False


# ---------------------------------------------------------------------------
# load_video(None)
# ---------------------------------------------------------------------------


def test_load_video_none_keeps_controls_disabled(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(None)
    assert not widget._play_button.isEnabled()


def test_load_video_none_shows_no_video_message(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(None)
    assert widget._message_label.text() == NO_VIDEO_MESSAGE
    assert widget._stack.currentWidget() is widget._message_label


def test_load_video_none_clears_has_video(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    widget.load_video(None)
    assert widget._has_video is False


# ---------------------------------------------------------------------------
# load_video(path)
# ---------------------------------------------------------------------------


def test_load_video_path_enables_controls(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    assert widget._play_button.isEnabled()
    assert widget._pause_button.isEnabled()
    assert widget._stop_button.isEnabled()
    assert widget._seek_slider.isEnabled()


def test_load_video_path_sets_has_video(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    assert widget._has_video is True


def test_load_video_path_switches_to_video_surface(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    assert widget._stack.currentWidget() is widget._video_widget


def test_play_button_is_play_pause_toggle(qapp):
    widget = VideoPlayerWidget()
    assert widget._play_button.text() == "Play/Pause"
    assert widget._pause_button is widget._play_button


def test_toggle_play_pause_emits_play_when_stopped(qapp):
    widget = VideoPlayerWidget()
    received = []
    widget.playRequested.connect(lambda: received.append("play"))

    widget.toggle_play_pause()

    assert received == ["play"]


def test_toggle_play_pause_emits_pause_when_playing(qapp, monkeypatch):
    widget = VideoPlayerWidget()
    received = []
    widget.pauseRequested.connect(lambda: received.append("pause"))
    monkeypatch.setattr(VideoPlayerWidget, "is_playing", property(lambda self: True))

    widget.toggle_play_pause()

    assert received == ["pause"]


def test_stop_emits_seek_zero(qapp):
    widget = VideoPlayerWidget()
    received = []
    widget.seekRequested.connect(received.append)

    widget.stop()

    assert received == [0]


# ---------------------------------------------------------------------------
# Playback status signal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state, expected",
    [
        (QMediaPlayer.PlaybackState.PlayingState, "Playing"),
        (QMediaPlayer.PlaybackState.PausedState, "Paused"),
        (QMediaPlayer.PlaybackState.StoppedState, "Stopped"),
    ],
)
def test_playback_status_changed_signal(qapp, state, expected):
    widget = VideoPlayerWidget()
    received: list[str] = []
    widget.playbackStatusChanged.connect(received.append)
    widget._on_playback_state_changed(state)
    assert received == [expected]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_error_shows_message_and_disables_controls(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    assert widget._has_video is True

    widget._on_error_occurred(QMediaPlayer.Error.ResourceError, "File not found")
    assert widget._has_video is False
    assert not widget._play_button.isEnabled()
    assert "File not found" in widget._message_label.text()
    assert widget._stack.currentWidget() is widget._message_label


def test_no_error_does_not_change_state(qapp):
    widget = VideoPlayerWidget()
    widget.load_video(Path("/fake/video.mp4"))
    widget._on_error_occurred(QMediaPlayer.Error.NoError, "")
    assert widget._has_video is True
