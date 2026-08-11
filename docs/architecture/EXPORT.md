# Export

Export owns final deliverable generation. It turns project artifacts plus current edit state into rendered media output.

Related documents:

- [PIPELINE.md](PIPELINE.md)
- [TIMELINE.md](TIMELINE.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)
- [APPLICATION.md](APPLICATION.md)

## Code Ownership

- `automatedub_studio/export/manager.py`
- `automatedub_studio/ui/export_wizard.py`
- `automatedub_studio/ui/export_progress_window.py`
- `automatedub_studio/backend/export_service.py`
- `automatedub_studio/backend/export_worker.py`
- `automatedub_studio/ui/export_dialog.py`
- `automatedub/vertical_slice/mix.py`

## Responsibilities

- Coordinate export jobs through `ExportManager`.
- Collect user export settings through `ExportWizard`.
- Build final mix/render plans from current project edit state.
- Run media rendering through FFmpeg boundaries.
- Keep rendering work outside the UI thread.
- Report progress and retain a non-dismissible progress window until verification succeeds or fails.
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

Studio-managed exports also write metadata under:

- `exports/<filename>.export.json`

Metadata records the output path, subtitle path, selected video preset, codec,
quality, audio mode, subtitle mode, and stage list for future export history.

## Export Pipeline

```text
MainWindow
    -> ExportWizard
    -> ExportManager
    -> ExportProgressWindow observes events

ExportManager
    -> Preparing Project
    -> Rendering Audio
    -> Encoding Video
    -> Finalizing MP4
    -> Verifying Output
```

Every stage reports Started, Progress, Completed, and Failed events. The
application-modal progress window cannot be dismissed while export is running.
It exposes Open File, Open Folder, and Close only after a successful
verification. Failures retain the window with `Export Failed`, the diagnostic
reason, and Retry.

`Verifying Output` runs only after FFmpeg completes. It requires a real,
non-empty output file and a successful FFprobe read with exactly one video
stream and exactly one audio stream. Export metadata and the completion state
are written only after those checks pass.

## Export Presets

`ExportWizard` presents editor-oriented strategies instead of raw FFmpeg
arguments:

- output folder
- filename
- video encoding preset:
  - Copy Original: stream-copy the source video.
  - H.264: re-encode to H.264/yuv420p. This is the default.
  - H.265 (HEVC): re-encode to H.265/yuv420p when a supported encoder exists.
  - Original Codec: advanced stream-copy of the source codec.
- compression quality: Highest Quality, High, Balanced, Small File; disabled for copy presets
- audio mode: Khmer only, Original only, Mixed
- subtitle mode: None, External (.srt), Embedded, Burned Into Video

The wizard separates Video Encoding from Compression Quality and shows an
export preview with video codec, AAC audio codec, subtitle mode, estimated
file size, speed, and compatibility. It persists the last selected export
settings in application settings so repeated exports keep the user's preferred
strategy.

Internally, presets map to encoder choices in `backend/export_service.py`.
Quality maps to encoder CRF values. Raw CRF and FFmpeg arguments remain hidden
from the normal dialog.

## Preset Validation

Before export, Studio validates the selected strategy against the source video
and current timeline:

- Fastest is available only when the Video track has no clips representing
  video edits and the source is approved for stream-copy MP4 output.
- The approved Fastest sources are H.264, H.265/HEVC, or MPEG-4 video in MP4
  or MOV containers. AV1, VP9, unknown codecs, and other containers are
  rejected conservatively.
- Compatible is always available and re-encodes to H.264/yuv420p.
- H.264/H.265 availability is validated against FFmpeg's installed encoders.
  H.265 prefers `hevc_videotoolbox` on macOS and falls back to `libx265`; it
  is disabled when neither is present. H.264 uses the equivalent supported
  encoder and is disabled if one cannot be found.
- H.265 always re-encodes; selecting `Small File` never changes it into a
  stream copy.
- Original Codec is an advanced stream-copy option. It is blocked by video
  edits and warns when the source codec, including AV1 or VP9, has limited
  playback compatibility.

The wizard gives every preset an inline `Available` or `Unavailable` state and
an exact reason. The same result is listed in Export Diagnostics alongside the
source codec/container and FFmpeg encoder inventory. Refreshing capabilities
re-evaluates and automatically enables any preset whose requirements are now
satisfied. `ExportManager` refreshes the full capability report immediately
before rendering, and the pure export service repeats the stream-copy safety
validation, so UI state cannot bypass either encoder or copy requirements.

External subtitles create a separate `.srt` file. Embedded subtitles are muxed
as an MP4 subtitle stream, while Burned Into Video re-renders the picture and
therefore cannot be combined with copy presets.

`pipeline/audio.wav` is used as full-movie audio only after an explicit
Original Movie Audio track has been inserted into the Timeline. Without that
track, the export mixer starts from silence and uses the visible TTS clips.

## Capability Audit

Before the wizard presents export options, Studio probes the source with
FFprobe and FFmpeg with `-version`, `-encoders`, and `-muxers`. The capability
report records codec, container, pixel format, resolution, frame rate, video
and audio timeline state, subtitle mode, installed encoders, hardware
encoders, and MP4 muxer support.

| Preset | Required video codec | Required encoder/support | Availability rule | Previous failure mode |
| --- | --- | --- | --- | --- |
| Copy Original | Source codec unchanged | Safe MP4 stream copy; no video edits | Source codec/container must be approved for MP4 copy | Copying AV1, VP9, or an unsupported container into MP4 created an output that was not reliably playable. |
| H.264 | H.264/yuv420p | `h264_videotoolbox` or `libx264`; MP4 muxer | Disabled if no supported H.264 encoder or MP4 muxer exists | None when a compatible H.264 encoder was available. |
| H.265 (HEVC) | H.265/yuv420p | `hevc_videotoolbox` or `libx265`; MP4 muxer | Disabled if no supported H.265 encoder or MP4 muxer exists | The old path assumed `libx265` was installed and failed late in FFmpeg when it was not. |
| Original Codec | Source codec unchanged | Safe MP4 stream copy; no video edits | Same MP4 copy safety rule as Copy Original | It exposed unsafe source codecs as an advanced option, even though the output target remained MP4. |

The Export Diagnostics panel shows the report, the selected preset's required
and actual encoder, and the planned FFmpeg mux command. The final executed
command remains in `exports/last_export_debug.json`.

The current renderer delegates existing mixed-audio export to the tested
Milestone 9 backend. Original-only and Khmer-only modes use existing audio
artifacts when available.

## Boundary With Playback

Export mixing is separate from editing playback. Editing playback is real-time and consumes `Timeline`. Export may translate timeline edits into an FFmpeg plan, but export-specific processing must not become a requirement for preview playback.

## Boundary With Timeline

Timeline owns edit state. Export reads it. Export should not mutate live Timeline state as a side effect of rendering.

## Future Guidance

- Keep pure export logic testable without Qt.
- Keep worker/progress UI code separate from render logic.
- Add explicit tests for every new exported artifact or render option.
