# Application

The Application subsystem is the Studio shell. It composes UI widgets, owns global actions, routes signals, and coordinates project, timeline, playback, regeneration, and export services.

Related documents:

- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)
- [TIMELINE.md](TIMELINE.md)
- [PLAYBACK.md](PLAYBACK.md)
- [EXPORT.md](EXPORT.md)
- [SETTINGS.md](SETTINGS.md)

## Code Ownership

- `automatedub_studio/app.py`: application setup.
- `automatedub_studio/main.py`: Studio executable entry point.
- `automatedub_studio/ui/main_window.py`: main shell and orchestration.
- `automatedub_studio/ui/project_info_panel.py`: project metadata display.
- `automatedub_studio/inspector/segment_inspector.py`: selected clip inspector.

## Responsibilities

- Create the main window and top-level widgets.
- Own menu and toolbar actions.
- Connect Timeline, Inspector, Playback, Project, Regeneration, and Export signals.
- Keep the UI responsive by running long jobs through background workers.
- Present non-intrusive feedback for expected blocked operations.
- Preserve application-level shortcuts such as Play/Pause and timeline editing commands.

## Non-Responsibilities

- The Application does not own media processing algorithms.
- The Application does not own provider-specific API details.
- The Application does not own final export mixing internals.
- The Application does not create a second editable model outside the Timeline.

## Interaction Pattern

```text
MainWindow
    -> loads Project
    -> initializes Timeline
    -> publishes Timeline to Playback
    -> routes Inspector edits into Timeline commands
    -> starts backend jobs for regeneration/export/proxy creation
```

## UI Boundary

Widgets should emit intent through signals and expose focused update methods. Business logic belongs in:

- project services for loading and persistence
- backend jobs for long-running work
- timeline model/services for edit state
- playback controller for preview transport
- export services for render output

## Error And Status Reporting

- Expected blocked actions should use status-bar messages.
- Long-running operations should show progress and remain cancelable where appropriate.
- Hard failures that prevent the project from opening or exporting may use dialogs.

## Future Guidance

- Add new top-level user workflows through `MainWindow` orchestration, then delegate.
- Keep direct widget-to-provider calls out of the UI.
- Add tests at the subsystem boundary when changing signal routing.
