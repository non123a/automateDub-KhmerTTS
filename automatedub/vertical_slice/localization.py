"""VS2 movie-dialogue localization from Chinese transcript to Khmer dialogue."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from automatedub.config import ToolConfig

PROMPT_VERSION = 1
TRANSLATION_VERSION = 1
LOCALIZATION_BATCH_SIZE = 20
LOCALIZATION_HTTP_TIMEOUT_SECONDS = 300


class VS2Error(RuntimeError):
    """Raised when the VS2 localization step cannot complete."""


class LLMEndpointError(VS2Error):
    def __init__(self, message: str, attempt: dict[str, object]) -> None:
        super().__init__(message)
        self.attempt = attempt


class EndpointUnsupported(LLMEndpointError):
    """Raised when an OpenAI-compatible endpoint is unavailable."""


@dataclass(frozen=True)
class TranscriptSegmentForLocalization:
    id: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranslationSegment:
    id: int
    start: float
    end: float
    source_language: str
    target_language: str
    source_text: str
    target_text: str
    notes: str | None = None


@dataclass(frozen=True)
class TranslationArtifact:
    version: int
    source_transcript: str
    prompt_artifact: str
    engine: dict[str, str]
    segments: list[TranslationSegment]


class DialogueLocalizer(Protocol):
    def localize(self, transcript_path: Path, translation_path: Path, prompt_path: Path) -> None:
        """Localize transcript dialogue and write translation artifacts."""


class NBWCodeDialogueLocalizer:
    def __init__(self, tool_config: ToolConfig) -> None:
        self.tool_config = tool_config

    def localize(self, transcript_path: Path, translation_path: Path, prompt_path: Path) -> None:
        base_url, api_key, model = validate_llm_config(self.tool_config)
        transcript = load_transcript(transcript_path)
        batches = split_transcript_batches(transcript, LOCALIZATION_BATCH_SIZE)
        prompts = [build_localization_prompt(batch) for batch in batches]
        write_prompt_artifact(
            prompt_path=prompt_path,
            prompts=prompts,
            model=model,
            source_transcript=transcript_path.name,
            batch_size=LOCALIZATION_BATCH_SIZE,
        )

        translated_segments: list[TranslationSegment] = []
        for batch_index, batch in enumerate(batches, start=1):
            prompt = prompts[batch_index - 1]
            response_payload = call_openai_compatible_responses_api(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=prompt,
                debug_dir=translation_path.parent / "debug",
                segment_count=len(batch),
                batch_index=batch_index,
                batch_count=len(batches),
            )
            try:
                batch_translation = normalize_openai_compatible_localization_response(
                    response_payload=response_payload,
                    transcript=batch,
                    source_transcript=transcript_path.name,
                    prompt_artifact=prompt_path.name,
                    model=model,
                )
            except VS2Error as exc:
                write_localization_error_debug(
                    debug_dir=translation_path.parent / "debug",
                    error_payload={
                        "provider_base_url": base_url,
                        "model": model,
                        "phase": "response_normalization",
                        "batch_index": batch_index,
                        "batch_count": len(batches),
                        "error": str(exc),
                        "raw_response": response_payload,
                    },
                )
                raise
            translated_segments.extend(batch_translation.segments)

        translation = TranslationArtifact(
            version=TRANSLATION_VERSION,
            source_transcript=transcript_path.name,
            prompt_artifact=prompt_path.name,
            engine={"provider": "openai-compatible", "model": model},
            segments=translated_segments,
        )
        write_translation_artifact(translation_path, translation)


def split_transcript_batches(
    transcript: list[TranscriptSegmentForLocalization],
    batch_size: int,
) -> list[list[TranscriptSegmentForLocalization]]:
    if batch_size < 1:
        raise VS2Error("localization batch size must be at least 1")
    return [
        transcript[start : start + batch_size]
        for start in range(0, len(transcript), batch_size)
    ]


def validate_llm_config(tool_config: ToolConfig) -> tuple[str, str, str]:
    if not tool_config.nbw_automatedub_api_key:
        raise VS2Error("NBW_AUTOMATEDUB_API_KEY is required for VS2 localization")
    return (
        tool_config.nbw_base_url,
        tool_config.nbw_automatedub_api_key,
        tool_config.localization_model,
    )


def build_responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/responses"):
        return normalized
    if normalized.endswith("/chat/completions"):
        return normalized.removesuffix("/chat/completions") + "/responses"
    return f"{normalized}/responses"


def build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/responses"):
        return normalized.removesuffix("/responses") + "/chat/completions"
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def detect_supported_endpoint(base_url: str, api_key: str, model: str) -> str:
    try:
        call_responses_endpoint(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt="Reply with JSON only.",
            user_prompt='Return {"ok":true}.',
            max_tokens=16,
            timeout=30,
        )
        return "responses"
    except EndpointUnsupported:
        try:
            call_chat_completions_endpoint(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt="Reply with JSON only.",
                user_prompt='Return {"ok":true}.',
                max_tokens=16,
                timeout=30,
            )
        except EndpointUnsupported as exc:
            raise RuntimeError("neither /responses nor /chat/completions is supported") from exc
        return "chat/completions"


def check_nbw_status(base_url: str, api_key: str | None, model: str) -> dict[str, object]:
    status: dict[str, object] = {
        "base_url": base_url,
        "api_key_present": bool(api_key),
        "model": model,
        "endpoint": None,
        "authentication_valid": False,
        "connectivity_ok": False,
        "error": None,
    }
    if not api_key:
        status["error"] = "NBW_AUTOMATEDUB_API_KEY is not set"
        return status

    try:
        endpoint = detect_supported_endpoint(base_url, api_key, model)
    except VS2Error as exc:
        status["connectivity_ok"] = True
        status["error"] = str(exc)
        return status
    except RuntimeError as exc:
        status["error"] = str(exc)
        return status

    status["endpoint"] = endpoint
    status["authentication_valid"] = True
    status["connectivity_ok"] = True
    return status


def load_transcript(transcript_path: Path) -> list[TranscriptSegmentForLocalization]:
    if not transcript_path.exists():
        raise VS2Error(f"transcript file does not exist: {transcript_path}")
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VS2Error(f"transcript file is not valid JSON: {transcript_path}") from exc

    if not isinstance(payload, dict):
        raise VS2Error("transcript JSON root must be an object")
    if payload.get("language") != "zh":
        raise VS2Error("transcript language must be zh")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise VS2Error("transcript JSON must contain a segments list")

    segments: list[TranscriptSegmentForLocalization] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise VS2Error("each transcript segment must be an object")
        segment_id = raw_segment.get("id")
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        text = raw_segment.get("text")
        if not isinstance(segment_id, int):
            raise VS2Error("each transcript segment must contain integer id")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            raise VS2Error("each transcript segment must contain numeric start and end")
        if not isinstance(text, str):
            raise VS2Error("each transcript segment must contain source text")
        segments.append(
            TranscriptSegmentForLocalization(
                id=segment_id,
                start=float(start),
                end=float(end),
                text=text,
            )
        )

    return segments


def build_localization_prompt(
    segments: list[TranscriptSegmentForLocalization],
) -> dict[str, object]:
    system_prompt = (
        "You are the official Khmer dubbing translator for a television drama. "
        "Translate Chinese dialogue into natural spoken Khmer for dubbing. "
        "Preserve meaning, emotion, and conversational movie-style delivery. "
        "Avoid word-for-word translation. Preserve approximately similar speaking duration. "
        "Never merge segments. Never split segments. "
        "Keep punctuation suitable for spoken dialogue. "
        "Return valid JSON only."
    )
    source_segments = [
        {
            "id": segment.id,
            "start": segment.start,
            "end": segment.end,
            "source_language": "zh",
            "target_language": "km",
            "source_text": segment.text,
        }
        for segment in segments
    ]
    user_prompt = (
        "Localize each segment into Khmer. Return a JSON object with exactly this shape: "
        '{"segments":[{"id":0,"target_text":"...","notes":null}]}. '
        "The returned segments array must have exactly the same length and IDs as the input. "
        "Do not include Markdown. Do not include commentary.\n\n"
        f"Input segments:\n{json.dumps(source_segments, ensure_ascii=False, indent=2)}"
    )
    return {
        "version": PROMPT_VERSION,
        "system": system_prompt,
        "user": user_prompt,
        "input_segments": source_segments,
    }


def write_prompt_artifact(
    prompt_path: Path,
    prompts: list[dict[str, object]],
    model: str,
    source_transcript: str,
    batch_size: int,
) -> None:
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if len(prompts) == 1:
        prompt_payload: dict[str, object] | list[dict[str, object]] = prompts[0]
    else:
        prompt_payload = [
            {
                "batch_index": index,
                "prompt": prompt,
            }
            for index, prompt in enumerate(prompts, start=1)
        ]
    payload = {
        "version": PROMPT_VERSION,
        "source_transcript": source_transcript,
        "engine": {"provider": "openai-compatible", "model": model},
        "batch_size": batch_size,
        "batch_count": len(prompts),
        "prompt": prompt_payload,
    }
    write_json(prompt_path, payload)


def call_openai_compatible_responses_api(
    base_url: str,
    api_key: str,
    model: str,
    prompt: dict[str, object],
    debug_dir: Path | None = None,
    segment_count: int | None = None,
    batch_index: int | None = None,
    batch_count: int | None = None,
) -> dict[str, object]:
    system_prompt = str(prompt["system"])
    user_prompt = str(prompt["user"])
    prompt_size = len(system_prompt) + len(user_prompt)
    estimated_input_tokens = estimate_input_tokens(prompt_size)
    print_localization_request_summary(
        segment_count=segment_count,
        prompt_size=prompt_size,
        estimated_input_tokens=estimated_input_tokens,
        batch_index=batch_index,
        batch_count=batch_count,
    )
    responses_url = build_responses_url(base_url)
    chat_url = build_chat_completions_url(base_url)
    responses_payload = build_responses_payload(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=4096,
    )
    request_debug: dict[str, object] = {
        "provider_base_url": base_url,
        "model": model,
        "segment_count": segment_count,
        "prompt_size_characters": prompt_size,
        "estimated_input_tokens": estimated_input_tokens,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "fallback_attempted": False,
        "attempts": [
            {
                "endpoint": "Responses",
                "url": responses_url,
                "payload": responses_payload,
            }
        ],
    }
    write_localization_request_debug(debug_dir, request_debug)

    try:
        return post_json(
            url=responses_url,
            api_key=api_key,
            payload=responses_payload,
            timeout=LOCALIZATION_HTTP_TIMEOUT_SECONDS,
            endpoint_name="Responses",
        )
    except EndpointUnsupported as responses_exc:
        chat_payload = build_chat_completions_payload(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,
        )
        request_debug["fallback_attempted"] = True
        request_debug["attempts"].append(
            {
                "endpoint": "Chat Completions",
                "url": chat_url,
                "payload": chat_payload,
            }
        )
        write_localization_request_debug(debug_dir, request_debug)
        try:
            return post_json(
                url=chat_url,
                api_key=api_key,
                payload=chat_payload,
                timeout=LOCALIZATION_HTTP_TIMEOUT_SECONDS,
                endpoint_name="Chat Completions",
            )
        except LLMEndpointError as chat_exc:
            error_payload = build_localization_error_payload(
                base_url=base_url,
                model=model,
                fallback_attempted=True,
                segment_count=segment_count,
                prompt_size=prompt_size,
                estimated_input_tokens=estimated_input_tokens,
                batch_index=batch_index,
                batch_count=batch_count,
                attempts=[responses_exc.attempt, chat_exc.attempt],
            )
            write_localization_error_debug(debug_dir, error_payload)
            raise VS2Error(format_localization_error(error_payload, debug_dir)) from chat_exc
    except LLMEndpointError as responses_exc:
        error_payload = build_localization_error_payload(
            base_url=base_url,
            model=model,
            fallback_attempted=False,
            segment_count=segment_count,
            prompt_size=prompt_size,
            estimated_input_tokens=estimated_input_tokens,
            batch_index=batch_index,
            batch_count=batch_count,
            attempts=[responses_exc.attempt],
        )
        write_localization_error_debug(debug_dir, error_payload)
        raise VS2Error(format_localization_error(error_payload, debug_dir)) from responses_exc


def call_responses_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout: int,
) -> dict[str, object]:
    request_payload = build_responses_payload(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
    )
    return post_json(
        url=build_responses_url(base_url),
        api_key=api_key,
        payload=request_payload,
        timeout=timeout,
        endpoint_name="Responses",
    )


def call_chat_completions_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout: int,
) -> dict[str, object]:
    request_payload = build_chat_completions_payload(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
    )
    return post_json(
        url=build_chat_completions_url(base_url),
        api_key=api_key,
        payload=request_payload,
        timeout=timeout,
        endpoint_name="Chat Completions",
    )


def build_responses_payload(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> dict[str, object]:
    return {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": max_tokens,
    }


def build_chat_completions_payload(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> dict[str, object]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }


def post_json(
    url: str,
    api_key: str,
    payload: dict[str, object],
    timeout: int,
    endpoint_name: str,
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(response_body)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        attempt = build_endpoint_attempt_result(
            endpoint_name=endpoint_name,
            url=url,
            status_code=exc.code,
            response_body=response_body,
            exception=exc,
        )
        if exc.code in {404, 405, 501}:
            raise EndpointUnsupported(
                f"{endpoint_name} endpoint is not supported: HTTP {exc.code}: {response_body}",
                attempt,
            ) from exc
        raise LLMEndpointError(
            f"{endpoint_name} request failed: HTTP {exc.code}: {response_body}",
            attempt,
        ) from exc
    except json.JSONDecodeError as exc:
        attempt = build_endpoint_attempt_result(
            endpoint_name=endpoint_name,
            url=url,
            status_code=None,
            response_body=response_body,
            exception=exc,
        )
        raise LLMEndpointError(
            f"{endpoint_name} response was not valid JSON: {exc}", attempt
        ) from exc
    except OSError as exc:
        attempt = build_endpoint_attempt_result(
            endpoint_name=endpoint_name,
            url=url,
            status_code=None,
            response_body=None,
            exception=exc,
        )
        raise LLMEndpointError(f"{endpoint_name} request failed: {exc}", attempt) from exc
    if not isinstance(payload, dict):
        raise VS2Error("LLM localization response root must be an object")
    return payload


def build_endpoint_attempt_result(
    endpoint_name: str,
    url: str,
    status_code: int | None,
    response_body: str | None,
    exception: BaseException,
) -> dict[str, object]:
    return {
        "endpoint": endpoint_name,
        "url": url,
        "http_status_code": status_code,
        "response_body": response_body,
        "exception_type": type(exception).__name__,
        "exception": str(exception),
    }


def build_localization_error_payload(
    base_url: str,
    model: str,
    fallback_attempted: bool,
    segment_count: int | None,
    prompt_size: int,
    estimated_input_tokens: int,
    batch_index: int | None,
    batch_count: int | None,
    attempts: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "provider_base_url": base_url,
        "model": model,
        "segment_count": segment_count,
        "prompt_size_characters": prompt_size,
        "estimated_input_tokens": estimated_input_tokens,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "fallback_attempted": fallback_attempted,
        "attempts": attempts,
    }


def write_localization_request_debug(
    debug_dir: Path | None,
    request_payload: dict[str, object],
) -> None:
    if debug_dir is None:
        return
    write_json(debug_dir / "localization_request.json", request_payload)


def write_localization_error_debug(
    debug_dir: Path | None,
    error_payload: dict[str, object],
) -> None:
    if debug_dir is None:
        return
    write_json(debug_dir / "localization_error.json", error_payload)


def format_localization_error(
    error_payload: dict[str, object],
    debug_dir: Path | None,
) -> str:
    lines = [
        "LLM localization request failed",
        f"Provider base URL: {error_payload['provider_base_url']}",
        f"Request model: {error_payload['model']}",
        f"Transcript segment count: {error_payload.get('segment_count') or 'unknown'}",
        f"Prompt size: {error_payload.get('prompt_size_characters')} characters",
        f"Estimated input tokens: {error_payload.get('estimated_input_tokens')}",
        f"Responses fallback attempted: {yes_no(bool(error_payload['fallback_attempted']))}",
    ]
    attempts = error_payload.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            lines.extend(
                [
                    "",
                    f"{attempt.get('endpoint', 'Endpoint')} result:",
                    f"Endpoint URL: {attempt.get('url')}",
                    f"HTTP status code: {attempt.get('http_status_code') or 'unavailable'}",
                    f"HTTP response body: {attempt.get('response_body') or 'unavailable'}",
                    f"Underlying exception: {attempt.get('exception_type')}: "
                    f"{attempt.get('exception')}",
                ]
            )
    if debug_dir is not None:
        lines.extend(
            [
                "",
                f"Debug request: {debug_dir / 'localization_request.json'}",
                f"Debug error: {debug_dir / 'localization_error.json'}",
            ]
        )
    return "\n".join(lines)


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def estimate_input_tokens(character_count: int) -> int:
    return max(1, (character_count + 3) // 4)


def print_localization_request_summary(
    segment_count: int | None,
    prompt_size: int,
    estimated_input_tokens: int,
    batch_index: int | None,
    batch_count: int | None,
) -> None:
    batch_label = ""
    if batch_index is not None and batch_count is not None:
        batch_label = f" batch {batch_index}/{batch_count}"
    print(f"localization{batch_label}: transcript segment count: {segment_count or 'unknown'}")
    print(f"localization{batch_label}: prompt size: {prompt_size} characters")
    print(f"localization{batch_label}: estimated input tokens: {estimated_input_tokens}")


def normalize_openai_compatible_localization_response(
    response_payload: dict[str, object],
    transcript: list[TranscriptSegmentForLocalization],
    source_transcript: str,
    prompt_artifact: str,
    model: str,
) -> TranslationArtifact:
    response_text = extract_openai_compatible_text(response_payload)
    localized_payload = parse_localization_json(response_text)
    raw_segments = localized_payload.get("segments")
    if not isinstance(raw_segments, list):
        raise VS2Error("LLM localization JSON must contain a segments list")
    if len(raw_segments) != len(transcript):
        raise VS2Error("LLM localization changed the segment count")

    by_id: dict[int, dict[str, object]] = {}
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise VS2Error("each localized segment must be an object")
        segment_id = raw_segment.get("id")
        if not isinstance(segment_id, int):
            raise VS2Error("each localized segment must contain integer id")
        by_id[segment_id] = raw_segment

    output_segments: list[TranslationSegment] = []
    for source_segment in transcript:
        localized_segment = by_id.get(source_segment.id)
        if localized_segment is None:
            raise VS2Error(f"LLM localization omitted segment id {source_segment.id}")
        target_text = localized_segment.get("target_text")
        if not isinstance(target_text, str) or not target_text.strip():
            raise VS2Error(f"localized segment {source_segment.id} is missing target_text")
        notes = localized_segment.get("notes")
        if notes is not None and not isinstance(notes, str):
            notes = str(notes)
        output_segments.append(
            TranslationSegment(
                id=source_segment.id,
                start=source_segment.start,
                end=source_segment.end,
                source_language="zh",
                target_language="km",
                source_text=source_segment.text,
                target_text=target_text.strip(),
                notes=notes,
            )
        )

    return TranslationArtifact(
        version=TRANSLATION_VERSION,
        source_transcript=source_transcript,
        prompt_artifact=prompt_artifact,
        engine={"provider": "openai-compatible", "model": model},
        segments=output_segments,
    )


def extract_openai_compatible_text(response_payload: dict[str, object]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = response_payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        response_text = "".join(parts).strip()
        if response_text:
            return response_text

    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    raise VS2Error("LLM response did not contain text")


def parse_localization_json(response_text: str) -> dict[str, object]:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        raise VS2Error("LLM response included Markdown instead of raw JSON")
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise VS2Error("LLM response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise VS2Error("LLM localization JSON root must be an object")
    return payload


def translation_artifact_to_json(artifact: TranslationArtifact) -> dict[str, object]:
    return {
        "version": artifact.version,
        "source_transcript": artifact.source_transcript,
        "prompt_artifact": artifact.prompt_artifact,
        "engine": artifact.engine,
        "segments": [
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "source_language": segment.source_language,
                "target_language": segment.target_language,
                "source_text": segment.source_text,
                "target_text": segment.target_text,
                "notes": segment.notes,
            }
            for segment in artifact.segments
        ],
    }


def write_translation_artifact(translation_path: Path, artifact: TranslationArtifact) -> None:
    translation_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(translation_path, translation_artifact_to_json(artifact))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
