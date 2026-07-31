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
- Studio usage of `QSettings` in `automatedub_studio/ui/main_window.py`

## Configuration Sources

- Environment variables.
- `.env` files.
- CLI arguments.
- Project metadata such as `project.json`.
- Studio application preferences through `QSettings`.

## Responsibilities

- Load tool and provider configuration.
- Validate required local dependencies.
- Expose settings through typed objects such as `ToolConfig`.
- Keep provider credentials out of project artifacts.
- Persist user preferences separately from project edit state.

## Non-Responsibilities

- Settings does not own Timeline edit state.
- Settings does not own imported transcript or translation data.
- Settings does not execute provider calls directly.

## Project Settings Boundary

Project metadata describes the project and source/editor media choices. User editing state belongs in timeline edit files. Global user preferences belong in application settings.

## Provider Settings

Provider selection, API keys, language IDs, model names, and speed defaults should flow through configuration boundaries and provider adapters.

See [PROVIDERS.md](PROVIDERS.md).

## Future Guidance

- Prefer typed settings objects over scattered environment reads.
- Keep validation messages actionable.
- Add tests for default, `.env`, and environment override behavior.
