---
status: SOURCE-DERIVED
curated: 2026-11-13
---
# Clip Studio task guide

## Before starting: resource decisions

1. Is `yt-dlp` installed? `clips_open` says so plainly if not. The user installs it themselves
   (their package manager or the project's install page); the plugin installs nothing.
2. FFmpeg and ffprobe are needed for every cut.
3. Does the video have captions? `clips_open` answers this. If not, a speech recognizer is needed:
   that is Caption Studio's interview (`captions_recognizer_setup`), and the user chooses.
4. What are the clips for? The purpose sets length (Shorts: under a minute), shape (vertical) and
   whether captions are burned in. Ask once if the user did not say.

## Worked flow

Request: "Find the three best moments in <link> for Shorts."

1. `clips_open {url}` -> project_id, title, 18:40 long, 12 chapters, transcript "written by the uploader".
2. `clips_outline {project_id}` -> 38 windows of 30 s; most replayed around 9:08 and 10:27; a 4.6 s pause at 3:42.
3. `clips_transcript {project_id, start: "8:30", end: "11:00"}` -> read the sentences; note where a thought begins and ends.
   Repeat for the other promising spots. `clips_transcript {project_id, query: "..."}` finds a phrase.
4. `clips_propose {project_id, clips: [{start, end, title, reason} x3]}` -> final times on speech boundaries,
   `opens_with`, `ends_with`, preview links. Fix any clip that opens mid-thought by proposing it again with its `clip_id`.
5. Show the three to the user; they pick two and ask for vertical with captions.
6. `clips_cut {project_id, clip_ids: ["c1","c3"], shape: "vertical", framing: "crop" or "fit", captions: "burned"}`
   -> two MP4 files and two SRT files. Report paths and lengths.

Exact request ("cut 12:30 to 13:10"): `clips_open`, `clips_propose` with `exact: true`, `clips_cut`.

## Failure diagnosis

| What you see | Cause | What to do |
|---|---|---|
| "yt-dlp was not found" | Not installed or not on PATH | User installs it or sets `clip_ytdlp`; or opens a local recording with `media_path` |
| "YouTube asked for a sign-in" | Bot check, age or region gate | Not supported (no cookies or sign-in are used); the user downloads the video and opens it with `media_path`; do not ask for credentials |
| "not available to you" | Private, removed, members-only | Nothing to do without access; say so |
| "YouTube could not be read ... update yt-dlp" | YouTube changed, yt-dlp is old | User updates yt-dlp |
| `no_captions` in the open result | No uploader or recognized captions | `clips_transcribe` (user's recognizer) or `clips_use_transcript` |
| "came out N seconds long instead of M" | Section fetch was cut short | Run `clips_cut` again for that clip; nothing partial is kept |
| Clip opens or ends mid-sentence | Unpunctuated recognized captions | Read around it and propose again with `clip_id`; use `exact: true` only for user-given times |
| Edges of the picture missing in a vertical clip | Centre crop of slides or screen content | Cut again with `framing: "fit"` |
| No dead air removed, `dead_air` says the voice is not clearly louder than the background | Loud music or game sound under the voice | Use `skip` spans for the slow parts instead |
| Dead air removed but the clip still feels slow | Pauses shorter than `max_pause`, or filler talk | Lower `max_pause` to 0.5, or mark filler with `skip` |
| "Nothing much is left" | Skips and pauses remove almost the whole clip | Propose a longer clip or fewer skips |
| Streamer or avatar missing or cut off in a vertical clip | No face box saved, or the avatar moved in this scene | `clips_frame` for that clip, `clips_face` (or `face` in `clips_cut`), cut again, look at a frame of the result |
| "project is busy" | Another cut or download of the same project is running | Wait for it |

## Acceptance criteria (observable)

- Every delivered clip exists at the reported path, plays, has picture and sound, and its length matches the proposal within 1 second.
- Each clip starts on the first word of `opens_with` and ends after the last word of `ends_with`.
- For a streamer or VTuber video, every vertical or square clip shows the face, confirmed by looking at a frame of the finished clip.
- The user chose the clips, the shape and the caption style; nothing was cut before they answered (unless they gave exact times).
- The answer names where the transcript came from and reminds the user to watch the clips; nothing was uploaded.
