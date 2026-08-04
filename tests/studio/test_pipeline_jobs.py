from __future__ import annotations

import io
import json
import wave

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice.tts import GeneratedSpeech
from automatedub_studio.pipeline.jobs import (
    EXPECTED_PIPELINE_FLOW,
    STAGE_TTS_GENERATION,
    BulkKhmerTTSGenerationJob,
    CopySourceVideoJob,
    CreateProjectJob,
    PipelineContext,
    SpeechDetectionJob,
    TimelineGenerationJob,
    default_pipeline_jobs,
)
from automatedub_studio.project.loader import load_project
from automatedub_studio.project.manager import NewProjectRequest, ProjectManager
from automatedub_studio.project.timeline_edits import load_timeline_edits
from automatedub_studio.providers.base.interfaces import SynthesizedSpeech, VoiceInfo
from automatedub_studio.providers.manager import ProviderManager
from automatedub_studio.providers.registry import ProviderDescriptor, ProviderRegistry


def _wav_bytes(seconds: float = 0.05, frame_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(frame_rate)
        wav.writeframes(b"\x00\x00" * int(seconds * frame_rate))
    return buffer.getvalue()


class FakePipelineTTSProvider:
    id = "fake_tts"
    name = "Fake TTS"
    calls: list[tuple[str, ToolConfig]] = []
    fail_texts: set[str] = set()

    def __init__(self, tool_config: ToolConfig):
        self.tool_config = tool_config

    def validate(self) -> None:
        return None

    def list_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="voice-42", name="Voice 42")]

    def synthesize(self, text: str) -> SynthesizedSpeech:
        raise AssertionError("bulk pipeline should reuse regeneration_service provider.generate")

    def generate(self, text: str) -> GeneratedSpeech:
        self.__class__.calls.append((text, self.tool_config))
        if text in self.__class__.fail_texts:
            raise RuntimeError(f"failed {text}")
        return GeneratedSpeech(audio=_wav_bytes())


def _provider_manager() -> ProviderManager:
    registry = ProviderRegistry()
    registry.register_tts(
        ProviderDescriptor("fake_tts", "Fake TTS", "tts", FakePipelineTTSProvider)
    )
    return ProviderManager(
        ToolConfig(
            tts_provider="cambai",
            camb_voice_id="voice-42",
            camb_language="km-kh",
            tts_speed=1.25,
            tts_model="tts-model",
        ),
        registry=registry,
    )


def _context(tmp_path) -> PipelineContext:
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    return PipelineContext(
        request=NewProjectRequest(
            project_name="Khmer Cut",
            project_location=tmp_path,
            video_file=video_file,
            source_language="Chinese",
            target_language="Khmer",
        ),
        project_manager=ProjectManager(),
        tool_config=ToolConfig(),
        provider_manager=_provider_manager(),
        tts_provider_factory=lambda _config: FakePipelineTTSProvider(_config),
    )


