# ADR 0009: Use A Capability-Based Voice Engine

Status: accepted

## Problem

Khmer voice provider availability and quality are uncertain. Designing around one provider would create lock-in and product risk.

## Alternatives

- Pick one TTS provider early.
- Build separate integrations per provider.
- Build a provider-independent Voice Engine based on capabilities.

## Tradeoffs

- Capability modeling takes more upfront design.
- It allows providers to be replaced, combined, benchmarked, and routed by quality, cost, licensing, and feature support.

## Final Decision

AutomateDub will use a capability-based Voice Engine. Providers advertise capabilities such as TTS, expressive speech, cloning, conversion, speed control, pronunciation, duration constraints, streaming, and batch synthesis.

## Consequences

- Product logic must request capabilities, not provider names.
- Voice cloning requires consent and license records before use.

## Future Reconsideration

If one provider becomes dominant, it may be the default route but still must remain behind the Voice Engine contract.

