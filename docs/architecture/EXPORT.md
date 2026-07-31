# Export

Export owns final deliverable generation. It turns project artifacts plus current edit state into rendered media output.

Related documents:

- [PIPELINE.md](PIPELINE.md)
- [TIMELINE.md](TIMELINE.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)
- [APPLICATION.md](APPLICATION.md)

## Code Ownership

- `automatedub_studio/backend/export_service.py`
- `automatedub_studio/backend/export_worker.py`
- `automatedub_studio/ui/export_dialog.py`
- `automatedub/vertical_slice/mix.py`

## Responsibilities

- Build final mix/render plans from current project edit state.
- Run media rendering through FFmpeg boundaries.
- Keep rendering work outside the UI thread.
- Report progress and support cancellation where practical.
- Clean temporary artifacts on success, failure, or cancellation.
- Preserve source video and source project artifacts.

## Inputs

Export may read:

- source video
- `audio.wav`
- `translation.json`
- generated TTS WAVs
- regenerated clip WAVs
- saved/current timeline edits
- export options

## Outputs

Export writes final user-facing media, typically MP4, and may create temporary intermediate audio during rendering.

## Boundary With Playback

Export mixing is separate from editing playback. Editing playback is real-time and consumes `Timeline`. Export may translate timeline edits into an FFmpeg plan, but export-specific processing must not become a requirement for preview playback.

## Boundary With Timeline

Timeline owns edit state. Export reads it. Export should not mutate live Timeline state as a side effect of rendering.

## Future Guidance

- Keep pure export logic testable without Qt.
- Keep worker/progress UI code separate from render logic.
- Add explicit tests for every new exported artifact or render option.
