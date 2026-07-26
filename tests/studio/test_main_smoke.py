from __future__ import annotations

from automatedub_studio.app import create_application
from automatedub_studio.ui.main_window import MainWindow


def test_application_launches_and_closes_cleanly(qapp):
    app = create_application([])
    window = MainWindow()

    window.show()
    assert window.isVisible() is True

    window.close()
    assert window.isVisible() is False
    assert app is not None
