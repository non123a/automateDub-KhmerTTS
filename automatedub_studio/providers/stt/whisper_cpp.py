"""Whisper.cpp STT provider adapter."""

from __future__ import annotations

from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice.transcription import (
    WhisperCppTranscriber,
    validate_model_path,
    validate_whisper_cpp,
)
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    provider_registry,
)

WHISPER_CPP_PROVIDER_ID = "whisper_cpp"


class WhisperCppSTTProvider:
    id = WHISPER_CPP_PROVIDER_ID
    name = "Whisper.cpp"

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config

    def validate(self) -> None:
        validate_whisper_cpp(self.tool_config)
        validate_model_path(self.tool_config.whisper_model_path)

    def transcribe(self, audio_path: Path, transcript_path: Path) -> object:
        return WhisperCppTranscriber(self.tool_config).transcribe(audio_path, transcript_path)


provider_registry.register_stt(
    ProviderDescriptor(
        id=WHISPER_CPP_PROVIDER_ID,
        name="Whisper.cpp",
        kind="stt",
        factory=WhisperCppSTTProvider,
        config_fields=(
            ProviderConfigField("executable", "Executable", default="whisper-cli"),
            ProviderConfigField("model_path", "Model Path", default="models/ggml-small.bin"),
            ProviderConfigField("threads", "Threads", default="auto"),
        ),
    )
)
