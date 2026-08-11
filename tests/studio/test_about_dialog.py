from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton

from automatedub_studio.ui.about_dialog import APP_DESCRIPTION, APP_NAME, APP_VERSION, AboutDialog


def test_about_dialog_shows_expected_text(qapp):
    dialog = AboutDialog()
    labels_text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert APP_NAME in labels_text
    assert APP_VERSION in labels_text
    assert APP_DESCRIPTION in labels_text


def test_about_dialog_exposes_beta_support_links(qapp):
    dialog = AboutDialog()
    labels = {button.text() for button in dialog.findChildren(QPushButton)}

    assert {"GitHub", "Website", "Report Bug"}.issubset(labels)
