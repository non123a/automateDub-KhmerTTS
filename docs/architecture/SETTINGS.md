# Settings

Settings owns configuration sources for the CLI, Studio, providers, media tools, and user preferences.

Related documents:

- [APPLICATION.md](APPLICATION.md)
- [PROVIDERS.md](PROVIDERS.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)

## Code Ownership

- `automatedub/config.py`
- `automatedub/doctor.py`
- `automatedub/setup.py`
- `automatedub_studio/settings/manager.py`
- `automatedub_studio/ui/settings_window.py`
- `automatedub_studio/providers/registry.py`
- Studio usage of `QSettings` in `automatedub_studio/ui/main_window.py`

## Configuration Sources

- Environment variables.
- `.env` files.
- CLI arguments.
- Project metadata such as `project.json`.
- Studio application preferences through `QSettings`.
- Studio settings through `SettingsManager`.
- Provider credentials through `CredentialStore`.

## Responsibilities

- Load tool and provider configuration.
- Validate required local dependencies.
- Expose settings through typed objects such as `ToolConfig`.
- Keep provider credentials out of project artifacts.
- Persist user preferences separately from project edit state.
- Store first-run completion and the default project folder.

## Non-Responsibilities

- Settings does not own Timeline edit state.
- Settings does not own imported transcript or translation data.
- Settings does not execute provider calls directly.

## Project Settings Boundary

Project metadata describes the project and source/editor media choices. User editing state belongs in timeline edit files. Global user preferences belong in application settings.

## Provider Settings

Provider selection, API keys, language IDs, model names, and speed defaults should flow through configuration boundaries and provider adapters.

See [PROVIDERS.md](PROVIDERS.md).

## Settings Window

Studio exposes application settings through `SettingsWindow` with sections for:

- General
- AI Providers
- Voices
- Models
- Cache
- Logs
- Advanced

The first-run wizard uses the same `SettingsManager` boundary for default
project folder and provider choices, so setup does not introduce a second
configuration path.

Provider selectors are populated from `ProviderRegistry`; the UI must not keep
its own hardcoded provider lists. Provider-specific fields come from provider
descriptors, allowing adapters to define configuration needs such as API key,
base URL, executable, model path, model, default voice, language, speaking
rate, timeout, and diagnostics.

Changing a provider selection rebuilds only that descriptor-driven
configuration panel. Saving persists provider IDs through `SettingsManager`, so
restart restores the same STT, Translation, and TTS selections.

## Secure Settings

`SettingsManager` stores non-secret preferences in a user settings file. Secrets
go through the `CredentialStore` abstraction.

Projects may store provider identifiers and selected voice, but must never store
API keys.

```text
SettingsWindow
    -> SettingsManager
    -> CredentialStore
    -> ProviderManager
    -> ProviderRegistry
```

## Diagnostics, Cache, And Logs

- Provider diagnostics call `validate()` and report connection/authentication state and latency.
- Voice browsing calls `TTSProvider.list_voices()`, supports manual refresh, and automatically reloads voices after successful TTS validation.
- The voice browser shows loading, empty, and error states instead of silently leaving a blank list.
- Voice selection stores provider voice IDs and reselects them after restart when the provider returns the same voice.
- Cache usage is computed from the configured cache directory, with a clear-cache action.
- Logs show recent pipeline errors and can open the configured log directory.

## Future Guidance

- Prefer typed settings objects over scattered environment reads.
- Keep validation messages actionable.
- Add tests for default, `.env`, and environment override behavior.
