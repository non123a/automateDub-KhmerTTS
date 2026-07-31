from __future__ import annotations

import json

from automatedub_studio.settings.manager import JsonCredentialStore, SettingsManager


def test_settings_manager_stores_credentials_outside_settings_file(tmp_path):
    settings_path = tmp_path / "settings.json"
    credentials_path = tmp_path / "credentials.json"
    manager = SettingsManager(
        settings_path=settings_path,
        credential_store=JsonCredentialStore(credentials_path),
    )

    manager.set_provider_selection(
        stt_provider_id="whisper_cpp",
        translation_provider_id="nbwcode",
        tts_provider_id="cambai",
        selected_voice="voice-1",
    )
    manager.set_provider_setting("cambai", "api_key", "secret-key", secret=True)
    manager.set_provider_setting("cambai", "language", "km-kh")

    settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    credentials_payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert "secret-key" not in settings_path.read_text(encoding="utf-8")
    assert settings_payload["tts_provider_id"] == "cambai"
    assert settings_payload["selected_voice"] == "voice-1"
    assert credentials_payload["provider.cambai.api_key"] == "secret-key"


def test_settings_manager_builds_tool_config_from_saved_settings(tmp_path):
    manager = SettingsManager(
        settings_path=tmp_path / "settings.json",
        credential_store=JsonCredentialStore(tmp_path / "credentials.json"),
    )
    manager.set_provider_selection(
        stt_provider_id="whisper_cpp",
        translation_provider_id="nbwcode",
        tts_provider_id="cambai",
        selected_voice="voice-9",
    )
    manager.set_provider_setting("whisper_cpp", "model_path", "/models/test.bin")
    manager.set_provider_setting("nbwcode", "api_key", "nbw-secret", secret=True)
    manager.set_provider_setting("nbwcode", "model", "translation-model")
    manager.set_provider_setting("cambai", "api_key", "camb-secret", secret=True)
    manager.set_provider_setting("cambai", "language", "km-kh")
    manager.set_provider_setting("cambai", "model", "tts-model")

    tool_config = manager.tool_config()

    assert tool_config.stt_provider == "whisper_cpp"
    assert tool_config.translation_provider == "nbwcode"
    assert tool_config.tts_provider == "cambai"
    assert str(tool_config.whisper_model_path) == "/models/test.bin"
    assert tool_config.nbw_automatedub_api_key == "nbw-secret"
    assert tool_config.localization_model == "translation-model"
    assert tool_config.camb_api_key == "camb-secret"
    assert tool_config.camb_voice_id == "voice-9"
    assert tool_config.tts_model == "tts-model"


def test_settings_manager_cache_and_log_diagnostics(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "a.bin").write_bytes(b"123")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text(
        "ok\nERROR first\nfailed second\n", encoding="utf-8"
    )
    manager = SettingsManager(settings_path=tmp_path / "settings.json")
    manager.save(
        type(manager.data)(
            cache_dir=str(cache_dir),
            log_dir=str(log_dir),
        )
    )

    assert manager.cache_usage_bytes() == 3
    assert manager.recent_log_errors() == ["ERROR first", "failed second"]
    manager.clear_cache()
    assert manager.cache_usage_bytes() == 0
    assert cache_dir.is_dir()
