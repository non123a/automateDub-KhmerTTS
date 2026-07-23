# Knowledge Architecture

## Purpose

AutomateDub should maintain persistent media memory. The platform should understand media well enough to preserve character, context, emotion, relationships, pronunciation, and localization choices across a project.

## Why A Knowledge Layer

A sequential pipeline treats each stage as a file transformation. That is too weak for premium localization.

A knowledge layer enables:

- character continuity
- correction propagation
- context-aware translation
- series memory
- running jokes and callbacks
- pronunciation consistency
- relationship-aware dialogue
- quality evaluation against known facts
- reuse across episodes and related projects

## Knowledge Graph

The knowledge model should behave like a versioned graph:

```text
MediaProject
  -> Scene
  -> DialogueLine
  -> SpeakerTurn
  -> Character
  -> Relationship
  -> EmotionState
  -> LocalizationPreference
  -> PronunciationHint
  -> VoiceAssignment
```

Edges should carry:

- evidence
- confidence
- source artifact
- time range
- creator: model, human, import, provider
- version
- supersession state

## Movie Memory

`MediaMemory` is a central domain object.

It should remember:

- characters
- aliases
- previous dialogue
- relationships
- running jokes
- pronunciation
- voice assignments
- corrections
- emotion history
- scene history
- translation preferences
- localization constraints
- quality history

For series, memory should have scopes:

- global platform memory
- organization memory
- series memory
- project/movie memory
- scene memory
- line memory

Higher-scope memory may suggest defaults. Lower-scope memory may override them.

## Fact Lifecycle

Facts are never silently overwritten.

Lifecycle:

- proposed
- confirmed
- rejected
- superseded
- deprecated

Human-confirmed facts outrank inferred facts. A correction should invalidate dependent artifacts through explicit lineage rules.

## Search And Retrieval

Initial implementation can use relational queries. Later versions should add:

- full-text search for dialogue and corrections
- vector retrieval for semantically similar lines
- character memory retrieval during rewrite
- pronunciation memory retrieval during TTS planning

Do not require a vector database in the first implementation, but design memory records so indexing can be added.

