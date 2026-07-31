"""Camb.ai TTS provider adapter."""

from __future__ import annotations

from automatedub.config import ToolConfig
from automatedub.vertical_slice.tts import (
    CambAIProvider,
    GeneratedSpeech,
    TtsVoice,
    list_cambai_voices,
    validate_cambai_tts_config,
)
from automatedub_studio.providers.base.interfaces import SynthesizedSpeech, VoiceInfo
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    provider_registry,
)

CAMBAI_TTS_PROVIDER_ID = "cambai"


class CambAITTSProvider:
    id = CAMBAI_TTS_PROVIDER_ID
    name = "Camb.ai"

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config
        self._provider: CambAIProvider | None = None

    @property
    def provider(self) -> CambAIProvider:
        if self._provider is None:
            self._provider = CambAIProvider(self.tool_config)
        return self._provider

    def validate(self) -> None:
        validate_cambai_tts_config(self.tool_config)

    def list_voices(self) -> list[VoiceInfo]:
        return [_voice_info(voice) for voice in list_cambai_voices(self.tool_config)]

    def synthesize(self, text: str) -> SynthesizedSpeech:
        speech: GeneratedSpeech = self.provider.generate(text)
        return SynthesizedSpeech(audio=speech.audio, metadata=speech.metadata)


def _voice_info(voice: TtsVoice) -> VoiceInfo:
    return VoiceInfo(
        id=voice.id,
        name=voice.name,
        language=voice.language,
        gender=voice.gender,
    )


provider_registry.register_tts(
    ProviderDescriptor(
        id=CAMBAI_TTS_PROVIDER_ID,
        name="Camb.ai",
        kind="tts",
        factory=CambAITTSProvider,
        config_fields=(
            ProviderConfigField("api_key", "API Key", secret=True),
            ProviderConfigField("voice_id", "Default Voice"),
            ProviderConfigField("language", "Language", default="km-kh"),
            ProviderConfigField("model", "Model"),
            ProviderConfigField("timeout", "Timeout", default="300"),
        ),
    )
)
