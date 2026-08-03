from __future__ import annotations

from automatedub.config import ToolConfig
from automatedub_studio.providers.base.interfaces import SynthesizedSpeech, VoiceInfo
from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    ProviderRegistry,
)
from automatedub_studio.settings.manager import JsonCredentialStore, SettingsManager
from automatedub_studio.ui.home_window import HomeWindow
from automatedub_studio.ui.settings_window import SettingsWindow


class FakeProvider:
    id = "fake"
    name = "Fake"

    def __init__(self, _tool_config: ToolConfig):
        pass

    def validate(self) -> None:
        return None

    def transcribe(self, _audio_path, _transcript_path):
        return None

    def translate(self, _transcript_path, _translation_path, _prompt_path) -> None:
        return None

    def list_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="voice-1", name="Voice One", language="km-kh")]

    def synthesize(self, text: str) -> SynthesizedSpeech:
        return SynthesizedSpeech(audio=text.encode())


class AlternateProvider(FakeProvider):
    pass


class EmptyVoiceProvider(FakeProvider):
    def list_voices(self) -> list[VoiceInfo]:
        return []


class MultiVoiceProvider(FakeProvider):
    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="voice-1", name="Voice One", language="km-kh"),
            VoiceInfo(id="voice-2", name="Voice Two", language="km-kh"),
        ]


class CountingTTSProvider(FakeProvider):
    validate_count = 0
    voice_count = 0

    def validate(self) -> None:
        type(self).validate_count += 1

    def list_voices(self) -> list[VoiceInfo]:
        type(self).voice_count += 1
        return super().list_voices()


class FailingProvider(FakeProvider):
    def validate(self) -> None:
        raise RuntimeError("bad credentials")


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_stt(
        ProviderDescriptor(
            "fake_stt",
            "Fake STT",
            "stt",
            FakeProvider,
            (ProviderConfigField("model_path", "Model Path"),),
        )
    )
    registry.register_stt(
        ProviderDescriptor(
            "alt_stt",
            "Future STT",
            "stt",
            AlternateProvider,
            (ProviderConfigField("threads", "Threads"),),
        )
    )
    registry.register_translation(
        ProviderDescriptor(
            "fake_translation",
            "Fake Translation",
            "translation",
            FakeProvider,
            (
                ProviderConfigField("api_key", "API Key", secret=True),
                ProviderConfigField("model", "Model"),
            ),
        )
    )
    registry.register_translation(
        ProviderDescriptor(
            "alt_translation",
            "Future Translation",
            "translation",
            AlternateProvider,
            (
                ProviderConfigField("base_url", "Base URL"),
                ProviderConfigField("temperature", "Temperature"),
            ),
        )
    )
    registry.register_tts(
        ProviderDescriptor(
            "fake_tts",
            "Fake TTS",
            "tts",
            FakeProvider,
            (ProviderConfigField("voice_id", "Default Voice"),),
        )
    )
    registry.register_tts(
        ProviderDescriptor(
            "alt_tts",
            "Future TTS",
            "tts",
            AlternateProvider,
            (
                ProviderConfigField("language", "Language"),
                ProviderConfigField("speaking_rate", "Speaking Rate"),
            ),
        )
    )
    return registry


def _settings(tmp_path) -> SettingsManager:
    return SettingsManager(
        settings_path=tmp_path / "settings.json",
        credential_store=JsonCredentialStore(tmp_path / "credentials.json"),
    )


def test_settings_window_sections_and_dynamic_provider_combos(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )

    window = SettingsWindow(settings, provider_manager)

    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
        "General",
        "AI Providers",
        "Voices",
        "Models",
        "Cache",
        "Logs",
        "Advanced",
    ]
    assert window.stt_combo.itemText(0) == "Fake STT"
    assert window.stt_combo.itemText(1) == "Future STT"
    assert window.translation_combo.itemText(0) == "Fake Translation"
    assert window.tts_combo.itemText(0) == "Fake TTS"


