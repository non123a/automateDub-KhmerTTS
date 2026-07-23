# ADR 0001: Use Python 3.12+ And uv

Status: accepted

## Problem

AutomateDub needs a language and package workflow suitable for AI providers, media tooling, ML experiments, CLI/API services, and long-running workers.

## Alternatives

- Python with `uv`
- Python with `pip` and `venv`
- Python with Poetry
- Conda/Mamba
- Node/TypeScript

## Tradeoffs

- Python has the strongest ecosystem for ASR, diarization, ML evaluation, FFmpeg orchestration, and AI SDKs.
- `uv` gives fast dependency resolution and lockfile-based reproducibility.
- Some GPU and ML dependencies may still require documented installation exceptions.
- Node/TypeScript may be useful for future dashboard work, but should not own core media/AI orchestration.

## Final Decision

Use Python 3.12+ and `uv` for production package management and execution.

## Consequences

- Production dependencies should be locked.
- Research dependencies must be isolated from production dependency groups.
- GPU/Metal/CUDA exceptions must be documented.

## Future Reconsideration

Reconsider Python version and dependency strategy when core ML dependencies reliably support newer Python releases or if dashboard code becomes a separate TypeScript application.

