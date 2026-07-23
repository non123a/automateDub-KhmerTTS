# MVP And Version Scope

## Recommendation

The MVP should be a full vertical slice on one 5-10 minute clip, not a full movie automation system.

Reason: the hardest unknowns are not ordinary engineering tasks. Khmer voice quality, speech timing, source audio separation, and speaker consistency must be proven together. A clip-level vertical slice exposes those risks faster than building a large partial pipeline.

## MVP

Goal: produce one watchable Khmer-dubbed clip with persisted state and retryable steps.

Included:

- import one source movie
- probe media metadata
- detect scenes
- generate one or more clips
- extract clip audio
- diarize speakers
- transcribe Chinese speech
- translate to Khmer
- rewrite Khmer dialogue for natural spoken delivery
- assign stable synthetic voices per detected speaker
- generate Khmer voice lines
- fit generated lines to source timing within agreed tolerance
- mix generated speech with original or processed background audio
- render a final dubbed clip
- store all step status, artifacts, errors, and provider metadata
- resume or retry failed steps from the CLI

Excluded:

- full-movie automation
- perfect voice cloning
- exact original actor voice matching
- perfect removal of Chinese dialogue
- web dashboard
- upload automation
- distributed workers
- face recognition
- custom model training
- fully automated quality approval

## Version 1

Goal: process a whole movie with bounded manual review.

Expected additions:

- cross-clip speaker reconciliation
- full movie batch runner
- operator correction files or CLI commands
- final concatenation/render plan
- cost and processing-time reports
- quality review checkpoints
- better retry controls

## Version 2

Goal: improve quality and reduce manual work.

Expected additions:

- better source separation
- provider ensemble or fallback routing
- improved prompt evaluation
- Khmer style guide presets
- voice profile library
- duration-aware rewrite iterations
- artifact comparison tools
- optional human review workflow

## Version 3

Goal: production-scale automation.

Expected additions:

- PostgreSQL deployment
- worker queue
- GPU/server execution
- web dashboard
- multi-job management
- role-based access if more users are added
- object storage support
- automated upload pipeline

## Research Track

These features should not block the MVP, but the architecture must leave room for them:

- licensed voice cloning
- emotional TTS
- age and gender estimation
- speaking style detection
- pitch and speed adaptation
- face-assisted character tracking
- custom Khmer TTS model training
- cultural adaptation and idiom conversion

## Product Challenge

"Almost fully automated" should not mean "no review" in early versions. For this domain, automation should first mean:

- no repeated manual file handling
- no restarting from zero
- no manual copying between tools
- clear review checkpoints
- traceable outputs

Removing human review too early would hide quality problems rather than solve them.
