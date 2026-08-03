"""Stable provider interfaces for Studio processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProviderError(RuntimeError):
    """Raised when a provider cannot be resolved or used."""


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    kind: str


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    name: str
    language: str | None = None
    gender: str | None = None


@dataclass(frozen=True)
class SynthesizedSpeech:
    audio: bytes
    metadata: dict[str, object] | None = None


class STTProvider(Protocol):
    id: str
    name: str

    def validate(self) -> None:
        """Validate provider configuration and local dependencies."""

    def transcribe(self, audio_path: Path, transcript_path: Path) -> object:
        """Transcribe source audio into a normalized transcript artifact."""


class TranslationProvider(Protocol):
    id: str
    name: str

    def validate(self) -> None:
        """Validate provider configuration and service availability."""

    def translate(
        self,
        transcript_path: Path,
        translation_path: Path,
        prompt_path: Path,
    ) -> None:
        """Translate/localize transcript text into target-language dialogue."""


class TTSProvider(Protocol):
    id: str
    name: str

    def validate(self) -> None:
        """Validate provider configuration and service availability."""

    def list_voices(self) -> list[VoiceInfo]:
        """List available voices when supported."""

    def synthesize(self, text: str) -> SynthesizedSpeech:
        """Generate speech audio for one text input."""

    def generate(self, text: str) -> object:
        """Generate speech through the shared editor/CLI TTS implementation."""
