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

    tool_config = config.load_tool_config()

    assert tool_config.homebrew_path == "brew"
    assert tool_config.ffmpeg_path == "custom-ffmpeg"
    assert tool_config.ffprobe_path == "custom-ffprobe"
    assert tool_config.whisper_cpp_path == "custom-whisper"
    assert str(tool_config.whisper_model_path) == "/models/model.bin"
