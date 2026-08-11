# Project System

The Project System owns project discovery, loading, metadata, and edit persistence. It turns project-directory artifacts into application state without becoming the live editing model.

Related documents:

- [APPLICATION.md](APPLICATION.md)
- [TIMELINE.md](TIMELINE.md)
- [PLAYBACK.md](PLAYBACK.md)
- [SETTINGS.md](SETTINGS.md)

## Code Ownership

- `automatedub_studio/project/models.py`
- `automatedub_studio/project/manager.py`
- `automatedub_studio/project/recent_projects.py`
- `automatedub_studio/project/browser.py`
- `automatedub_studio/project/assets.py`
- `automatedub_studio/project/session.py`
- `automatedub_studio/project/loader.py`
- `automatedub_studio/project/edits.py`
- `automatedub_studio/project/timeline_edits.py`
- `automatedub_studio/project/video_proxy.py`
- `automatedub_studio/backend/video_proxy_job.py`

## Project Artifacts

Common project files include:

- `project.json`: project metadata and source/editor video references.
- `.autodub/` project folder for new Studio-managed projects.
- `source/`: imported source video storage.
- `pipeline/`: pipeline stage artifacts.
- `timeline/`: timeline-specific project artifacts.
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

## Creation Order

1. Home window collects project name, location, source video, and languages.
2. UI passes a `NewProjectRequest` to `PipelineManager`.
3. `PipelineManager` runs jobs that call `ProjectManager` for project structure and video copy.
4. Source video is copied into `source/`.
5. `project.json` is initialized and updated with pipeline artifact paths.
6. ProcessingWindow observes pipeline state and can open the editor when the project is ready.

## Application Experience Services

- `RecentProjectsManager` persists recent project metadata outside project folders, including name, last-opened time, status, and pinned state.
- `ProjectBrowser` reads project details and performs project-level actions: rename, duplicate, archive, and delete.
- `MissingAssetRecovery` checks media references in `project.json` and can relink missing source/editor media.
- `SessionRecoveryManager` records open sessions and detects unclean shutdown state for recovery prompts.

These services are Qt-free. UI widgets invoke them but do not own filesystem rules.

## Ownership Boundary

- `translation.json` is imported project data and should not be rewritten by inspector edits.
- `timeline.edited.json` stores user-editable timeline state.
- `TimelineClip` becomes the live editing object after project load.
- Project services may construct Timeline state but should not drive live editing behavior.

## Video Discovery And Proxy

Video discovery accepts project metadata first, then supported video files in the project directory. If a codec is not editor-friendly, the proxy workflow creates an H.264 editor video without modifying the source.

Export continues to reference the source video. Preview loads the editor video.

The project loader resolves media through one `MediaAsset` model:

- `source_video`: original source used for export
- `proxy_video`: editor-safe preview media
- `extracted_audio`: source audio used by timeline tracks

These paths are stored as absolute `Path` values on `Project.media`. The
compatibility fields on `Project` remain available for older serialization,
but new subsystems use `source_video_path`, `preview_video_path`,
`export_video_path`, and `extracted_audio_path`.

Metadata stores project-relative paths. This is important for source files
under `source/`; storing only a basename causes a reopened project to resolve
the source incorrectly while the proxy still works.

## Persistence Rules

- Save current timeline edits to `timeline.edited.json`.
- Preserve imported `translation.json`.
- Persist regenerated clip paths when they become timeline state.
- Keep path handling project-relative where practical for portability.
- Keep recent-project and session-recovery state in user application data, not inside project edit artifacts.

## Future Guidance

- Add new persisted editor fields to `TimelineClip` serialization first.
- Keep migration of older edited timelines close to project/timeline loading.
- Avoid storing UI-only state in project artifacts unless it is intentionally persistent.
