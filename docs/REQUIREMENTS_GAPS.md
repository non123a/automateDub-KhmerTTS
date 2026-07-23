# Requirements Gaps

This document records product, legal, operational, and quality questions that must be answered before implementation decisions become expensive to change.

## Product Decisions Needed

- What is the acceptable cost per finished movie?
- What is the acceptable processing time per movie?
- Is the first useful output a full movie, a 5-10 minute clip, or selected scenes?
- Should the original Chinese dialogue be removed, lowered, or left faintly audible?
- Should Khmer subtitles be generated alongside dubbed video?
- Is human review required before final render?
- What level of Khmer formality and regional style is preferred?
- Should profanity, jokes, idioms, and cultural references be localized or preserved?

## Input Media Questions

- Expected source formats: MP4, MKV, MOV, AVI?
- Expected source quality: 720p, 1080p, 4K?
- Are source subtitles available?
- Are subtitle tracks embedded, external, or burned into video?
- Are movies Mandarin only, or also Cantonese and regional Chinese varieties?
- Are there multiple audio channels or commentary tracks?

## Voice And Legal Questions

- Will generated voices be generic, licensed synthetic voices, cloned voices, or manually recorded actor voices?
- If cloning is used, whose consent is required and how will it be stored?
- Is matching the original actor voice desired or prohibited?
- Are there restrictions from AI providers for dubbing copyrighted or sensitive content?

## Operational Questions

- Must processing run offline on macOS?
- Is cloud processing acceptable for transcription, translation, TTS, or diarization?
- Is GPU hardware available now or planned later?
- Should artifacts be retained permanently or cleaned after rendering?
- Should the system support multiple jobs at once in v1?

## Quality Measurement

Automated quality metrics should be defined early:

- transcription confidence or sample review score
- diarization correction rate
- translation adequacy score
- Khmer naturalness score
- generated speech duration delta
- render audio/video sync drift
- manual intervention count per clip

## Recommended Clarifications Before Coding

1. Approve a cloud-assisted MVP or require offline-first design.
2. Pick the first target: one 5-10 minute clip or one full movie.
3. Define whether voice cloning is allowed.
4. Define budget constraints for provider evaluation.
5. Define the Khmer dialogue style target.
