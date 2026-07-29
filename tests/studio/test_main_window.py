from __future__ import annotations

from conftest import make_valid_project
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMenu

from automatedub_studio.playback.playback_controller import PlaybackMode
from automatedub_studio.ui import main_window as main_window_module
from automatedub_studio.ui.main_window import WINDOW_TITLE, MainWindow


def _memory_settings() -> QSettings:
    return QSettings("automatedub-test", "MainWindowTest")


def _menu_titles(window: MainWindow) -> list[str]:
    return [menu.title().replace("&", "") for menu in window.menuBar().findChildren(QMenu)]


def _action_texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_window_title(qapp):
    window = MainWindow(settings=_memory_settings())

    assert window.windowTitle() == WINDOW_TITLE == "AutomateDub Studio"


def test_menu_bar_has_file_and_help_menus(qapp):
    window = MainWindow(settings=_memory_settings())

    assert "File" in _menu_titles(window)
    assert "Help" in _menu_titles(window)


def test_file_menu_has_open_project_and_exit(qapp):
    window = MainWindow(settings=_memory_settings())
    file_menu = next(m for m in window.menuBar().findChildren(QMenu) if m.title() == "&File")

    expected = ["Open Project...", "Save Project", "Export Video...", "Exit"]
    assert _action_texts(file_menu) == expected
    assert window.open_project_action.isEnabled() is True


def test_help_menu_has_about(qapp):
    window = MainWindow(settings=_memory_settings())
    help_menu = next(m for m in window.menuBar().findChildren(QMenu) if m.title() == "&Help")

    assert _action_texts(help_menu) == ["About"]


def test_status_bar_shows_ready(qapp):
    window = MainWindow(settings=_memory_settings())

    assert window.statusBar().currentMessage() == "Ready"


def test_exit_action_closes_window(qapp):
    window = MainWindow(settings=_memory_settings())
    window.show()

    window.exit_action.trigger()

    assert window.isVisible() is False


def test_geometry_persists_across_instances(qapp, tmp_path):
    settings_path = tmp_path / "settings.ini"

    settings1 = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window1 = MainWindow(settings=settings1)
    window1.resize(800, 600)
    window1.close()
    settings1.sync()

    settings2 = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window2 = MainWindow(settings=settings2)

    assert abs(window2.size().width() - 800) <= 5
    assert abs(window2.size().height() - 600) <= 5


def test_open_project_path_updates_window_title(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=7)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.windowTitle() == f"{WINDOW_TITLE} - output"


def test_open_project_path_updates_status_bar(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=7)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    message = window.statusBar().currentMessage()
    assert "Project Loaded" in message
    assert "Segments: 7" in message
    assert "TTS Files: 7" in message
    assert "Audio: ✓" in message
    assert "Video: Missing" in message


def test_open_project_path_reports_video_found(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, with_video=True)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert "Video: Found" in window.statusBar().currentMessage()


def test_open_project_path_populates_info_panel(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=4)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.info_panel.project_path_label.text() == str(project_dir)
    assert window.info_panel.segment_count_label.text() == "4"
    assert window.info_panel.tts_count_label.text() == "4"
    assert window.info_panel.video_label.text() == "Missing"


def test_open_project_path_stores_project(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.project is not None
    assert window.project.project_path == project_dir
    assert window.project.segment_count == 2


def test_open_project_path_invalid_project_shows_message_and_does_not_crash(
    qapp, tmp_path, monkeypatch
):
    shown_messages = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        staticmethod(lambda *args, **kwargs: shown_messages.append(args)),
    )
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(tmp_path / "not-a-project")

    assert len(shown_messages) == 1
    assert window.project is None
    assert window.statusBar().currentMessage() == "Ready"
    assert window.windowTitle() == WINDOW_TITLE


# ---------------------------------------------------------------------------
# Milestone 3: Video player integration
# ---------------------------------------------------------------------------


def test_main_window_has_video_player(qapp):
    from automatedub_studio.playback.video_player import VideoPlayerWidget

    window = MainWindow(settings=_memory_settings())
    assert isinstance(window.video_player, VideoPlayerWidget)


