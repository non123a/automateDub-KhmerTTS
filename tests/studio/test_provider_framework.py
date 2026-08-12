from __future__ import annotations

import json
from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice import localization
from automatedub_studio.pipeline.jobs import (
    CreateProjectJob,
    PipelineContext,
    TranscriptionJob,
    TranslationJob,
)
from automatedub_studio.project.manager import NewProjectRequest, ProjectManager
from automatedub_studio.providers.base.interfaces import SynthesizedSpeech, VoiceInfo
from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.providers.registry import ProviderDescriptor, ProviderRegistry
from automatedub_studio.providers.translation.nbwcode import NBWCodeTranslationProvider


class FakeSTTProvider:
    id = "fake_stt"
    name = "Fake STT"

    def __init__(self, _tool_config: ToolConfig):
        self.validated = False

    def validate(self) -> None:
        self.validated = True

    def prepare(self, _progress) -> None:
        return None

    def transcribe(self, audio_path: Path, transcript_path: Path) -> object:
        assert self.validated
        transcript_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_audio": audio_path.name,
                    "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "你好"}],
                }
            ),
            encoding="utf-8",
        )
        return {"ok": True}


class FakeTranslationProvider:
    id = "fake_translation"
    name = "Fake Translation"

    def __init__(self, _tool_config: ToolConfig):
        self.validated = False

    def validate(self) -> None:
        self.validated = True

    def translate(
        self,
        transcript_path: Path,
        translation_path: Path,
        prompt_path: Path,
    ) -> None:
        assert self.validated
        assert transcript_path.is_file()
        source_text = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"][0].get(
            "edited_text"
        ) or json.loads(transcript_path.read_text(encoding="utf-8"))["segments"][0]["text"]
        prompt_path.write_text("prompt", encoding="utf-8")
        translation_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "segments": [
                        {
                            "id": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "source_language": "zh",
                            "target_language": "km",
                            "source_text": source_text,
                            "target_text": "សួស្តី",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )


class FakeTTSProvider:
    id = "fake_tts"
    name = "Fake TTS"

    def __init__(self, _tool_config: ToolConfig):
        pass

    def validate(self) -> None:
        return None

    def list_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="voice-1", name="Voice 1")]

    def synthesize(self, text: str) -> SynthesizedSpeech:
        return SynthesizedSpeech(audio=f"wav:{text}".encode())


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_stt(
        ProviderDescriptor("fake_stt", "Fake STT", "stt", FakeSTTProvider)
    )
    registry.register_translation(
        ProviderDescriptor(
            "fake_translation",
            "Fake Translation",
            "translation",
            FakeTranslationProvider,
        )
    )
    registry.register_tts(
        ProviderDescriptor("fake_tts", "Fake TTS", "tts", FakeTTSProvider)
    )
    return registry


def _request(tmp_path) -> NewProjectRequest:
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    return NewProjectRequest(
        project_name="Khmer Cut",
        project_location=tmp_path,
        video_file=video_file,
        source_language="Chinese",
        target_language="Khmer",
    )


def test_default_provider_registry_discovers_registered_adapters():
    manager = ProviderManager(ToolConfig())

    assert any(provider.id == "whisper_cpp" for provider in manager.available_stt_providers())
    assert any(
        provider.id == "nbwcode"
        for provider in manager.available_translation_providers()
    )
    assert any(provider.id == "cambai" for provider in manager.available_tts_providers())


def test_provider_manager_resolves_configured_provider_ids():
    manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )

    assert manager.stt_provider().id == "fake_stt"
    assert manager.translation_provider().id == "fake_translation"
    assert manager.tts_provider().list_voices()[0].id == "voice-1"
    assert manager.project_metadata() == {
        "stt_provider_id": "fake_stt",
        "translation_provider_id": "fake_translation",
        "tts_provider_id": "fake_tts",
        "selected_voice": "170542",
    }


