# Vertical Slice Operations

Status: VS2 implemented.

The vertical-slice implementation proves the product workflow one step at a time before replacing shortcuts with the frozen production architecture.

## VS0: Audio Extraction

VS0 accepts one MP4 file and extracts its audio to WAV.

```bash
uv run automatedub dub movie.mp4 output/
```

Expected output:

```text
output/audio.wav
```

The generated WAV uses:

- codec: PCM signed 16-bit little-endian
- sample rate: 16000 Hz
- channels: mono

## Requirements

- Python 3.12+
- `uv`
- Homebrew
- FFmpeg available on `PATH`
- FFprobe available on `PATH`
- whisper.cpp `whisper-cli` available on `PATH`
- `models/ggml-small.bin`
- `NBW_BASE_URL` for VS2 localization
- `NBW_AUTOMATEDUB_API_KEY` for VS2 localization
- `LOCALIZATION_MODEL` for VS2 localization

## Setup

Prepare the local environment:

```bash
uv run automatedub setup
```

The setup command:

- checks Homebrew
- checks FFmpeg
- checks FFprobe
- checks whisper.cpp
- creates `models/`
- downloads `models/ggml-small.bin` if missing
- verifies the model SHA256 checksum
- runs the same checks as `doctor`

Validate without changing files:

```bash
uv run automatedub doctor
```

The CLI validates:

- input path exists
- input path is a file
- input file has `.mp4` suffix
- FFmpeg is available
- output directory can be created

## VS1: Local Chinese Transcription

VS1 extends the same command:

```bash
uv run automatedub dub movie.mp4 output/
```

Expected outputs:

```text
output/audio.wav
output/transcript.json
```

Transcript schema:

```json
{
  "version": 1,
  "language": "zh",
  "source_audio": "audio.wav",
  "engine": {
    "provider": "local",
    "model": "whisper.cpp:ggml-small.bin"
  },
  "text": "full transcript text",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 5.7,
      "text": "segment text"
    }
  ]
}
```

VS1 uses a generic `LocalTranscriber` boundary. The first implementation is `WhisperCppTranscriber`.

On this Apple M1 Pro environment, the default whisper.cpp Metal path exited with signal 11 during smoke testing. The implementation retries signal failures with `-ng` to disable GPU, which completed successfully.

## VS2: Khmer Dialogue Localization

VS2 extends the same command:

```bash
uv run automatedub dub movie.mp4 output/
```

Expected outputs:

```text
output/audio.wav
output/transcript.json
output/translation_prompt.json
output/translation.json
```

VS2 consumes `output/transcript.json` and does not modify it. It writes a new localization artifact and saves the exact prompt used for reproducibility.

`translation.json` schema:

```json
{
  "version": 1,
  "source_transcript": "transcript.json",
  "prompt_artifact": "translation_prompt.json",
  "engine": {
    "provider": "openai-compatible",
    "model": "configured model"
  },
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 5.7,
      "source_language": "zh",
      "target_language": "km",
      "source_text": "Chinese source dialogue",
      "target_text": "Khmer localized dialogue",
      "notes": null
    }
  ]
}
```

VS2 uses a generic `DialogueLocalizer` boundary. The MVP implementation is
`NBWCodeDialogueLocalizer`.

Configure the localizer by creating a `.env` file in the repository root:

```bash
NBW_BASE_URL=https://www.nbwcode.top/v1
NBW_AUTOMATEDUB_API_KEY=...
LOCALIZATION_MODEL=gpt-5.5
```

The CLI loads `.env` automatically. Values exported in the shell take precedence
over values from `.env`.

`NBW_BASE_URL` may point to the base API URL, such as `/v1`, or directly to a
`/responses` or `/chat/completions` endpoint. The implementation tests `/responses`
first and automatically falls back to `/chat/completions` when Responses is unsupported.

For MVP reliability, VS2 localizes transcripts in batches of 20 segments. Each
batch preserves source segment IDs and timestamps, then the CLI merges all batch
results into the existing `translation.json` schema. Before each request, the CLI
prints the batch segment count, prompt size in characters, and estimated input
tokens. Localization HTTP requests use a 300-second timeout.

Doctor reports NBWCode status separately:

```text
=== NBWCode ===

Base URL:
✓ https://www.nbwcode.top/v1

API Key:
✓ Present

Model:
✓ gpt-5.5

Endpoint:
✓ Responses
```

Localization prompt priorities:

1. Preserve meaning.
2. Preserve emotion.
3. Preserve natural spoken Khmer.
4. Avoid word-for-word translation.
5. Preserve approximately similar speaking duration.
6. Never merge segments.
7. Never split segments.
8. Keep punctuation suitable for spoken dialogue.
9. Return valid JSON only.

## Current Shortcut Boundaries

The current vertical slice intentionally does not implement:

- translation
- TTS
- rendering
- database
- workflow engine
- provider abstraction
- caching
- quality intelligence
