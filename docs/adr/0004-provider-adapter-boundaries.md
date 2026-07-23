# ADR 0004: Use Capability-Based Provider Abstraction

Status: accepted

## Problem

AutomateDub depends on fast-changing AI capabilities across transcription, diarization, translation, rewrite, TTS, voice conversion, source separation, and quality judging. Vendor APIs, model quality, prices, language support, and policies will change.

## Alternatives

- Call provider SDKs directly from workflow code.
- Create one adapter per provider without capability modeling.
- Use capability-based provider contracts and a provider registry.

## Tradeoffs

- Direct SDK usage is faster initially but creates lock-in and weak tests.
- Simple adapters help replacement but still encourage provider-name routing.
- Capability-based routing adds upfront modeling but supports long-term provider independence.

## Final Decision

Use provider-independent contracts and a provider capability registry. Product logic requests capabilities; infrastructure adapters translate to provider SDKs.

## Consequences

- Provider-native schemas cannot leak into domain or application logic.
- Every provider invocation must record model, adapter version, cost, latency, request hash, output artifacts, and policy constraints.

## Future Reconsideration

If internal models become dominant, they should be registered as providers with capabilities rather than special-cased.

