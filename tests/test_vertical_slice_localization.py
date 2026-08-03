from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice import localization


class _CapturePostHandler(BaseHTTPRequestHandler):
    captured: dict[str, object] = {}

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode(
            "utf-8"
        )
        self.__class__.captured = {
            "request_version": self.request_version,
            "command": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": body,
        }
        response_body = b'{"output_text":"{}"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, *_args) -> None:
        return None


def sample_transcript_payload() -> dict[str, object]:
    return {
        "version": 1,
        "language": "zh",
        "source_audio": "audio.wav",
        "engine": {"provider": "local", "model": "whisper.cpp:ggml-small.bin"},
        "text": "你好",
        "segments": [{"id": 0, "start": 0.0, "end": 1.5, "text": "你好"}],
    }


def transcript_payload_with_segment_count(segment_count: int) -> dict[str, object]:
    payload = sample_transcript_payload()
    payload["segments"] = [
        {
            "id": index,
            "start": float(index),
            "end": float(index + 1),
            "text": f"你好{index}",
        }
        for index in range(segment_count)
    ]
    payload["text"] = " ".join(segment["text"] for segment in payload["segments"])
    return payload


def test_load_transcript_preserves_segment_fields(tmp_path):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(sample_transcript_payload()), encoding="utf-8")

    segments = localization.load_transcript(transcript_path)

    assert segments == [
        localization.TranscriptSegmentForLocalization(id=0, start=0.0, end=1.5, text="你好")
    ]


def test_load_transcript_rejects_non_chinese_language(tmp_path):
    payload = sample_transcript_payload()
    payload["language"] = "en"
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(localization.VS2Error, match="transcript language must be zh"):
        localization.load_transcript(transcript_path)


def test_build_localization_prompt_contains_dubbing_instruction():
    prompt = localization.build_localization_prompt(
        [localization.TranscriptSegmentForLocalization(id=0, start=0.0, end=1.5, text="你好")]
    )

    assert "official Khmer dubbing translator" in str(prompt["system"])
    assert "Never merge segments" in str(prompt["system"])
    assert '"source_text": "你好"' in str(prompt["user"])


def test_normalize_openai_compatible_response_preserves_source_data():
    transcript = [
        localization.TranscriptSegmentForLocalization(id=0, start=0.0, end=1.5, text="你好")
    ]
    response = {
        "output_text": json.dumps(
            {"segments": [{"id": 0, "target_text": "សួស្តី។", "notes": None}]},
            ensure_ascii=False,
        )
    }

    artifact = localization.normalize_openai_compatible_localization_response(
        response_payload=response,
        transcript=transcript,
        source_transcript="transcript.json",
        prompt_artifact="translation_prompt.json",
        model="test-model",
    )

    segment = artifact.segments[0]
    assert segment.id == 0
    assert segment.start == 0.0
    assert segment.end == 1.5
    assert segment.source_language == "zh"
    assert segment.target_language == "km"
    assert segment.source_text == "你好"
    assert segment.target_text == "សួស្តី។"
    assert segment.notes is None


def test_normalize_openai_compatible_response_rejects_segment_count_change():
    response = {"output_text": json.dumps({"segments": []})}

    with pytest.raises(localization.VS2Error, match="changed the segment count"):
        localization.normalize_openai_compatible_localization_response(
            response_payload=response,
            transcript=[
                localization.TranscriptSegmentForLocalization(
                    id=0,
                    start=0.0,
                    end=1.5,
                    text="你好",
                )
            ],
            source_transcript="transcript.json",
            prompt_artifact="translation_prompt.json",
            model="test-model",
        )


def test_parse_localization_json_rejects_markdown():
    with pytest.raises(localization.VS2Error, match="included Markdown"):
        localization.parse_localization_json("```json\n{}\n```")


