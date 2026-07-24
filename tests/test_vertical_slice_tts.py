from __future__ import annotations

import json
import sys
import types

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice import tts


def minimal_wav_bytes() -> bytes:
    return b"RIFF\x24\x00\x00\x00WAVEfmt "


def sample_translation_payload() -> dict[str, object]:
    return {
        "version": 1,
        "source_transcript": "transcript.json",
        "prompt_artifact": "translation_prompt.json",
        "engine": {"provider": "openai-compatible", "model": "test-model"},
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 1.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "你好",
                "target_text": "សួស្តី។",
                "notes": None,
            },
            {
                "id": 12,
                "start": 1.0,
                "end": 2.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "拜拜",
                "target_text": "លាហើយ។",
                "notes": None,
            },
        ],
    }


def test_load_translation_segments_reads_ids_and_target_text(tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(json.dumps(sample_translation_payload()), encoding="utf-8")

    segments = tts.load_translation_segments(translation_path)

    assert segments == [
        tts.TtsSegment(id=0, target_text="សួស្តី។"),
        tts.TtsSegment(id=12, target_text="លាហើយ។"),
    ]


def test_tts_segment_output_path_zero_pads_ids(tmp_path):
    assert tts.tts_segment_output_path(tmp_path / "tts", 7) == tmp_path / "tts" / "0007.wav"


def test_build_speech_url_and_payload():
    assert tts.build_speech_url("https://gateway.example/v1") == (
        "https://gateway.example/v1/audio/speech"
    )
    payload = tts.build_speech_payload(model="tts-model", text="សួស្តី។")
    assert payload["model"] == "tts-model"
    assert payload["input"] == "សួស្តី។"
    assert payload["response_format"] == "wav"


def test_validate_wav_audio_rejects_non_wav():
    with pytest.raises(tts.VS3Error, match="did not return WAV"):
        tts.validate_wav_audio(b"not audio", segment_id=0)


def test_nbwcode_tts_generates_wav_per_segment(monkeypatch, tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(
        json.dumps(sample_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    calls: list[tuple[str, str, str, str]] = []

    def fake_synthesize(base_url: str, api_key: str, model: str, text: str) -> bytes:
        calls.append((base_url, api_key, model, text))
        return minimal_wav_bytes()

    monkeypatch.setattr(tts, "synthesize_nbwcode_speech", fake_synthesize)
    synthesizer = tts.NBWCodeTextToSpeechSynthesizer(
        ToolConfig(
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="test-key",
            tts_provider="nbwcode",
            tts_model="test-tts-model",
        )
    )

    result = synthesizer.synthesize_segments(translation_path, tmp_path / "tts")

    assert calls == [
        ("https://gateway.example/v1", "test-key", "test-tts-model", "សួស្តី។"),
        ("https://gateway.example/v1", "test-key", "test-tts-model", "លាហើយ។"),
    ]
    assert result.failures == []
    assert [path.name for path in result.generated] == ["0000.wav", "0012.wav"]
    assert (tmp_path / "tts" / "0000.wav").read_bytes() == minimal_wav_bytes()
    assert not (tmp_path / "tts" / "errors.json").exists()


def test_nbwcode_tts_continues_after_segment_failure(monkeypatch, tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(
        json.dumps(sample_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    def fake_synthesize(base_url: str, api_key: str, model: str, text: str) -> bytes:
        if text == "សួស្តី។":
            raise tts.VS3Error("provider failed")
        return minimal_wav_bytes()

    monkeypatch.setattr(tts, "synthesize_nbwcode_speech", fake_synthesize)
    synthesizer = tts.NBWCodeTextToSpeechSynthesizer(
        ToolConfig(
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="test-key",
            tts_provider="nbwcode",
            tts_model="test-tts-model",
        )
    )

    result = synthesizer.synthesize_segments(translation_path, tmp_path / "tts")

    assert [path.name for path in result.generated] == ["0012.wav"]
    assert len(result.failures) == 1
    assert result.failures[0].id == 0
    assert not (tmp_path / "tts" / "0000.wav").exists()
    assert (tmp_path / "tts" / "0012.wav").exists()
    error_log = json.loads((tmp_path / "tts" / "errors.json").read_text(encoding="utf-8"))
    assert error_log["failures"][0]["id"] == 0
    assert error_log["failures"][0]["error"] == "provider failed"


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def describe(self) -> tts.TtsProviderInfo:
        return tts.TtsProviderInfo(
            provider="fake",
            model="fake-model",
            voice_id="voice-1",
            language="km-kh",
        )

    def generate(self, text: str) -> tts.GeneratedSpeech:
        self.calls.append(text)
        return tts.GeneratedSpeech(
            audio=minimal_wav_bytes(),
            metadata={"provider_request_id": f"request-{len(self.calls)}"},
        )


def test_provider_synthesizer_writes_usage(tmp_path):
    output_dir = tmp_path / "output"
    translation_path = output_dir / "translation.json"
    translation_path.parent.mkdir()
    translation_path.write_text(
        json.dumps(sample_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    provider = FakeProvider()
    synthesizer = tts.ProviderTextToSpeechSynthesizer(provider, output_dir=output_dir)

    result = synthesizer.synthesize_segments(translation_path, output_dir / "tts")

    assert provider.calls == ["សួស្តី។", "លាហើយ។"]
    assert result.usage_path == output_dir / "usage" / "tts_usage.json"
    usage = json.loads(result.usage_path.read_text(encoding="utf-8"))
    assert usage["provider"] == "fake"
    assert usage["model"] == "fake-model"
    assert usage["voice_id"] == "voice-1"
    assert usage["segments_processed"] == 2
    assert usage["characters_processed"] == len("សួស្តី។") + len("លាហើយ។")
    assert usage["provider_metadata"]["language"] == "km-kh"
    assert usage["provider_metadata"]["0"]["provider_request_id"] == "request-1"


def test_cambai_provider_uses_sdk_client(monkeypatch):
    class FakeStreamTtsOutputConfiguration:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_types = types.ModuleType("camb.types")
    fake_types.StreamTtsOutputConfiguration = FakeStreamTtsOutputConfiguration
    monkeypatch.setitem(sys.modules, "camb.types", fake_types)

    class FakeTextToSpeech:
        def __init__(self) -> None:
            self.calls = []

        def tts(self, **kwargs):
            self.calls.append(kwargs)
            return [minimal_wav_bytes()]

    class FakeClient:
        def __init__(self) -> None:
            self.text_to_speech = FakeTextToSpeech()

    client = FakeClient()
    provider = tts.CambAIProvider(
        ToolConfig(
            tts_provider="cambai",
            tts_model="test-tts-model",
            camb_api_key="camb-key",
            camb_language="km-kh",
            camb_voice_id="123",
        ),
        client=client,
    )

    speech = provider.generate("សួស្តី។")

    assert speech.audio == minimal_wav_bytes()
    assert client.text_to_speech.calls == [
        {
            "text": "សួស្តី។",
            "voice_id": 123,
            "language": "km-kh",
            "speech_model": "test-tts-model",
            "output_configuration": client.text_to_speech.calls[0]["output_configuration"],
        }
    ]
    assert client.text_to_speech.calls[0]["output_configuration"].kwargs == {"format": "wav"}


def test_list_cambai_voices_normalizes_sdk_response():
    class FakeVoiceCloning:
        def list_voices(self):
            return {
                "data": [
                    {
                        "id": 123,
                        "name": "Khmer Female",
                        "gender": "female",
                        "language": "km-kh",
                    }
                ]
            }

    class FakeClient:
        def __init__(self) -> None:
            self.voice_cloning = FakeVoiceCloning()

    voices = tts.list_cambai_voices(
        ToolConfig(camb_api_key="camb-key"),
        client=FakeClient(),
    )

    assert voices == [
        tts.TtsVoice(
            id="123",
            name="Khmer Female",
            gender="female",
            language="km-kh",
            metadata={
                "id": 123,
                "name": "Khmer Female",
                "gender": "female",
                "language": "km-kh",
            },
        )
    ]


def test_validate_tts_config_rejects_unsupported_provider():
    with pytest.raises(tts.VS3Error, match="unsupported TTS provider"):
        tts.validate_tts_config(ToolConfig(tts_provider="other"))


def test_select_sample_segments_covers_requested_minutes_from_start_segment(tmp_path):
    translation_path = tmp_path / "translation.json"
    payload = sample_translation_payload()
    payload["segments"] = [
        {
            "id": 0,
            "start": 0.0,
            "end": 30.0,
            "target_text": "មួយ",
        },
        {
            "id": 1,
            "start": 30.0,
            "end": 70.0,
            "target_text": "ពីរ",
        },
        {
            "id": 2,
            "start": 70.0,
            "end": 130.0,
            "target_text": "បី",
        },
        {
            "id": 3,
            "start": 130.0,
            "end": 180.0,
            "target_text": "បួន",
        },
    ]
    translation_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    selected = tts.select_sample_segments(translation_path, start_segment=1, minutes=1)

    assert selected == [
        tts.SampleSegment(id=1, start=30.0, end=70.0, target_text="ពីរ"),
        tts.SampleSegment(id=2, start=70.0, end=130.0, target_text="បី"),
    ]


def test_select_sample_segments_rejects_missing_start_segment(tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(
        json.dumps(sample_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(tts.VS3Error, match="start segment does not exist"):
        tts.select_sample_segments(translation_path, start_segment=99, minutes=2)


def test_select_sample_segments_requires_timestamps(tmp_path):
    translation_path = tmp_path / "translation.json"
    payload = sample_translation_payload()
    del payload["segments"][0]["start"]
    translation_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(tts.VS3Error, match="numeric start and end"):
        tts.select_sample_segments(translation_path, start_segment=0, minutes=2)
