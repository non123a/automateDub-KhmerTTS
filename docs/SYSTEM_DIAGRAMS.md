# System Diagrams

## Platform Context

```text
Operators / Reviewers / API Clients
              |
              v
CLI / API / Review UI / Batch Interface
              |
              v
Workflow Orchestration + Policy Layer
              |
              v
Domain Knowledge Layer
              |
              v
Provider-Independent Intelligence Subsystems
              |
              v
AI Providers / Media Tools / Storage / Workers / Observability
```

## Knowledge-Driven Localization Flow

```text
Media Import
  -> Rights Gate
  -> Media Understanding
  -> Knowledge Extraction
  -> Character Intelligence
  -> Dialogue Understanding
  -> Localization Intelligence
  -> Voice Planning
  -> Voice Engine
  -> Mix And Render
  -> Quality Intelligence
  -> Human Review
  -> Learning System
  -> Export
```

## Core Data Relationships

```text
MediaProject
  -> MediaAsset
  -> MediaMemory
      -> Scene
      -> DialogueLine
      -> Character
      -> Relationship
      -> LocalizationPreference
      -> VoiceAssignment
      -> Correction
      -> QualityEvaluation
```

## Provider Routing

```text
Application Capability Request
        |
        v
Provider Registry
  -> capability match
  -> language support
  -> cost policy
  -> quality score
  -> licensing constraints
  -> availability/rate limits
        |
        v
Provider Adapter
        |
        v
Provider Invocation Record + Artifact Output
```

## Correction Propagation

```text
Human Correction
  -> New Decision Version
  -> Knowledge Fact Supersession
  -> Dependency Graph Lookup
  -> Mark Affected Artifacts Stale
  -> Selective Rerun
  -> New Quality Evaluation
```

## SaaS Evolution

```text
Organization
  -> Projects
  -> Users / Roles
  -> Media Assets
  -> Jobs
  -> Artifacts
  -> Provider Usage
  -> Cost Events
  -> Audit Logs
```

