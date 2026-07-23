# Cache Strategy

## Purpose

Expensive media and AI stages must be cacheable, reproducible, and invalidatable. Cache design is part of cost control and reliability.

## Cache Key

Use a stable cache key derived from:

- input artifact content hashes
- normalized task name
- task version
- provider and model version
- prompt/template version
- relevant config snapshot
- language/style settings
- rights and consent constraints when they affect output legality

## Cacheable Stages

Cache by default:

- FFprobe metadata
- scene detection
- speech activity detection
- audio extraction
- source separation
- diarization
- speaker embeddings
- transcription
- translation
- dialogue rewrite
- TTS generation
- timing analysis
- mix plans
- rendered outputs

Rendering and mixing are cacheable only when all input artifacts and command/config versions match exactly.

## Invalidation

Invalidate downstream artifacts when:

- source media changes
- stream selection changes
- clip timestamps change
- speaker/character mapping changes
- transcript correction changes source text
- translation or rewrite changes
- voice assignment changes
- provider/model/prompt version changes
- consent or license scope changes
- quality thresholds change and require reevaluation

Invalidation should mark artifacts stale; it should not delete them automatically.

## Storage Policy

Cache records should track:

- hit/miss
- avoided estimated cost
- artifact size
- last used time
- retention class
- legal hold
- recompute cost

Garbage collection should prefer deleting artifacts that are cheap to recompute, not legally required, not approved output, and not recently used.

