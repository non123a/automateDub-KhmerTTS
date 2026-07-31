# Providers

Providers wrap external AI and media-service capabilities behind stable application boundaries.

Related documents:

- [PIPELINE.md](PIPELINE.md)
- [SETTINGS.md](SETTINGS.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)

## Code Ownership

Provider-facing code currently appears in:

- `automatedub/vertical_slice/transcription.py`
- `automatedub/vertical_slice/localization.py`
- `automatedub/vertical_slice/tts.py`
- `automatedub/config.py`
- `automatedub_studio/backend/regeneration_service.py`

## Provider Types

- Transcription providers convert audio into source-language transcript segments.
- Localization providers convert transcript segments into natural Khmer dialogue.
- TTS providers generate speech audio from Khmer text and voice settings.
- Media tools such as FFmpeg/FFprobe are external process dependencies, not AI providers, but should still be isolated behind command/service boundaries.

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

## Future Guidance

- Add new providers by capability, not by hardcoded provider names in core logic.
- Keep provider SDK objects out of widgets.
- Add tests with mocked providers before wiring live-provider behavior.
