# Character Intelligence

## Purpose

Character Intelligence owns the difference between anonymous audio speakers and narrative characters. This subsystem is required for long-form dubbing, TV series, anime, and any product where viewers expect continuity.

## Core Concepts

- `Character`: narrative identity in the localized work.
- `SpeakerTurn`: a detected speech interval from source audio.
- `SpeakerCluster`: model-inferred grouping of speaker turns.
- `Actor`: real performer, optional and legally sensitive.
- `VoiceProfile`: target voice identity for generated localized audio.
- `VoiceAssignment`: versioned decision linking a character or cluster to a voice profile.
- `CharacterMemory`: accumulated facts, style, aliases, corrections, and preferences.

## Character Profile

Each character should support:

- character ID
- aliases and localized names
- relationships
- speaking style
- vocabulary preferences
- emotional baseline
- voice profile
- voice history
- pronunciation preferences
- translation preferences
- confidence score
- correction history
- first and last known appearance
- evidence links

## Evolution Through A Movie

Character knowledge should evolve as new evidence appears:

1. Diarization proposes speaker turns.
2. Speaker clustering proposes recurring voices.
3. Dialogue and scene context propose character identity.
4. Human review confirms, merges, splits, or renames identities.
5. Corrections update character memory.
6. Downstream localization and voice decisions use the latest approved memory.

## Correction Propagation

Supported corrections:

- merge two speaker clusters
- split one speaker cluster
- assign cluster to character
- rename character
- change alias/localized name
- change speaking style
- change voice assignment
- add pronunciation hint

Each correction creates a new decision version and invalidates affected downstream artifacts only.

## Risks

- Audio-only identity will fail with overlapping speakers and similar voices.
- Visual identity may be needed for complex films and anime.
- Character names may not be known until later scenes.

Recommendation:

- Store uncertain identity as uncertainty, not fake certainty.
- Add face/visual hints later through the same evidence model.

