# Localization Intelligence

## Purpose

Localization Intelligence turns understood source dialogue into audience-ready Khmer. It is broader than translation.

## Responsibilities

- semantic translation
- cultural adaptation
- idiom conversion
- natural Khmer dialogue
- regional Khmer variation
- audience adaptation
- genre adaptation
- comedy adaptation
- drama adaptation
- speech pacing
- duration optimization
- emotion preservation
- glossary and terminology consistency
- character-specific language

## Pipeline

```text
Source Dialogue
  -> Meaning Extraction
  -> Context Retrieval
  -> Semantic Translation
  -> Cultural Adaptation
  -> Character Voice Rewrite
  -> Timing Rewrite
  -> Quality Evaluation
  -> Human Review When Needed
```

## Inputs

Localization should receive:

- source dialogue line
- surrounding dialogue
- scene summary
- character memory
- relationship context
- emotion state
- target audience profile
- regional Khmer preference
- glossary
- pronunciation constraints
- timing constraints
- prior corrections

## Outputs

Localization should produce:

- semantic translation
- localized Khmer line
- alternative candidates
- rationale summary
- timing estimate
- style and register metadata
- uncertainty flags
- quality scores
- prompt/model/provider provenance

## Audience Profiles

The architecture should support profiles such as:

- general Cambodian audience
- children/family-safe
- formal education
- corporate training
- anime fan style
- comedy-forward
- dramatic/literary
- short-form social media

Profiles should be versioned production assets.

## Recommendation

Localization deserves its own subsystem. It should not be a single LLM call embedded in a pipeline stage.

