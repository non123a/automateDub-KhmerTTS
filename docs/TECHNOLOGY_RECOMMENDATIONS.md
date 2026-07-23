# Technology Recommendations

Status: revised after architecture review.

## Summary

AutomateDub should use conservative infrastructure around high-risk AI and media components. The original technology direction was broadly reasonable, but several choices need stronger constraints before implementation.

The main recommendation is: design for PostgreSQL-compatible durable workflow state, immutable artifacts, provider capability routing, explicit quality gates, and cost accounting from day one. The first runtime can still be local, but the architecture must not be local-only.

## Python And Packaging

Recommendation: Python 3.12+ with `uv`.

Good:

- Python has the strongest ecosystem for ASR, diarization, media orchestration, ML evaluation, and provider SDKs.
- `uv` gives fast dependency resolution, lockfiles, and good developer ergonomics.

Weaknesses:

- GPU/ML packages often have special installation paths and may not behave cleanly under one universal lockfile.
- Some research dependencies will be heavy and unstable.

Alternatives:

- Poetry: mature, but slower and less compelling than `uv` for modern Python workflows.
- Conda/Mamba: stronger for ML environments, but heavy for an application runtime.
- Node/TypeScript: better for web/dashboard work, weaker for local AI/media.

Recommendation:

- Use Python + `uv` for production.
- Keep research dependencies isolated from production dependency groups.
- Document exceptions for CUDA, Metal, PyTorch, diarization, and source separation packages.

## Application Structure

Recommendation: Clean Architecture with enforced dependency direction.

Good:

- Separates domain logic from CLI, database, FFmpeg, and providers.
- Supports future dashboard/API without rewriting the pipeline.

Weaknesses:

- Too much purity can create duplicate domain, ORM, DTO, and provider models.

Recommendation:

- Keep domain/application/infrastructure/interface layers.
- Add explicit `research/` and `benchmarks/` directories outside production imports.
- Add contract tests that prevent provider-native schemas from leaking into application logic.

## ORM

Recommendation: SQLAlchemy 2.0 with Alembic.

Good:

- Mature, flexible, PostgreSQL-ready, and suitable for complex workflow metadata.

Weaknesses:

- ORM misuse can obscure query performance and locking behavior.
- Mapping rich domain entities directly to ORM models can create coupling.

Alternatives:

- Django ORM: productive, but pulls the project toward a web-app shape too early.
- SQLModel: convenient, but less mature for complex workflow schemas.
- Raw SQL: precise, but slower for broad schema evolution.

Recommendation:

- Use SQLAlchemy Core/ORM pragmatically.
- Keep domain objects independent from ORM models where business rules matter.
- Add migration tests early.

## Database

Recommendation: PostgreSQL-compatible schema from day one; SQLite allowed only as a local profile.

Good:

- SQLite is simple for one local operator.
- PostgreSQL is the correct long-term target for workers, dashboard, locking, JSON querying, and audit data.

Weaknesses:

- "SQLite first, PostgreSQL later" can become a trap if schema, locking, and indexing are not designed for PostgreSQL now.

Alternatives:

- PostgreSQL from day one: more operational setup, but less migration risk.
- SQLite only: unacceptable for eventual scale.
- DuckDB: useful for analytics, not workflow state.

Recommendation:

- Design and test against PostgreSQL semantics.
- Permit SQLite for local development and single-user experiments.
- Require PostgreSQL before distributed workers or dashboard use.

## Queue And Workflow

Recommendation: queue-compatible task semantics now; local runner first only as an implementation of the same contract.

Good:

- A local runner reduces early operational burden.

Weaknesses:

- Deferring workflow semantics creates expensive rewrites later.

Alternatives:

- Dramatiq: simple Python worker model with Redis; good likely first distributed queue.
- RQ: very simple Redis queue; good for basic jobs, less powerful workflow control.
- Celery: mature and feature-rich; operationally heavier.
- Temporal: excellent workflow durability, but too much operational complexity for the initial project unless scale becomes central.

Recommendation:

- Define job/task/attempt/lease/retry/cancel/progress semantics now.
- Start with an in-process runner that uses those records.
- Choose Dramatiq or RQ before Celery unless complex routing is proven necessary.

## Configuration

Recommendation: Pydantic Settings plus typed YAML/TOML profiles.

Good:

- Strong validation and `.env` support.
- Job profile snapshots improve reproducibility.

Weaknesses:

- Provider capabilities, budget policy, retention policy, and prompt registry should not be buried in ad hoc settings.

Recommendation:

- Separate runtime settings, job profiles, provider capability registry, budget policy, retention policy, and prompt registry.
- Validate profile cost and provider compatibility before a job starts.

## Logging And Observability

Recommendation: structured JSON logs plus OpenTelemetry-compatible metrics/traces.

Good:

- JSON logs with job/clip/task correlation are necessary.

Weaknesses:

- Logs alone do not answer provider cost, queue health, cache hit rate, or quality regression questions.

