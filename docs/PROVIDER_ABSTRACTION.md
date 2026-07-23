# Provider Abstraction

## Goal

The system must replace OpenAI, Claude, Gemini, Azure, local LLMs, local ASR, local diarization, TTS providers, and dubbing specialists without changing business logic.

## Architecture Rule

Provider SDKs belong only in infrastructure adapters. Domain and application services depend on normalized provider contracts and capability descriptions.

## Provider Registry

Maintain a provider registry with:

- provider name and adapter version
- model names and pinned versions where possible
- supported capabilities
- supported languages/locales
- input/output limits
- rate limits
- retryability rules
- cost model
- data retention policy
- safety/licensing constraints
- observed benchmark scores
- deprecation status

## Provider Invocation Record

Every provider call should record:

- provider, model, adapter version
- normalized capability
- request hash
- input artifact IDs
- output artifact IDs
- prompt/template version
- config snapshot
- latency
- token/character/audio duration units
- estimated and actual cost
- retry count
- raw provider response artifact where allowed
- normalized warnings/errors

## Contract Types

Minimum provider contracts:

- `TranscriptionProvider`
- `DiarizationProvider`
- `EmbeddingProvider`
- `TranslationProvider`
- `RewriteProvider`
- `TtsProvider`
- `VoiceConversionProvider`
- `SourceSeparationProvider`
- `QualityJudgeProvider`

Each contract should return normalized results plus provider evidence. Do not expose provider-native response types downstream.

## Fallback And Routing

Provider routing should be policy-driven:

- choose cheapest provider that meets quality threshold
- route high-risk scenes to stronger provider
- fallback on retryable failure
- block when provider terms conflict with source rights or consent
- estimate cost before starting a job

