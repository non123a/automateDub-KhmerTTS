"""Minimal runtime configuration for the vertical slice."""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from automatedub.runtime import resolve_runtime_binary

DEFAULT_TTS_MODEL = "mars-8.1-flash-beta"
DEFAULT_CAMB_VOICE_ID = "170542"
DEFAULT_TTS_SYNC_OFFSET_MS = 150
DEFAULT_TTS_SPEED = 0.85
DEFAULT_CAMB_API_BASE_URL = "https://client.camb.ai/apis"


@dataclass(frozen=True)
class ToolConfig:
    homebrew_path: str = "brew"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    whisper_cpp_path: str = "whisper-cli"
    whisper_model_path: Path = Path("models/ggml-small.bin")
    stt_provider: str = "whisper_cpp"
    translation_provider: str = "nbwcode"
    nbw_base_url: str = "https://www.nbwcode.top/v1"
    nbw_automatedub_api_key: str | None = None
    localization_model: str = "gpt-5.5"
    translation_wire_api: str = "responses"
    tts_provider: str = "cambai"
    tts_model: str = DEFAULT_TTS_MODEL
    camb_api_key: str | None = None
    camb_api_base_url: str = DEFAULT_CAMB_API_BASE_URL
    camb_language: str = "km-kh"
    camb_voice_id: str | None = DEFAULT_CAMB_VOICE_ID
    tts_sync_offset_ms: int = DEFAULT_TTS_SYNC_OFFSET_MS
    tts_speed: float = DEFAULT_TTS_SPEED
    duck_volume: float = 0.0


def load_tool_config(env_file: Path | None = Path(".env")) -> ToolConfig:
    dotenv_values = load_dotenv_values(env_file) if env_file is not None else {}

    def get_config_value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, dotenv_values.get(name, default))

    def get_config_int(name: str, default: int) -> int:
        raw_value = get_config_value(name, str(default))
        if raw_value is None:
            return default
        return int(raw_value)

    def get_config_float(name: str, default: float) -> float:
        raw_value = get_config_value(name, str(default))
        if raw_value is None:
            return default
        return float(raw_value)

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
        stt_provider=get_config_value("STT_PROVIDER", "whisper_cpp") or "whisper_cpp",
        translation_provider=get_config_value("TRANSLATION_PROVIDER", "nbwcode") or "nbwcode",
        nbw_base_url=get_config_value("NBW_BASE_URL", "https://www.nbwcode.top/v1")
        or "https://www.nbwcode.top/v1",
        nbw_automatedub_api_key=get_config_value("NBW_AUTOMATEDUB_API_KEY"),
        localization_model=get_config_value("LOCALIZATION_MODEL", "gpt-5.5") or "gpt-5.5",
        translation_wire_api=get_config_value("TRANSLATION_WIRE_API", "responses")
        or "responses",
        tts_provider=get_config_value("TTS_PROVIDER", "cambai") or "cambai",
        tts_model=(
            get_config_value(
                "CAMB_TTS_MODEL",
                get_config_value("TTS_MODEL", DEFAULT_TTS_MODEL),
            )
            or DEFAULT_TTS_MODEL
        ),
        camb_api_key=get_config_value("CAMB_API_KEY"),
        camb_api_base_url=(
            get_config_value("CAMB_API_BASE_URL", DEFAULT_CAMB_API_BASE_URL)
            or DEFAULT_CAMB_API_BASE_URL
        ),
        camb_language=get_config_value("CAMB_LANGUAGE", "km-kh") or "km-kh",
        camb_voice_id=get_config_value("CAMB_VOICE_ID", DEFAULT_CAMB_VOICE_ID),
        tts_sync_offset_ms=get_config_int(
            "TTS_SYNC_OFFSET_MS", DEFAULT_TTS_SYNC_OFFSET_MS
        ),
        tts_speed=get_config_float("TTS_SPEED", DEFAULT_TTS_SPEED),
        duck_volume=get_config_float("DUCK_VOLUME", 0.0),
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
    tool = Path(name).name.lower().removesuffix(".exe")
    if tool in {"ffmpeg", "ffprobe", "whisper-cli"}:
        return resolve_runtime_binary(tool, name)
    return shutil.which(name)
