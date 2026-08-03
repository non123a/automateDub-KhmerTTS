"""NBWCode TTS provider adapter."""

from __future__ import annotations

from automatedub.config import ToolConfig
from automatedub.vertical_slice.tts import (
    DEFAULT_TTS_VOICE,
    GeneratedSpeech,
    NBWCodeProvider,
    validate_nbwcode_tts_config,
)
from automatedub_studio.providers.base.interfaces import SynthesizedSpeech, VoiceInfo
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    provider_registry,
)

NBWCODE_TTS_PROVIDER_ID = "nbwcode"


class NBWCodeTTSProvider:
    id = NBWCODE_TTS_PROVIDER_ID
    name = "NBWCode TTS"

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config
        self._provider: NBWCodeProvider | None = None

    @property
    def provider(self) -> NBWCodeProvider:
        if self._provider is None:
            self._provider = NBWCodeProvider(self.tool_config)
        return self._provider

    def validate(self) -> None:
        validate_nbwcode_tts_config(self.tool_config)

    def list_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id=DEFAULT_TTS_VOICE, name=DEFAULT_TTS_VOICE)]

    def synthesize(self, text: str) -> SynthesizedSpeech:
        speech: GeneratedSpeech = self.provider.generate(text)
        return SynthesizedSpeech(audio=speech.audio, metadata=speech.metadata)

    def generate(self, text: str) -> GeneratedSpeech:
        return self.provider.generate(text)


provider_registry.register_tts(
    ProviderDescriptor(
        id=NBWCODE_TTS_PROVIDER_ID,
        name="NBWCode TTS",
        kind="tts",
        factory=NBWCodeTTSProvider,
        config_fields=(
            ProviderConfigField("api_key", "API Key", secret=True),
            ProviderConfigField("base_url", "Base URL", default="https://www.nbwcode.top/v1"),
            ProviderConfigField("model", "Model"),
            ProviderConfigField("timeout", "Timeout", default="300"),
        ),
    )
)
