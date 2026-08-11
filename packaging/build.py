"""Reproducible Studio packaging entry point.

The script is intentionally thin: it centralizes artifact naming and invokes the
platform packaging backend selected by CI or a release engineer.
"""

from __future__ import annotations

import argparse
import platform as platform_module
import subprocess
from pathlib import Path

from automatedub_studio.metadata import APP_VERSION, release_artifact_name

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


def current_platform() -> str:
    system = platform_module.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return system


def package_command(platform_name: str, *, clean: bool = True) -> list[str]:
    command = ["pyinstaller"]
    if clean:
        command.append("--clean")
    command.extend(["--noconfirm", str(ROOT / "packaging" / "automatedub-studio.spec")])
    if platform_name not in {"linux", "windows", "macos"}:
        raise ValueError(f"unsupported platform: {platform_name}")
    command.extend(["--distpath", str(DIST_DIR / platform_name)])
    return command


def release_artifact(platform_name: str, suffix: str) -> Path:
    return DIST_DIR / release_artifact_name(platform_name, APP_VERSION, suffix)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AutomateDub Studio packages.")
    parser.add_argument(
        "--platform",
        choices=("windows", "macos", "linux"),
        default=current_platform(),
    )
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args(argv)

    subprocess.run(
        package_command(args.platform, clean=not args.no_clean),
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
