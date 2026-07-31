# Providers

Providers wrap external AI and media-service capabilities behind stable application boundaries. Studio pipeline code resolves AI services through the Provider Manager, not by constructing concrete SDK or CLI implementations directly.

Related documents:

- [PIPELINE.md](PIPELINE.md)
- [SETTINGS.md](SETTINGS.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)

## Code Ownership

- `automatedub_studio/providers/base/interfaces.py`
- `automatedub_studio/providers/registry.py`
- `automatedub_studio/providers/manager.py`
- `automatedub_studio/providers/stt/`
- `automatedub_studio/providers/translation/`
- `automatedub_studio/providers/tts/`
- `automatedub/vertical_slice/transcription.py`
- `automatedub/vertical_slice/localization.py`
- `automatedub/vertical_slice/tts.py`
- `automatedub/config.py`

## Provider Types

- Transcription providers convert audio into source-language transcript segments.
- Localization providers convert transcript segments into natural Khmer dialogue.
- TTS providers generate speech audio from Khmer text and voice settings.
- Media tools such as FFmpeg/FFprobe are external process dependencies, not AI providers, but should still be isolated behind command/service boundaries.

## Interfaces

All provider implementations conform to one capability interface:

- `STTProvider`: `validate()`, `transcribe(audio_path, transcript_path)`.
- `TranslationProvider`: `validate()`, `translate(transcript_path, translation_path, prompt_path)`.
- `TTSProvider`: `validate()`, `list_voices()`, `synthesize(text)`.

The interfaces live in `providers/base/interfaces.py` and use normalized paths and return values so the pipeline does not know about provider-specific SDKs or HTTP APIs.

## Registry

`ProviderRegistry` stores provider descriptors by capability. Providers self-register from their adapter modules at import time:

```text
providers/stt/whisper_cpp.py
    -> registers whisper_cpp

providers/translation/nbwcode.py
    -> registers nbwcode

providers/tts/cambai.py
    -> registers cambai
```

The UI and Pipeline discover available providers from the registry. They should not maintain their own provider lists.

## Provider Manager

`ProviderManager` resolves configured provider identifiers to provider instances:

```text
PipelineManager
    -> ProviderManager
    -> ProviderRegistry
    -> Provider adapter
    -> existing vertical-slice implementation
```

The manager reads application settings through `ToolConfig`:

- `STT_PROVIDER`
- `TRANSLATION_PROVIDER`
- `TTS_PROVIDER`
- provider-specific configuration such as model names or API keys

Project metadata stores provider identifiers and selected voice only. It must not store API keys or secrets.

## Current Adapters

- `whisper_cpp`: wraps `WhisperCppTranscriber`.
- `nbwcode`: wraps the current translation/localization implementation.
- `cambai`: wraps the current Camb.ai TTS implementation.
- `nbwcode` TTS remains available as a legacy TTS adapter.

Adapters preserve existing behavior. They are boundary objects, not rewrites of provider internals.

## Responsibilities

- Hide concrete provider API details behind provider abstractions.
- Report capability and configuration status clearly.
- Accept settings through `ToolConfig` or dedicated settings services.
- Return normalized project artifacts or service outcomes.
- Preserve failure information without destroying previous good artifacts.

## Non-Responsibilities

- Providers do not own UI state.
- Providers do not own Timeline editing decisions.
- Providers do not decide export layout.

## Regeneration Boundary

Clip regeneration must use the selected `TimelineClip` fields:

- `khmer_text`
- `voice_model`
- `speaking_rate`
- source metadata needed to create the output path

It must not read from imported `translation.json` as an editing source of truth.

## Configuration

Provider settings are loaded through configuration boundaries, not directly from UI widgets. See [SETTINGS.md](SETTINGS.md).

## Lifecycle

1. Application loads settings into `ToolConfig`.
2. Provider modules self-register descriptors.
3. `ProviderManager` resolves selected provider IDs.
4. Pipeline job calls `validate()`.
5. Pipeline job calls the provider capability method.
6. Provider adapter delegates to the existing implementation.
7. Pipeline writes normalized artifacts into the project.

## Future Guidance

- Add new providers by capability, not by hardcoded provider names in core logic.
- Keep provider SDK objects out of widgets.
- Add tests with mocked providers before wiring live-provider behavior.
