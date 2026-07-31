"""Provider registry for Studio AI services."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

from automatedub.config import ToolConfig
from automatedub_studio.providers.base.interfaces import (
    STTProvider,
    TranslationProvider,
    TTSProvider,
)


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    name: str
    kind: str
    factory: Callable[[ToolConfig], object]
    config_fields: tuple[ProviderConfigField, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderConfigField:
    key: str
    label: str
    secret: bool = False
    default: str = ""
    placeholder: str = ""


class ProviderRegistry:
    def __init__(self) -> None:
        self._stt: dict[str, ProviderDescriptor] = {}
        self._translation: dict[str, ProviderDescriptor] = {}
        self._tts: dict[str, ProviderDescriptor] = {}

    def register_stt(self, descriptor: ProviderDescriptor) -> None:
        self._stt[descriptor.id] = descriptor

    def register_translation(self, descriptor: ProviderDescriptor) -> None:
        self._translation[descriptor.id] = descriptor

    def register_tts(self, descriptor: ProviderDescriptor) -> None:
        self._tts[descriptor.id] = descriptor

    def stt_descriptors(self) -> list[ProviderDescriptor]:
        return sorted(self._stt.values(), key=lambda item: item.name)

    def translation_descriptors(self) -> list[ProviderDescriptor]:
        return sorted(self._translation.values(), key=lambda item: item.name)

    def tts_descriptors(self) -> list[ProviderDescriptor]:
        return sorted(self._tts.values(), key=lambda item: item.name)

    def create_stt(self, provider_id: str, tool_config: ToolConfig) -> STTProvider:
        return self._create(self._stt, provider_id, tool_config)

    def create_translation(
        self, provider_id: str, tool_config: ToolConfig
    ) -> TranslationProvider:
        return self._create(self._translation, provider_id, tool_config)

    def create_tts(self, provider_id: str, tool_config: ToolConfig) -> TTSProvider:
        return self._create(self._tts, provider_id, tool_config)

    @staticmethod
    def _create(
        descriptors: dict[str, ProviderDescriptor],
        provider_id: str,
        tool_config: ToolConfig,
    ):
        descriptor = descriptors.get(provider_id)
        if descriptor is None:
            available = ", ".join(sorted(descriptors)) or "none"
            raise KeyError(f"unknown provider '{provider_id}'. Available: {available}")
        return descriptor.factory(tool_config)


provider_registry = ProviderRegistry()
_registered_defaults = False


def ensure_default_providers_registered() -> ProviderRegistry:
    global _registered_defaults  # noqa: PLW0603 - module-level registry bootstrap
    if _registered_defaults:
        return provider_registry
    importlib.import_module("automatedub_studio.providers.stt")
    importlib.import_module("automatedub_studio.providers.translation")
    importlib.import_module("automatedub_studio.providers.tts")
    _registered_defaults = True
    return provider_registry
