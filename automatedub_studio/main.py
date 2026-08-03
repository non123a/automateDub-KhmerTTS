"""Entry point for AutomateDub Studio."""

from __future__ import annotations

import sys

from automatedub_studio.app import create_application, create_initial_window, startup_paths
from automatedub_studio.settings.manager import SettingsManager
from automatedub_studio.ui.main_window import MainWindow


def main() -> int:
    app = create_application(sys.argv)
    editor_windows: list[MainWindow] = []
    settings_manager = SettingsManager()
    window = create_initial_window(settings_manager=settings_manager)

    def open_editor(project_dir) -> None:
        editor = MainWindow(tool_config=settings_manager.tool_config())
        editor_windows.append(editor)
        editor.show()
        editor.open_project_path(project_dir)

    window.openProjectRequested.connect(open_editor)
    if hasattr(app, "fileOpenRequested"):
        app.fileOpenRequested.connect(window.open_path)
    window.show()
    window.maybe_show_first_run_wizard()
    for path in startup_paths(sys.argv):
        window.open_path(path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
