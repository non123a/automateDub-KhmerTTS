"""NBWCode translation provider adapter."""

from __future__ import annotations

from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice.localization import (
    NBWCodeDialogueLocalizer,
    validate_llm_config,
)
from automatedub_studio.providers.registry import (
    ProviderConfigField,
    ProviderDescriptor,
    provider_registry,
)

NBWCODE_TRANSLATION_PROVIDER_ID = "nbwcode"


class NBWCodeTranslationProvider:
    id = NBWCODE_TRANSLATION_PROVIDER_ID
    name = "NBWCode Translation"

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config

    def validate(self) -> None:
        validate_llm_config(self.tool_config)

    def translate(
        self,
        transcript_path: Path,
        translation_path: Path,
        prompt_path: Path,
    ) -> None:
        NBWCodeDialogueLocalizer(self.tool_config).localize(
            transcript_path=transcript_path,
            translation_path=translation_path,
            prompt_path=prompt_path,
        )


provider_registry.register_translation(
    ProviderDescriptor(
        id=NBWCODE_TRANSLATION_PROVIDER_ID,
        name="NBWCode Translation",
        kind="translation",
        factory=NBWCodeTranslationProvider,
        config_fields=(
            ProviderConfigField("api_key", "API Key", secret=True),
            ProviderConfigField("model", "Model", default="gpt-5.5"),
            ProviderConfigField("temperature", "Temperature", default="0.2"),
            ProviderConfigField("timeout", "Timeout", default="300"),
        ),
    )
)
