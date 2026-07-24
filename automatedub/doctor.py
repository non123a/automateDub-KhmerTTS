"""Environment checks for the vertical-slice CLI."""

from __future__ import annotations

from dataclasses import dataclass

from automatedub.config import ToolConfig, resolve_executable
from automatedub.vertical_slice.localization import check_nbw_status


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
        *check_nbwcode(tool_config),
        *check_cambai(tool_config),
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


def check_nbwcode(tool_config: ToolConfig) -> list[DoctorCheck]:
    status = check_nbw_status(
        base_url=tool_config.nbw_base_url,
        api_key=tool_config.nbw_automatedub_api_key,
        model=tool_config.localization_model,
    )
    endpoint = status["endpoint"]
    endpoint_detail = "Responses" if endpoint == "responses" else None
    if endpoint == "chat/completions":
        endpoint_detail = "Chat Completions (fallback)"
    return [
        DoctorCheck("nbw base url", True, str(status["base_url"])),
        DoctorCheck(
            "nbw api key",
            bool(status["api_key_present"]),
            "Present" if status["api_key_present"] else "Missing",
        ),
        DoctorCheck("nbw model", True, str(status["model"])),
        DoctorCheck(
            "nbw endpoint",
            endpoint_detail is not None,
            endpoint_detail or str(status["error"] or "Unavailable"),
        ),
        DoctorCheck(
            "nbw authentication",
            bool(status["authentication_valid"]),
            "Valid" if status["authentication_valid"] else str(status["error"] or "Invalid"),
        ),
        DoctorCheck(
            "nbw connectivity",
            bool(status["connectivity_ok"]),
            "OK" if status["connectivity_ok"] else str(status["error"] or "Failed"),
        ),
    ]


def check_cambai(tool_config: ToolConfig) -> list[DoctorCheck]:
    return [
        DoctorCheck(
            "camb provider",
            tool_config.tts_provider == "cambai",
            "Camb.ai" if tool_config.tts_provider == "cambai" else tool_config.tts_provider,
        ),
        DoctorCheck("camb model", bool(tool_config.tts_model), tool_config.tts_model or "Missing"),
        DoctorCheck(
            "camb voice id",
            bool(tool_config.camb_voice_id),
            tool_config.camb_voice_id or "Missing",
        ),
        DoctorCheck(
            "camb language",
            bool(tool_config.camb_language),
            tool_config.camb_language or "Missing",
        ),
    ]


def doctor_succeeded(checks: list[DoctorCheck]) -> bool:
    return all(check.ok for check in checks)
