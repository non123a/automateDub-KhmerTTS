# Processing Pipeline

The Processing Pipeline owns batch media and language processing. It is separate from Studio editing playback and should remain usable from the CLI.

Related documents:

- [PROVIDERS.md](PROVIDERS.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)
- [EXPORT.md](EXPORT.md)
- [SETTINGS.md](SETTINGS.md)

## Code Ownership

- `automatedub/cli.py`
- `automatedub/vertical_slice/audio.py`
- `automatedub/vertical_slice/transcription.py`
- `automatedub/vertical_slice/localization.py`
- `automatedub/vertical_slice/tts.py`
- `automatedub/vertical_slice/mix.py`
- `automatedub/vertical_slice/tts_combine.py`
- `automatedub/vertical_slice/duration_report.py`
- `automatedub_studio/pipeline/manager.py`
- `automatedub_studio/pipeline/jobs.py`
- `automatedub_studio/pipeline/timeline_generation.py`

## Pipeline Stages

```text
input video
    -> audio extraction
    -> transcription
    -> localization
    -> TTS generation
    -> mix planning/audio mix
    -> export/render
```

The current vertical slice has implemented processing through mix artifacts. Studio uses those artifacts as project inputs and edit references.

## Studio Project Pipeline

New Studio projects use an observable Pipeline Manager:

```text
ProcessingWindow
    -> observes PipelineManager
    -> renders stage state

PipelineManager
    -> Create Project
    -> Copy Source Video
    -> Extract Audio
    -> Transcription through ProviderManager
    -> Speech Detection artifact
    -> Translation through ProviderManager
    -> Timeline Generation

Jobs
    -> existing vertical-slice modules
```

Each job emits Started, Progress, Completed, and Failed events. On failure the
manager stops remaining jobs and leaves retry/cancel decisions to the UI.

TTS generation remains out of this Studio processing flow until a later
milestone.

AI stages must request provider capabilities through `ProviderManager`. They
must not instantiate Whisper, translation clients, Camb.ai, or other concrete
providers directly.

## Responsibilities

- Validate media/tooling prerequisites.
- Run deterministic media commands through FFmpeg/FFprobe boundaries.
- Call provider abstractions for transcription, localization, and TTS.
- Write pipeline artifacts into project output directories.
- Preserve diagnostic artifacts such as usage and duration reports.

## Non-Responsibilities

- The pipeline does not own live Studio timeline state.
- The pipeline does not drive real-time playback.
- The pipeline does not directly edit `TimelineClip` state in the UI.

## Studio Relationship

Studio consumes pipeline output:

- `source/<video>` stores the imported source video.
- `pipeline/audio.wav` becomes original audio source material.
- `pipeline/transcript.json` stores transcription output.
- `pipeline/speech_segments.json` stores detected segment timing.
- `pipeline/translation.json` seeds initial segment and clip metadata.
- `timeline/timeline.edited.json` stores the initial Timeline model.
- `tts/*.wav` seeds Khmer TTS clips.
- `mixed_audio.wav` and mix plans are export/render artifacts, not editing playback requirements.

## Provider Boundary

Provider-specific code belongs behind provider abstractions. Pipeline stages should request capabilities and data, not depend on concrete provider implementation details.

See [PROVIDERS.md](PROVIDERS.md).

## Future Guidance

- Keep stage functions testable without a GUI.
- Make new pipeline artifacts explicit and documented.
- Avoid coupling processing-stage timing corrections to Studio editing timing unless the Timeline model intentionally stores them.
