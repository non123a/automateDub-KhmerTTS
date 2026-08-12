"""Opt-in editor performance diagnostics for investigation builds."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def diagnostics_enabled() -> bool:
    return os.environ.get("AUTOMATEDUB_PERF_DIAGNOSTICS") == "1"


class EditorPerformanceDiagnostics:
    """Collect wall-clock stage timings without affecting normal sessions."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self.started = time.perf_counter()
        self.events: list[dict[str, Any]] = []

    def mark(self, stage: str, **details: Any) -> None:
        if not diagnostics_enabled():
            return
        self.events.append(
            {
                "stage": stage,
                "elapsed_seconds": round(time.perf_counter() - self.started, 4),
                **details,
            }
        )

    def write(self, **summary: Any) -> None:
        if not diagnostics_enabled():
            return
        destination = self.project_path / "pipeline" / "debug" / "editor_performance.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "total_open_to_editor_ready_seconds": round(
                        time.perf_counter() - self.started, 4
                    ),
                    "events": self.events,
                    **summary,
                }, indent=2),
            encoding="utf-8",
        )
