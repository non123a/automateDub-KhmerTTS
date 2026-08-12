from __future__ import annotations

import json

from automatedub.vertical_slice.localization import load_transcript
from automatedub.vertical_slice.transcription import (
    Transcript,
    TranscriptSegment,
    write_transcript,
)


def test_transcript_persists_timing_and_edited_text(tmp_path):
    path = tmp_path / "transcript.json"
    write_transcript(
        path,
        Transcript(
            version=1,
            language="zh",
            source_audio="audio.wav",
            engine={"provider": "whisper.cpp", "model": "ggml-small.bin"},
            text="original",
            segments=[
                TranscriptSegment(7, 12.34, 15.82, "original", "corrected text"),
            ],
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["segments"] == [
        {
            "id": 7,
            "start": 12.34,
            "end": 15.82,
            "text": "original",
            "edited_text": "corrected text",
        }
    ]


def test_translation_uses_edited_transcript_text(tmp_path):
    path = tmp_path / "transcript.json"
    path.write_text(
        json.dumps(
            {
                "language": "zh",
                "segments": [
                    {"id": 1, "start": 1.0, "end": 2.0, "text": "raw", "edited_text": "fixed"}
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_transcript(path)[0].text == "fixed"
