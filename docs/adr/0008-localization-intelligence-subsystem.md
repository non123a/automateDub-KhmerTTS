# ADR 0008: Create A Localization Intelligence Subsystem

Status: accepted

## Problem

Translation alone is insufficient for Khmer media localization. The platform must adapt idioms, humor, register, audience, genre, timing, and character voice.

## Alternatives

- Direct Chinese-to-Khmer translation.
- Translation plus rewrite stage.
- Dedicated Localization Intelligence subsystem.

## Tradeoffs

- More stages increase cost and evaluation burden.
- Dedicated localization improves quality, control, correction, and future reuse.

## Final Decision

AutomateDub will model localization as a subsystem with semantic translation, cultural adaptation, character rewrite, timing rewrite, and quality evaluation.

## Consequences

- Style guides, audience profiles, glossary, and correction memory become production assets.
- Prompt/model changes must be versioned and benchmarked.

## Future Reconsideration

Some stages may be combined for low-cost modes if benchmarks prove quality is acceptable.

