from __future__ import annotations

import json

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


def test_validate_tts_config_requires_nbwcode_provider():
    with pytest.raises(tts.VS3Error, match="TTS_PROVIDER"):
        tts.validate_tts_config(ToolConfig(tts_provider="other"))
