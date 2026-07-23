# Engineering Principles

This document is the product philosophy for AutomateDub. Future ADRs should reference these principles explicitly.

## 1. Production Quality Beats Demo Speed

The system should first become reliable on a small, representative clip before expanding to full movies. Demos that bypass job state, quality gates, cost tracking, or artifact provenance are not production progress.

## 2. Evidence Before Provider Commitment

No AI provider is approved because its marketing page lists a feature. Providers must be benchmarked on representative Chinese movie audio and Khmer output before adoption.

## 3. Durable State Is The Product

The value is not a single generated file. The value is the ability to resume, inspect, correct, rerun selectively, compare outputs, and explain why a result exists.

## 4. Quality Is A Pipeline Stage

Quality checks are not afterthoughts. Transcription, diarization, translation, voice generation, timing, audio mix, and final render each need measurable quality gates.

## 5. Human Review Is Normal

Manual review and correction are expected product states. The architecture must make correction cheap, traceable, and safe to propagate.

## 6. Provider Independence Is Mandatory

Business logic must not depend on OpenAI, Claude, Gemini, Azure, ElevenLabs, CAMB.AI, Narakeet, FFmpeg command strings, or any provider SDK schema.

## 7. Cost Is A First-Class Signal

Every expensive operation should record estimated and actual cost, duration, provider, model, cache key, and output artifact.

## 8. Immutable Artifacts, Mutable Decisions

Generated artifacts are immutable. Decisions such as character assignment, voice assignment, approvals, and corrections are versioned and may supersede earlier decisions.

## 9. Research Must Not Contaminate Production

Experiments, notebooks, benchmark harnesses, and provider spikes must be isolated from production package dependencies and runtime paths.

## 10. Design For Years, Ship In Slices

The architecture should support years of evolution: local CLI, dashboard, distributed workers, provider changes, custom voices, and large archives. Delivery should still happen through narrow vertical slices.

