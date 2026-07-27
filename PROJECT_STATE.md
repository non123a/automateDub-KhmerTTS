# Project State

AutomateDub is a planned knowledge-driven AI localization platform for Khmer media. Its long-term purpose is to localize movies, series, anime, short-form video, podcasts, audiobooks, educational content, and corporate media with consistent characters, natural Khmer dialogue, high-quality voices, measurable quality, and traceable human review.

The current implementation strategy is vertical-slice first. The immediate product proof is the Smallest Working Pipeline: take one Chinese MP4 and produce one playable Khmer MP4 by extracting audio, transcribing speech, translating/localizing dialogue to Khmer, generating Khmer speech, replacing or covering the original dialogue, and rendering a final MP4.

Current milestone: VS5, Render Playable MP4, is the next implementation phase to build. The project has completed VS0 through VS4.

Completed milestones:

- VS0: Minimal project harness and audio extraction. The CLI accepts an input MP4 and output directory, validates local environment/tooling, and produces `output/audio.wav`.
- VS1: Transcription. Extracted audio is converted into timestamped Chinese transcript JSON using a local Whisper path through a `LocalTranscriber` boundary.
- VS2: Khmer Dialogue Localization. Transcript JSON is converted into `translation.json` with Khmer localized dialogue while preserving segment timestamps. It uses NBWCode through a `DialogueLocalizer` boundary, preferring `/responses` and falling back to `/chat/completions`.
- VS3: Khmer Speech Generation. Translated segments produce Khmer speech audio through a provider-independent `TTSProvider` boundary. Camb.ai is the first production provider implementation, configured through `.env` with `TTS_PROVIDER=cambai`, `CAMB_API_KEY`, `CAMB_LANGUAGE`, `CAMB_VOICE_ID`, and `TTS_MODEL`. NBWCode remains available as a legacy provider behind the same interface. VS3 writes one WAV per successful segment, continues after segment failures, preserves `tts/errors.json`, and writes `usage/tts_usage.json` without pricing estimates.
- VS4: Dialogue Replacement And Mix. `output/audio.wav`, `output/translation.json`, and `output/tts/*.wav` produce `output/mixed_audio.wav` and `output/mix_plan.json`. The implementation overlays generated Khmer speech at approximate source segment start times with a configurable mix-layer `TTS_SYNC_OFFSET_MS` delay adjustment, defaulting to 200 ms. Each generated speech track's real WAV duration is compared against its translation segment's window and given a bounded `atempo` correction (clamped to `[0.85, 1.15]`) so short TTS renders inside long whisper.cpp segment windows are nudged toward the window without ever fully stretching to fill trailing silence; the applied `atempo` is recorded per segment in `mix_plan.json`.
- Dialogue-aware ducking: instead of a constant global attenuation, the original/background track stays at full volume except during dialogue windows derived from `translation.json` segment `start`/`end` timestamps. Overlapping or touching (adjacent) segment windows are merged into single ducking spans before the FFmpeg filter graph is built, so a given moment in time is only ever attenuated once. Each merged span becomes one timeline-enabled `volume=volume=<DUCK_VOLUME>:enable='between(t,start,end)'` filter chained onto the original track (`mix.build_duck_filters`); with no dialogue at all, the chain degrades to a passthrough `anull` filter and the track plays at full volume throughout. `.env` accepts `DUCK_VOLUME` (default `0.0`, fully muting the original during dialogue), loaded through `ToolConfig.duck_volume`. The applied `duck_volume` and the merged `duck_windows` are recorded in `mix_plan.json`. The ducking helper only takes an input/output filter-graph label, dialogue windows, and a volume, independent of what audio feeds that label -- swapping in a future source-separated music/SFX stem in place of the single mixed source track requires no change to this logic.
- Duration diagnostics: `automatedub duration-report output/` compares each translation segment's expected window duration against its generated TTS WAV duration and writes `output/duration_report.json` with per-segment ratios and the worst mismatches ranked, without mutating any pipeline artifact.
- Optional Khmer-only timeline: `automatedub tts combine output/` produces `output/tts_combined.wav`, a Khmer-speech-only audio track the same duration as `output/audio.wav`, with each TTS clip placed at its segment's original `start` timestamp (no ducking, no atempo, no original audio mixed in) and silence everywhere else, including where a segment's TTS file is missing. Timing and skip bookkeeping are written to `output/tts_combined_plan.json` alongside the generated ffmpeg command.
- Configurable TTS speed: `.env` accepts `TTS_SPEED` (default `1.0`), loaded through `ToolConfig.tts_speed` and reported by `automatedub doctor` as a two-line `TTS Speed:` / `✓ 1.0` block. The `TtsProviderInfo` abstraction exposes a `speed` field on every provider's `describe()` output. Camb.ai natively supports speaking-rate control, so `CambAIProvider.generate()` passes `voice_settings=StreamTtsVoiceSettings(speaking_rate=tool_config.tts_speed)` to the SDK's `text_to_speech.tts()` call; NBWCode's HTTP payload is left unchanged since its API has no confirmed speed parameter, keeping the abstraction ready for future providers without hardcoding Camb.ai-specific logic into the rest of the pipeline.

