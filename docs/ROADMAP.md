# Final Roadmap

Status: vertical-slice first, architecture unchanged.

The final architecture remains the destination. The implementation strategy now prioritizes product proof: build the smallest complete workflow before building the durable platform subsystems.

## Track VS: Smallest Working Pipeline

Goal: prove that one Chinese MP4 can become one playable Khmer MP4.

Deliverables:

- minimal CLI
- audio extraction
- transcription through one provider
- Khmer translation through one provider
- Khmer speech generation through one provider and one synthetic voice
- approximate dialogue replacement or ducking
- final MP4 render
- demo notes covering cost, latency, quality, timing, and provider issues

Exit criteria:

- one playable Khmer MP4 is generated from one Chinese MP4
- observed product risks are recorded
- team chooses the next production subsystem to replace

## Track P1: Durable Platform Core

Goal: replace ad hoc vertical-slice execution with durable platform state.

Deliverables:

- workflow/job/task/attempt model
- artifact lineage and cache model
- provider invocation ledger
- cost ledger
- quality record model
- rights and consent model
- local CLI inspection

Exit criteria:

- the same vertical-slice workflow can run with persisted state, provenance, and retry visibility

## Track P2: Provider Abstraction

Goal: remove direct provider coupling from the vertical slice.

Deliverables:

- transcription provider contract
- translation/localization provider contract
- TTS provider contract
- provider capability registry
- provider routing policy
- provider invocation records

Exit criteria:

- transcription, translation, and TTS can each be swapped without changing workflow logic

## Track P3: Media Pipeline Hardening

Goal: make media handling robust enough for varied real inputs.

Deliverables:

- FFprobe stream selection
- codec/container handling
- audio extraction hardening
- mix/render validation
- small legal media fixtures

Exit criteria:

- common MP4 variants are handled predictably with clear failures

## Track P4: Voice Engine

Goal: replace one-off TTS with the approved capability-based Voice Engine.

Deliverables:

- voice capability routing
- voice profiles and voice assets
- consent/license records
- pronunciation hints
- duration and emotion planning

Exit criteria:

- one voice provider can be replaced or expanded through capability routing

## Track P5: Localization Intelligence

Goal: replace literal translation with natural Khmer localization.

Deliverables:

- semantic translation
- cultural adaptation
- dialogue rewrite
- style guides
- timing-aware rewrite
- localization QA

Exit criteria:

- translated output is reviewable as natural Khmer localization, not just converted text

## Track P6: Knowledge And Character Intelligence

Goal: add durable media understanding and recurring character consistency.

Deliverables:

- media memory
- knowledge facts with evidence/confidence
- speaker turns and speaker clusters
- character profiles
- correction propagation

Exit criteria:

- recurring characters can be tracked, corrected, and reused across a clip/project

## Track P7: Quality Intelligence And Learning

Goal: reduce repeated human work while preserving review quality.

Deliverables:

- quality gates
- human review records
- correction memory
- provider performance learning
- scoped learning controls

Exit criteria:

- corrections improve future outputs and quality records guide review effort

## Track P8: Long-Form, Multi-Format, And SaaS Readiness

Goal: scale from one clip to broader products.

Deliverables:

- full movie and episodic workflows
- podcast/audiobook profiles
- short-form profiles
- reviewer tools
- tenant-aware SaaS foundations
- usage reporting

Exit criteria:

- multiple media types use the same core architecture without redesign
