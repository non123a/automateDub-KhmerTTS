# Cost Management

## Requirement

Cost tracking must be first-class from the beginning. Full movie processing can become expensive through repeated ASR, LLM, TTS, source separation, and rendering work.

## Cost Ledger

Record cost events for:

- API token usage
- TTS character/audio duration usage
- ASR audio duration usage
- provider minimum charges
- GPU time
- CPU render time
- storage growth
- manual review time if tracked

Each cost event should link to provider invocation, task attempt, job run, artifact, movie, and billing period.

## Estimates

Before running a job, estimate:

- cost per clip
- cost per movie
- best/expected/worst-case provider spend
- expected local processing duration
- expected storage use

The operator should be able to set budget limits that pause a job before exceeding configured thresholds.

## Reporting

Required reports:

- cost by job
- cost by provider
- cost by stage
- cost by day/month
- cache savings
- failed-call waste
- manual review count and duration

This prepares the architecture for a future billing or operations dashboard without coupling it to a dashboard now.

