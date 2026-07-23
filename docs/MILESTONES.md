# Implementation Milestones

Status: vertical-slice first.

The final architecture remains approved and frozen. These milestones change implementation order only.

## VS0: Minimal Project Harness And Audio Extraction

Status: implemented.

Type: vertical slice foundation.

Success:

- basic Python project and CLI exist
- CLI accepts input/output paths
- environment/tool validation is testable
- one MP4 produces `output/audio.wav`

## VS1: Transcription

Status: implemented.

Type: AI step.

Success:

- extracted audio produces timestamped Chinese transcript JSON
- provider response parsing is tested with mocks

## VS2: Khmer Dialogue Localization

Status: implemented.

Type: AI step.

Success:

- transcript JSON produces `translation.json` with Khmer localized dialogue
- segment timestamps are preserved

## VS3: Khmer Speech Generation

Type: voice step.

Success:

- translated segments produce Khmer speech audio using one synthetic voice
- generated audio metadata records segment mapping and duration

## VS4: Dialogue Replacement And Mix

Type: audio assembly step.

Success:

- generated Khmer speech is approximately aligned to source speech positions
- original dialogue is replaced or covered enough for demo validation

## VS5: Render Playable MP4

Type: product proof.

Success:

- one command produces a playable Khmer MP4 from one Chinese MP4
- basic FFprobe validation passes

## VS6: Demonstration And Next-Milestone Decision

Type: product/technical decision gate.

Success:

- demo output is reviewed
- cost, latency, provider, timing, and quality issues are recorded
- next replacement milestone is approved before work continues

## Post-Vertical-Slice Milestones

After VS6, milestones return toward the frozen architecture:

- P1: Durable Platform Core
- P2: Provider Abstraction
- P3: Media Pipeline Hardening
- P4: Voice Engine
- P5: Localization Intelligence
- P6: Knowledge And Character Intelligence
- P7: Quality Intelligence And Learning
- P8: Long-Form, Multi-Format, And SaaS Readiness
