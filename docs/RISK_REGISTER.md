# Risk Register

Status: updated for the final platform architecture.

## R0: Overbuilding The Platform Too Early

Severity: high

Likelihood: medium

Problem: Designing for a world-class localization platform can lead to building abstractions before the first useful localized clip exists.

Mitigation:

- build narrow vertical slices
- enforce architecture contracts without implementing every future capability
- keep SaaS fields dormant until needed
- use benchmark evidence to prioritize

## R1: Khmer Voice Quality

Severity: critical

Likelihood: high

Problem: High-quality Khmer TTS, emotional speech, and voice cloning may not be available from mainstream providers at the desired quality.

Mitigation:

- run provider evaluation before committing to a TTS stack
- keep TTS behind an adapter
- support manually curated voice profiles
- consider custom model training only after proving data and licensing feasibility

## R2: Voice Cloning Consent And Legal Constraints

Severity: critical

Likelihood: medium

Problem: Cloning or imitating voices can create legal, ethical, and provider-policy issues.

Mitigation:

- store consent metadata
- start with licensed synthetic voices
- do not design around unauthorized imitation of real actors

## R3: Dialogue And Background Separation

Severity: high

Likelihood: high

Problem: Movie audio usually has dialogue, music, and effects mixed together. Removing only Chinese dialogue while preserving the rest may be imperfect.

Mitigation:

- set MVP expectation as ducking or approximate separation
- evaluate source separation models
- preserve original audio as a reference artifact
- allow manual review for bad mixes

## R4: Speaker Consistency Across Clips

Severity: high

Likelihood: high

Problem: Diarization labels are local to clips and may not map to the same character across a whole movie.

Mitigation:

- store embeddings
- perform cross-clip speaker clustering
- allow operator correction
- add visual face cues in future versions

## R5: Natural Khmer Dialogue Quality

Severity: high

Likelihood: medium

Problem: Literal translation will sound robotic and may not fit timing.

Mitigation:

- separate translation from dialogue rewrite
- store prompt versions
- define Khmer style guides
- create human-reviewed golden examples

## R6: Timing Drift

Severity: high

Likelihood: medium

Problem: Khmer line length may differ significantly from Chinese source timing.

Mitigation:

- rewrite with duration targets
- use conservative TTS speed adjustment
- flag impossible timing cases
- support silence trimming and pause insertion

## R7: Provider Lock-In

Severity: medium

Likelihood: high

Problem: AI provider models, prices, limits, and policies change.

Mitigation:

- use provider interfaces
- store provider and model versions
- keep local fallbacks where practical
- avoid provider-specific types in domain logic

## R8: Cost Growth

Severity: medium

Likelihood: high

Problem: Full-movie processing can become expensive due to repeated transcription, translation, and TTS calls.

Mitigation:

- cache all provider outputs
- avoid rerunning completed steps
- track cost per step
- use cheaper models for drafts and stronger models for final pass

## R9: Long-Running Job Reliability

Severity: high

Likelihood: medium

Problem: A full movie can take hours. Failures must not lose progress.

Mitigation:

- persist each step
- make steps idempotent
- write artifacts atomically
- support retry and resume commands

## R10: Hardware Constraints

Severity: medium

Likelihood: medium

Problem: macOS local processing may be slow for diarization, source separation, and local ASR/TTS.

Mitigation:

- support cloud providers
- add GPU/server worker path later
- make batch size and model choice configurable

## R11: Weak Workflow Model

Severity: high

Likelihood: medium

Problem: A simple linear pipeline step table may not support correction branches, human review, distributed workers, cancellation, retries, and selective reruns.

Mitigation:

- design job/task/attempt semantics before implementation
- model immutable artifact lineage
- make human corrections create new decision versions
- require task idempotency keys and cache policies

## R12: Quality Gates Added Too Late

Severity: high

Likelihood: high

Problem: If quality checks are treated as post-processing, the system may produce expensive unusable artifacts and hide failures until final render.

Mitigation:

- make QA a dedicated pipeline layer
- define thresholds per stage
- require human acceptance gates for early versions
- store quality records as durable artifacts/metadata

## R13: Cost Blindness

Severity: high

Likelihood: high

Problem: Full-movie processing can create uncontrolled API, GPU, CPU, and storage cost, especially after retries or corrections.

Mitigation:

- add a cost ledger from the start
- estimate job cost before execution
- enforce budget limits
- track cache savings and failed-call waste

## R14: Research Contaminates Production

Severity: medium

Likelihood: medium

Problem: AI experiments can introduce unstable dependencies, scripts, and assumptions into production code paths.

Mitigation:

- separate `research/`, `benchmarks/`, and production packages
- require benchmark scorecards before provider adoption
- prevent production imports from research modules

## R15: Knowledge Layer Complexity

Severity: high

Likelihood: medium

Problem: A central knowledge layer can become too abstract, slow, or hard to query if modeled without practical use cases.

Mitigation:

- start with project-level media memory
- require every knowledge fact to support a known workflow decision
- defer graph/vector infrastructure until relational queries are insufficient
- keep facts versioned and evidence-backed

## R16: Learning System Privacy Risk

Severity: critical

Likelihood: medium

Problem: Reusing corrections or customer media across tenants without explicit permission would create legal and trust risk.

Mitigation:

- scope memory by project, series, organization, and platform
- require opt-in for cross-project or platform learning
- support deletion and rollback
- audit every promoted learning artifact

## R17: SaaS Retrofitting Risk

Severity: high

Likelihood: medium

Problem: A local-only data model can block future organizations, permissions, audit, billing, and tenant isolation.

Mitigation:

- model projects, ownership, usage, provider invocations, and audit from the beginning
- use default local organization/user in single-user mode
- require tenant isolation before commercial SaaS launch

## R18: Automatic QA False Confidence

Severity: high

Likelihood: high

Problem: Model-based or metric-based quality scoring can approve unnatural Khmer or inconsistent character behavior.

Mitigation:

- require human acceptance for early versions
- benchmark quality scorers against native speaker review
- track false-pass and false-fail rates
- use QA scores to prioritize review before using them to skip review
