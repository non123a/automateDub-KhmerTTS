# ADR 0012: Separate Research, Benchmarks, And Production

Status: accepted

## Problem

AI localization requires experimentation, but production systems require reproducibility. Mixing research scripts with production code creates dependency, quality, and operational risk.

## Alternatives

- Keep all code in one package.
- Use notebooks and scripts ad hoc.
- Separate production, research, and benchmarks with clear dependency rules.

## Tradeoffs

- Separate areas require discipline and promotion process.
- They prevent unstable experiments from becoming hidden production dependencies.

## Final Decision

The repository will separate `automatedub/`, `research/`, `benchmarks/`, and `tests/`. Production code must not import from research code.

## Consequences

- Benchmark tooling may depend on production contracts.
- Provider adoption requires benchmark scorecards.

## Future Reconsideration

If the project becomes multi-repo later, research and benchmarks may move into dedicated repositories.

