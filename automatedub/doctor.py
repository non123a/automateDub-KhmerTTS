"""Environment checks for the vertical-slice CLI."""

from __future__ import annotations

from dataclasses import dataclass

from automatedub.config import ToolConfig, resolve_executable


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(tool_config: ToolConfig) -> list[DoctorCheck]:
    checks = [
        check_executable("homebrew", tool_config.homebrew_path),
        check_executable("ffmpeg", tool_config.ffmpeg_path),
        check_executable("ffprobe", tool_config.ffprobe_path),
        check_executable("whisper.cpp", tool_config.whisper_cpp_path),
        check_model(tool_config),
    ]
    return checks


def check_executable(label: str, executable: str) -> DoctorCheck:
    path = resolve_executable(executable)
    if path is None:
        return DoctorCheck(label, False, f"not found: {executable}")
    return DoctorCheck(label, True, path)


def check_model(tool_config: ToolConfig) -> DoctorCheck:
    model_path = tool_config.whisper_model_path.expanduser()
    if not model_path.exists():
        return DoctorCheck("whisper model", False, f"not found: {model_path}")
    if not model_path.is_file():
        return DoctorCheck("whisper model", False, f"not a file: {model_path}")
    return DoctorCheck("whisper model", True, str(model_path))


def doctor_succeeded(checks: list[DoctorCheck]) -> bool:
    return all(check.ok for check in checks)
