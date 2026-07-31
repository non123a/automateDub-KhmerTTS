# Project System

The Project System owns project discovery, loading, metadata, and edit persistence. It turns project-directory artifacts into application state without becoming the live editing model.

Related documents:

- [APPLICATION.md](APPLICATION.md)
- [TIMELINE.md](TIMELINE.md)
- [PLAYBACK.md](PLAYBACK.md)
- [SETTINGS.md](SETTINGS.md)

## Code Ownership

- `automatedub_studio/project/models.py`
- `automatedub_studio/project/loader.py`
- `automatedub_studio/project/edits.py`
- `automatedub_studio/project/timeline_edits.py`
- `automatedub_studio/project/video_proxy.py`
- `automatedub_studio/backend/video_proxy_job.py`

## Project Artifacts

Common project files include:

- `project.json`: project metadata and source/editor video references.
- `audio.wav`: extracted original movie audio.
- `translation.json`: imported transcript/translation data.
- `translation.edited.json`: legacy/edit compatibility data.
- `timeline.edited.json`: saved Timeline source-of-truth edits.
- `tts/*.wav`: imported/generated segment TTS audio.
- `tts/clips/*.wav`: regenerated clip draft audio.
- `proxy_video.mp4`: optional editor proxy video.

## Loading Order

1. Discover and load project metadata.
2. Discover or prepare editor video.
3. Load transcript/translation segments.
4. Create a default Timeline from imported artifacts.
5. Load `timeline.edited.json` if present.
6. Overlay saved timeline values onto `TimelineClip` objects.
7. Publish the Timeline to Playback.

## Ownership Boundary

- `translation.json` is imported project data and should not be rewritten by inspector edits.
- `timeline.edited.json` stores user-editable timeline state.
- `TimelineClip` becomes the live editing object after project load.
- Project services may construct Timeline state but should not drive live editing behavior.

## Video Discovery And Proxy

Video discovery accepts project metadata first, then supported video files in the project directory. If a codec is not editor-friendly, the proxy workflow creates an H.264 editor video without modifying the source.

Export continues to reference the source video. Preview loads the editor video.

## Persistence Rules

- Save current timeline edits to `timeline.edited.json`.
- Preserve imported `translation.json`.
- Persist regenerated clip paths when they become timeline state.
- Keep path handling project-relative where practical for portability.

## Future Guidance

- Add new persisted editor fields to `TimelineClip` serialization first.
- Keep migration of older edited timelines close to project/timeline loading.
- Avoid storing UI-only state in project artifacts unless it is intentionally persistent.
