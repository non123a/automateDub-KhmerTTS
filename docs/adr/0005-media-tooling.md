# ADR 0005: Use FFmpeg-Centered Media Processing

Status: accepted

## Problem

AutomateDub must probe, segment, extract, mix, and render real media with reliable timestamp, stream, codec, and audio behavior.

## Alternatives

- FFmpeg/FFprobe as authoritative tools
- MoviePy-first
- OpenCV-first
- Cloud video processing first
- Custom media processing

## Tradeoffs

- FFmpeg is mature, portable, and precise, but command construction is low-level and must be tested carefully.
- MoviePy is easier but can hide behavior that matters in production.
- OpenCV is useful for frame analysis but not enough for audio and rendering.
- Cloud video processing adds cost and provider dependence.

## Final Decision

Use FFmpeg and FFprobe as authoritative media tools. Use PySceneDetect or other detectors behind replaceable media-analysis contracts.

## Consequences

- Media commands need fixture-based tests.
- Stream selection, timestamps, codecs, subtitles, frame rates, and audio layouts must be represented explicitly.

## Future Reconsideration

Specialist media services may be added later for scale or quality, but they must remain behind infrastructure adapters.

