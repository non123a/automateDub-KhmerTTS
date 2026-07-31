"""Provider Manager used by Studio pipeline and application settings."""

from __future__ import annotations

from dataclasses import dataclass

from automatedub.config import ToolConfig, load_tool_config
from automatedub_studio.providers.base.interfaces import (
    ProviderError,
    STTProvider,
    TranslationProvider,
    TTSProvider,
)
from automatedub_studio.providers.registry import (
    ProviderDescriptor,
    ProviderRegistry,
    ensure_default_providers_registered,
)


@dataclass(frozen=True)
class ProviderSelection:
    stt_provider_id: str
    translation_provider_id: str
    tts_provider_id: str
    selected_voice: str | None = None


class ProviderManager:
    """Resolves provider implementations from settings and registry."""

    def __init__(
        self,
        tool_config: ToolConfig | None = None,
        registry: ProviderRegistry | None = None,
    ):
        self.tool_config = tool_config if tool_config is not None else load_tool_config()
        self.registry = registry if registry is not None else ensure_default_providers_registered()

    @property
    def selection(self) -> ProviderSelection:
        return ProviderSelection(
            stt_provider_id=self.tool_config.stt_provider,
            translation_provider_id=self.tool_config.translation_provider,
            tts_provider_id=self.tool_config.tts_provider,
            selected_voice=self.tool_config.camb_voice_id,
        )

    def stt_provider(self, provider_id: str | None = None) -> STTProvider:
        return self._resolve(
            lambda selected: self.registry.create_stt(selected, self.tool_config),
            provider_id or self.selection.stt_provider_id,
        )

    def translation_provider(self, provider_id: str | None = None) -> TranslationProvider:
        return self._resolve(
            lambda selected: self.registry.create_translation(selected, self.tool_config),
            provider_id or self.selection.translation_provider_id,
        )

    def tts_provider(self, provider_id: str | None = None) -> TTSProvider:
        return self._resolve(
            lambda selected: self.registry.create_tts(selected, self.tool_config),
            provider_id or self.selection.tts_provider_id,
        )

    def available_stt_providers(self) -> list[ProviderDescriptor]:
        return self.registry.stt_descriptors()

    def available_translation_providers(self) -> list[ProviderDescriptor]:
        return self.registry.translation_descriptors()

    def available_tts_providers(self) -> list[ProviderDescriptor]:
        return self.registry.tts_descriptors()

    def project_metadata(self) -> dict[str, object]:
        selection = self.selection
        return {
            "stt_provider_id": selection.stt_provider_id,
            "translation_provider_id": selection.translation_provider_id,
            "tts_provider_id": selection.tts_provider_id,
            "selected_voice": selection.selected_voice,
        }

    @staticmethod
    def _resolve(factory, provider_id: str):
        try:
            return factory(provider_id)
        except KeyError as exc:
            raise ProviderError(str(exc)) from exc