def test_pipeline_transcription_and_translation_use_provider_manager(tmp_path):
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    context = PipelineContext(
        request=_request(tmp_path),
        project_manager=ProjectManager(),
        tool_config=provider_manager.tool_config,
        provider_manager=provider_manager,
    )
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path

    TranscriptionJob().run(context, lambda _value, message="": None)
    TranslationJob().run(context, lambda _value, message="": None)

    assert (context.pipeline_path / "transcript.json").is_file()
    assert (context.pipeline_path / "translation.json").is_file()
    metadata = json.loads((context.project_path / "project.json").read_text(encoding="utf-8"))
    assert metadata["providers"] == provider_manager.project_metadata()
    trace = json.loads(
        (context.pipeline_path / "debug" / "translation_provider_trace.json").read_text(
            encoding="utf-8"
        )
    )
    assert trace["selected_provider_id"] == "fake_translation"
    assert trace["provider_id"] == "fake_translation"
    assert trace["provider_class"] == "FakeTranslationProvider"
    assert trace["provider_module"] == __name__


def test_saved_edited_transcript_is_not_regenerated_without_explicit_action(tmp_path):
    provider_manager = ProviderManager(
        ToolConfig(
            stt_provider="fake_stt",
            translation_provider="fake_translation",
            tts_provider="fake_tts",
        ),
        registry=_registry(),
    )
    context = PipelineContext(
        request=_request(tmp_path),
        project_manager=ProjectManager(),
        tool_config=provider_manager.tool_config,
        provider_manager=provider_manager,
    )
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path
    transcript_path = context.pipeline_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(
            {
                "version": 1,
                "language": "zh",
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 1.0,
                        "text": "recognized",
                        "edited_text": "corrected",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    TranscriptionJob().run(context, lambda _value, message="": None)
    TranslationJob().run(context, lambda _value, message="": None)

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert payload["segments"][0]["edited_text"] == "corrected"
    translation = json.loads(
        (context.pipeline_path / "translation.json").read_text(encoding="utf-8")
    )
    assert translation["segments"][0]["source_text"] == "corrected"


def test_nbwcode_translation_provider_validate_uses_authenticated_request_path(
    monkeypatch,
):
    calls: list[ToolConfig] = []

    def fake_validate(tool_config: ToolConfig) -> None:
        calls.append(tool_config)

    monkeypatch.setattr(
        "automatedub_studio.providers.translation.nbwcode."
        "validate_openai_compatible_connection",
        fake_validate,
    )
    config = ToolConfig(
        nbw_base_url="https://gateway.example/v1",
        nbw_automatedub_api_key="key",
        localization_model="test-model",
    )
    provider = NBWCodeTranslationProvider(config)

    provider.validate()

    assert calls == [config]


def test_nbwcode_translation_provider_does_not_instantiate_legacy_localizer(
    monkeypatch,
    tmp_path,
):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(
            {
                "language": "zh",
                "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "你好"}],
            }
        ),
        encoding="utf-8",
    )

    def fail_legacy_init(*_args, **_kwargs):
        raise AssertionError("legacy localizer should not be instantiated")

    def fake_call(**_kwargs):
        return {"output_text": '{"segments":[{"id":0,"target_text":"សួស្តី","notes":null}]}'}

    monkeypatch.setattr(localization.NBWCodeDialogueLocalizer, "__init__", fail_legacy_init)
    monkeypatch.setattr(localization, "call_openai_compatible_responses_api", fake_call)
    monkeypatch.setattr(
        "automatedub_studio.providers.translation.nbwcode."
        "validate_openai_compatible_connection",
        lambda _tool_config: None,
    )
    provider = NBWCodeTranslationProvider(
        ToolConfig(
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="key",
            localization_model="test-model",
        )
    )

    provider.validate()
    provider.translate(
        transcript_path=transcript_path,
        translation_path=tmp_path / "translation.json",
        prompt_path=tmp_path / "translation_prompt.json",
    )

    assert (tmp_path / "translation.json").is_file()