Alternatives:

- structlog or standard `logging` with JSON formatter: both acceptable.
- OpenTelemetry: recommended architecture target for traces/metrics.

Recommendation:

- Use structured logs from the first implementation.
- Design metrics for stage duration, provider latency, cost, cache hits, artifact sizes, retry counts, and QA failures.

## Testing

Recommendation: pytest ecosystem plus contract, golden, benchmark, and migration suites.

Good:

- pytest, pytest-cov, Ruff, and Pyright/mypy are appropriate.

Weaknesses:

- Normal unit tests will not catch AI quality regressions or media sync issues.

Recommendation:

- Separate tests into unit, integration, contract, golden media, provider-live, benchmark, and migration suites.
- Paid provider tests must be opt-in and budget-limited.
- Maintain small legal media fixtures.

## Video Processing

Recommendation: FFmpeg/FFprobe as authoritative media tools; PySceneDetect as a benchmarked scene detector.

Good:

- FFmpeg is the correct production foundation for stream handling, codecs, timestamps, mixing, and rendering.

Weaknesses:

- FFmpeg command construction is fragile without fixture coverage.
- PySceneDetect may not be reliable enough for dialogue-aware segmentation by itself.

Alternatives:

- MoviePy: convenient but hides FFmpeg behavior.
- OpenCV: useful for frame analysis, insufficient for audio/rendering.
- Cloud video pipelines: expensive and unnecessary now.

Recommendation:

- Use FFmpeg directly through a controlled command builder.
- Keep PySceneDetect replaceable.
- Add media fixture tests for MP4/MKV, multiple audio tracks, subtitle tracks, variable frame rate, and multi-channel audio.

## Speech Separation

Recommendation: source-separation provider contract with Demucs or comparable models benchmarked, not assumed.

Good:

- Background preservation matters.

Weaknesses:

- Movie audio is often too mixed for clean dialogue removal.

Alternatives:

- Ducking original audio under generated speech.
- Demucs-style music/vocal separation.
- Specialist dialogue isolation services.

Recommendation:

- Treat ducking as the reliable baseline.
- Treat source separation as optional quality improvement until benchmarked.

## Diarization

Recommendation: benchmark pyannote.audio, NVIDIA NeMo, and any cloud diarization path before selecting defaults.

Good:

- pyannote.audio is practical in Python.
- NeMo can be stronger in GPU/server environments.

Weaknesses:

- Both may struggle with movies, music, effects, and overlap.

Recommendation:

- Keep diarization behind a provider contract.
- Model uncertainty and corrections.
- Do not rely on diarization labels as stable character IDs.

## Transcription

Recommendation: provider abstraction with OpenAI, Whisper/faster-whisper, and at least one additional ASR path benchmarked.

Good:

- Cloud ASR can reduce local model complexity.
- Local fallback protects against cost, privacy, or connectivity constraints.

Weaknesses:

- Output schemas differ widely.
- Chinese variant and subtitle hint handling are unresolved.

Recommendation:

- Normalize segment, word timing where available, confidence, language, speaker association, and uncertainty markers.
- Benchmark on target audio before choosing a default.

## Translation And Rewriting

Recommendation: LLM provider abstraction with separate semantic translation, dialogue rewrite, and optional style adaptation.

Good:

- Separation improves auditability and correction.

Weaknesses:

- Two or three LLM stages increase cost.
- Khmer quality cannot be judged only by the model that generated it.

Alternatives:

- OpenAI, Claude, Gemini, local LLMs, and specialist translation services should all be possible.

Recommendation:

- Use prompt/version registries and benchmark sets.
- Include glossary, character memory, style guide, and reviewer correction memory.
- Add model-judge scoring only as an assist, not the final approval authority.

## Khmer Voice Generation

Recommendation: no default provider until Track 0 / M0 benchmarks are complete.

Good:

- The previous architecture correctly identified this as high risk.

Weaknesses:

- Any implementation that assumes provider availability is premature.

Alternatives:

- Azure Khmer standard voices as a baseline.
- Narakeet or other Khmer-specific TTS providers if API and licensing fit.
- Dubbing-specialist providers such as CAMB.AI if direct testing proves quality and terms.
- Licensed human-recorded voice assets.
- Future custom Khmer TTS or voice conversion.

Recommendation:

- Move Khmer voice proof-of-quality to architecture research before coding.
- Separate TTS, expressive TTS, voice cloning, voice conversion, emotion planning, and timing fit.
- Track consent and license data as first-class records.

## CI/CD

Recommendation: GitHub Actions for normal CI, with opt-in provider benchmark jobs.

Good:

- Standard, easy to run on pull requests.

Weaknesses:

- Media and provider tests can be slow and costly.

Recommendation:

- Normal CI: lint, type checks, unit tests, migration tests, lightweight fixtures.
- Scheduled/manual CI: provider-live tests and benchmark reports with strict budget caps.
