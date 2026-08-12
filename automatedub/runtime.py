"""Central resolution for application-managed native media runtimes."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path


def platform_runtime_name(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    return {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(value, value)


def application_resource_directory() -> Path:
    """Locate PyInstaller resources independently from the source checkout."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1] / "automatedub_studio" / "resources"


def application_runtime_directories(system: str | None = None) -> tuple[Path, ...]:
    """Return package locations used for native executable resources."""
    resources = application_resource_directory()
    if getattr(sys, "frozen", False) and platform_runtime_name(system) == "macos":
        bundle_root = Path(sys.executable).resolve().parents[1]
        # PyInstaller's BUNDLE target relocates Mach-O executables to Frameworks.
        return (resources, bundle_root / "Frameworks")
    return (resources,)


def bundled_binary_path(name: str, system: str | None = None) -> Path:
    suffix = ".exe" if platform_runtime_name(system) == "windows" else ""
    return (
        application_resource_directory()
        / "runtime"
        / "bin"
        / platform_runtime_name(system)
        / f"{name}{suffix}"
    )


def bundled_whisper_path(system: str | None = None) -> Path:
    suffix = ".exe" if platform_runtime_name(system) == "windows" else ""
    return (
        application_resource_directory()
        / "runtime"
        / "whisper"
        / platform_runtime_name(system)
        / f"whisper-cli{suffix}"
    )


def resolve_runtime_binary(
    name: str,
    configured: str | None = None,
    *,
    system: str | None = None,
) -> str | None:
    """Resolve bundled tools in packaged apps, PATH/configuration in development."""
    suffix = ".exe" if platform_runtime_name(system) == "windows" else ""
    relative = (
        Path("runtime") / "whisper" / platform_runtime_name(system) / f"whisper-cli{suffix}"
        if name == "whisper-cli"
        else Path("runtime") / "bin" / platform_runtime_name(system) / f"{name}{suffix}"
    )
    candidates = [directory / relative for directory in application_runtime_directories(system)]
    bundled = next(
        (candidate for candidate in candidates if candidate.is_file()),
        application_resource_directory() / relative,
    )
    if getattr(sys, "frozen", False):
        return str(bundled) if bundled.is_file() else None

    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file():
            return str(configured_path)
        if found := shutil.which(configured):
            return found
    return str(bundled) if bundled.is_file() else None