Current working pipeline: `automatedub dub input.mp4 output/` now runs VS0 through VS4: extract audio, transcribe, localize, generate per-segment TTS WAVs through the configured TTS provider, then write a mixed audio track and mix plan. `automatedub tts output/` reruns only VS3, `automatedub tts sample output/` generates a short voice-quality preview in `output/sample/` with per-segment WAVs, `sample.wav`, and `sample.txt`, `automatedub tts combine output/` writes the optional Khmer-only `tts_combined.wav` timeline described above, `automatedub tts providers` reports configured provider status, `automatedub camb voices` lists Camb.ai voices, `automatedub camb test [output/]` generates one `tts/test.wav` from the first translated segment, `automatedub mix output/` reruns only VS4 from existing artifacts, and `automatedub duration-report output/` writes the duration diagnostic described above.

Next milestone: VS5 should combine the original video stream with `output/mixed_audio.wav`, write one playable Khmer MP4, and run basic FFprobe validation.

Current blocker: the vertical slice is not yet end-to-end playable because final MP4 rendering is not implemented.

Architecture decisions that still matter:

- The final architecture is frozen and remains the long-term destination.
- The product is not a one-off dubbing script; it is a durable knowledge-driven localization platform.
- The core design centers on a knowledge layer, workflow orchestration, and provider-independent voice capabilities.
- The workflow is expected to become a graph with persistent artifacts and correction-driven reruns.
- Khmer voice generation is the highest-risk subsystem and must be handled through provider capability benchmarking, not assumptions.

Implementation constraints:

- Use Python 3.12+ with `uv`.
- Keep the first runtime local, but do not make the architecture local-only.
- Design for PostgreSQL-compatible durable workflow state from day one; SQLite is only a local profile.
- Use FFmpeg/FFprobe as the media foundation.
- Keep providers behind capability boundaries where possible.
- Keep TTS synchronization offsets in the mix layer; do not mutate Whisper or translation timestamps for render-time alignment.
- Use explicit quality gates, logging, cost accounting, and benchmark tracking.
- Treat ducking original audio under generated speech as the reliable baseline for mix/render work.

Things that must never change:

- Natural Khmer localization, not literal translation.
- Consistent character identity and continuity.
- Provider-independent voice routing, not provider-name-based logic.
- Human review remains necessary until evidence shows it can be reduced safely.
- Corrections must remain versioned, evidence-backed, and able to supersede prior facts.
- Voice cloning is not the MVP default and requires explicit consent and licensing.
- Do not assume a production-quality Khmer TTS provider exists without benchmarks.

AutomateDub Studio (PySide6 desktop GUI):

