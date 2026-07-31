# Playback

Playback owns Studio preview transport and real-time audio/video coordination.

Related documents:

- [TIMELINE.md](TIMELINE.md)
- [APPLICATION.md](APPLICATION.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)

## Code Ownership

- `automatedub_studio/playback/playback_controller.py`
- `automatedub_studio/playback/video_player.py`
- `automatedub_studio/playback/timeline_audio.py`

## Responsibilities

- Keep video visual-only and muted.
- Use the video/timeline position as the preview clock.
- Evaluate active audio clips from the current `Timeline`.
- Play active audio clips on unmuted, unsoloed/solo-respecting audio tracks.
- Reuse media player objects where practical.
- Avoid continuous seeking during normal playback drift.
- Support frame stepping, previous/next segment jumps, playback speed, looped selection playback, and clip audition as separate transport concerns.

## Playback Source Of Truth

Playback consumes:

```text
Timeline
    -> active audio tracks
    -> active TimelineClip objects at playhead
    -> QMediaPlayer / QAudioOutput
```

Playback must not use imported segment ordering, `EditableSegment`, `MixSpeechTrack`, or legacy playback modes as the live preview source.

## Reference Tracks

Reference-only tracks may exist in the Timeline for visual/audio context. Playback discovery should respect track metadata and avoid treating non-playback reference tracks as editable dialogue sources.

## Transport

- Play/Pause toggles from the current playhead.
- Stop halts playback and seeks to zero.
- Frame stepping advances the master clock by one video frame.
- Previous/Next Segment seek to the adjacent clip boundary.
- Timeline/ruler scrubbing updates the playhead and preview position.
- Loop selection replays the selected timeline range.
- Double-click audition plays one clip in isolation and is not required for normal timeline playback.

## Non-Responsibilities

- Playback does not write project artifacts.
- Playback does not generate TTS.
- Playback does not perform export mixing.
- Playback does not mutate clip text or edit metadata.

## Future Guidance

- Keep timing correction conservative.
- Treat media player position as approximate during normal playback.
- Add tests when changing player reuse, source loading, or seek policy.
