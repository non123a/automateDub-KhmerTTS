# Project State

AutomateDub is a planned knowledge-driven AI localization platform for Khmer media. Its long-term purpose is to localize movies, series, anime, short-form video, podcasts, audiobooks, educational content, and corporate media with consistent characters, natural Khmer dialogue, high-quality voices, measurable quality, and traceable human review.

The current implementation strategy is vertical-slice first. The immediate product proof is the Smallest Working Pipeline: take one Chinese MP4 and produce one playable Khmer MP4 by extracting audio, transcribing speech, translating/localizing dialogue to Khmer, generating Khmer speech, replacing or covering the original dialogue, and rendering a final MP4.

Current milestone: VS5, Render Playable MP4, is the next implementation phase to build. The project has completed VS0 through VS4.

Completed milestones:

- VS0: Minimal project harness and audio extraction. The CLI accepts an input MP4 and output directory, validates local environment/tooling, and produces `output/audio.wav`.
- VS1: Transcription. Extracted audio is converted into timestamped Chinese transcript JSON using a local Whisper path through a `LocalTranscriber` boundary.
- VS2: Khmer Dialogue Localization. Transcript JSON is converted into `translation.json` with Khmer localized dialogue while preserving segment timestamps. It uses NBWCode through a `DialogueLocalizer` boundary, preferring `/responses` and falling back to `/chat/completions`.
- VS3: Khmer Speech Generation. Translated segments produce Khmer speech audio through a provider-independent `TTSProvider` boundary. Camb.ai is the first production provider implementation, configured through `.env` with `TTS_PROVIDER=cambai`, `CAMB_API_KEY`, `CAMB_LANGUAGE`, `CAMB_VOICE_ID`, and `TTS_MODEL`. NBWCode remains available as a legacy provider behind the same interface. VS3 writes one WAV per successful segment, continues after segment failures, preserves `tts/errors.json`, and writes `usage/tts_usage.json` without pricing estimates.
- VS4: Dialogue Replacement And Mix. `output/audio.wav`, `output/translation.json`, and `output/tts/*.wav` produce `output/mixed_audio.wav` and `output/mix_plan.json`. The implementation ducks the original source audio and overlays generated Khmer speech at approximate source segment start times.

Current working pipeline: `automatedub dub input.mp4 output/` now runs VS0 through VS4: extract audio, transcribe, localize, generate per-segment TTS WAVs through the configured TTS provider, then write a mixed audio track and mix plan. `automatedub tts output/` reruns only VS3, `automatedub tts sample output/` generates a short voice-quality preview in `output/sample/` with per-segment WAVs, `sample.wav`, and `sample.txt`, `automatedub tts providers` reports configured provider status, `automatedub camb voices` lists Camb.ai voices, `automatedub camb test [output/]` generates one `tts/test.wav` from the first translated segment, and `automatedub mix output/` reruns only VS4 from existing artifacts.

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

Test findings:

- Total test functions: 85.
- VS0 is covered by input validation, FFmpeg command construction, audio extraction success/failure, and path naming.
- VS1 is covered by WAV/model validation, whisper.cpp command construction, transcript normalization, transcript writing, CLI invocation, retry behavior, and failure reporting.
- VS2 is covered by transcript parsing, prompt construction, response normalization, batch splitting/merging, Responses-to-Chat Completions fallback, debug artifact writing, and endpoint detection.
- VS3 is covered by translation parsing, provider selection, NBWCode request construction, mocked Camb.ai SDK generation, mocked Camb.ai voice listing, WAV validation, one-segment Camb.ai test generation, per-segment file generation, sample segment selection, sample WAV generation, FFmpeg sample concatenation command construction, sample text writing, failure continuation, error log writing, and usage artifact writing.
- VS4 is covered by mix path naming, translation timing parsing, missing TTS skipping, FFmpeg mix command construction, mix-plan writing, mixed-audio output behavior, and no-TTS failure handling.
- Failing areas: there is no tested VS5 render pipeline, so final MP4 output remains unverified by tests.
- Missing tests: no end-to-end `dub` integration test with real module chaining, no final render tests, no media fixture tests, no provider-live tests, and no coverage for durable workflow state, caching, or quality gates.