- Studio is a separate GUI application in `automatedub_studio/` for reviewing and editing dubbing projects.
- Studio Milestone 1 — Project model, loader, and smoke-test wiring.
- Studio Milestone 2 — Loader cleanup and smoke-test against real `output/` directories.
- Studio Milestone 3 — VideoPlayerWidget (Play/Pause/Stop, seek slider, QStackedWidget for no-video vs video surface).
- Studio Milestone 4 — TimelineWidget (two-lane QGraphicsScene/QGraphicsView, ClipItem selection, Ctrl+Wheel zoom, playhead tracking).
- Studio Milestone 5 — SegmentInspectorWidget dock (empty state, full segment details, placeholder controls). Complete.
- Studio Milestone 6 — Editable clip timing. `Segment.offset_ms` mutable field; horizontal drag in `_TimelineView`; both lanes reposition together via `apply_offset`; live inspector offset display (`+250 ms` / `-120 ms`); `File → Save Project` writes `translation.edited.json` (modified segments only); `apply_edits` auto-loads offsets on project open; `QUndoStack` with `OffsetChangeCommand` for Ctrl+Z/Ctrl+Y. Complete. 250 tests passing.
- Next Studio milestone: Milestone 7 (TBD).

Test findings:

- Total test functions: 228 (125 pipeline + 103 studio).
- VS0 is covered by input validation, FFmpeg command construction, audio extraction success/failure, and path naming.
- VS1 is covered by WAV/model validation, whisper.cpp command construction, transcript normalization, transcript writing, CLI invocation, retry behavior, and failure reporting.
- VS2 is covered by transcript parsing, prompt construction, response normalization, batch splitting/merging, Responses-to-Chat Completions fallback, debug artifact writing, and endpoint detection.
- VS3 is covered by translation parsing, provider selection, NBWCode request construction, mocked Camb.ai SDK generation, mocked Camb.ai voice listing, WAV validation, one-segment Camb.ai test generation, per-segment file generation, sample segment selection, sample WAV generation, FFmpeg sample concatenation command construction, sample text writing, failure continuation, error log writing, and usage artifact writing.
- VS4 is covered by mix path naming, translation timing parsing, configurable TTS sync delay calculation, missing TTS skipping, bounded atempo computation and clamping, FFmpeg mix command construction (including per-segment atempo), mix-plan writing (including atempo field), mixed-audio output behavior, and no-TTS failure handling.
- Dialogue-aware ducking is covered by merging overlapping/adjacent dialogue windows, keeping separate non-overlapping windows apart, returning no windows when there is no dialogue, generating chained per-window `volume`/`enable` filter automation (including the single-window and passthrough/`anull` cases), configurable `DUCK_VOLUME` loading from default/`.env`/environment variable, and end-to-end `mix_plan.json` reporting of `duck_volume` and merged `duck_windows` for both the default mute and a custom duck volume.
- Duration report is covered by WAV duration probing (valid and invalid files), segment window loading, per-segment duration measurement with missing-file skipping, full report generation and worst-mismatch ranking, and the no-generated-WAV failure case, plus CLI success/error paths.
- The optional Khmer-only `tts_combine` artifact is covered by missing-TTS-file skipping, segment placement at `start` with no sync offset, FFmpeg command/filter-graph construction (silent lavfi base, per-segment delay, no atempo/ducking, `duration=first`), zero-track command generation, end-to-end plan/audio writing with included and skipped segments, and the no-generated-WAV failure case, plus CLI success/error/missing-argument paths.
- Configurable TTS speed is covered by default/`.env`/environment-variable loading of `TTS_SPEED` into `ToolConfig`, the doctor check's configured and default value reporting, the CLI's `TTS Speed:` display block, both providers' `describe()` reporting the configured speed, and the mocked Camb.ai SDK call asserting `voice_settings=StreamTtsVoiceSettings(speaking_rate=...)` is passed through to `text_to_speech.tts()`.
- Failing areas: there is no tested VS5 render pipeline, so final MP4 output remains unverified by tests.
- Missing tests: no end-to-end `dub` integration test with real module chaining, no final render tests, no media fixture tests, no provider-live tests, and no coverage for durable workflow state, caching, or quality gates.
