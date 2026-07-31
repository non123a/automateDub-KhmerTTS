# Architecture Overview

This directory documents the application architecture that future AutomateDub Studio work should follow. Each document covers one subsystem and links to related subsystems instead of duplicating details.

## Application Shape

```text
Application
    |-- Project Manager
    |-- Processing Pipeline
    |-- Timeline
    |-- Playback
    |-- Providers
    |-- Export
    `-- Settings
```

## Entry Points

- Studio GUI: `automatedub_studio/app.py`, `automatedub_studio/main.py`
- Studio shell: `automatedub_studio/ui/main_window.py`
- CLI pipeline: `automatedub/cli.py`
- Vertical-slice processing modules: `automatedub/vertical_slice/`

## Project Lifecycle

1. A project directory is opened through the application shell.
2. The Project Manager loads source artifacts such as `audio.wav`, `translation.json`, TTS WAVs, video metadata, and saved timeline edits.
3. The Timeline is constructed from project artifacts, then edited values from `timeline.edited.json` are overlaid.
4. Playback receives the Timeline model and evaluates active clips from it.
5. Inspector edits mutate `TimelineClip` state, then project save persists the timeline edit snapshot.
6. Regeneration creates new draft clips and writes new audio under the project TTS clip area.
7. Export reads project artifacts and current edit state to produce deliverables without changing editing playback behavior.

See [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md), [TIMELINE.md](TIMELINE.md), [PLAYBACK.md](PLAYBACK.md), and [EXPORT.md](EXPORT.md).

## Subsystem Responsibilities

- Application: owns startup, window composition, global actions, and high-level signal routing. See [APPLICATION.md](APPLICATION.md).
- Project Manager: owns project discovery, loading, metadata, and persistence boundaries. See [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md).
- Processing Pipeline: owns import-time and batch processing stages. See [PIPELINE.md](PIPELINE.md).
- Timeline: owns editable timeline state and clip/track layout. See [TIMELINE.md](TIMELINE.md).
- Playback: owns preview transport and real-time audio/video coordination. See [PLAYBACK.md](PLAYBACK.md).
- Providers: owns external AI/service integrations behind stable capability boundaries. See [PROVIDERS.md](PROVIDERS.md).
- Export: owns final render/mix output. See [EXPORT.md](EXPORT.md).
- Settings: owns configuration sources and user/application preferences. See [SETTINGS.md](SETTINGS.md).

## Ownership Boundaries

- `TimelineClip` is the editor source of truth during Studio editing.
- `Segment`, `EditableSegment`, `MixSpeechTrack`, and imported JSON artifacts are import/export data, not live editor state.
- Playback consumes the Timeline model directly and must not rebuild clip order from legacy segment lists.
- Providers are accessed through backend/service boundaries, not directly from widgets.
- Export may translate timeline state into render plans, but export-specific mixing must not leak into editing playback.
- Project loading may create default timeline state, but user edits are stored in `timeline.edited.json`.

## High-Level Interactions

```text
Project Manager
    -> creates/loads project artifacts
    -> builds Timeline
    -> overlays saved Timeline edits

Timeline
    -> publishes Timeline model changes
    -> drives Inspector selection
    -> supplies Playback source of truth

Inspector
    -> edits selected TimelineClip
    -> requests save/regeneration through Application shell

Playback
    -> reads active clips from Timeline
    -> uses video as visual master clock

Export
    -> reads project artifacts plus saved/current edits
    -> writes output media
```

## Rules For Future Work

- Prefer adding to the relevant subsystem document instead of expanding this overview.
- Do not introduce a second live editing model.
- Keep UI widgets thin: route long-running work through backend services/jobs.
- Keep processing/export code usable without a `QApplication` where practical.
- Keep provider-specific behavior behind provider adapters or service boundaries.
