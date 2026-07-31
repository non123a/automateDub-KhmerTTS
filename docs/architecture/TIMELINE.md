# Timeline

The Timeline subsystem owns live editor state: tracks, clips, selection, playhead state, layout, and edit commands.

Related documents:

- [APPLICATION.md](APPLICATION.md)
- [PROJECT_SYSTEM.md](PROJECT_SYSTEM.md)
- [PLAYBACK.md](PLAYBACK.md)
- [EXPORT.md](EXPORT.md)

## Code Ownership

- `automatedub_studio/timeline/timeline_clip.py`
- `automatedub_studio/timeline/timeline_widget.py`
- `automatedub_studio/timeline/clip_item.py`
- `automatedub_studio/timeline/state.py`
- `automatedub_studio/timeline/ruler_widget.py`
- `automatedub_studio/timeline/waveform_cache.py`
- `automatedub_studio/timeline/waveform_renderer.py`
- `automatedub_studio/edit/commands.py`

## Model

```text
Timeline
    -> TimelineTrack[]
        -> TimelineClip[]
```

`TimelineClip` is the live source of truth during editing. It owns clip identity, track, timing, source path/window, mute/volume, lock state, text metadata, voice settings, and selection state.

## Initial Track Layout

```text
Video
Original Movie Audio
Original Speech Segments
Khmer TTS
Draft Regeneration
Audio Track 3
Audio Track 4
```

Reference tracks are read-only. Khmer TTS and Draft Regeneration clips remain editable.

## Responsibilities

- Own track and clip models.
- Draw track headers, clips, waveform previews, ruler, and playhead.
- Manage clip selection and marquee/range selection.
- Apply move, trim, mute, copy/paste, duplicate, and split commands where allowed.
- Emit changes when the Timeline model mutates.
- Persist through project timeline edit serialization.

## Reference Clip Rules

Original Movie Audio and Original Speech Segments:

- can be selected
- can open the inspector
- can provide text/audio reference
- cannot move, trim, regenerate, delete, or change duration

Blocked edit attempts emit a non-modal read-only status signal.

## Non-Responsibilities

- Timeline does not perform TTS generation directly.
- Timeline does not decode audio for playback.
- Timeline does not export final media.
- Timeline does not use `Segment` or `EditableSegment` as live edit state.

## Playback Relationship

Playback consumes the `Timeline` model. It must not rebuild playback from transcript ordering or legacy speech-track lists.

See [PLAYBACK.md](PLAYBACK.md).

## Future Guidance

- Add timeline features by extending `Timeline`, `TimelineTrack`, and `TimelineClip`.
- Preserve one source of truth for edits.
- Keep rendering helpers separate from clip model logic.
- Add commands for undoable mutations.
