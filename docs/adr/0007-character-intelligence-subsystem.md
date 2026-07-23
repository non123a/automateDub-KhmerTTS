# ADR 0007: Create A Character Intelligence Subsystem

Status: accepted

## Problem

Diarization speakers, movie characters, actors, and generated voices are different concepts. Conflating them creates downstream errors and makes corrections expensive.

## Alternatives

- Treat diarization labels as characters.
- Use a simple speaker table.
- Model Character, SpeakerTurn, SpeakerCluster, Actor, VoiceProfile, VoiceAsset, and VoiceAssignment separately.

## Tradeoffs

- Separate identity concepts add schema and workflow complexity.
- They allow correction, provenance, voice consistency, and series continuity.

## Final Decision

AutomateDub will have a dedicated Character Intelligence subsystem with separate identity concepts and versioned correction propagation.

## Consequences

- Character corrections must invalidate affected downstream localization and voice artifacts.
- Human-reviewed character facts outrank model-inferred facts.

## Future Reconsideration

Visual identity may be added later as another evidence source without changing the core identity model.

