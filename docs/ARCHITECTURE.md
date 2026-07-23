# AutomateDub Platform Architecture

Status: approved for implementation planning after final self-review.

## 1. Vision

AutomateDub is a knowledge-driven AI localization platform for Khmer media. It should not be designed as a one-off video dubbing script. It should become a durable platform that can localize movies, TV series, anime, YouTube videos, TikTok clips, podcasts, audiobooks, educational content, and corporate training material without rewriting the core.

The platform's core competency is not "run ASR, translate, TTS, render." Its core competency is maintaining a structured understanding of media, characters, dialogue, context, localization decisions, voices, quality evidence, and human corrections over time.

## 2. Product Thesis

The winning product will be the system that preserves meaning, character, emotion, timing, and audience fit at scale. Literal translation and generic TTS are insufficient. The architecture must therefore optimize for:

- consistent character identity
- natural Khmer localization
- provider-independent voice generation
- durable movie memory
- measurable quality
- learning from corrections
- reproducible, cacheable, auditable workflows
- eventual SaaS operation

## 3. Architectural Style

AutomateDub should be built as a modular platform around a knowledge layer and workflow engine.

```text
                  Interfaces
        CLI | API | Review UI | Batch Jobs
                     |
                Application
     Workflow | Review | Provider Routing | Policy
                     |
              Domain Knowledge Layer
 Media Memory | Characters | Dialogue | Localization | Voices
                     |
              Intelligence Subsystems
 Extraction | Character | Localization | Voice | Quality | Learning
                     |
              Infrastructure
 Providers | Media Tools | Storage | Database | Workers | Observability
```

This is superior to a simple sequential pipeline because corrections, character understanding, running context, provider evaluation, and quality evidence must influence future decisions. A linear pipeline forgets too much.

## 4. Core Platform Subsystems

### 4.1 Workflow Orchestration

Responsible for:

- jobs, workflow definitions, task runs, attempts, retries, leases, cancellation, progress, and review gates
- dependency tracking between artifacts and decisions
- selective reruns after corrections
- local execution now and distributed workers later

The workflow engine must operate on versioned artifacts and domain decisions, not temporary files.

### 4.2 Knowledge Layer

Responsible for:

- persistent media memory
- characters, aliases, relationships, scene context, dialogue, emotion, locations, continuity, pronunciation, and correction history
- provenance for every inferred fact
- confidence scores and supersession of incorrect facts

The knowledge layer is the durable center of the product.

### 4.3 Character Intelligence

Responsible for:

- turning diarized speaker turns into stable character identities
- maintaining character memory across scenes, episodes, seasons, and future titles
- tracking speaking style, vocabulary, emotional baseline, voice assignment, pronunciation, translation preferences, and corrections
- propagating identity corrections to downstream artifacts

### 4.4 Localization Intelligence

Responsible for:

- semantic translation
- cultural adaptation
- idiom conversion
- natural Khmer dialogue
- regional Khmer style
- audience adaptation
- genre-aware tone for comedy, drama, anime, education, corporate, and short-form media
- timing-aware rewrite and speech pacing

Localization is a subsystem, not a prompt.

### 4.5 Voice Engine

Responsible for provider-independent voice capabilities:

- speech synthesis
- expressive speech
- voice cloning
- voice conversion
- emotion control
- speaking speed control
- pronunciation dictionaries
- duration constraints
- streaming and batch synthesis
- future model routing

Providers advertise capabilities. Product logic asks for capabilities.

### 4.6 Quality Intelligence

Responsible for:

- translation quality
- localization quality
- character consistency
- voice consistency
- pronunciation quality
- emotion preservation
- timing accuracy
- audio quality
- render validation
- human review prioritization

Quality Intelligence should reduce human review over time, but not remove human review before evidence proves it can.

### 4.7 Learning System

Responsible for:

- converting approved corrections into reusable memory
- tracking provider performance
- improving translation preferences, pronunciation dictionaries, character profiles, voice assignments, and rewrite behavior
- separating project-specific learning from global reusable learning

Learning must be explicit, permissioned, reviewable, and reversible.

### 4.8 Benchmark Framework

Responsible for:

- provider evaluations
- regression scorecards
- cost/latency/failure metrics
- licensing checks
- promotion or demotion of providers

No provider becomes a default because it works once.

## 5. Domain Model

### Media

- `MediaAsset`: source or derived media item; can be video, audio, subtitle, script, audiobook chapter, podcast episode, or short-form clip.
- `MediaProject`: localization project around one or more media assets.
- `Series`: optional grouping for TV/anime/episodic content.
- `Episode`: one unit inside a series.
- `Scene`: narrative or structural section.
- `Shot`: optional visual subdivision for future visual intelligence.
- `TimelineInterval`: source-time range with media stream references.
- `Track`: audio, video, subtitle, transcript, generated voice, or mix track.

### Knowledge

- `MediaMemory`: persistent knowledge base for a media project or series.
- `KnowledgeFact`: versioned claim about a character, scene, relationship, emotion, pronunciation, or continuity.
- `Evidence`: provider output, human review, source artifact, or benchmark result supporting a fact.
- `Correction`: human or system correction that supersedes prior facts or artifacts.
- `Confidence`: score and reason attached to inferred facts.

### Character

- `Character`: narrative identity.
- `CharacterAlias`: names, nicknames, translated names, romanizations, Khmer renderings.
- `SpeakerTurn`: diarized source speech interval.
- `SpeakerCluster`: model-derived group of speaker turns.
- `Actor`: real-world performer, only when known and legally useful.
- `Relationship`: character-to-character relationship with evidence and time range.
- `CharacterStyle`: vocabulary, register, formality, humor, emotional baseline, catchphrases.
- `CharacterMemory`: evolving profile across the project or series.

