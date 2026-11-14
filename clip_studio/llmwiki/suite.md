---
status: SOURCE-DERIVED
curated: 2026-11-13
---
# Clipping this suite's own finished work (`clips_from_studio`)

Opens a finished podcast episode, lesson video or narrated tutorial as a Clip Studio project, so "make three shorts from my last
podcast episode" works. Code: `clip_studio/suite.py`. It reads only what each part recorded in its own plugin-data folder.

## Request flow

1. `clips_from_studio` with no arguments (or `part`): lists finished items, newest first: id, part, title, date, length, `media_path`,
   `captions_path`, a note.
2. Ask the user which one (unless they said "my last episode": the first row).
3. `clips_from_studio` with `item_id`: opens it as a project. Captions become the transcript when the part wrote them. Then the usual flow:
   `clips_outline`, `clips_transcript`, `clips_propose`, show, `clips_cut`.

## What each part records (and what is listed)

| Part | Where | Listed when | Media | Captions |
|---|---|---|---|---|
| podcast | `creator-studio-podcast/projects/<id>/project.json` | `phase` is `assembled`; `result.audio_path` is `assembled-<hex>.wav` in that folder | audio only | `captions.srt` in the same folder, written by `podcast_episode_files` (one speaker-labelled cue per sentence from measured turn times; not word-aligned). Without it: no transcript. |
| lesson | `creator-studio-youtube/projects/<id>/project.json` | `phase` is `assembled`; `result.video.output_path` is `<hex>.mp4` in `creator-studio-youtube/` | video | `captions.srt` in the project folder. The captions are already burned into the lesson video: cut with captions none or file. |
| tutorial | `creator-studio-tutorial/<job>/narrated-<hex>.json` | the receipt says `state: complete` and `narrated-<hex>.mp4` exists | video | `narrated-<hex>.srt` (segment level). |

File names are rebuilt from the recorded ids and must sit directly in the part's own folder (no links, no other paths, not empty). Shorts
and clips a part rendered without recording them in a project are not listed; give those to `clips_open` as `media_path`. The mixed audio
of `podcast_mix` is also not recorded by the part, so it is not listed.

Item ids: `podcast:<project id>`, `lesson:<project id>`, `tutorial:<job id>:<narrated id>`. Any other text is refused.

## Audio-only items (podcast episodes)

The result says so (`audio_only`). Every clip is cut as an MP4 video: a plain dark picture with the clip title and a moving waveform
(Pillow draws the picture, FFmpeg `showwaves` draws the wave), 1080x1920 vertical, 1080x1080 square or 1280x720 source. Captions can be a side
SRT or burned in. There is no face to follow, so `clips_frame` and `clips_face` do not apply. A recording of your own that is audio only and
opened with `clips_open` still gives an `.m4a` for source and refuses vertical and square, as before.

## Notes

- Opening the same item twice returns the same project; an existing transcript is kept, not replaced.
- Times in the transcript of an episode come from the script, not from the speech. Tell the user cut points can be off by a fraction of a second.
- Nothing is published or uploaded.
