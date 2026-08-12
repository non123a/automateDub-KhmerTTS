"""Assert PyInstaller collected all target-native application runtime files."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expected_members(platform: str) -> tuple[str, ...]:
    suffix = ".exe" if platform == "windows" else ""
    prefix = "runtime"
    return (
        f"{prefix}/bin/{platform}/ffmpeg{suffix}",
        f"{prefix}/bin/{platform}/ffprobe{suffix}",
        f"{prefix}/whisper/{platform}/whisper-cli{suffix}",
    )


def _is_windows_pe(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(2) == b"MZ"
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "macos", "linux"), required=True)
    args = parser.parse_args()
    executable_name = (
        "AutomateDub Studio.exe" if args.platform == "windows" else "AutomateDub Studio"
    )
    executable = ROOT / "dist" / args.platform / "AutomateDub Studio" / executable_name
    if args.platform == "macos":
        executable = (
            ROOT
            / "dist"
            / args.platform
            / "AutomateDub.app"
            / "Contents"
            / "MacOS"
            / executable_name
        )
    if not executable.is_file():
        raise RuntimeError(f"Packaged executable is missing: {executable}")
    resource_root = executable.parent / "_internal"
    if args.platform == "macos":
        resource_root = executable.parent.parent / "Frameworks"
    missing = []
    for member in expected_members(args.platform):
        if not (resource_root / member).is_file():
            missing.append(member)
    if missing:
        raise RuntimeError(f"Packaged runtime files are missing: {', '.join(missing)}")
    environment = {key: value for key, value in os.environ.items() if key.upper() != "PATH"}
    for member in expected_members(args.platform)[:2]:
        binary = resource_root / member
        if args.platform == "windows" and not _is_windows_pe(binary):
            raise RuntimeError(f"Bundled {binary.name} is not a native Windows executable")
        result = subprocess.run(
            [str(binary), "-version"],
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Bundled {binary.name} cannot run without PATH: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
