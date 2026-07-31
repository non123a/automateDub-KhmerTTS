# Release

This document is the release checklist for AutomateDub Studio.

## Checklist

1. Update `APP_VERSION` in `automatedub_studio/metadata.py`.
2. Update `PROJECT_STATE.md`.
3. Run:

```bash
uv run pytest
uv run ruff check
git diff --check
```

4. Create a tag:

```bash
git tag v<version>
git push origin v<version>
```

5. Let the packaging workflow produce release assets.
6. Verify artifact names match:

```text
AutomateDub-Studio-<version>-windows-setup.exe
AutomateDub-Studio-<version>-macos.dmg
AutomateDub-Studio-<version>-linux.AppImage
```

7. Smoke-test each package on a clean machine.

## CI/CD

Workflows:

- `.github/workflows/tests.yml`: runs pytest, Ruff, and whitespace checks.
- `.github/workflows/package.yml`: builds packages on Windows, macOS, and Linux.

Package creation uses `packaging/build.py`, which delegates to the platform
packaging templates under `packaging/`.

## Release Notes

Release notes should mention:

- application version
- supported platforms
- known media-tool requirements
- migration notes for `.autodub` projects
- major fixed issues and user-facing workflow changes
