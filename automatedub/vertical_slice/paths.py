"""Path conventions for vertical-slice outputs."""

from __future__ import annotations

from pathlib import Path

AUDIO_FILENAME = "audio.wav"
TRANSCRIPT_FILENAME = "transcript.json"
TRANSLATION_FILENAME = "translation.json"
TRANSLATION_PROMPT_FILENAME = "translation_prompt.json"


def audio_output_path(output_dir: Path) -> Path:
    return output_dir / AUDIO_FILENAME


def transcript_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSCRIPT_FILENAME


def translation_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSLATION_FILENAME


def translation_prompt_output_path(output_dir: Path) -> Path:
    return output_dir / TRANSLATION_PROMPT_FILENAME
