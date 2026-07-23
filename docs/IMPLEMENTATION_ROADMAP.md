# Implementation Roadmap

Status: vertical-slice strategy.

The final architecture remains frozen and is still the long-term destination. Implementation order changes: prove the complete product workflow first, then replace shortcuts with production subsystems incrementally.

## Strategy

The first implementation target is the Smallest Working Pipeline:

```text
Chinese MP4
  -> extract audio
  -> transcribe speech
  -> translate to Khmer
  -> generate one Khmer voice
  -> replace or cover original dialogue
  -> render playable Khmer MP4
```

This first version intentionally does not implement the durable platform core. It may use temporary shortcuts:

- one synthetic Khmer voice
- no speaker diarization
- no character memory
- no workflow engine
- no database
- no caching
- no quality intelligence
- no provider abstraction
- minimal configuration
- basic CLI

These shortcuts are permitted only to validate the end-to-end product. They must be isolated so they can be replaced by the approved architecture later.

## Phase VS0: Minimal Project Harness And Audio Extraction

Status: implemented.

Goal: create only enough project structure to run and test the vertical slice, with one tangible media-processing result.

Scope:

- Python project setup with `uv`
- minimal package layout
- basic CLI entrypoint
- local output directory convention
- smoke tests for CLI argument parsing and environment validation
- documented required external tools and credentials
- input MP4 validation
- FFmpeg availability validation
- WAV extraction to `output/audio.wav`

Exit:

- `automatedub` CLI accepts an input MP4 path and output directory.
- one MP4 produces `output/audio.wav`.

## Phase VS1: Transcription

Status: implemented.

Goal: convert extracted Chinese speech into timestamped text.

Scope:

- integrate one transcription path
- use local whisper.cpp through a generic `LocalTranscriber` boundary
- require no API key and no network after setup
- produce a simple JSON transcript with segments, text, start, and end
- no diarization
- no cloud provider abstraction

Exit:

- one extracted audio file produces `output/transcript.json`.
- tests cover transcript normalization using mocked provider output.

## Phase VS2: Khmer Translation

Status: implemented.

Goal: produce Khmer text for each transcript segment.

Scope:

- integrate one LLM dialogue-localization path
- use NBWCode as an OpenAI-compatible provider through a generic `DialogueLocalizer` boundary
- prefer `/responses` and automatically fall back to `/chat/completions`
- localize segment-by-segment or in small batches
- preserve segment timestamps
- write `output/translation.json`
- write `output/translation_prompt.json`
- preserve `output/transcript.json` unchanged
- no style guide, character memory, or localization intelligence yet

Exit:

- one Chinese transcript produces Khmer localized dialogue.
- tests cover translation response parsing and fallback errors with mocked provider output.

## Phase VS3: Khmer Speech Generation

Status: implemented.

Goal: synthesize Khmer speech for translated segments using one voice.

Scope:

- integrate one Khmer-capable TTS path
- use one synthetic voice
- generate one audio file per segment
- write failed segment records to a simple error log
- no voice profiles, cloning, emotional control, or provider registry

Exit:

- translated segments produce Khmer speech audio.
- tests cover TTS request construction, per-segment files, and failure bookkeeping with mocked provider output.

## Phase VS4: Dialogue Replacement And Mix

Goal: create an audio track where generated Khmer speech replaces or covers the original dialogue enough for a product demo.

Scope:

- simplest viable strategy: duck original audio under generated speech or replace the entire audio track
- align generated speech approximately to source segment timestamps
- tolerate timing imperfections
- write a mixed audio file

Exit:

- generated Khmer speech is audible in the approximate original dialogue positions.
- tests cover timing/mix plan generation.

## Phase VS5: Render Playable MP4

Goal: produce one playable Khmer MP4.

Scope:

- combine original video stream with mixed/generated Khmer audio
- preserve basic video properties where practical
- write final MP4
- run a basic FFprobe validation

Exit:

- one command takes an MP4 input and produces a playable Khmer MP4 output.
- tests cover render command construction and output validation behavior.

## Phase VS6: Demonstration And Decision Gate

Goal: decide what production subsystem to replace first.

Scope:

- run the full vertical slice on one short Chinese MP4
- record observed failures
- record cost, latency, provider quality, and manual notes informally
- decide whether the next milestone is Durable Platform Core, Voice Engine, Localization Intelligence, or Media Pipeline hardening

Exit:

- one playable MP4 exists.
- the team approves the next milestone.

## After The Vertical Slice

Once the smallest working pipeline is demonstrated, replace shortcuts in this order unless evidence suggests otherwise:

1. Durable platform core: workflow state, artifacts, cost, cache, quality records.
2. Provider abstraction: transcription, translation, TTS, and later media/source-separation capabilities.
3. Media pipeline hardening: probing, stream selection, extraction, render validation.
4. Voice Engine: capability routing, voice profiles, consent/license records.
5. Localization Intelligence: style guides, timing-aware rewrite, Khmer quality review.
6. Knowledge and Character Intelligence: media memory, speaker/character identity, correction propagation.
7. Quality Intelligence and Learning System.
8. Long-form, multi-format, and SaaS evolution.
