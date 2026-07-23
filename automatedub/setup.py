"""Environment setup for the local vertical slice."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from automatedub.config import ToolConfig, resolve_executable
from automatedub.doctor import DoctorCheck, doctor_succeeded, run_doctor

RECOMMENDED_MODEL_NAME = "ggml-small.bin"
RECOMMENDED_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
)
RECOMMENDED_MODEL_SHA256 = "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"


class SetupError(RuntimeError):
    """Raised when local setup cannot complete."""


@dataclass(frozen=True)
class SetupResult:
    model_path: Path
    downloaded_model: bool
    checks: list[DoctorCheck]


def run_setup(
    tool_config: ToolConfig,
    download_file: Callable[[str, Path], None] | None = None,
) -> SetupResult:
    require_executable("homebrew", tool_config.homebrew_path)
    require_executable("ffmpeg", tool_config.ffmpeg_path)
    require_executable("ffprobe", tool_config.ffprobe_path)
    require_executable("whisper.cpp", tool_config.whisper_cpp_path)

    model_path = tool_config.whisper_model_path.expanduser()
    model_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = False
    if not model_path.exists():
        downloader = download_file or download_url
        with tempfile.TemporaryDirectory(prefix="automatedub-model-") as temp_dir:
            temp_path = Path(temp_dir) / model_path.name
            downloader(RECOMMENDED_MODEL_URL, temp_path)
            verify_model_checksum(temp_path)
            shutil.move(str(temp_path), model_path)
        downloaded = True

    verify_model_checksum(model_path)
    checks = run_doctor(tool_config)
    if not doctor_succeeded(checks):
        failed = ", ".join(check.name for check in checks if not check.ok)
        raise SetupError(f"setup completed but doctor checks failed: {failed}")

    return SetupResult(model_path=model_path, downloaded_model=downloaded, checks=checks)


def require_executable(label: str, executable: str) -> str:
    path = resolve_executable(executable)
    if path is None:
        raise SetupError(f"{label} is required but was not found on PATH: {executable}")
    return path


def download_url(url: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(url) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    except OSError as exc:
        raise SetupError(f"failed to download model from {url}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_checksum(model_path: Path) -> None:
    actual = sha256_file(model_path)
    if actual != RECOMMENDED_MODEL_SHA256:
        raise SetupError(
            "whisper model checksum mismatch: "
            f"expected {RECOMMENDED_MODEL_SHA256}, got {actual}"
        )
