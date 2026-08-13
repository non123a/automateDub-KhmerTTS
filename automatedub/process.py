"""Safe external-process launching for application runtime tools.

Windows FFmpeg, ffprobe, and whisper-cli are console-subsystem executables.
Launching them from a frozen GUI application without creation flags makes
Windows create a transient console window for every invocation.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


def is_windows_gui_runtime() -> bool:
    """Return whether child console windows must be suppressed."""
    return sys.platform == "win32" and (
        bool(getattr(sys, "frozen", False))
        or os.environ.get("AUTOMATEDUB_HIDE_WINDOWS_SUBPROCESSES") == "1"
    )


def gui_subprocess_kwargs() -> dict[str, Any]:
    """Windows-only creation settings that preserve pipes and exit codes."""
    if not is_windows_gui_runtime():
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run an application runtime command without a Windows console flash."""
    return subprocess.run(command, **gui_subprocess_kwargs(), **kwargs)


def popen(command: list[str], **kwargs: Any) -> subprocess.Popen[str]:
    """Start a cancellable application runtime command without a console flash."""
    return subprocess.Popen(command, **gui_subprocess_kwargs(), **kwargs)
