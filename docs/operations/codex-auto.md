# codex-auto

`bin/codex-auto` is a local wrapper around the `codex` CLI.

It handles one specific failure mode: Codex exits after a transient `503` service error and reports that the retry limit was exceeded. When that happens, the wrapper waits 30 seconds and continues the last Codex session with:

```bash
codex resume --last
```

## Usage

Start Codex through the wrapper:

```bash
./bin/codex-auto
```

Pass normal Codex arguments after `--`:

```bash
./bin/codex-auto -- --cd /path/to/project
./bin/codex-auto -- -m gpt-5
./bin/codex-auto -- exec "summarize this repository"
```

## Options

```bash
./bin/codex-auto --wait 30
./bin/codex-auto --max-resumes 5
./bin/codex-auto --rerun -- exec "run the test suite"
```

- `--wait`: seconds to wait before continuing. Default: `30`.
- `--max-resumes`: maximum automatic continues. Default: `0`, meaning unlimited.
- `--rerun`: rerun the original command instead of `codex resume --last`.

## Environment Variables

```bash
CODEX_AUTO_WAIT_SECONDS=30
CODEX_AUTO_MAX_RESUMES=0
```

## Detection Rule

The wrapper only auto-continues when both conditions appear in Codex output:

- a retryable service signal such as `503` or `service unavailable`
- a retry-limit message such as `exceeded retry limit`, `retry limit exceeded`, or `maximum retries`

Other failures exit normally so real errors are not hidden.
