# Quality Pipeline

## Purpose

Quality control must be a dedicated architecture layer. A generated artifact is not successful merely because a provider returned output or FFmpeg produced a file.

## Quality Gates

Required gates:

- media import: source readable, selected streams valid, rights metadata present
- scene/clip planning: clips respect min/max duration and avoid obvious dialogue breaks
- diarization: speaker overlap, unknown speaker rate, cluster confidence
- transcription: language match, timestamp coverage, uncertainty markers, missing-dialogue detection
- translation: meaning preservation, named entities, taboo/profanity policy, cultural adaptation policy
- rewrite: spoken Khmer naturalness, duration target, character tone consistency
- voice generation: pronunciation, emotion, voice consistency, artifact quality, duration fit
- mix: Chinese dialogue bleed, background preservation, loudness, clipping, sync
- render: codecs, duration, A/V sync, playable output, expected tracks/subtitles
- human acceptance: explicit approve/reject/request-change record

## Quality Records

Every quality evaluation should produce:

- input artifact IDs
- output artifact ID or decision ID
- metric names and values
- evaluator type: automated, model judge, human, hybrid
- threshold version
- status: passed, warning, failed, needs_review
- notes and correction links

## Human Review

Human review should be versioned and structured:

- reviewer identity or local operator label
- reviewed artifact
- decision
- changed text, speaker mapping, voice assignment, or timing
- reason codes
- downstream invalidation rules

Corrections must not mutate previous artifacts. They create new decision versions and invalidate dependent downstream artifacts.

## Automated Scoring

Automated scoring should be useful but not authoritative for early versions. Candidate metrics:

- speech coverage ratio
- average and max timing delta
- percentage of lines exceeding speed-adjustment limit
- transcription uncertainty rate
- diarization unknown/overlap rate
- translation/rewrite model-judge score
- TTS duration deviation
- audio loudness and clipping
- render duration mismatch

Human acceptance remains required until benchmarks prove automated gates are reliable.

