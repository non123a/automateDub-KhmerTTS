# Khmer Voice Architecture

## Verdict

Khmer voice generation is the highest-risk subsystem and must be validated in Track 0 / M0. The project must be designed around provider uncertainty, not around the assumption that a production-quality Khmer TTS or voice cloning provider exists.

## Current Provider Reality

As of 2026-07-23, public provider evidence is mixed:

- Azure Speech lists two Khmer standard neural voices, `km-KH-SreymomNeural` and `km-KH-PisethNeural`, but the support table does not show style/role support or voice conversion for those Khmer voices. Source: https://learn.microsoft.com/en-au/azure/ai-services/speech-service/language-support
- Amazon Polly's official supported-language page does not list Khmer. Source: https://docs.aws.amazon.com/polly/latest/dg/supported-languages.html
- ElevenLabs' official TTS model language lists do not list Khmer. Its speech-to-text page lists Khmer, but only as ASR, not TTS, and with moderate WER. Sources: https://help.elevenlabs.io/hc/en-us/articles/13313366263441-What-languages-do-you-support and https://elevenlabs.io/speech-to-text/khmer
- CAMB.AI lists Khmer for dubbing/translation, but its TTS list in the same support article does not list Khmer. This needs direct API verification. Source: https://help.camb.ai/en/articles/8765503-what-languages-are-supported-for-which-tool
- Narakeet claims Khmer TTS voices. This may be useful for baseline evaluation, but API terms, voice quality, licensing, emotional control, and timing control must be tested. Source: https://www.narakeet.com/languages/khmer-text-to-speech/

Conclusion: Khmer TTS providers may exist, but production-quality dramatic dubbing is unproven.

## Required Voice Domain Model

Do not use a single overloaded `VoiceProfile` object. Use separate concepts:

- `VoiceAsset`: a generated, recorded, or cloned voice artifact.
- `VoiceProviderCapability`: provider/model support for language, emotion, speed, SSML, cloning, voice conversion, streaming, sample rates, formats, and licensing.
- `VoiceProfile`: target voice identity used by the project, independent of one provider.
- `VoiceAssignment`: versioned mapping between a movie character or speaker cluster and a voice profile.
- `ConsentRecord`: proof and scope of consent for recorded/cloned voices.
- `VoiceLicense`: commercial usage, redistribution, retention, geographic, and revocation terms.
- `VoiceGenerationRequest`: normalized request with text, language, timing, pronunciation hints, style/emotion, and provider constraints.
- `VoiceGenerationResult`: normalized result with audio artifact, duration, provider metadata, cost, warnings, and quality scores.

## Synthesis Capabilities

Voice generation should be decomposed into separate provider capabilities:

- plain TTS
- expressive TTS
- SSML/pronunciation control
- emotional speech control
- duration-constrained speech
- voice cloning
- voice conversion
- batch generation
- streaming generation

Providers may support only a subset. The workflow must select providers by declared capability, not by provider name.

## Emotional Speech

Emotional speech should be a separate module. It should translate source emotion into normalized delivery instructions:

- emotion label
- intensity
- pace
- energy
- pitch direction
- whisper/shout/cry/laugh markers where allowed
- provider-specific rendering strategy

If a TTS provider cannot honor emotion instructions, the system should record that limitation and route the line to review or a different provider.

## Voice Cloning

Voice cloning must not be part of the MVP default. Add it later only when:

- the source speaker has explicit consent or the voice is licensed for cloning
- consent artifacts are stored and revocable
- provider terms allow the intended dubbing and distribution
- retention and deletion behavior is implemented
- cloned voice quality beats licensed synthetic alternatives in benchmarks

Voice cloning should integrate through `VoiceAsset` and `ConsentRecord`, not through special cases in TTS generation.

## Benchmark Requirements

Each provider must be benchmarked with:

- male, female, older, younger, calm, angry, sad, and fast dialogue samples
- short lines, long lines, names, exclamations, whispers, and overlapping-scene context
- Khmer native speaker ratings for naturalness, pronunciation, emotion, and acceptability
- duration fit against source timing
- batch latency and failure rate
- cost per finished minute
- terms/licensing review

Provider adoption requires a scorecard, not a subjective demo.
