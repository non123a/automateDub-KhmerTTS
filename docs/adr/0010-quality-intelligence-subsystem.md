# ADR 0010: Create A Quality Intelligence Subsystem

Status: accepted

## Problem

Media localization quality cannot be validated by checking that files exist. Translation, character, timing, voice, audio, and render quality need measurable review.

## Alternatives

- Manual review only.
- Simple validation checks.
- Dedicated Quality Intelligence subsystem with automatic and human evaluations.

## Tradeoffs

- Quality scoring adds data modeling and workflow complexity.
- It reduces review burden over time and prevents expensive bad outputs from moving downstream.

## Final Decision

AutomateDub will use a Quality Intelligence subsystem with quality records, gates, metrics, model-assisted review, and human acceptance.

## Consequences

- Workflow progression depends on quality gates.
- Human review remains required until automatic scoring is proven.

## Future Reconsideration

As benchmark evidence grows, some gates may become fully automated for low-risk content.

