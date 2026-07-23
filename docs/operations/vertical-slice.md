# Vertical Slice Operations

Status: VS1 implemented.

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
