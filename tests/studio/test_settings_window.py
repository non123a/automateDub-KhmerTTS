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
    registry.register_tts(
        ProviderDescriptor(
            "fake_tts",
            "Fake TTS",
            "tts",
            FakeProvider,
            (ProviderConfigField("voice_id", "Default Voice"),),
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
    assert window.translation_combo.itemText(0) == "Fake Translation"
    assert window.tts_combo.itemText(0) == "Fake TTS"


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


def test_home_settings_button_opens_settings_window(qapp, tmp_path):
    settings = _settings(tmp_path)
    window = HomeWindow(settings_manager=settings)

    window._show_settings()

    assert len(window.settings_windows) == 1
    assert isinstance(window.settings_windows[0], SettingsWindow)
