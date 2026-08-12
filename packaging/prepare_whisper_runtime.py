"""Build and stage the target platform's Whisper.cpp CLI for PyInstaller."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "automatedub_studio" / "resources" / "runtime" / "whisper"
WHISPER_CPP_TAG = "v1.8.3"
WHISPER_CPP_REPOSITORY = "https://github.com/ggml-org/whisper.cpp.git"


def platform_name(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    return {"darwin": "macos", "macos": "macos", "windows": "windows", "linux": "linux"}[value]


def prepare(*, system: str | None = None) -> Path:
    target = platform_name(system)
    source = ROOT / "build" / "whisper.cpp"
    build = source / "build"
    if shutil.which("cmake") is None:
        raise RuntimeError("CMake is required to build the bundled Whisper.cpp runtime.")
    executable_name = "whisper-cli.exe" if target == "windows" else "whisper-cli"
    if not source.is_dir():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                WHISPER_CPP_TAG,
                WHISPER_CPP_REPOSITORY,
                str(source),
            ],
            check=True,
        )
    cmake_args = [
        "cmake",
        "-S",
        str(source),
        "-B",
        str(build),
        "-DWHISPER_BUILD_TESTS=OFF",
        "-DGGML_OPENMP=OFF",
    ]
    if target == "windows":
        cmake_args.extend(["-A", "x64"])
    subprocess.run(cmake_args, check=True)
    subprocess.run(
        ["cmake", "--build", str(build), "--config", "Release", "--target", "whisper-cli"],
        check=True,
    )
    candidates = (
        build / "bin" / executable_name,
        build / "bin" / "Release" / executable_name,
        build / "Release" / executable_name,
    )
    executable = next((candidate for candidate in candidates if candidate.is_file()), None)
    if executable is None:
        raise RuntimeError(f"whisper.cpp did not produce {executable_name}")
    destination = RUNTIME_ROOT / target / executable_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, destination)
    for dependency in executable.parent.iterdir():
        if dependency.is_file() and dependency.suffix.lower() in {".dll", ".dylib", ".so"}:
            shutil.copy2(dependency, destination.parent / dependency.name)
    if target != "windows":
        destination.chmod(destination.stat().st_mode | 0o111)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "macos", "linux"))
    args = parser.parse_args()
    destination = prepare(system=args.platform)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
