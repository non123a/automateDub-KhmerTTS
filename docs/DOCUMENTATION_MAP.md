# Documentation Map

This document explains why each project document exists and when it should be updated.

## README.md

Purpose: orient a new reader quickly.

Update when:

- project status changes
- setup instructions are added
- major architecture or scope changes occur

## docs/ARCHITECTURE.md

Purpose: define the final platform architecture, domain model, knowledge model, subsystem boundaries, repository structure, SaaS evolution path, and implementation readiness gate.

Update when:

- a major component is added or replaced
- the pipeline changes
- persistence or task execution changes
- provider strategy changes

## docs/PRODUCT_PHILOSOPHY.md

Purpose: define the product principles that guide engineering decisions.

Update when:

- target users or product priorities change
- quality, provider independence, learning, or cost principles change

## docs/KNOWLEDGE_ARCHITECTURE.md

Purpose: define media memory, evidence-backed facts, confidence, corrections, and retrieval strategy.

Update when:

- knowledge fact types change
- memory scopes change
- graph/search/vector storage decisions change

## docs/SYSTEM_DIAGRAMS.md

Purpose: provide compact subsystem, workflow, provider routing, correction propagation, and SaaS evolution diagrams.

Update when:

- subsystem boundaries change
- workflow or correction flow changes
- SaaS ownership model changes

## docs/CHARACTER_INTELLIGENCE.md

Purpose: define character identity, speaker clustering, aliases, relationships, style, voice assignment, and correction propagation.

Update when:

- character identity model changes
- visual identity or series continuity features are added

## docs/LOCALIZATION_ARCHITECTURE.md

Purpose: define cultural adaptation, Khmer dialogue rewrite, audience profiles, timing-aware localization, and localization QA.

Update when:

- style guide or audience profile strategy changes
- translation/rewrite stages are combined or split

## docs/LEARNING_SYSTEM.md

Purpose: define how corrections, provider results, pronunciation fixes, and quality outcomes become reusable memory.

Update when:

- learning scopes or privacy rules change
- correction promotion policies change

## docs/SCALABILITY_PLAN.md

Purpose: define the evolution from local product to team product, SaaS, and enterprise deployment.

Update when:

- deployment strategy changes
- tenant, billing, object storage, or worker architecture changes

## docs/TECHNICAL_DEBT_PREVENTION.md

Purpose: define architecture fitness checks and non-negotiable rules that prevent long-term platform debt.

Update when:

- architecture rules change
- recurring shortcuts or debt patterns are found

## docs/IMPLEMENTATION_ROADMAP.md

Purpose: map the approved platform architecture into implementation phases without containing code.

Update when:

- implementation sequencing changes
- a phase is completed or split

## docs/FINAL_SELF_REVIEW.md

Purpose: record the final CTO/founding-engineer self-review before implementation planning.

Update when:

- the final architecture verdict changes
- a new major weakness is discovered

## docs/ARCHITECTURE_REVIEW.md

Purpose: record the formal pre-implementation architecture review verdict, risks, required improvements, and approval decision.

Update when:

- a formal review cycle is completed
- architecture approval status changes
- a major risk is accepted, retired, or escalated

## docs/ENGINEERING_PRINCIPLES.md

Purpose: define the engineering philosophy that future ADRs and architecture changes must reference.

Update when:

- the project changes its quality, cost, provider-independence, or research discipline
- a principle is added, removed, or superseded

## docs/VOICE_ARCHITECTURE.md

Purpose: define the Khmer voice-generation architecture, provider uncertainty model, consent/licensing model, and benchmark requirements.

Update when:

- voice providers are benchmarked
- consent/licensing rules change
- voice cloning or voice conversion moves into scope

## docs/QUALITY_PIPELINE.md

Purpose: define quality gates, review records, automated scoring, and correction propagation.

Update when:

- quality thresholds change
- human review flow changes
- new automated scoring becomes reliable

## docs/PROVIDER_ABSTRACTION.md

Purpose: define provider contracts, capability registry, invocation records, and fallback/routing policy.

Update when:

- adding or removing a provider category
- changing provider routing or benchmark requirements
- provider metadata requirements change

## docs/CACHE_STRATEGY.md

Purpose: define reusable cache keys, cacheable stages, invalidation rules, and retention policy.

Update when:

- task inputs or artifact lineage rules change
- storage lifecycle policy changes
- cache invalidation bugs are found

## docs/COST_MANAGEMENT.md

Purpose: define cost ledger, estimates, budget limits, and cost reporting requirements.

Update when:

- provider pricing assumptions change
- cost events or reports are added
- billing/dashboard needs change

## docs/BENCHMARK_PLAN.md

Purpose: define the architecture benchmark process required before provider commitment or implementation.

Update when:

- benchmark datasets change
- providers are added or removed
- scorecard criteria change

## docs/REQUIREMENTS_GAPS.md

Purpose: track unresolved product and operational questions that affect technical design.

Update when:

- the product owner answers an open requirement
- a new ambiguity is discovered
- legal, cost, or quality constraints change

## docs/ROADMAP.md

Purpose: describe the current vertical-slice-first implementation sequence and later return path to the frozen architecture.

Update when:

- milestones are completed
- priorities change
- a phase is split, removed, or added

## docs/MILESTONES.md

Purpose: provide concrete implementation milestone scope and success criteria.

Update when:

- estimates change based on implementation evidence
- a milestone is accepted
- scope moves between MVP and future versions

## docs/MVP_AND_VERSIONS.md

Purpose: separate what belongs in the first useful release from later automation, quality, and scale work.

Update when:

- MVP scope changes
- a future feature moves into the current release
- the product owner changes the acceptable quality bar

## docs/TECHNOLOGY_RECOMMENDATIONS.md

Purpose: summarize technology choices, tradeoffs, and recommendations in a review-friendly format.

Update when:

- a core tool is selected or replaced
- provider evaluations produce new evidence
- deployment assumptions change

## docs/RISK_REGISTER.md

Purpose: make major technical, legal, and operational risks visible.

Update when:

- a risk is retired
- a mitigation is proven or rejected
- a new high-impact uncertainty appears

## docs/operations/codex-auto.md

Purpose: document the local Codex auto-resume wrapper.

Update when:

- wrapper behavior changes
- supported command-line options change

## docs/operations/vertical-slice.md

Purpose: document how to run the current vertical-slice implementation.

Update when:

- a vertical-slice milestone changes CLI behavior
- required tools or credentials change
- generated outputs change

## docs/adr/

Purpose: preserve important architecture decisions and their tradeoffs.

Update by adding a new ADR when:

- selecting core infrastructure
- changing a previous architectural decision
- adopting or rejecting a major provider
- introducing a new deployment model

Do not rewrite history in old ADRs except for minor typo fixes. Supersede them with new ADRs.