def _write_translation(context: PipelineContext) -> None:
    translation_path = context.pipeline_path / "translation.json"
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
                        "source_text": "你好",
                        "target_text": "សួស្តី",
                    },
                    {
                        "id": 1,
                        "start": 1.0,
                        "end": 2.0,
                        "source_language": "zh",
                        "target_language": "km",
                        "source_text": "再见",
                        "target_text": "លាហើយ",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["translation"] = translation_path


def test_create_and_copy_jobs_populate_project_structure(tmp_path):
    context = _context(tmp_path)
    progress_events = []

    CreateProjectJob().run(context, lambda value, message="": progress_events.append(value))
    CopySourceVideoJob().run(context, lambda value, message="": progress_events.append(value))

    assert context.created_project is not None
    assert (context.project_path / "source" / "movie.mp4").read_bytes() == b"video"
    metadata = json.loads((context.project_path / "project.json").read_text(encoding="utf-8"))
    assert metadata["source_video"] == "source/movie.mp4"
    assert metadata["editor_video"] == "source/movie.mp4"
    assert progress_events[-1] == 100


def test_speech_detection_job_writes_timing_artifact(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    transcript_path = context.pipeline_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(
            {
                "segments": [
                    {"id": 1, "start": 0.5, "end": 1.25, "text": "你好"},
                    {"id": 2, "start": 2.0, "end": 3.0, "text": "再见"},
                ]
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["transcript"] = transcript_path

    SpeechDetectionJob().run(context, lambda _value, message="": None)

    output_path = context.pipeline_path / "speech_segments.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["segments"] == [
        {"id": 1, "start": 0.5, "end": 1.25},
        {"id": 2, "start": 2.0, "end": 3.0},
    ]


def test_timeline_generation_populates_timeline_directory_and_loader_uses_pipeline_paths(
    tmp_path,
):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    translation_path = context.pipeline_path / "translation.json"
    translation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "segments": [
                    {
                        "id": 1,
                        "start": 0.5,
                        "end": 1.25,
                        "source_language": "zh",
                        "target_language": "km",
                        "source_text": "你好",
                        "target_text": "សួស្តី",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["audio"] = audio_path
    context.artifacts["translation"] = translation_path
    context.skip_tts = True

    TimelineGenerationJob().run(context, lambda _value, message="": None)

    timeline_path = context.project_path / "timeline" / "timeline.edited.json"
    assert timeline_path.is_file()
    timeline = load_timeline_edits(context.project_path)
    assert timeline is not None
    assert timeline.clip_by_id("original:1") is not None
    project = load_project(context.project_path)
    assert project.audio_path == audio_path
    assert project.translation_path == translation_path


def test_bulk_tts_stage_is_scheduled_after_translation():
    stages = [job.stage.id for job in default_pipeline_jobs()]

    assert stages == EXPECTED_PIPELINE_FLOW
    assert stages[stages.index(STAGE_TTS_GENERATION) - 1] == "translation"
    assert stages[stages.index(STAGE_TTS_GENERATION) + 1] == "timeline_generation"


def test_bulk_tts_generation_reuses_regeneration_service_and_writes_wavs(
    monkeypatch,
    tmp_path,
):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    _write_translation(context)
    FakePipelineTTSProvider.calls = []
    service_calls = []

    from automatedub_studio.backend import regeneration_service
    from automatedub_studio.pipeline import jobs as jobs_module

    original = regeneration_service.regenerate_segment

    def tracked_regenerate_segment(*args, **kwargs):
        service_calls.append(args[0].id)
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs_module, "regenerate_segment", tracked_regenerate_segment)
    progress_messages: list[str] = []

    BulkKhmerTTSGenerationJob().run(
        context,
        lambda _value, message="": progress_messages.append(message),
    )

    assert service_calls == [0, 1]
    assert [text for text, _config in FakePipelineTTSProvider.calls] == ["សួស្តី", "លាហើយ"]
    assert {config.camb_voice_id for _text, config in FakePipelineTTSProvider.calls} == {
        "voice-42"
    }
    assert {config.tts_speed for _text, config in FakePipelineTTSProvider.calls} == {1.25}
    assert (context.project_path / "tts" / "0000.wav").is_file()
    assert (context.project_path / "tts" / "0001.wav").is_file()
    assert any("Segment 0" in message for message in progress_messages)
    debug_dir = context.pipeline_path / "debug"
    provider_trace = json.loads(
        (debug_dir / "tts_provider_trace.json").read_text(encoding="utf-8")
    )
    provider_config = json.loads(
        (debug_dir / "tts_provider.json").read_text(encoding="utf-8")
    )
    requests = json.loads(
        (debug_dir / "tts_requests.json").read_text(encoding="utf-8")
    )
    tts_results = json.loads(
        (debug_dir / "tts_results.json").read_text(encoding="utf-8")
    )
    outputs = json.loads((debug_dir / "tts_outputs.json").read_text(encoding="utf-8"))
    generation_trace = json.loads(
        (debug_dir / "tts_generation_trace.json").read_text(encoding="utf-8")
    )
    results = json.loads(
        (debug_dir / "tts_generation_results.json").read_text(encoding="utf-8")
    )
    assert provider_trace["provider_id"] == "fake_tts"
    assert provider_trace["provider_class"] == "FakePipelineTTSProvider"
    assert provider_trace["voice_id"] == "voice-42"
    assert provider_config["selected_provider_id"] == "cambai"
    assert provider_config["speech_model"] == "tts-model"
    assert provider_config["language"] == "km-kh"
    assert provider_config["speed"] == 1.25
    assert provider_config["sync_offset"] == 150
    assert len(requests["requests"]) == 2
    assert requests["requests"][0]["text"] == "សួស្តី"
    assert requests["requests"][0]["output_path"].endswith("/tts/0000.wav")
    assert requests["requests"][0]["request_payload"]["speech_model"] == "tts-model"
    assert len(tts_results["segments"]) == 2
    assert tts_results["summary"]["succeeded"] == 2
    assert outputs["synthesis_requests_queued"] == 2
    assert [segment["success"] for segment in outputs["segments"]] == [True, True]
    assert generation_trace["entered"] is True
    assert generation_trace["skipped"] is False
    assert generation_trace["translation_segments_loaded"] == 2
    assert generation_trace["completed"] == 2
    assert generation_trace["failed"] == 0
    assert len(generation_trace["output_files_written"]) == 2
    assert results["summary"]["segments_attempted"] == 2
    assert results["summary"]["succeeded"] == 2
    assert results["segments"][0]["khmer_text"] == "សួស្តី"
    assert results["segments"][0]["provider"] == "cambai"
    assert results["segments"][0]["voice_id"] == "voice-42"
    assert results["segments"][0]["speaking_rate"] == 1.25
    assert results["segments"][0]["request_started"] is True
    assert results["segments"][0]["file_exists"] is True
    assert results["segments"][0]["file_size"] > 0
    assert results["segments"][0]["audio_duration"] is not None
    assert results["segments"][0]["validation_result"] == "passed"
    assert (
        results["comparison_with_inspector_regenerate"]["provider_method"]
        == "provider.generate(text)"
    )


def test_bulk_tts_generation_continues_after_failed_segment(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    _write_translation(context)
    FakePipelineTTSProvider.calls = []
    FakePipelineTTSProvider.fail_texts = {"សួស្តី"}

    try:
        BulkKhmerTTSGenerationJob().run(context, lambda _value, message="": None)
    finally:
        FakePipelineTTSProvider.fail_texts = set()

    assert [text for text, _config in FakePipelineTTSProvider.calls] == ["សួស្តី", "លាហើយ"]
    assert not (context.project_path / "tts" / "0000.wav").exists()
    assert (context.project_path / "tts" / "0001.wav").is_file()
    outputs = json.loads(
        (context.pipeline_path / "debug" / "tts_outputs.json").read_text(encoding="utf-8")
    )
    results = json.loads(
        (context.pipeline_path / "debug" / "tts_generation_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert outputs["failed_segment_ids"] == [0]
    assert [segment["success"] for segment in outputs["segments"]] == [False, True]
    assert results["summary"]["succeeded"] == 1
    assert results["summary"]["failed"] == 1
    assert results["summary"]["common_failure_reason"] == "failed សួស្តី"
    assert results["segments"][0]["response_body"] is None
    assert results["segments"][0]["validation_result"] == "not_run"
    assert results["segments"][0]["file_exists"] is False


def test_bulk_tts_generation_fails_stage_when_every_segment_fails(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    _write_translation(context)
    FakePipelineTTSProvider.calls = []
    FakePipelineTTSProvider.fail_texts = {"សួស្តី", "លាហើយ"}

    try:
        with pytest.raises(RuntimeError, match="All 2 Khmer speech generation requests failed"):
            BulkKhmerTTSGenerationJob().run(context, lambda _value, message="": None)
    finally:
        FakePipelineTTSProvider.fail_texts = set()

    assert context.tts_generation_completed == 0
    assert context.tts_failed_segment_ids == [0, 1]
    results = json.loads(
        (context.pipeline_path / "debug" / "tts_generation_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert results["summary"]["succeeded"] == 0
    assert results["summary"]["failed"] == 2
    assert results["summary"]["common_failure_reason"] in {
        "failed សួស្តី",
        "failed លាហើយ",
    }


def test_timeline_generation_imports_generated_bulk_tts_wavs(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path
    _write_translation(context)
    FakePipelineTTSProvider.calls = []
    BulkKhmerTTSGenerationJob().run(context, lambda _value, message="": None)

    TimelineGenerationJob().run(context, lambda _value, message="": None)

    timeline = load_timeline_edits(context.project_path)
    assert timeline is not None
    khmer_clip = timeline.clip_by_id("khmer:0")
    assert khmer_clip is not None
    assert khmer_clip.source_path == context.project_path / "tts" / "0000.wav"


def test_timeline_generation_maps_original_speech_to_pipeline_audio_offset(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path
    translation_path = context.pipeline_path / "translation.json"
    translation_path.write_text(
        json.dumps(
            {
                "version": 1,
                "segments": [
                    {
                        "id": 23,
                        "start": 52.32,
                        "end": 53.10,
                        "source_language": "zh",
                        "target_language": "km",
                        "source_text": "source 23",
                        "target_text": "target 23",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    context.artifacts["translation"] = translation_path
    context.skip_tts = True

    TimelineGenerationJob().run(context, lambda _value, message="": None)

    timeline = load_timeline_edits(context.project_path)
    assert timeline is not None
    original_clip = timeline.clip_by_id("original:23")
    assert original_clip is not None
    assert original_clip.source_path == context.project_path / "pipeline" / "audio.wav"
    assert original_clip.start_time == 52.32
    assert original_clip.end_time == 53.10
    assert original_clip.source_offset == 52.32
    assert original_clip.duration == pytest.approx(0.78)


def test_timeline_generation_is_blocked_without_completed_tts(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path
    _write_translation(context)

    with pytest.raises(RuntimeError, match="TTS generation did not complete"):
        TimelineGenerationJob().run(context, lambda _value, message="": None)


def test_timeline_generation_is_blocked_when_expected_tts_wav_is_missing(tmp_path):
    context = _context(tmp_path)
    CreateProjectJob().run(context, lambda _value, message="": None)
    audio_path = context.pipeline_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    context.artifacts["audio"] = audio_path
    _write_translation(context)
    FakePipelineTTSProvider.calls = []
    BulkKhmerTTSGenerationJob().run(context, lambda _value, message="": None)
    (context.project_path / "tts" / "0001.wav").unlink()

    with pytest.raises(RuntimeError, match="TTS output validation failed"):
        TimelineGenerationJob().run(context, lambda _value, message="": None)