### Dialogue

- `DialogueLine`: source-language utterance linked to time, speaker turn, scene, and character when known.
- `TranscriptVariant`: provider or human transcript output.
- `TranslationVariant`: semantic translation candidate.
- `LocalizationVariant`: audience-ready Khmer line.
- `PronunciationHint`: name, phrase, or phonetic guidance.
- `TimingConstraint`: target start, end, duration, pauses, allowed stretch/compression.

### Voice

- `VoiceProfile`: platform-level target voice identity.
- `VoiceAsset`: recorded, synthetic, cloned, or converted voice material.
- `VoiceAssignment`: versioned link from character/cluster to voice profile.
- `VoiceGenerationRequest`: provider-independent request.
- `VoiceGenerationResult`: generated audio and provider evidence.
- `ConsentRecord`: permission for recorded/cloned/converted voices.
- `VoiceLicense`: allowed usage and restrictions.

### Quality

- `QualityEvaluation`: assessment of an artifact or decision.
- `QualityMetric`: named measurement and threshold.
- `ReviewTask`: human review request.
- `ReviewDecision`: approve, reject, request change, or override.
- `AcceptanceGate`: policy that controls workflow progression.

### Operations

- `WorkflowDefinition`
- `JobRun`
- `TaskRun`
- `TaskAttempt`
- `ArtifactVersion`
- `ProviderCapability`
- `ProviderInvocation`
- `CostEvent`
- `CacheRecord`

## 6. Knowledge Model

The knowledge layer stores time-aware, evidence-backed facts.

```text
MediaProject
  -> MediaMemory
      -> Characters
      -> Character relationships
      -> Scene summaries
      -> Dialogue history
      -> Emotion timeline
      -> Pronunciation memory
      -> Localization preferences
      -> Voice assignments
      -> Corrections
      -> Quality evidence
```

Rules:

- Facts are versioned.
- Facts have evidence.
- Facts can be superseded.
- Confidence is explicit.
- Human-approved facts outrank model-inferred facts.
- Series-level memory may inform episode-level localization.
- Project memory may be exported, imported, or archived.

This enables the system to understand continuity: a joke from episode 2, a nickname from scene 4, a relationship reveal, or a pronunciation correction should affect future lines.

## 7. Revised Workflow

The workflow is a graph, not a straight line.

```text
Import/Rights Gate
  -> Media Understanding
  -> Knowledge Extraction
  -> Character Intelligence
  -> Dialogue Understanding
  -> Localization Intelligence
  -> Voice Planning
  -> Voice Engine
  -> Mix/Render
  -> Quality Intelligence
  -> Human Review
  -> Learning
  -> Export
```

Corrections can branch backward:

```text
Human corrects character mapping
  -> supersede CharacterFact
  -> invalidate affected localization and voice assignment decisions
  -> reuse unaffected cached artifacts
  -> rerun dependent tasks only
```

## 8. Repository Structure

Target structure once implementation begins:

```text
automatedub/
  domain/
    media/
    knowledge/
    character/
    localization/
    voice/
    quality/
    workflow/
    cost/
    rights/
  application/
    workflows/
    services/
    policies/
    ports/
  infrastructure/
    providers/
    media/
    persistence/
    storage/
    workers/
    observability/
  interfaces/
    cli/
    api/
    review/
  config/
  operations/
research/
  experiments/
  provider_spikes/
  notebooks/
benchmarks/
  datasets/
  scorecards/
  reports/
tests/
  unit/
  integration/
  contract/
  golden/
  migration/
docs/
  adr/
  operations/
```

Production code must not import from `research/`. Benchmark tooling may import production contracts but must not become a runtime dependency.

## 9. Storage Architecture

Use three coordinated stores:

- Relational database for workflow state, identities, facts, costs, rights, quality, and provider invocations.
- Blob/artifact storage for large immutable media, provider responses, generated audio, renders, benchmark outputs, and prompt artifacts.
- Search/vector index later for semantic retrieval across dialogue, characters, scenes, and corrections.

Start local with filesystem blob storage and a PostgreSQL-compatible relational schema. SaaS should move blob storage to object storage and database to managed PostgreSQL.

## 10. SaaS Evolution

The architecture must support:

- organizations and projects
- users, roles, and review permissions
- tenant-isolated storage
- usage metering and billing
- provider key ownership: platform keys, customer keys, or hybrid
- background workers
- job queues
- audit logs
- web review interface
- export formats for video, audio, subtitle, transcript, and localization packages

These do not need to be implemented first, but the core domain model must not block them.

## 11. Success Metrics

Platform-level success:

- accepted localized minutes per week
- human review minutes per finished media minute
- correction rate by subsystem
- provider cost per finished minute
- cache savings
- average rerun scope after correction
- voice consistency score
- translation/localization acceptance score
- timing-fit pass rate
- render validation pass rate

MVP success:

- one legally usable 5-10 minute clip localized into natural Khmer
- recurring characters maintain consistent identity and voice
- every output has provenance, quality evidence, and cost records
- corrections rerun only affected downstream tasks

## 12. Implementation Readiness

Implementation may begin when:

- product philosophy is accepted
- ADRs 0006-0012 are accepted
- benchmark plan has representative clips and scoring rubric
- Khmer voice risk has at least one viable path or an explicit fallback
- domain model is approved
- workflow and artifact lineage model is approved
- quality gates and human review policy are approved
- cost/cache/provider registry designs are approved

