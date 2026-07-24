"""Path conventions for vertical-slice outputs."""

from __future__ import annotations

from pathlib import Path

AUDIO_FILENAME = "audio.wav"
TRANSCRIPT_FILENAME = "transcript.json"
TRANSLATION_FILENAME = "translation.json"
TRANSLATION_PROMPT_FILENAME = "translation_prompt.json"
MIXED_AUDIO_FILENAME = "mixed_audio.wav"
MIX_PLAN_FILENAME = "mix_plan.json"
TTS_DIRECTORY_NAME = "tts"
TTS_ERROR_LOG_FILENAME = "errors.json"
USAGE_DIRECTORY_NAME = "usage"
TTS_USAGE_FILENAME = "tts_usage.json"


def audio_output_path(output_dir: Path) -> Path:
    return output_dir / AUDIO_FILENAME


def transcript_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSCRIPT_FILENAME


def translation_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSLATION_FILENAME


def translation_prompt_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSLATION_PROMPT_FILENAME


def mixed_audio_output_path(output_dir: Path) -> Path:
    return output_dir / MIXED_AUDIO_FILENAME


def mix_plan_output_path(output_dir: Path) -> Path:
    return output_dir / MIX_PLAN_FILENAME


def tts_output_dir_path(output_dir: Path) -> Path:
    return output_dir / TTS_DIRECTORY_NAME


def tts_error_log_output_path(output_dir: Path) -> Path:
    return tts_output_dir_path(output_dir) / TTS_ERROR_LOG_FILENAME


def usage_output_dir_path(output_dir: Path) -> Path:
    return output_dir / USAGE_DIRECTORY_NAME


def tts_usage_output_path(output_dir: Path) -> Path:
    return usage_output_dir_path(output_dir) / TTS_USAGE_FILENAME
