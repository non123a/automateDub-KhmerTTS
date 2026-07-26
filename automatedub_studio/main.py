"""Entry point for AutomateDub Studio."""

from __future__ import annotations

import sys

from automatedub_studio.app import create_application
from automatedub_studio.ui.main_window import MainWindow


def main() -> int:
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