def test_settings_window_switching_provider_rebuilds_dynamic_config(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    window = SettingsWindow(settings, provider_manager)

    window.tts_combo.setCurrentIndex(window.tts_combo.findData("alt_tts"))

    assert ("tts", "alt_tts", "language") in window.provider_inputs
    assert ("tts", "alt_tts", "speaking_rate") in window.provider_inputs
    assert window.voice_status_label.text() == "Refresh voices for the selected TTS provider."


def test_settings_window_saves_provider_config_and_secret(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    window = SettingsWindow(settings, provider_manager)
    window.translation_combo.setCurrentIndex(0)
    window.provider_inputs[("fake_translation", "api_key")].setText("secret")
    window.provider_inputs[("fake_translation", "model")].setText("model-a")

    window.save_settings()

    assert settings.data.translation_provider_id == "fake_translation"
    assert settings.provider_setting("fake_translation", "model") == "model-a"
    assert settings.provider_setting("fake_translation", "api_key", secret=True) == "secret"


def test_settings_window_persists_provider_selection(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    window = SettingsWindow(settings, provider_manager)
    window.stt_combo.setCurrentIndex(window.stt_combo.findData("alt_stt"))
    window.translation_combo.setCurrentIndex(window.translation_combo.findData("alt_translation"))
    window.tts_combo.setCurrentIndex(window.tts_combo.findData("alt_tts"))

    window.save_settings()
    reloaded = _settings(tmp_path)
    restored = SettingsWindow(
        reloaded,
        ProviderManager(reloaded.tool_config(), registry=_registry()),
    )

    assert reloaded.data.stt_provider_id == "alt_stt"
    assert reloaded.data.translation_provider_id == "alt_translation"
    assert reloaded.data.tts_provider_id == "alt_tts"
    assert restored.stt_combo.currentData() == "alt_stt"
    assert restored.translation_combo.currentData() == "alt_translation"
    assert restored.tts_combo.currentData() == "alt_tts"


def test_settings_window_voice_browser_uses_tts_provider(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    window = SettingsWindow(settings, provider_manager)

    window.refresh_voices()

    assert window.voice_list.count() == 1
    assert "Voice One" in window.voice_list.item(0).text()
    assert "km-kh" in window.voice_list.item(0).text()
    assert "Loaded 1 voice" in window.voice_status_label.text()


def test_settings_window_test_connection_uses_selected_provider(qapp, tmp_path):
    CountingTTSProvider.validate_count = 0
    CountingTTSProvider.voice_count = 0
    registry = ProviderRegistry()
    registry.register_tts(
        ProviderDescriptor("counting_tts", "Counting TTS", "tts", CountingTTSProvider)
    )
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(tts_provider="counting_tts"),
        registry=registry,
    )
    window = SettingsWindow(settings, provider_manager)

    window.test_provider(window._selected_descriptors()[-1])

    assert CountingTTSProvider.validate_count >= 1
    assert CountingTTSProvider.voice_count >= 1
    assert "Connected" in window.connection_status_label.text()
    assert "latency" in window.diagnostics_label.text()


def test_settings_window_voice_browser_refreshes_after_validation(qapp, tmp_path):
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    window = SettingsWindow(settings, provider_manager)

    window.test_provider(window._selected_descriptors()[-1])

    assert window.voice_list.count() == 1
    assert "Loaded 1 voice" in window.voice_status_label.text()


def test_settings_window_voice_selection_persists_voice_id(qapp, tmp_path):
    registry = ProviderRegistry()
    registry.register_tts(
        ProviderDescriptor("multi_tts", "Multi TTS", "tts", MultiVoiceProvider)
    )
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(ToolConfig(tts_provider="multi_tts"), registry=registry)
    window = SettingsWindow(settings, provider_manager)
    window.refresh_voices()
    window.voice_list.setCurrentRow(1)

    window.save_settings()
    reloaded = _settings(tmp_path)
    restored = SettingsWindow(
        reloaded,
        ProviderManager(reloaded.tool_config(), registry=registry),
    )
    restored.refresh_voices()

    assert reloaded.data.selected_voice == "voice-2"
    assert restored.voice_list.currentItem() is not None
    assert "Voice Two" in restored.voice_list.currentItem().text()


def test_settings_window_voice_browser_shows_empty_state(qapp, tmp_path):
    registry = ProviderRegistry()
    registry.register_tts(
        ProviderDescriptor(
            "empty_tts",
            "Empty TTS",
            "tts",
            EmptyVoiceProvider,
        )
    )
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(tts_provider="empty_tts"),
        registry=registry,
    )
    window = SettingsWindow(settings, provider_manager)
    window.refresh_voices()

    assert window.voice_list.count() == 1
    assert "No voices available" in window.voice_list.item(0).text()
    assert "No voices available" in window.voice_status_label.text()


def test_settings_window_provider_failure_is_visible(qapp, tmp_path):
    registry = ProviderRegistry()
    registry.register_tts(
        ProviderDescriptor("failing_tts", "Failing TTS", "tts", FailingProvider)
    )
    settings = _settings(tmp_path)
    provider_manager = ProviderManager(
        ToolConfig(tts_provider="failing_tts"),
        registry=registry,
    )
    window = SettingsWindow(settings, provider_manager)

    window.test_provider(window._selected_descriptors()[-1])
    window.refresh_voices()

    assert "Connection Failed" in window.connection_status_label.text()
    assert "bad credentials" in window.diagnostics_label.text()
    assert "Unable to load voices" in window.voice_status_label.text()


def test_home_settings_button_opens_settings_window(qapp, tmp_path):
    settings = _settings(tmp_path)
    window = HomeWindow(settings_manager=settings)

    window._show_settings()

    assert len(window.settings_windows) == 1
    assert isinstance(window.settings_windows[0], SettingsWindow)
