"""VS0 audio extraction using FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from automatedub import process
from automatedub.config import ToolConfig, resolve_executable
from automatedub.vertical_slice.paths import audio_output_path


class VS0Error(RuntimeError):
    """Raised when the VS0 audio extraction step cannot complete."""


def validate_input_mp4(input_path: Path) -> Path:
    resolved = input_path.expanduser()
    if not resolved.exists():
        raise VS0Error(f"input file does not exist: {input_path}")
    if not resolved.is_file():
        raise VS0Error(f"input path is not a file: {input_path}")
    if resolved.suffix.lower() != ".mp4":
        raise VS0Error(f"input file must be an MP4: {input_path}")
    return resolved


def validate_ffmpeg(tool_config: ToolConfig) -> str:
    ffmpeg = resolve_executable(tool_config.ffmpeg_path)
    if ffmpeg is None:
        raise VS0Error("AutomateDub media runtime is unavailable. Please reinstall AutomateDub.")
    return ffmpeg


def build_extract_audio_command(ffmpeg: str, input_path: Path, output_path: Path) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]


def extract_audio(
    input_path: Path,
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> Path:
    config = tool_config or ToolConfig()
    source = validate_input_mp4(input_path)
    ffmpeg = validate_ffmpeg(config)

    destination_dir = output_dir.expanduser()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = audio_output_path(destination_dir)

    command = build_extract_audio_command(ffmpeg, source, destination)
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, **process.gui_subprocess_kwargs()
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
        raise VS0Error(f"audio extraction failed: {message}") from exc

    if not destination.exists():
        raise VS0Error(f"audio extraction did not create expected file: {destination}")

    return destination
