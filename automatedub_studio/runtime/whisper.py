"""Resolve the bundled Whisper.cpp runtime and its reusable speech model."""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from automatedub.runtime import bundled_whisper_path, resolve_runtime_binary

MODEL_FILENAME = "ggml-small.bin"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"


class WhisperRuntimeError(RuntimeError):
    """Raised when the application-managed Whisper runtime is unavailable."""


def application_data_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AutomateDub"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AutomateDub"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AutomateDub"


def bundled_whisper_executable(system: str | None = None) -> Path:
    return bundled_whisper_path(system)


def resolve_whisper_executable(system: str | None = None) -> Path:
    executable = resolve_runtime_binary("whisper-cli", system=system)
    if executable is None:
        raise WhisperRuntimeError(
            "Bundled Whisper.cpp speech recognition is unavailable. Please reinstall AutomateDub."
        )
    return Path(executable)


def managed_model_path(data_directory: Path | None = None) -> Path:
    return (data_directory or application_data_directory()) / "models" / MODEL_FILENAME


def ensure_whisper_model(
    *,
    data_directory: Path | None = None,
    progress=None,
    url: str = MODEL_URL,
) -> Path:
    """Download the required model once, atomically, into application data."""
    destination = managed_model_path(data_directory)
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".bin.download")
    if progress is not None:
        progress("Downloading required speech recognition model...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            received = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                received += len(chunk)
                if progress is not None and total:
                    percent = received * 100 // total
                    progress(f"Downloading required speech recognition model... {percent}%")
        if temporary.stat().st_size == 0:
            raise WhisperRuntimeError("Downloaded speech recognition model is empty.")
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise WhisperRuntimeError(
            "Unable to download the required speech recognition model. "
            "Check your internet connection and retry."
        ) from exc
    return destination
