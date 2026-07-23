# Architecture Benchmark Plan

## Purpose

Benchmarks are Track 0 / M0 deliverables. They decide whether the proposed system is feasible and which providers are acceptable.

## Dataset

Create a small legally usable benchmark set:

- 3-5 Chinese movie-like clips, 30-90 seconds each
- Mandarin and Cantonese if both are in scope
- clean dialogue, music-under-dialogue, action/noise, overlapping speakers
- at least two recurring characters
- human reference transcript and Khmer translation
- source rights documented

## Provider Benchmarks

Required evaluations:

- Khmer TTS and voice/dubbing providers
- Chinese transcription providers
- diarization providers
- translation/rewrite LLMs
- source separation models
- FFmpeg render/mix strategies

## Scorecards

Each benchmark report should include:

- provider/model/version
- capability tested
- input fixture
- output artifacts
- automatic metrics
- human ratings where relevant
- latency
- failure rate
- cost
- licensing/retention notes
- recommendation: approve, reject, watch, or use only as fallback

## Exit Criteria

M0 is complete only when:

- at least two Khmer voice paths are evaluated
- at least two ASR paths are evaluated
- at least two translation/rewrite LLM paths are evaluated
- diarization is tested on noisy and overlapping speech
- one end-to-end benchmark clip has a cost and quality report
- unresolved provider gaps are documented as accepted risks or blockers
