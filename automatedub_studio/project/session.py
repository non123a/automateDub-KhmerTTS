"""Session recovery state for unclean Studio shutdowns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SessionSnapshot:
    project_path: Path
    autosave_path: Path | None
    opened_at: str
    clean: bool


class SessionRecoveryManager:
    """Persists enough state to offer recovery after an unclean shutdown."""

    def __init__(self, path: Path):
        self.path = path

    def mark_open(self, project_path: Path, autosave_path: Path | None = None) -> None:
        payload = {
            "project_path": str(Path(project_path).expanduser()),
            "autosave_path": str(Path(autosave_path).expanduser())
            if autosave_path is not None
            else None,
            "opened_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "clean": False,
        }
        self._write(payload)

    def mark_clean(self) -> None:
        payload = self._read()
        if payload:
            payload["clean"] = True
            self._write(payload)

    def has_unclean_session(self) -> bool:
        payload = self._read()
        return bool(payload) and not bool(payload.get("clean", True))

    def recoverable_session(self) -> SessionSnapshot | None:
        payload = self._read()
        if not payload or bool(payload.get("clean", True)):
            return None
        project_path = payload.get("project_path")
        if not isinstance(project_path, str):
            return None
        autosave_path = payload.get("autosave_path")
        return SessionSnapshot(
            project_path=Path(project_path),
            autosave_path=Path(autosave_path) if isinstance(autosave_path, str) else None,
            opened_at=str(payload.get("opened_at") or ""),
            clean=False,
        )

    def _read(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def default_session_state_path() -> Path:
    return Path.home() / ".automatedub_studio" / "session.json"
