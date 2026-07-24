# AutomateDub

AutomateDub is a planned knowledge-driven AI localization platform for Khmer media. Its long-term goal is to localize movies, series, anime, short-form video, podcasts, audiobooks, educational media, and corporate content with consistent characters, natural Khmer dialogue, high-quality voices, measurable quality, and traceable human review.

This repository is currently ready for vertical-slice implementation planning. No implementation code has started.

## Current Status

- Final platform architecture documents have been drafted.
- Implementation code has not started.
- Implementation strategy is vertical-slice first: prove one Chinese MP4 can become one playable Khmer MP4, then replace shortcuts with production architecture subsystems.
- The initial product can be local and CLI-first, but the core architecture is designed for future SaaS.
- The system is centered on media memory, character intelligence, localization intelligence, provider-independent voice generation, quality intelligence, and learning from corrections.

## Documentation

- [Software Architecture](docs/ARCHITECTURE.md)
- [Product Philosophy](docs/PRODUCT_PHILOSOPHY.md)
- [Formal Architecture Review](docs/ARCHITECTURE_REVIEW.md)
- [Engineering Principles](docs/ENGINEERING_PRINCIPLES.md)
- [System Diagrams](docs/SYSTEM_DIAGRAMS.md)
- [Knowledge Architecture](docs/KNOWLEDGE_ARCHITECTURE.md)
- [Character Intelligence](docs/CHARACTER_INTELLIGENCE.md)
- [Localization Architecture](docs/LOCALIZATION_ARCHITECTURE.md)
- [Khmer Voice Architecture](docs/VOICE_ARCHITECTURE.md)
- [Quality Pipeline](docs/QUALITY_PIPELINE.md)
- [Learning System](docs/LEARNING_SYSTEM.md)
- [Provider Abstraction](docs/PROVIDER_ABSTRACTION.md)
- [Cache Strategy](docs/CACHE_STRATEGY.md)
- [Cost Management](docs/COST_MANAGEMENT.md)
- [Architecture Benchmark Plan](docs/BENCHMARK_PLAN.md)
- [Scalability Plan](docs/SCALABILITY_PLAN.md)
- [Technical Debt Prevention](docs/TECHNICAL_DEBT_PREVENTION.md)
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Final Self Review](docs/FINAL_SELF_REVIEW.md)
- [Final Roadmap](docs/ROADMAP.md)
- [Final Milestones](docs/MILESTONES.md)
- [MVP And Versions](docs/MVP_AND_VERSIONS.md)
- [Technology Recommendations](docs/TECHNOLOGY_RECOMMENDATIONS.md)
- [Requirements Gaps](docs/REQUIREMENTS_GAPS.md)
- [Risk Register](docs/RISK_REGISTER.md)
- [Documentation Map](docs/DOCUMENTATION_MAP.md)
- [codex-auto wrapper](docs/operations/codex-auto.md)
- [Vertical Slice Operations](docs/operations/vertical-slice.md)
- [Architecture Decision Records](docs/adr/)

## Local Operations Helpers

Run Codex through the auto-resume wrapper:

```bash
./bin/codex-auto
```

When Codex exits after a `503` retry-limit failure, the wrapper waits 30 seconds and runs `codex resume --last`.

## Final Technology Baseline

- Language: Python 3.12+
- Dependency and package management: `uv`
- CLI: Typer
- Configuration: Pydantic Settings with `.env` support
- Database: PostgreSQL-compatible schema from day one; SQLite allowed only as a local/development profile
- Migrations: Alembic
- Task execution: queue-compatible workflow semantics now; local runner first; Dramatiq/RQ/Celery later if needed
- Media processing: FFmpeg, PySceneDetect, MoviePy only for light orchestration if needed
- Audio source separation: Demucs or equivalent model behind an adapter
- Diarization: provider-independent contract; benchmark pyannote.audio, NVIDIA NeMo, and cloud options
- Transcription: provider-independent contract; benchmark OpenAI, Whisper-family/local, and additional ASR options
- Translation/localization: provider-independent Localization Intelligence layer
- Khmer voice generation: capability-based Voice Engine; no default provider until benchmark evidence exists
- Testing: pytest, pytest-cov, contract tests, golden media tests, migration tests, and benchmark scorecards

## Non-Goals For The First Implementation

- No GUI.
- No upload automation.
- No fully autonomous quality approval.
- No unlicensed voice cloning.
- No attempt to perfectly separate vocals, music, and effects in v1.

## Implementation Readiness Gate

Before implementation starts, the product owner and architecture reviewer should approve or revise:

- product philosophy
- final architecture
- ADRs 0006-0013
- budget tolerance for cloud AI services
- legal/licensing constraints for source movies and generated voices
- Khmer voice provider strategy
- local-only versus cloud-assisted processing
- benchmark results for Khmer TTS, ASR, diarization, translation, and source separation
- quality gates and human review policy

## First Implementation Target

The first implementation target is the Smallest Working Pipeline:

1. Accept one Chinese MP4 file.
2. Extract audio.
3. Transcribe speech.
4. Translate to Khmer.
5. Generate Khmer speech using one provider.
6. Replace or cover the original dialogue.
7. Render one playable Khmer MP4.

Temporary shortcuts are allowed for this vertical slice only. The frozen architecture remains the long-term replacement path.

## Current CLI

Prepare local tools and the recommended Whisper model:

```bash
uv run automatedub setup
```

Validate local configuration:

```bash
uv run automatedub doctor
```

VS1 extracts audio and transcribes Chinese speech locally:

```bash
uv run automatedub dub movie.mp4 output/
```

Expected results:

```text
output/audio.wav
output/transcript.json
output/translation_prompt.json
output/translation.json
output/tts/0000.wav
output/tts/0001.wav
```

VS2 localization uses NBWCode. VS3 speech generation uses the configured TTS
provider; Camb.ai is the first production provider. Create a local `.env` file
in the repository root:

```bash
NBW_BASE_URL=https://www.nbwcode.top/v1
NBW_AUTOMATEDUB_API_KEY=...
LOCALIZATION_MODEL=gpt-5.5
TTS_PROVIDER=cambai
CAMB_API_KEY=...
CAMB_VOICE_ID=170542
CAMB_LANGUAGE=km-kh
TTS_MODEL=mars-8.1-flash-beta
```

The CLI loads `.env` automatically. Shell environment variables still override
values in `.env` when both are present.

The localizer prefers `/responses` and automatically falls back to `/chat/completions` if
the configured provider does not support Responses.

VS3 reads `output/translation.json` and writes one WAV per translated segment to
`output/tts/`. Failed TTS segments are recorded in `output/tts/errors.json`.

To generate speech from an existing translation without rerunning audio
extraction, transcription, or localization:

```bash
uv run automatedub tts output/
```

To generate a short voice-quality sample from an existing translation:

```bash
uv run automatedub tts sample output/ --start-segment 0 --minutes 2
```

This writes selected segment WAVs to `output/sample/`, concatenates them into
`output/sample/sample.wav`, and writes the sampled Khmer text to
`output/sample/sample.txt`. It does not mix with the original source audio.
