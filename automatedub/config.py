"""Minimal runtime configuration for the vertical slice."""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolConfig:
    homebrew_path: str = "brew"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    whisper_cpp_path: str = "whisper-cli"
    whisper_model_path: Path = Path("models/ggml-small.bin")
    nbw_base_url: str = "https://www.nbwcode.top/v1"
    nbw_automatedub_api_key: str | None = None
    localization_model: str = "gpt-5.5"
    tts_provider: str = "cambai"
    tts_model: str = "mars-flash"
    camb_api_key: str | None = None
    camb_language: str = "km-kh"
    camb_voice_id: str | None = None


def load_tool_config(env_file: Path | None = Path(".env")) -> ToolConfig:
    dotenv_values = load_dotenv_values(env_file) if env_file is not None else {}

    def get_config_value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, dotenv_values.get(name, default))

    return ToolConfig(
        homebrew_path=get_config_value("AUTOMATEDUB_HOMEBREW_BIN", "brew") or "brew",
        ffmpeg_path=get_config_value("AUTOMATEDUB_FFMPEG_BIN", "ffmpeg") or "ffmpeg",
        ffprobe_path=get_config_value("AUTOMATEDUB_FFPROBE_BIN", "ffprobe") or "ffprobe",
        whisper_cpp_path=get_config_value("AUTOMATEDUB_WHISPER_CPP_BIN", "whisper-cli")
        or "whisper-cli",
        whisper_model_path=Path(
            get_config_value("AUTOMATEDUB_WHISPER_MODEL", "models/ggml-small.bin")
            or "models/ggml-small.bin"
        ),
        nbw_base_url=get_config_value("NBW_BASE_URL", "https://www.nbwcode.top/v1")
        or "https://www.nbwcode.top/v1",
        nbw_automatedub_api_key=get_config_value("NBW_AUTOMATEDUB_API_KEY"),
        localization_model=get_config_value("LOCALIZATION_MODEL", "gpt-5.5") or "gpt-5.5",
        tts_provider=get_config_value("TTS_PROVIDER", "cambai") or "cambai",
        tts_model=get_config_value("TTS_MODEL", "mars-flash") or "mars-flash",
        camb_api_key=get_config_value("CAMB_API_KEY"),
        camb_language=get_config_value("CAMB_LANGUAGE", "km-kh") or "km-kh",
        camb_voice_id=get_config_value("CAMB_VOICE_ID"),
    )


def load_dotenv_values(env_file: Path) -> dict[str, str]:
    env_path = env_file.expanduser()
    if not env_path.exists():
        return {}
    if not env_path.is_file():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_dotenv_line(line)
        if parsed is None:
            continue
        name, value = parsed
        values[name] = value
    return values


def parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()
    if "=" not in stripped:
        return None

    name, raw_value = stripped.split("=", 1)
    name = name.strip()
    if not name:
        return None

    value = raw_value.strip()
    if value and value[0] in {"'", '"'}:
        try:
            parsed = shlex.split(value, comments=False, posix=True)
        except ValueError:
            return name, value
        return name, parsed[0] if parsed else ""

    return name, value.split(" #", 1)[0].strip()


def resolve_executable(name: str) -> str | None:
    return shutil.which(name)
