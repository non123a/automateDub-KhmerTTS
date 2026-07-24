from __future__ import annotations

from automatedub import config


def test_resolve_executable_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)

    assert config.resolve_executable("missing-tool") is None


def test_resolve_executable_returns_path(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert config.resolve_executable("ffmpeg") == "/usr/bin/ffmpeg"


def test_load_tool_config_reads_environment(monkeypatch):
    monkeypatch.setenv("AUTOMATEDUB_FFMPEG_BIN", "custom-ffmpeg")
    monkeypatch.setenv("AUTOMATEDUB_FFPROBE_BIN", "custom-ffprobe")
    monkeypatch.setenv("AUTOMATEDUB_WHISPER_CPP_BIN", "custom-whisper")
    monkeypatch.setenv("AUTOMATEDUB_WHISPER_MODEL", "/models/model.bin")
    monkeypatch.setenv("NBW_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("NBW_AUTOMATEDUB_API_KEY", "test-key")
    monkeypatch.setenv("LOCALIZATION_MODEL", "test-model")
    monkeypatch.setenv("TTS_PROVIDER", "cambai")
    monkeypatch.setenv("TTS_MODEL", "test-tts-model")
    monkeypatch.setenv("CAMB_API_KEY", "camb-key")
    monkeypatch.setenv("CAMB_LANGUAGE", "km-kh")
    monkeypatch.setenv("CAMB_VOICE_ID", "123")
    monkeypatch.setenv("TTS_SYNC_OFFSET_MS", "275")

    tool_config = config.load_tool_config(env_file=None)

    assert tool_config.homebrew_path == "brew"
    assert tool_config.ffmpeg_path == "custom-ffmpeg"
    assert tool_config.ffprobe_path == "custom-ffprobe"
    assert tool_config.whisper_cpp_path == "custom-whisper"
    assert str(tool_config.whisper_model_path) == "/models/model.bin"
    assert tool_config.nbw_base_url == "https://gateway.example/v1"
    assert tool_config.nbw_automatedub_api_key == "test-key"
    assert tool_config.localization_model == "test-model"
    assert tool_config.tts_provider == "cambai"
    assert tool_config.tts_model == "test-tts-model"
    assert tool_config.camb_api_key == "camb-key"
    assert tool_config.camb_language == "km-kh"
    assert tool_config.camb_voice_id == "123"
    assert tool_config.tts_sync_offset_ms == 275


def test_load_tool_config_uses_nbw_defaults(monkeypatch):
    monkeypatch.delenv("NBW_BASE_URL", raising=False)
    monkeypatch.delenv("LOCALIZATION_MODEL", raising=False)
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    monkeypatch.delenv("TTS_MODEL", raising=False)
    monkeypatch.delenv("TTS_SYNC_OFFSET_MS", raising=False)

    tool_config = config.load_tool_config(env_file=None)

    assert tool_config.nbw_base_url == "https://www.nbwcode.top/v1"
    assert tool_config.localization_model == "gpt-5.5"
    assert tool_config.tts_provider == "cambai"
    assert tool_config.tts_model == config.DEFAULT_TTS_MODEL
    assert tool_config.camb_language == "km-kh"
    assert tool_config.tts_sync_offset_ms == 200


def test_load_tool_config_reads_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.delenv("NBW_BASE_URL", raising=False)
    monkeypatch.delenv("NBW_AUTOMATEDUB_API_KEY", raising=False)
    monkeypatch.delenv("LOCALIZATION_MODEL", raising=False)
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    monkeypatch.delenv("TTS_MODEL", raising=False)
    monkeypatch.delenv("CAMB_API_KEY", raising=False)
    monkeypatch.delenv("CAMB_LANGUAGE", raising=False)
    monkeypatch.delenv("CAMB_VOICE_ID", raising=False)
    monkeypatch.delenv("TTS_SYNC_OFFSET_MS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# AutomateDub local config",
                "NBW_BASE_URL=https://gateway.example/v1",
                "NBW_AUTOMATEDUB_API_KEY=test-key",
                'LOCALIZATION_MODEL="test model"',
                "TTS_PROVIDER=cambai",
                "TTS_MODEL=test-tts-model",
                "CAMB_API_KEY=camb-key",
                "CAMB_LANGUAGE=km-kh",
                "CAMB_VOICE_ID=123",
                "TTS_SYNC_OFFSET_MS=325",
            ]
        ),
        encoding="utf-8",
    )

    tool_config = config.load_tool_config(env_file=env_file)

    assert tool_config.nbw_base_url == "https://gateway.example/v1"
    assert tool_config.nbw_automatedub_api_key == "test-key"
    assert tool_config.localization_model == "test model"
    assert tool_config.tts_provider == "cambai"
    assert tool_config.tts_model == "test-tts-model"
    assert tool_config.camb_api_key == "camb-key"
    assert tool_config.camb_language == "km-kh"
    assert tool_config.camb_voice_id == "123"
    assert tool_config.tts_sync_offset_ms == 325


def test_environment_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALIZATION_MODEL", "env-model")
    env_file = tmp_path / ".env"
    env_file.write_text("LOCALIZATION_MODEL=dotenv-model", encoding="utf-8")

    tool_config = config.load_tool_config(env_file=env_file)

    assert tool_config.localization_model == "env-model"


def test_parse_dotenv_line_supports_export_and_inline_comments():
    assert config.parse_dotenv_line("export NBW_AUTOMATEDUB_API_KEY=test-key") == (
        "NBW_AUTOMATEDUB_API_KEY",
        "test-key",
    )
    assert config.parse_dotenv_line("LOCALIZATION_MODEL=gpt-5.5 # default model") == (
        "LOCALIZATION_MODEL",
        "gpt-5.5",
    )
    assert config.parse_dotenv_line("# comment") is None
