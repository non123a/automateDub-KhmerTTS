"""Minimal runtime configuration for the vertical slice."""

from __future__ import annotations

import os
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


def load_tool_config() -> ToolConfig:
    return ToolConfig(
        homebrew_path=os.environ.get("AUTOMATEDUB_HOMEBREW_BIN", "brew"),
        ffmpeg_path=os.environ.get("AUTOMATEDUB_FFMPEG_BIN", "ffmpeg"),
        ffprobe_path=os.environ.get("AUTOMATEDUB_FFPROBE_BIN", "ffprobe"),
        whisper_cpp_path=os.environ.get("AUTOMATEDUB_WHISPER_CPP_BIN", "whisper-cli"),
        whisper_model_path=Path(
            os.environ.get("AUTOMATEDUB_WHISPER_MODEL", "models/ggml-small.bin")
        ),
    )


def resolve_executable(name: str) -> str | None:
    return shutil.which(name)
