# Build

This document describes the reproducible build path for AutomateDub Studio.

## Requirements

- Python 3.12+
- `uv`
- FFmpeg and FFprobe available on `PATH`
- PyInstaller for local packaging
- Platform-specific tools:
  - Windows: Inno Setup for installer generation
  - macOS: `hdiutil` for optional DMG creation
  - Linux: `appimagetool` for AppImage generation

## Version Source

Studio version metadata lives in:

- `automatedub_studio/metadata.py`

`pyproject.toml`, the About dialog, packaging names, and release docs should use
that value. Do not introduce another version constant.

## Clean Build

From a fresh clone:

```bash
uv sync
uv run pytest
uv run ruff check
uv run python packaging/build.py --platform linux
```

Use `--platform windows`, `--platform macos`, or `--platform linux` on the
matching operating system.

## Output

Build output is written under `dist/`.

Release artifacts use this naming pattern:

```text
AutomateDub-Studio-<version>-<platform>.<suffix>
```

Examples:

- `AutomateDub-Studio-0.1.0-windows-setup.exe`
- `AutomateDub-Studio-0.1.0-macos.dmg`
- `AutomateDub-Studio-0.1.0-linux.AppImage`

## Platform Notes

Windows packaging uses:

- `packaging/automatedub-studio.spec`
- `packaging/windows/AutomateDubStudio.iss`

macOS packaging uses:

- `packaging/automatedub-studio.spec`
- `packaging/macos/create-dmg.sh`

Linux packaging uses:

- `packaging/automatedub-studio.spec`
- `packaging/linux/automatedub-studio.desktop`
- `packaging/linux/automatedub-studio.xml`
- `packaging/linux/build-appimage.sh`
