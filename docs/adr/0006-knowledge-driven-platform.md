# ADR 0006: Use A Knowledge-Driven Localization Platform

Status: accepted

## Problem

A simple sequential dubbing pipeline does not preserve enough context for premium localization. Character identity, relationships, emotion, pronunciation, running jokes, and corrections must influence downstream decisions and future work.

## Alternatives

- Linear media pipeline.
- Workflow pipeline with metadata only.
- Knowledge-driven platform with persistent media memory.

## Tradeoffs

- A knowledge layer adds modeling and persistence complexity.
- It reduces long-term rework by making context, corrections, and continuity first-class.

## Final Decision

AutomateDub will use a central knowledge layer and persistent media memory as a core domain concept.

## Consequences

- Implementation must model facts, evidence, confidence, correction, and supersession.
- Localization and voice generation will consume memory, not just immediate transcript text.

## Future Reconsideration

If early vertical slices show the knowledge model is too heavy, scope implementation to project-level memory first while preserving the architecture boundary.

