"""Entry point for AutomateDub Studio."""

from __future__ import annotations

import sys

from automatedub_studio.app import create_application, create_initial_window
from automatedub_studio.ui.main_window import MainWindow


def main() -> int:
    app = create_application(sys.argv)
    editor_windows: list[MainWindow] = []
    window = create_initial_window()

    def open_editor(project_dir) -> None:
        editor = MainWindow()
        editor_windows.append(editor)
        editor.show()
        editor.open_project_path(project_dir)

    window.openProjectRequested.connect(open_editor)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
