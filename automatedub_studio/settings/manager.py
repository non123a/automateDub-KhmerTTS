"""Qt-free settings and credential management for Studio."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Protocol

from automatedub.config import ToolConfig, load_tool_config


class CredentialStore(Protocol):
    def get(self, key: str) -> str | None:
        """Return a stored secret value."""

    def set(self, key: str, value: str) -> None:
        """Store a secret value."""

    def delete(self, key: str) -> None:
        """Delete a stored secret value."""


class JsonCredentialStore:
    """Simple credential-store implementation behind the CredentialStore boundary."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, key: str) -> str | None:
        value = self._read().get(key)
        return value if isinstance(value, str) else None

    def set(self, key: str, value: str) -> None:
        payload = self._read()
        payload[key] = value
        self._write(payload)

    def delete(self, key: str) -> None:
        payload = self._read()
        payload.pop(key, None)
        self._write(payload)

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


@dataclass(frozen=True)
class SettingsData:
    stt_provider_id: str = "whisper_cpp"
    translation_provider_id: str = "nbwcode"
    tts_provider_id: str = "cambai"
    selected_voice: str | None = None
    default_project_folder: str = ""
    first_run_completed: bool = False
    provider_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    cache_dir: str = "cache"
    log_dir: str = "logs"
    advanced: dict[str, str] = field(default_factory=dict)


class SettingsManager:
    def __init__(
        self,
        settings_path: Path | None = None,
        credential_store: CredentialStore | None = None,
    ):
        self.settings_path = settings_path or default_settings_path()
        self.credential_store = credential_store or JsonCredentialStore(
            self.settings_path.with_name("credentials.json")
        )
        self._data = self.load()

    @property
    def data(self) -> SettingsData:
        return self._data

    def load(self) -> SettingsData:
        if not self.settings_path.is_file():
            return SettingsData()
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return SettingsData()
        if not isinstance(payload, dict):
            return SettingsData()
        return SettingsData(
            stt_provider_id=str(payload.get("stt_provider_id", "whisper_cpp")),
            translation_provider_id=str(payload.get("translation_provider_id", "nbwcode")),
            tts_provider_id=str(payload.get("tts_provider_id", "cambai")),
            selected_voice=(
                str(payload["selected_voice"])
                if isinstance(payload.get("selected_voice"), str)
                else None
            ),
            default_project_folder=str(payload.get("default_project_folder", "")),
            first_run_completed=bool(payload.get("first_run_completed", False)),
            provider_settings=_string_map(payload.get("provider_settings")),
            cache_dir=str(payload.get("cache_dir", "cache")),
            log_dir=str(payload.get("log_dir", "logs")),
            advanced=_flat_string_map(payload.get("advanced")),
        )

    def save(self, data: SettingsData | None = None) -> None:
        self._data = data if data is not None else self._data
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(asdict(self._data), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def set_provider_selection(
        self,
        *,
        stt_provider_id: str,
        translation_provider_id: str,
        tts_provider_id: str,
        selected_voice: str | None = None,
    ) -> None:
        self._data = replace(
            self._data,
            stt_provider_id=stt_provider_id,
            translation_provider_id=translation_provider_id,
            tts_provider_id=tts_provider_id,
            selected_voice=selected_voice,
        )
        self.save()

    def set_default_project_folder(self, folder: Path | str) -> None:
        self._data = replace(self._data, default_project_folder=str(folder))
        self.save()

    def set_first_run_completed(self, completed: bool = True) -> None:
        self._data = replace(self._data, first_run_completed=completed)
        self.save()

    def set_provider_setting(
        self,
        provider_id: str,
        key: str,
        value: str,
        *,
        secret: bool = False,
    ) -> None:
        if secret:
            credential_key = self.credential_key(provider_id, key)
            if value:
                self.credential_store.set(credential_key, value)
            else:
                self.credential_store.delete(credential_key)
            return
        settings = {
            provider: dict(values)
            for provider, values in self._data.provider_settings.items()
        }
        settings.setdefault(provider_id, {})[key] = value
        self._data = replace(self._data, provider_settings=settings)
        self.save()

    def provider_setting(self, provider_id: str, key: str, *, secret: bool = False) -> str:
        if secret:
            return self.credential_store.get(self.credential_key(provider_id, key)) or ""
        return self._data.provider_settings.get(provider_id, {}).get(key, "")

    def tool_config(self) -> ToolConfig:
        base = load_tool_config()
        settings = self._data.provider_settings
        cambai = settings.get("cambai", {})
        nbwcode = settings.get("nbwcode", {})
        whisper = settings.get("whisper_cpp", {})
        camb_api_key = self.credential_store.get(self.credential_key("cambai", "api_key"))
        nbw_api_key = self.credential_store.get(self.credential_key("nbwcode", "api_key"))
        return replace(
            base,
            stt_provider=self._data.stt_provider_id,
            translation_provider=self._data.translation_provider_id,
            tts_provider=self._data.tts_provider_id,
            whisper_model_path=Path(whisper.get("model_path", str(base.whisper_model_path))),
            nbw_automatedub_api_key=nbw_api_key or base.nbw_automatedub_api_key,
            localization_model=nbwcode.get("model", base.localization_model),
            tts_model=cambai.get("model") or nbwcode.get("model") or base.tts_model,
            camb_api_key=camb_api_key or base.camb_api_key,
            camb_language=cambai.get("language", base.camb_language),
            camb_voice_id=self._data.selected_voice
            or cambai.get("voice_id")
            or base.camb_voice_id,
        )

    def cache_usage_bytes(self) -> int:
        return _directory_size(Path(self._data.cache_dir).expanduser())

    def clear_cache(self) -> None:
        cache_path = Path(self._data.cache_dir).expanduser()
        if cache_path.is_dir():
            shutil.rmtree(cache_path)
        cache_path.mkdir(parents=True, exist_ok=True)

    def recent_log_errors(self, limit: int = 20) -> list[str]:
        log_path = Path(self._data.log_dir).expanduser()
        if not log_path.is_dir():
            return []
        lines: list[str] = []
        for path in sorted(log_path.glob("*.log"), key=lambda item: item.stat().st_mtime):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "error" in line.lower() or "failed" in line.lower():
                    lines.append(line)
        return lines[-limit:]

    @staticmethod
    def credential_key(provider_id: str, key: str) -> str:
        return f"provider.{provider_id}.{key}"


def default_settings_path() -> Path:
    return Path.home() / ".automatedub_studio" / "settings.json"


def _directory_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _string_map(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, inner in value.items():
        if isinstance(inner, dict):
            result[str(key)] = _flat_string_map(inner)
    return result


def _flat_string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(inner) for key, inner in value.items()}
