"""Stage a relocatable, target-native FFmpeg/ffprobe runtime for packaging."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_LIBRARIES = ("/System/", "/usr/lib/")
LINUX_SYSTEM_LIBRARY_PREFIXES = (
    "libc.so",
    "libm.so",
    "libdl.so",
    "librt.so",
    "libpthread.so",
    "ld-linux",
)


def platform_name(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    return {"darwin": "macos", "macos": "macos", "windows": "windows", "linux": "linux"}[value]


def _copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.chmod(destination.stat().st_mode | 0o200)
    shutil.copy2(source, destination)
    if platform.system() != "Windows":
        destination.chmod(destination.stat().st_mode | 0o111)
    return destination


def _macos_dependencies(binary: Path) -> list[Path]:
    output = subprocess.run(
        ["otool", "-L", str(binary)], check=True, capture_output=True, text=True
    ).stdout
    dependencies: list[Path] = []
    for line in output.splitlines()[1:]:
        value = line.strip().split(" (", 1)[0]
        dependency = Path(value)
        if (
            value.startswith("/")
            and not value.startswith(SYSTEM_LIBRARIES)
            and dependency.is_file()
        ):
            dependencies.append(dependency)
    return dependencies


def _stage_macos_dependencies(binaries: list[Path], destination: Path) -> None:
    library_dir = destination / "lib"
    pending = list(binaries)
    copied: dict[Path, Path] = {}
    while pending:
        binary = pending.pop()
        for dependency in _macos_dependencies(binary):
            target = library_dir / dependency.name
            if dependency not in copied:
                copied[dependency] = _copy(dependency, target)
                pending.append(copied[dependency])

    for binary in [*binaries, *copied.values()]:
        dependencies = _macos_dependencies(binary)
        if binary.parent == library_dir:
            subprocess.run(
                ["install_name_tool", "-id", f"@rpath/{binary.name}", str(binary)],
                check=True,
            )
            rpath = "@loader_path"
        else:
            rpath = "@loader_path/lib"
        subprocess.run(
            ["install_name_tool", "-add_rpath", rpath, str(binary)],
            check=False,
            capture_output=True,
        )
        for dependency in dependencies:
            subprocess.run(
                [
                    "install_name_tool",
                    "-change",
                    str(dependency),
                    f"@rpath/{dependency.name}",
                    str(binary),
                ],
                check=True,
            )


def _linux_dependencies(binary: Path) -> list[Path]:
    output = subprocess.run(
        ["ldd", str(binary)], check=True, capture_output=True, text=True
    ).stdout
    dependencies: list[Path] = []
    for value in re.findall(r"=>\s+(/\S+)", output):
        dependency = Path(value)
        if dependency.is_file() and not dependency.name.startswith(LINUX_SYSTEM_LIBRARY_PREFIXES):
            dependencies.append(dependency)
    return dependencies


def _stage_linux_dependencies(binaries: list[Path], destination: Path) -> None:
    library_dir = destination / "lib"
    libraries = {
        dependency.resolve()
        for binary in binaries
        for dependency in _linux_dependencies(binary)
    }
    for dependency in libraries:
        _copy(dependency, library_dir / dependency.name)
    for binary in [*binaries, *(library_dir / dependency.name for dependency in libraries)]:
        rpath = "$ORIGIN/lib" if binary.parent == destination else "$ORIGIN"
        subprocess.run(
            ["patchelf", "--set-rpath", rpath, str(binary)],
            check=True,
        )


def prepare(*, system: str | None = None) -> list[Path]:
    target = platform_name(system)
    destination = ROOT / "automatedub_studio" / "resources" / "runtime" / "bin" / target
    destination.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if target == "windows" else ""
    staged: list[Path] = []
    for name in ("ffmpeg", "ffprobe"):
        source = shutil.which(f"{name}{suffix}")
        if source is None:
            raise RuntimeError(f"{name} is required to stage the packaged media runtime.")
        staged.append(_copy(Path(source), destination / f"{name}{suffix}"))
        if target == "windows":
            for dependency in Path(source).parent.glob("*.dll"):
                _copy(dependency, destination / dependency.name)
    if target == "macos":
        _stage_macos_dependencies(staged, destination)
    elif target == "linux":
        _stage_linux_dependencies(staged, destination)
    return staged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "macos", "linux"), required=True)
    args = parser.parse_args()
    for path in prepare(system=args.platform):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