def test_main_window_video_player_is_central_widget(qapp):
    from PySide6.QtWidgets import QSplitter

    window = MainWindow(settings=_memory_settings())
    central = window.centralWidget()
    assert isinstance(central, QSplitter)
    # The video player now lives inside a container widget (alongside the
    # playback mode selector) rather than directly in the splitter.
    assert central.isAncestorOf(window.video_player)


def test_open_project_no_video_disables_player_controls(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, with_video=False)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.video_player._has_video is False
    assert not window.video_player._play_button.isEnabled()


def test_open_project_with_video_enables_player_controls(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, with_video=True)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.video_player._has_video is True
    assert window.video_player._play_button.isEnabled()


def test_open_project_with_video_switches_to_video_surface(qapp, tmp_path):

    project_dir = make_valid_project(tmp_path, with_video=True)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert window.video_player._stack.currentWidget() is window.video_player._video_widget


# ---------------------------------------------------------------------------
# Studio V2 — Professional Playback
# ---------------------------------------------------------------------------


def test_mode_selector_has_four_modes(qapp):
    window = MainWindow(settings=_memory_settings())
    labels = [window.mode_selector.itemText(i) for i in range(window.mode_selector.count())]
    assert labels == ["Original", "Mixed", "Khmer TTS", "Timeline Preview"]


def test_mode_selector_starts_on_original(qapp):
    window = MainWindow(settings=_memory_settings())
    assert window.playback_controller.mode == PlaybackMode.ORIGINAL
    assert window.mode_selector.currentText() == "Original"


def test_snap_toolbar_action_toggles_timeline_snapping(qapp):
    window = MainWindow(settings=_memory_settings())

    assert window.snap_action.text() == "Snap: OFF"
    assert window.timeline._view._snap_enabled is False

    window.snap_action.trigger()

    assert window.snap_action.text() == "Snap: ON"
    assert window.timeline._view._snap_enabled is True


def test_selecting_mixed_mode_switches_controller(qapp):
    window = MainWindow(settings=_memory_settings())
    window.mode_selector.setCurrentIndex(window.mode_selector.findData(PlaybackMode.MIXED))
    assert window.playback_controller.mode == PlaybackMode.MIXED


def test_selecting_timeline_preview_mode_switches_controller(qapp):
    window = MainWindow(settings=_memory_settings())
    index = window.mode_selector.findData(PlaybackMode.TIMELINE_PREVIEW)
    window.mode_selector.setCurrentIndex(index)
    assert window.playback_controller.mode == PlaybackMode.TIMELINE_PREVIEW


def _write_valid_wav(path, seconds: float = 0.5, frame_rate: int = 16000) -> None:
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * int(frame_rate * seconds))


def test_open_project_populates_timeline_preview_tracks(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=3)
    for wav_path in (project_dir / "tts").glob("*.wav"):
        _write_valid_wav(wav_path)
    window = MainWindow(settings=_memory_settings())

    window.open_project_path(project_dir)

    assert len(window.playback_controller._timeline_tracks) > 0


def test_double_clicking_clip_plays_it_in_isolation(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    for wav_path in (project_dir / "tts").glob("*.wav"):
        _write_valid_wav(wav_path)
    window = MainWindow(settings=_memory_settings())
    window.open_project_path(project_dir)

    window._on_clip_play_requested(0)

    from PySide6.QtCore import QUrl

    from automatedub.vertical_slice.tts import tts_segment_output_path

    expected = tts_segment_output_path(window.project.tts_directory, 0)
    assert window.playback_controller._audio_player.source() == QUrl.fromLocalFile(str(expected))


def test_offset_edit_refreshes_timeline_preview_tracks(qapp, tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    for wav_path in (project_dir / "tts").glob("*.wav"):
        _write_valid_wav(wav_path)
    window = MainWindow(settings=_memory_settings())
    window.open_project_path(project_dir)

    baseline = next(t for t in window.playback_controller._timeline_tracks if t.id == 0)
    baseline_delay_ms = baseline.delay_ms

    window._on_offset_committed(0, 0, 250)

    track = next(t for t in window.playback_controller._timeline_tracks if t.id == 0)
    assert track.delay_ms == baseline_delay_ms + 250
