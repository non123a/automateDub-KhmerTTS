"""First-run wizard for application setup."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QWizard,
    QWizardPage,
)

from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.settings.manager import SettingsManager


class ProjectFolderPage(QWizardPage):
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setTitle("Default Project Folder")

        layout = QFormLayout(self)
        self.folder_edit = QLineEdit(settings_manager.data.default_project_folder)
        layout.addRow("Project Folder", self._path_row())

    def _path_row(self):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.folder_edit)
        button = QPushButton("Browse...")
        button.clicked.connect(self._browse)
        row.addWidget(button)
        return container

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Default Project Folder")
        if directory:
            self.folder_edit.setText(directory)


class ProviderSetupPage(QWizardPage):
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.provider_manager = ProviderManager(settings_manager.tool_config())
        self.setTitle("AI Providers")

        layout = QFormLayout(self)
        self.stt_combo = QComboBox()
        self.translation_combo = QComboBox()
        self.tts_combo = QComboBox()
        _populate(self.stt_combo, self.provider_manager.available_stt_providers())
        _populate(
            self.translation_combo,
            self.provider_manager.available_translation_providers(),
        )
        _populate(self.tts_combo, self.provider_manager.available_tts_providers())
        layout.addRow("STT Provider", self.stt_combo)
        layout.addRow("Translation Provider", self.translation_combo)
        layout.addRow("TTS Provider", self.tts_combo)

        self.status_label = QLabel("Connectivity has not been tested.")
        layout.addRow("Status", self.status_label)
        self.test_button = QPushButton("Test Connectivity")
        self.test_button.clicked.connect(self._test_connectivity)
        layout.addRow("", self.test_button)

    def _test_connectivity(self) -> None:
        errors: list[str] = []
        for label, provider in (
            ("STT", self.provider_manager.stt_provider(self.stt_combo.currentData())),
            (
                "Translation",
                self.provider_manager.translation_provider(self.translation_combo.currentData()),
            ),
            ("TTS", self.provider_manager.tts_provider(self.tts_combo.currentData())),
        ):
            try:
                provider.validate()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{label}: {exc}")
        self.status_label.setText("Connected" if not errors else "\n".join(errors))


class FirstRunWizard(QWizard):
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Set Up AutomateDub Studio")
        self.project_folder_page = ProjectFolderPage(settings_manager, self)
        self.provider_page = ProviderSetupPage(settings_manager, self)
        self.addPage(self.project_folder_page)
        self.addPage(self.provider_page)

    def accept(self) -> None:
        folder = self.project_folder_page.folder_edit.text().strip()
        if folder:
            self.settings_manager.set_default_project_folder(Path(folder).expanduser())
        self.settings_manager.set_provider_selection(
            stt_provider_id=self.provider_page.stt_combo.currentData(),
            translation_provider_id=self.provider_page.translation_combo.currentData(),
            tts_provider_id=self.provider_page.tts_combo.currentData(),
            selected_voice=self.settings_manager.data.selected_voice,
        )
        self.settings_manager.set_first_run_completed(True)
        super().accept()


def _populate(combo: QComboBox, descriptors) -> None:
    for descriptor in descriptors:
        combo.addItem(descriptor.name, descriptor.id)
