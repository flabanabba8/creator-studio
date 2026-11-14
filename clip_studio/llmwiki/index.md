---
status: SOURCE-DERIVED
curated: 2026-11-13
---
# Clip Studio wiki

Clip Studio reads a YouTube video or finished stream through its transcript, records suggested clips,
and cuts the ones the user picks. Tool names start with `clips_`. Skill: `clip-youtube-video`.
Tool texts: [suite tool reference](../../llmwiki/tools.md). Task guide: [task-guide.md](task-guide.md).

## What is implemented, and how

| Step | Tool | What actually happens |
|---|---|---|
| Open | `clips_open` | `yt-dlp -J` reads the video page; one caption track is saved (uploader captions first, else YouTube speech recognition in the spoken language, json3 with word times). No media is fetched. A local recording is probed with ffprobe instead. |
| No captions | `clips_transcribe`, `clips_use_transcript` | Audio track only (m4a) is fetched once, cut into pieces of about ten minutes at quiet points, and each piece goes to Caption Studio's `captions_generate` with the user's chosen recognizer. Word times are shifted back to video time, saved per piece, and attached as a partial transcript until the last piece. An interrupted run resumes. See [recognize.md](recognize.md). |
| Analyse | `clips_outline`, `clips_transcript` | Pure text work on the saved transcript: time windows, chapters, YouTube's most-replayed curve, pauses, caption sound markers, frequent words; paged reading and phrase search. No model is called; the host model does the judging. |
| Suggest | `clips_propose` | Stores clips; each edge is moved to the nearest sentence end/start within 2.5 s (else nearest word within 1 s) and padded by at most 0.15 s before and 0.25 s after, never into a neighbouring word. |
| Cut | `clips_cut` | YouTube: `yt-dlp --download-sections` with `--force-keyframes-at-cuts` fetches and encodes only that span (H.264/AAC MP4). Local file: one FFmpeg encode. Vertical/square/burned captions are a second local FFmpeg pass. Result length is checked with ffprobe. |

| Tighten | `clips_propose` (`skip`), `clips_cut` (`remove_pauses`) | Skips are stored per clip at sentence edges. Pauses: the clip's sound is read in 50 ms loudness steps; the bed is the quiet tenth, the voice level the middle of the steps inside transcript words; steps in the lower third between them are quiet; quiet runs longer than `max_pause` that touch no transcript word are removed, keeping 0.15 s on each side. If voice and bed are under 6 dB apart nothing is removed. Kept spans are joined with trim/concat (picture and sound cut at the same instants) and caption times are shifted by what was removed before them. |

| Face in view | `clips_frame`, `clips_face` | One second of video is fetched and a still saved plain and with a 10 percent grid (drawn with Pillow). The host model looks at it and saves a box in percent. Vertical/square cuts then use it: box under 30 percent wide = FFmpeg split, crop of the box widened to the panel's proportions, scaled to full width (a quarter to two fifths of the height), stacked over the rest; wider box = one crop of the output's proportions centred on the box. |

| Follow the face | `clips_cut`, `clips_face_ranges` | The saved box's look is compared through the clip (Pillow only, no detector model); layouts switch where it moved, and a stretch with no match is shown whole. See [tracking.md](tracking.md). |

| Audience | `clips_chat` | `yt-dlp` fetches the chat replay of a finished stream once; it is reduced to rates, spikes and paid messages and matched to the transcript. The raw replay is deleted. See [chat.md](chat.md). |

| Reel | `clips_join` | Cut clips are joined with FFmpeg's concat filter, with optional title cards, a chapter list and a combined caption file. See [reel.md](reel.md). |

| Post | `clips_post_facts`, `clips_post_save` | Facts and candidate thumbnail frames for a clip; saves the model's title, description and tags with a forced source credit. Nothing is uploaded. See [publish.md](publish.md). |

| Own work | `clips_from_studio` | Lists and opens finished podcast episodes, lessons and tutorials of this suite. See [suite.md](suite.md). |

## Facts worth knowing before acting

- Transcript quality decides clip quality. Uploader captions are usually correct but timed per line;
  YouTube speech recognition is timed per word but misspells names and has little punctuation in
  older videos (then sentences fall back to pauses and a 20 second cap).
- The most-replayed curve exists only on videos with enough views; its first seconds are always
  high and are ignored in the peak list.
- yt-dlp is the user's own program, found on PATH or set by the owner (`clip_ytdlp`). YouTube changes
  often; an outdated yt-dlp is the usual cause of sudden failures. The plugin never updates it.
- yt-dlp needs a JavaScript runtime for full YouTube support (Deno by default; the plugin passes
  `--js-runtimes node` when only Node is installed). Without one, speech-recognized tracks may come
  as VTT instead of json3; both are parsed.
- A sign-in check ("confirm you are not a bot") cannot be passed: Clip Studio never uses browser
  cookies or a sign-in. The user can download the video themselves and open it with `media_path`.
  Never ask for cookies, passwords or tokens in chat.
- Live: a finished stream is an ordinary video once YouTube has processed it. A stream still on air
  has no finished captions and section downloads are unreliable; the plugin refuses to cut it.
- Limits: one video per project, clips of 2 seconds to 15 minutes, 10 clips per cut call, 60 per project,
  picture height up to 1080.

## Evidence limits

Live-checked on Linux on 2026-11-13 with yt-dlp 2026.08.19 (see the suite VERIFICATION.md): opening a
video with uploader captions, outline, reading, search, proposing, cutting as filmed and vertical
with burned captions, a 57 s clip with one skipped stretch and pause removal, and a recognizer check that
each clip starts and ends on the intended words and that the trimmed clip's speech runs on correctly.
Not checked: a stream on air, `clips_transcribe` through a real recognizer,
a run through a Hermes session, Windows and macOS.
