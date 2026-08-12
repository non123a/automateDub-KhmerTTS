"""Application Settings window."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.providers.registry import ProviderConfigField, ProviderDescriptor
from automatedub_studio.settings.manager import SettingsManager


class SettingsWindow(QDialog):
    """Configures application preferences and provider settings."""

    def __init__(
        self,
        settings_manager: SettingsManager | None = None,
        provider_manager: ProviderManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.settings_manager = settings_manager or SettingsManager()
        self.provider_manager = provider_manager or ProviderManager(
            self.settings_manager.tool_config()
        )
        self.provider_inputs: dict[tuple[str, ...], QLineEdit] = {}

        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.addTab(self._build_ai_providers_tab(), "AI Providers")
        self.tabs.addTab(self._build_voices_tab(), "Voices")
        self.tabs.addTab(self._build_models_tab(), "Models")
        self.tabs.addTab(self._build_cache_tab(), "Cache")
        self.tabs.addTab(self._build_logs_tab(), "Logs")
        self.tabs.addTab(self._build_advanced_tab(), "Advanced")

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("settings_save_button")
        self.save_button.clicked.connect(self.save_settings)
        button_row.addWidget(self.save_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._refresh_provider_config()

    def _build_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        self.cache_dir_edit = QLineEdit(self.settings_manager.data.cache_dir)
        self.cache_dir_edit.setObjectName("settings_cache_dir_edit")
        layout.addRow("Cache Directory", self.cache_dir_edit)
        self.log_dir_edit = QLineEdit(self.settings_manager.data.log_dir)
        self.log_dir_edit.setObjectName("settings_log_dir_edit")
        layout.addRow("Log Directory", self.log_dir_edit)
        return widget

    def _build_ai_providers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        self.stt_combo = self._provider_combo(
            self.provider_manager.available_stt_providers(),
            self.settings_manager.data.stt_provider_id,
        )
        self.stt_combo.setObjectName("settings_stt_provider_combo")
        self.translation_combo = self._provider_combo(
            self.provider_manager.available_translation_providers(),
            self.settings_manager.data.translation_provider_id,
        )
        self.translation_combo.setObjectName("settings_translation_provider_combo")
        self.tts_combo = self._provider_combo(
            self.provider_manager.available_tts_providers(),
            self.settings_manager.data.tts_provider_id,
        )
        self.tts_combo.setObjectName("settings_tts_provider_combo")
        self.stt_combo.currentIndexChanged.connect(self._provider_selection_changed)
        self.translation_combo.currentIndexChanged.connect(self._provider_selection_changed)
        self.tts_combo.currentIndexChanged.connect(self._tts_provider_selection_changed)
        form.addRow("STT Provider", self.stt_combo)
        form.addRow("Translation Provider", self.translation_combo)
        form.addRow("TTS Provider", self.tts_combo)
        layout.addLayout(form)

        self.selected_provider_label = QLabel("Selected provider: Not tested")
        self.selected_provider_label.setObjectName("settings_selected_provider_label")
        self.selected_provider_label.setWordWrap(True)
        layout.addWidget(self.selected_provider_label)
        self.connection_status_label = QLabel("Connection status: Not tested")
        self.connection_status_label.setObjectName("settings_connection_status_label")
        self.connection_status_label.setWordWrap(True)
        layout.addWidget(self.connection_status_label)
        self.stt_status_label = QLabel("STT status: Not tested")
        self.stt_status_label.setObjectName("settings_stt_status_label")
        self.stt_status_label.setWordWrap(True)
        layout.addWidget(self.stt_status_label)
        self.tts_status_label = QLabel("TTS status: Not tested")
        self.tts_status_label.setObjectName("settings_tts_status_label")
        self.tts_status_label.setWordWrap(True)
        layout.addWidget(self.tts_status_label)
        self.provider_version_label = QLabel("Provider version: unavailable")
        self.provider_version_label.setObjectName("settings_provider_version_label")
        layout.addWidget(self.provider_version_label)

        self.provider_config_container = QWidget()
        self.provider_config_layout = QVBoxLayout(self.provider_config_container)
        layout.addWidget(self.provider_config_container)

        self.diagnostics_label = QLabel("Diagnostics: Not tested")
        self.diagnostics_label.setObjectName("settings_diagnostics_label")
        self.diagnostics_label.setWordWrap(True)
        layout.addWidget(self.diagnostics_label)
        return widget

    def _build_voices_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.voice_status_label = QLabel("Voices are shown after provider validation.")
        self.voice_status_label.setWordWrap(True)
        self.voice_status_label.setObjectName("settings_voice_status_label")
        layout.addWidget(self.voice_status_label)
        self.voice_count_label = QLabel("Voices: 0")
        self.voice_count_label.setObjectName("settings_voice_count_label")
        layout.addWidget(self.voice_count_label)
        self.voice_refresh_label = QLabel("Last refresh: never")
        self.voice_refresh_label.setObjectName("settings_voice_refresh_label")
        layout.addWidget(self.voice_refresh_label)
        self.voice_list = QListWidget()
        self.voice_list.setObjectName("settings_voice_list")
        layout.addWidget(self.voice_list)
        refresh_button = QPushButton("Refresh Voices")
        refresh_button.setObjectName("settings_refresh_voices_button")
        refresh_button.clicked.connect(self.refresh_voices)
        layout.addWidget(refresh_button)
        return widget

    def _build_models_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.models_label = QLabel("Models are configured per provider.")
        self.models_label.setObjectName("settings_models_label")
        layout.addWidget(self.models_label)
        layout.addStretch(1)
        return widget

    def _build_cache_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.cache_usage_label = QLabel()
        self.cache_usage_label.setObjectName("settings_cache_usage_label")
        layout.addWidget(self.cache_usage_label)
        clear_button = QPushButton("Clear Cache")
        clear_button.setObjectName("settings_clear_cache_button")
        clear_button.clicked.connect(self.clear_cache)
        layout.addWidget(clear_button)
        layout.addStretch(1)
        self.refresh_cache_usage()
        return widget

    def _build_logs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.log_errors = QTextEdit()
        self.log_errors.setObjectName("settings_log_errors")
        self.log_errors.setReadOnly(True)
        layout.addWidget(self.log_errors)
        refresh_button = QPushButton("Refresh Recent Errors")
        refresh_button.clicked.connect(self.refresh_logs)
        layout.addWidget(refresh_button)
        open_button = QPushButton("Open Log Directory")
        open_button.clicked.connect(self.open_log_directory)
        layout.addWidget(open_button)
        self.refresh_logs()
        return widget

    def _build_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Advanced settings will be added as backend capabilities mature.")
        label.setObjectName("settings_advanced_label")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return widget

    @staticmethod
    def _provider_combo(
        descriptors: list[ProviderDescriptor],
        selected_id: str,
    ) -> QComboBox:
        combo = QComboBox()
        for descriptor in descriptors:
            combo.addItem(descriptor.name, descriptor.id)
        index = combo.findData(selected_id)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _refresh_provider_config(self) -> None:
        while self.provider_config_layout.count():
            item = self.provider_config_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()
        self.provider_inputs.clear()
        for descriptor in self._selected_descriptors():
            group = QWidget()
            form = QFormLayout(group)
            form.addRow(QLabel(f"<b>{descriptor.name}</b>"))
            for field in descriptor.config_fields:
                edit = self._field_editor(descriptor, field)
                form.addRow(field.label, edit)
                self.provider_inputs[(descriptor.kind, descriptor.id, field.key)] = edit
                self.provider_inputs[(descriptor.id, field.key)] = edit
            test_button = QPushButton("Test Connection")
            test_button.clicked.connect(
                lambda _checked=False, current=descriptor: self.test_provider(current)
            )
            form.addRow(test_button)
            self.provider_config_layout.addWidget(group)
        self._update_selected_provider_label()
        self.connection_status_label.setText("Connection status: Not tested")

    def _field_editor(
        self,
        descriptor: ProviderDescriptor,
        field: ProviderConfigField,
    ) -> QLineEdit:
        value = self.settings_manager.provider_setting(
            descriptor.id,
            field.key,
            secret=field.secret,
        ) or field.default
        edit = QLineEdit(value)
        edit.setPlaceholderText(field.placeholder)
        edit.setObjectName(f"settings_{descriptor.id}_{field.key}")
        if field.secret:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        return edit

    def _selected_descriptors(self) -> list[ProviderDescriptor]:
        selections = [
            (
                self.provider_manager.available_stt_providers(),
                self.stt_combo.currentData(),
            ),
            (
                self.provider_manager.available_translation_providers(),
                self.translation_combo.currentData(),
            ),
            (
                self.provider_manager.available_tts_providers(),
                self.tts_combo.currentData(),
            ),
        ]
        descriptors: list[ProviderDescriptor] = []
        for available, selected_id in selections:
            descriptor = next(
                (item for item in available if item.id == selected_id),
                None,
            )
            if descriptor is not None:
                descriptors.append(descriptor)
        return descriptors

    def save_settings(self) -> None:
        data = self._persist_current_provider_state(selected_voice=self._selected_voice_id())
        self.settings_manager.save(
            type(data)(
                stt_provider_id=data.stt_provider_id,
                translation_provider_id=data.translation_provider_id,
                tts_provider_id=data.tts_provider_id,
                selected_voice=data.selected_voice,
                default_project_folder=data.default_project_folder,
                first_run_completed=data.first_run_completed,
                provider_settings=data.provider_settings,
                cache_dir=self.cache_dir_edit.text(),
                log_dir=self.log_dir_edit.text(),
                advanced=data.advanced,
            )
        )
        self.diagnostics_label.setText("Settings saved.")
        self.provider_manager = ProviderManager(
            self.settings_manager.tool_config(),
            registry=self.provider_manager.registry,
        )
        self.refresh_voices()

    def refresh_voices(self) -> None:
        self._persist_current_provider_state(selected_voice=self._selected_voice_id())
        self.provider_manager = ProviderManager(
            self.settings_manager.tool_config(),
            registry=self.provider_manager.registry,
        )
        self.voice_status_label.setText("Loading voices...")
        self.voice_list.clear()
        self.voice_count_label.setText("Voices: 0")
        QApplication.processEvents()
        try:
            provider = self.provider_manager.tts_provider(str(self.tts_combo.currentData()))
            provider.validate()
            voices = provider.list_voices()
        except Exception as exc:  # noqa: BLE001
            self.voice_status_label.setText(f"Unable to load voices: {exc}")
            self.voice_list.addItem("Unable to load voices.")
            self.voice_refresh_label.setText(f"Last refresh: {_now_text()}")
            self.connection_status_label.setText(
                f"Connection status: Connection Failed - {exc}"
            )
            self.tts_status_label.setText(f"TTS status: Connection Failed - {exc}")
            return
        if not voices:
            self.voice_status_label.setText("No voices available from this provider.")
            self.voice_list.addItem("No voices available.")
            self.voice_count_label.setText("Voices: 0")
            self.voice_refresh_label.setText(f"Last refresh: {_now_text()}")
            return
        self.voice_status_label.setText(f"Loaded {len(voices)} voice(s).")
        for voice in voices:
            language = voice.language or "unknown"
            item_text = f"{voice.name} | {language} | preview: unavailable"
            self.voice_list.addItem(item_text)
            item = self.voice_list.item(self.voice_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, voice.id)
            if voice.id == self.settings_manager.data.selected_voice:
                self.voice_list.setCurrentItem(item)
        self.voice_count_label.setText(f"Voices: {len(voices)}")
        self.voice_refresh_label.setText(f"Last refresh: {_now_text()}")

    def test_provider(self, descriptor: ProviderDescriptor) -> None:
        self._persist_current_provider_state(selected_voice=self._selected_voice_id())
        self.provider_manager = ProviderManager(
            self.settings_manager.tool_config(),
            registry=self.provider_manager.registry,
        )
        started = time.monotonic()
        try:
            provider = self._provider_for_descriptor(descriptor)
            provider.validate()
        except Exception as exc:  # noqa: BLE001
            self.diagnostics_label.setText(
                f"{descriptor.name}: Connection Failed: {exc}"
            )
            self.selected_provider_label.setText(f"Selected provider: {descriptor.name}")
            self.connection_status_label.setText(
                f"Connection status: Connection Failed - {exc}"
            )
            self._set_provider_status(descriptor, f"Connection Failed - {exc}")
            return
        latency_ms = round((time.monotonic() - started) * 1000)
        extra = ""
        voice_count: int | None = None
        if descriptor.kind == "tts":
            try:
                voices = self._provider_for_descriptor(descriptor).list_voices()
                voice_count = len(voices)
                extra = f", voices: {voice_count}"
                self.refresh_voices()
            except Exception as exc:  # noqa: BLE001
                extra = f", voices unavailable: {exc}"
        self.diagnostics_label.setText(
            f"{descriptor.name}: Connected, latency {latency_ms} ms{extra}"
        )
        self.selected_provider_label.setText(f"Selected provider: {descriptor.name}")
        self.connection_status_label.setText(
            f"Connection status: Connected, latency {latency_ms} ms"
        )
        self._set_provider_status(descriptor, f"Connected, latency {latency_ms} ms")
        if voice_count is not None:
            self.voice_count_label.setText(f"Voices: {voice_count}")
        self.provider_version_label.setText(
            f"Provider version: {getattr(provider, 'version', 'unavailable')}"
        )

    def _provider_for_descriptor(self, descriptor: ProviderDescriptor):
        if descriptor.kind == "stt":
            return self.provider_manager.stt_provider(descriptor.id)
        if descriptor.kind == "translation":
            return self.provider_manager.translation_provider(descriptor.id)
        return self.provider_manager.tts_provider(descriptor.id)

    def _set_provider_status(self, descriptor: ProviderDescriptor, status: str) -> None:
        if descriptor.kind == "stt":
            self.stt_status_label.setText(f"STT status: {status}")
        elif descriptor.kind == "tts":
            self.tts_status_label.setText(f"TTS status: {status}")

    def refresh_cache_usage(self) -> None:
        self.cache_usage_label.setText(
            f"Cache usage: {self.settings_manager.cache_usage_bytes()} bytes"
        )

    def clear_cache(self) -> None:
        self.settings_manager.clear_cache()
        self.refresh_cache_usage()

    def refresh_logs(self) -> None:
        lines = self.settings_manager.recent_log_errors()
        self.log_errors.setPlainText("\n".join(lines) if lines else "No recent pipeline errors.")

    def open_log_directory(self) -> None:
        path = Path(self.settings_manager.data.log_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _selected_voice_id(self) -> str | None:
        item = self.voice_list.currentItem()
        if item is None:
            return self.settings_manager.data.selected_voice
        voice_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(voice_id, str) and voice_id:
            return voice_id
        text = item.text()
        return text.split("|", 1)[0].strip() or None

    def _provider_selection_changed(self, _index: int = 0) -> None:
        self._refresh_provider_config()

    def _tts_provider_selection_changed(self, _index: int = 0) -> None:
        self._refresh_provider_config()
        self.voice_list.clear()
        self.voice_status_label.setText("Refresh voices for the selected TTS provider.")
        self.voice_count_label.setText("Voices: 0")
        self.voice_refresh_label.setText("Last refresh: never")

    def _persist_current_provider_state(self, selected_voice: str | None) -> object:
        self.settings_manager.set_provider_selection(
            stt_provider_id=str(self.stt_combo.currentData()),
            translation_provider_id=str(self.translation_combo.currentData()),
            tts_provider_id=str(self.tts_combo.currentData()),
            selected_voice=selected_voice,
        )
        for descriptor in self._selected_descriptors():
            for field in descriptor.config_fields:
                edit = self.provider_inputs.get((descriptor.id, field.key))
                edit = self.provider_inputs.get(
                    (descriptor.kind, descriptor.id, field.key),
                    edit,
                )
                if edit is not None:
                    self.settings_manager.set_provider_setting(
                        descriptor.id,
                        field.key,
                        edit.text(),
                        secret=field.secret,
                    )
        return self.settings_manager.data

    def _update_selected_provider_label(self) -> None:
        names = [descriptor.name for descriptor in self._selected_descriptors()]
        self.selected_provider_label.setText(
            "Selected provider: " + ", ".join(names) if names else "Selected provider: none"
        )


def _now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
