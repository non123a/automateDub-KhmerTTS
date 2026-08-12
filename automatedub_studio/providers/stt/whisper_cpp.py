"""Whisper.cpp STT provider adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice.transcription import WhisperCppTranscriber
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    provider_registry,
)
from automatedub_studio.runtime.whisper import (
    ensure_whisper_model,
    resolve_whisper_executable,
)

WHISPER_CPP_PROVIDER_ID = "whisper_cpp"


class WhisperCppSTTProvider:
    id = WHISPER_CPP_PROVIDER_ID
    name = "Whisper.cpp"

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config

    def validate(self) -> None:
        resolve_whisper_executable()

    def prepare(self, progress=None) -> Path:
        return ensure_whisper_model(progress=progress)

    def transcribe(self, audio_path: Path, transcript_path: Path) -> object:
        runtime_config = replace(
            self.tool_config,
            whisper_cpp_path=str(resolve_whisper_executable()),
            whisper_model_path=self.prepare(),
        )
        return WhisperCppTranscriber(runtime_config).transcribe(audio_path, transcript_path)


provider_registry.register_stt(
    ProviderDescriptor(
        id=WHISPER_CPP_PROVIDER_ID,
        name="Whisper.cpp",
        kind="stt",
        factory=WhisperCppSTTProvider,
        config_fields=(
            ProviderConfigField("runtime", "Runtime", default="Bundled Whisper.cpp"),
            ProviderConfigField("model", "Model", default="Whisper small (downloads once)"),
        ),
    )
)