def test_write_translation_artifact_writes_stable_schema(tmp_path):
    artifact = localization.TranslationArtifact(
        version=1,
        source_transcript="transcript.json",
        prompt_artifact="translation_prompt.json",
        engine={"provider": "openai-compatible", "model": "test-model"},
        segments=[
            localization.TranslationSegment(
                id=0,
                start=0.0,
                end=1.5,
                source_language="zh",
                target_language="km",
                source_text="你好",
                target_text="សួស្តី។",
            )
        ],
    )
    path = tmp_path / "translation.json"

    localization.write_translation_artifact(path, artifact)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["segments"][0] == {
        "id": 0,
        "start": 0.0,
        "end": 1.5,
        "source_language": "zh",
        "target_language": "km",
        "source_text": "你好",
        "target_text": "សួស្តី។",
        "notes": None,
    }


def test_openai_compatible_dialogue_localizer_writes_prompt_and_translation(monkeypatch, tmp_path):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(sample_transcript_payload()), encoding="utf-8")

    def fake_call(
        base_url: str,
        api_key: str,
        model: str,
        prompt: dict[str, object],
        debug_dir=None,
        segment_count=None,
        batch_index=None,
        batch_count=None,
        **_diagnostics,
    ) -> dict[str, object]:
        assert base_url == "https://gateway.example/v1"
        assert api_key == "test-key"
        assert model == "test-model"
        assert debug_dir == tmp_path / "debug"
        assert segment_count == 1
        assert batch_index == 1
        assert batch_count == 1
        assert "official Khmer dubbing translator" in str(prompt["system"])
        return {
            "output_text": json.dumps(
                {"segments": [{"id": 0, "target_text": "សួស្តី។", "notes": None}]},
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(localization, "call_openai_compatible_responses_api", fake_call)
    localizer = localization.NBWCodeDialogueLocalizer(
        ToolConfig(
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="test-key",
            localization_model="test-model",
        )
    )
    translation_path = tmp_path / "translation.json"
    prompt_path = tmp_path / "translation_prompt.json"

    localizer.localize(transcript_path, translation_path, prompt_path)

    assert translation_path.exists()
    assert prompt_path.exists()
    assert json.loads(translation_path.read_text(encoding="utf-8"))["segments"][0][
        "target_text"
    ] == "សួស្តី។"
    prompt_artifact = json.loads(prompt_path.read_text(encoding="utf-8"))
    assert prompt_artifact["batch_size"] == 20
    assert prompt_artifact["batch_count"] == 1


def test_nbwcode_dialogue_localizer_batches_and_merges_translation(monkeypatch, tmp_path):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(transcript_payload_with_segment_count(45), ensure_ascii=False),
        encoding="utf-8",
    )
    calls: list[tuple[int, int, int]] = []

    def fake_call(
        base_url: str,
        api_key: str,
        model: str,
        prompt: dict[str, object],
        debug_dir=None,
        segment_count=None,
        batch_index=None,
        batch_count=None,
        **_diagnostics,
    ) -> dict[str, object]:
        assert base_url == "https://gateway.example/v1"
        assert api_key == "test-key"
        assert model == "test-model"
        assert debug_dir == tmp_path / "debug"
        calls.append((segment_count, batch_index, batch_count))
        return {
            "output_text": json.dumps(
                {
                    "segments": [
                        {
                            "id": segment["id"],
                            "target_text": f"ខ្មែរ {segment['id']}",
                            "notes": None,
                        }
                        for segment in prompt["input_segments"]
                    ]
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(localization, "call_openai_compatible_responses_api", fake_call)
    localizer = localization.NBWCodeDialogueLocalizer(
        ToolConfig(
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="test-key",
            localization_model="test-model",
        )
    )
    translation_path = tmp_path / "translation.json"
    prompt_path = tmp_path / "translation_prompt.json"

    localizer.localize(transcript_path, translation_path, prompt_path)

    assert calls == [(20, 1, 3), (20, 2, 3), (5, 3, 3)]
    translation = json.loads(translation_path.read_text(encoding="utf-8"))
    assert len(translation["segments"]) == 45
    assert translation["segments"][0]["id"] == 0
    assert translation["segments"][44]["id"] == 44
    assert translation["segments"][44]["start"] == 44.0
    assert translation["segments"][44]["target_text"] == "ខ្មែរ 44"
    prompt_artifact = json.loads(prompt_path.read_text(encoding="utf-8"))
    assert prompt_artifact["batch_count"] == 3
    assert [batch["batch_index"] for batch in prompt_artifact["prompt"]] == [1, 2, 3]


def test_openai_compatible_dialogue_localizer_requires_api_key(tmp_path):
    localizer = localization.NBWCodeDialogueLocalizer(
        ToolConfig(nbw_base_url="https://gateway.example/v1", localization_model="test-model")
    )

    with pytest.raises(localization.VS2Error, match="NBW_AUTOMATEDUB_API_KEY"):
        localizer.localize(
            tmp_path / "transcript.json",
            tmp_path / "translation.json",
            tmp_path / "translation_prompt.json",
        )


def test_build_endpoint_urls_from_base_url():
    assert localization.build_responses_url("https://gateway.example/v1") == (
        "https://gateway.example/v1/responses"
    )
    assert localization.build_chat_completions_url("https://gateway.example/v1") == (
        "https://gateway.example/v1/chat/completions"
    )


def test_openai_compatible_call_falls_back_to_chat_completions(monkeypatch):
    calls: list[str] = []

    def fake_post_json(**kwargs):
        calls.append(kwargs["endpoint_name"])
        if kwargs["endpoint_name"] == "Responses":
            raise localization.EndpointUnsupported(
                "unsupported",
                {
                    "endpoint": "Responses",
                    "url": "https://gateway.example/v1/responses",
                    "http_status_code": 404,
                    "response_body": "not found",
                    "exception_type": "HTTPError",
                    "exception": "HTTP Error 404",
                },
            )
        return {"output_text": '{"segments":[]}'}

    monkeypatch.setattr(localization, "post_json", fake_post_json)

    payload = localization.call_openai_compatible_responses_api(
        base_url="https://gateway.example/v1",
        api_key="test-key",
        model="test-model",
        prompt={"system": "system", "user": "user"},
    )

    assert calls == ["Responses", "Chat Completions"]
    assert payload == {"output_text": '{"segments":[]}'}


def test_localization_request_debug_includes_redacted_http_details(monkeypatch, tmp_path):
    def fake_post_json(**kwargs):
        assert kwargs["provider_id"] == "nbwcode"
        assert kwargs["wire_api"] == "responses"
        return {"output_text": '{"segments":[]}'}

    monkeypatch.setattr(localization, "post_json", fake_post_json)

    localization.call_openai_compatible_responses_api(
        base_url="https://gateway.example/v1",
        api_key="secret-key",
        model="test-model",
        provider_id="nbwcode",
        wire_api="responses",
        prompt={"system": "system", "user": "user"},
        debug_dir=tmp_path / "debug",
    )

    request_debug = json.loads(
        (tmp_path / "debug" / "localization_request.json").read_text(encoding="utf-8")
    )
    attempt = request_debug["attempts"][0]
    assert attempt["provider_id"] == "nbwcode"
    assert attempt["model"] == "test-model"
    assert attempt["wire_api"] == "responses"
    assert attempt["url"] == "https://gateway.example/v1/responses"
    assert attempt["method"] == "POST"
    assert attempt["headers"]["Authorization"] == "Bearer <redacted>"
    assert attempt["json_payload"]["model"] == "test-model"


def test_openai_compatible_call_writes_debug_files_when_fallback_fails(monkeypatch, tmp_path):
    def fake_responses(**kwargs):
        raise localization.EndpointUnsupported(
            "unsupported",
            {
                "endpoint": "Responses",
                "url": "https://gateway.example/v1/responses",
                "http_status_code": 404,
                "response_body": "responses missing",
                "exception_type": "HTTPError",
                "exception": "HTTP Error 404",
            },
        )

    def fake_chat(**kwargs):
        raise localization.LLMEndpointError(
            "chat failed",
            {
                "endpoint": "Chat Completions",
                "url": "https://gateway.example/v1/chat/completions",
                "http_status_code": 400,
                "response_body": "bad request",
                "exception_type": "HTTPError",
                "exception": "HTTP Error 400",
            },
        )

    monkeypatch.setattr(localization, "post_json", fake_responses)
    monkeypatch.setattr(localization, "post_json", fake_chat)

    def fake_post_json(**kwargs):
        if kwargs["endpoint_name"] == "Responses":
            fake_responses(**kwargs)
        return fake_chat(**kwargs)

    monkeypatch.setattr(localization, "post_json", fake_post_json)

    with pytest.raises(localization.VS2Error) as exc_info:
        localization.call_openai_compatible_responses_api(
            base_url="https://gateway.example/v1",
            api_key="test-key",
            model="test-model",
            prompt={"system": "system", "user": "user"},
            debug_dir=tmp_path / "debug",
        )

    assert "Provider base URL: https://gateway.example/v1" in str(exc_info.value)
    assert "Request model: test-model" in str(exc_info.value)
    assert "Responses fallback attempted: yes" in str(exc_info.value)
    assert "HTTP response body: responses missing" in str(exc_info.value)
    assert "HTTP response body: bad request" in str(exc_info.value)

    request_debug = json.loads(
        (tmp_path / "debug" / "localization_request.json").read_text(encoding="utf-8")
    )
    error_debug = json.loads(
        (tmp_path / "debug" / "localization_error.json").read_text(encoding="utf-8")
    )
    assert request_debug["fallback_attempted"] is True
    assert len(request_debug["attempts"]) == 2
    assert request_debug["attempts"][0]["payload"]["model"] == "test-model"
    assert error_debug["fallback_attempted"] is True
    assert [attempt["response_body"] for attempt in error_debug["attempts"]] == [
        "responses missing",
        "bad request",
    ]


def test_endpoint_error_attempt_includes_request_and_response_headers():
    request_debug = {
        "url": "https://gateway.example/v1/responses",
        "method": "POST",
        "headers": {"authorization": "Bearer <redacted>"},
        "json_payload": {"model": "test-model"},
    }

    attempt = localization.build_endpoint_attempt_result(
        endpoint_name="Responses",
        url="https://gateway.example/v1/responses",
        status_code=403,
        response_body="blocked",
        response_headers={"cf-ray": "ray-id"},
        request_debug=request_debug,
        exception=RuntimeError("failed"),
    )

    assert attempt["request"] == request_debug
    assert attempt["response_headers"] == {"cf-ray": "ray-id"}


def test_post_json_uses_httpx_transport_and_writes_wire_debug(tmp_path):
    _CapturePostHandler.captured = {}
    server = HTTPServer(("127.0.0.1", 0), _CapturePostHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    try:
        payload = localization.post_json(
            url=f"http://127.0.0.1:{server.server_port}/responses",
            api_key="secret-key",
            payload={
                "model": "test-model",
                "input": [{"role": "user", "content": "Return JSON."}],
                "max_output_tokens": 16,
            },
            timeout=5,
            endpoint_name="Responses",
            provider_id="nbwcode",
            model="test-model",
            wire_api="responses",
            debug_dir=tmp_path / "debug",
        )
    finally:
        thread.join(timeout=5)
        server.server_close()

    assert payload == {"output_text": "{}"}
    captured = _CapturePostHandler.captured
    assert captured["request_version"] == "HTTP/1.1"
    assert captured["command"] == "POST"
    assert captured["path"] == "/responses"
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer secret-key"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == localization.OPENAI_COMPATIBLE_USER_AGENT
    assert json.loads(str(captured["body"]))["model"] == "test-model"

    request_debug = json.loads(
        (tmp_path / "debug" / "localization_http_request.json").read_text(
            encoding="utf-8"
        )
    )
    response_debug = json.loads(
        (tmp_path / "debug" / "localization_http_response.json").read_text(
            encoding="utf-8"
        )
    )
    assert request_debug["url"].endswith("/responses")
    assert request_debug["method"] == "POST"
    assert request_debug["http_version"] == "HTTP/1.0"
    assert request_debug["headers"]["authorization"] == "Bearer <redacted>"
    assert response_debug["status_code"] == 200
    assert response_debug["body"] == '{"output_text":"{}"}'


def test_detect_supported_endpoint_prefers_responses(monkeypatch):
    monkeypatch.setattr(
        localization,
        "call_responses_endpoint",
        lambda **kwargs: {"output_text": '{"ok":true}'},
    )

    assert (
        localization.detect_supported_endpoint("https://gateway.example/v1", "key", "model")
        == "responses"
    )
