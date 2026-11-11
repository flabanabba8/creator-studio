# Youtube Video Studio

> **Part of Creator Studio.** This is the original README of the stand-alone plugin, kept as the detailed reference for this part. Its install lines apply to the stand-alone plugin only; install `creator-studio` instead. Paths such as `llmwiki/` and `skills/` here are inside this part's folder.

Turn a research topic into a narrated video, creating its stills, illustrations, diagrams, charts, tables, slides and presentation materials with available native tools.

**At a glance**

- **Install:** `hermes plugins install flabanabba8/youtube-video-studio`, then `hermes plugins enable youtube-video-studio`.
- **Needs:** Hermes 0.22 or later, FFmpeg, Python Pillow (installed from the manifest). Speech and pictures come from tools you choose (for example Gemini speech through your own Google Cloud login, or an image tool already in your Hermes).
- **Internet:** Research uses your Hermes web tools and a page reader; Gemini narration, if you choose it, sends narration text to Google. Rendering is local. Nothing is uploaded or published.
- **Limits:** Linux is the only platform checked. It makes the video file; it does not upload it to YouTube. Picture and narration quality depend on the tools you select.
- **Credits:** Narration and images come from the services you choose; their terms apply. Licence: GPL-3.0-or-later.
- **AI assistance:** Written with AI coding assistants (Anthropic Claude and OpenAI Codex agents) under the maintainer's direction; what was actually tested is listed in VERIFICATION.md.

Read the [setup/task guide](llmwiki/task-guide.md) and [skill](skills/create-youtube-video/SKILL.md) for the production workflow, resource choices and observable acceptance.

## Supporting tools and detailed limits

A Hermes skill for source-backed video planning, paired with an offline tool that checks supplied chapter and caption timing and prepares a contiguous chapter block plus WebVTT and SRT captions. It draws on Breach Protocol's listener-first editorial and timed-production practices without assuming its characters or assets. It renders either a selected still image or up to six video clips with narration and optional selectable captions to 1–120 second MP4 segments using one CPU encoder thread. It can join up to 60 compatible segments identified in plugin storage into a longer private MP4. It does not access YouTube, verify platform eligibility, or publish.

Supply a measured `duration` in seconds, either no chapters or at least two `chapters` (each span at least 5 seconds) with `start` and `title`, and `captions` with `start`, `end`, and `text`. The timeline tool checks chapter spacing and caption bounds; it cannot verify that supplied times match media or that captions are accurate.

The chapter constraints follow [YouTube’s current chapter instructions](https://support.google.com/youtube/answer/9884579); correct formatting does not guarantee channel or video eligibility.

Example `youtube_check_timeline` input:

```json
{"duration":45,"chapters":[{"start":0,"title":"The finding"},{"start":15,"title":"How it works"},{"start":30,"title":"Limits"}],"captions":[{"start":0.5,"end":3.5,"text":"Here is the finding."}]}
```

The returned `chapters_description`, `captions_webvtt` and `captions_srt` are drafts. The selected timing values must come from the finished video, and caption accuracy must be checked against its audio.

Caption text is treated as literal text in WebVTT. SRT readers differ in their
interpretation of angle brackets; `srt_markup_warning` flags such text for
display review in the intended player. Caption styling is not supported.

For `youtube_render_still`, select trusted local PNG/JPEG and WAV/MP3/M4A files, provide duration, optional chapters and captions, and review the output. The narration must cover the selected duration. Each image or video input is limited to 512 MiB, while the audio input is limited to 2 GiB so longer mixed WAV files can be used. Each render has a 120-second execution timeout (with separate bounded metadata probes), so slow machines may need shorter outputs. The plugin requests removal of global source metadata and chapters, checks output streams and duration, compares input identity, size and modification time around the render, stores the MP4 privately, and makes no upload. Inspect all output metadata for residual personal data before sharing. Media under the active profile plugin-data directory requires explicit `allow_profile_media`; other profile configuration is blocked. A still image is the entire visual track for that mode. `youtube_render_clips` accepts 1–6 trusted local clips as `{path, seconds}` objects; each must cover its selected segment, and source clip audio is omitted in favor of the supplied audio, which may already contain an authorized music mix. The plugin does not mix music itself; optional Podcast Studio can prepare a local narration/music mix. Both render modes require visual, listening and rights review. Original stills/illustrations can be created separately with the selected native image tool and attached.

For longer videos, render separate segments with explicit `audio_start` offsets and, for clips, optional `{path, start, seconds}` selections. Each segment remains limited to 120 seconds and returns a `segment_id`. Its caption cues are relative to the start of that segment; clip and audio offsets are relative to their respective source files. `youtube_stitch_segments` joins 1–60 video-compatible IDs (at most two hours and 2 GiB of segment input) with a 120-second overall time limit. It stream-copies video and encodes one explicitly selected original or mixed audio file once; segment audio, subtitles and chapters are omitted. Supply the same intended audio timeline used when making the segments. It keeps the source segments and reports estimated segment boundaries from metadata. Encoding and segment metadata can still introduce timing differences; inspect and listen to the final video and prepare final-timeline SRT/VTT and chapter metadata separately. Long-form performance and audiovisual quality have not been verified.

For a later segment of a longer video, example `youtube_render_clips` arguments
are:

```json
{"clips":[{"path":"/path/to/clip.mp4","start":120,"seconds":60}],"audio_path":"/path/to/narration.wav","audio_start":120,"chapters":[],"captions":[]}
```

Keep the returned `segment_id` from each render and pass the IDs in order, together with the explicitly selected original `audio_path`, to `youtube_stitch_segments`. Captions sent to an individual render use times
relative to that segment; prepare captions and chapters again for the joined
video because the join omits those tracks.

Rendering and stitching use POSIX or Windows file locking. Synthetic Linux and Windows checks passed for still/clip segments and an original-audio join; Windows ACLs, real media and perceptual quality remain unverified. Timeline formatting does not use the lock.

## Shorts and descriptions

`youtube_render_short` cuts a 1-60 second 1080x1920 vertical clip from one explicitly selected local horizontal video, with an optional header, footer and burned caption cues (cue times are relative to the short). `youtube_description` assembles a blurb, chapter block, deduplicated sources and footer into plain text of at most 5,000 characters (our own bound; check the platform's current limits). Both are CPU-only, local and private; nothing is uploaded. The renderer verifies size, duration and streams only.

## Slides without a video model

`youtube_make_slides` (needs Pillow, declared as a plugin dependency) turns a text outline into plain 1920x1080 slide images; `youtube_render_slides` turns 1-12 stills into a CPU-only narrated 1280x720 MP4 with optional slow zoom or pan and returns a segment ID that `youtube_stitch_segments` can join. No GPU or video model is involved.

## Graphic input provenance

For `youtube_make_visual`, put the data fields in `data` and describe their origin in `provenance`. For example:

```json
{"kind":"flowchart","title":"Plan a lesson","data":{"nodes":[{"id":"a","label":"Research"},{"id":"b","label":"Review"}],"edges":[{"from":"a","to":"b"}]},"provenance":{"kind":"illustrative","note":"Conceptual teaching sequence, not measured research data"}}
```

`provenance.kind` accepts `sourced`, `measurement`, or `illustrative`; `note` is required. Flowcharts use unique node IDs and directed `from`/`to` edges without cycles. An illustrative label does not turn invented values into research evidence.

## 0.2.2 (2026-11-10): returning to earlier work, clearer research gates

Found by real owned Hermes runs: a returning user could not continue an earlier project because no tool listed projects; a mistyped project ID silently saved nothing; error pages were saved as sources; and a script using `sources` instead of `source_ids` got a misleading error.
- `youtube_project_status` with no `project_id` lists existing projects (ID, topic, phase, counts), newest first.
- A wrong or mistyped project ID returns an error listing the existing IDs.
- Pages with HTTP status 400 or above, and short pages that say "page not found", are not saved as sources (`page_unavailable`).
- A factual section without `source_ids` gets a message naming the exact key.
- Material from the Hermes profile cache is refused with a message saying to save it in the task folder or plugin data folder.
- Camoufox reader: guard against the Playwright pageError crash, stdout isolation, and a hard deadline.
- Skill and wiki: plain-language rule and a three-source research rule.
- Attaching the exact same file again (same SHA-256 and kind) reuses the existing material instead of adding a second copy (found when a returning session re-attached a take that was already in the project).

## 0.2.7 (2026-11-10)

Start-of-project discovery of a local speech server; see VERIFICATION.md.

## 0.2.6 (2026-11-10)

The skill lists the working folder first; see VERIFICATION.md.

## 0.2.5 (2026-11-10)

Source research finds an installed Camoufox by itself; see VERIFICATION.md.

## 0.2.4 (2026-11-10)

Assembly adds burned-in captions with SRT/VTT files, gentle motion on the pictures and chapters; see VERIFICATION.md.

## 0.2.3 (2026-11-10)

Skill and wiki now say how a returning session finds its project, attaches existing recordings and reviews pictures before assembly. Offline dry run on a copy of a real earlier project: list projects, attach six recordings (take 1 reused), six numbered slide pictures with review notes, assemble -> 78.16 s h264/aac mp4 (ffprobe).

## 0.2.8 (2026-11-10)

- `youtube_narrate` records the whole script with a speech server on this computer by itself: one request per turn, 60 words or fewer, no rerolls, raw takes kept, voice sample sent by the plugin (no allow-list path guessing).
- Assembled slides no longer zoom or pan: the slow motion cropped titles at the left edge and shrank table text. `youtube_render_slides` can still be asked for motion explicitly; use it only on pictures without text.

## 0.2.9 (2026-11-10)

- Chapters now work for short lessons: at least two chapters, each at least 5 seconds. The description notes that YouTube itself shows a chapter list in the player only for three or more chapters of ten seconds or more.
- Skill: the sourced table or flowchart must be attached as the picture of the section it explains and appear in the video; beginner terms are explained on the slide; slides use visuals where they fit; the session ends with the agent's own summary and a saved description file.

## 0.3.0 (2026-11-10)

- `youtube_make_visual` takes optional `project_id` and `section_index`: the sourced table/flowchart is attached as the picture of the section it explains, so it appears in the assembled video.
- `youtube_write_script` source-ID errors now name the IDs saved in the project (or say none are saved yet) and accept an unambiguous ID prefix.
- Skill: every lesson gets a research-driven visual that appears in the video; where source IDs come from.

## 0.3.1 (2026-11-10)

- `youtube_make_slides` takes optional `project_id` and `section_indexes` and attaches each slide as its section's picture, so the default workflow never stops for a missing image tool. Skill states this plainly.

## 0.3.2 (2026-11-10)

- Flowcharts and tables are drawn to fill the frame with large text (a four-step cycle becomes a 2x2 snake grid of large boxes; one text size for the whole table).
- Burned captions get their own bottom band below the picture, so they never cover a graphic or its source line.
- Skill: keep reading until three relevant sources are used, look at each picture before attaching, list each source with what was taken from it.

## 0.4.0 (2026-11-10)

- Gemini 3.8 Flash TTS (Vertex AI, Application Default Credentials) is a supported narration route and the default when set up: `youtube_start_topic` reports `gemini_speech` (available or the reason, 30 named voices with gender and trait), `youtube_narrate` takes `engine`, `voice` and `max_usd` (default 0.50 USD spend guard), one request per spoken part (100 words or fewer), no retries, raw takes kept, usage returned and stored in `gemini-usage.json`. The Google Cloud project is read from the machine's own configuration (environment or gcloud) and is never returned or written; error text shows `<project>`. The local-server route is unchanged.
- Re-attaching a picture with a new `review_note` replaces the earlier note; assembly refuses a picture whose note still says "not yet inspected".

## 0.4.1 (2026-11-10)

- Skill: when the host has an image tool, two or three explanatory illustrations (copied into the working folder, looked at, attached as section pictures), a cycle flowchart, and enough sections for each picture; a generated picture is never a chart.

## 0.4.2 (2026-11-10)

- Skill: Gemini narration is a standing choice capped by the plugin (0.50 USD): no spending question; keep fetching until three relevant sources are read; ask only when something truly cannot be found.

## 0.4.3 (2026-11-10)

- `youtube_make_visual` kind `cycle`: 3 to 10 steps on a ring with arrows, the last leading back to the first (for the eight Moon phases).
- Slide bullets start at a large size and shrink to fit, so short slides fill the frame; slides can be paired with an illustration through `image_path`.
- Skill: three illustrations without text inside, redo once if the lit side faces away from the Sun, eight-phase cycle, no mostly empty slides.

## 0.4.4 (2026-11-10)

- Skill: a numbered checklist at the top (sources, script, three illustrations when the host has an image tool, visuals, narration, description, own summary).

## 0.4.5 (2026-11-10)

- `youtube_assemble_project` takes `image_tool_available` (required in the tool schema): when true, assembly refuses until at least two generated illustrations (review_note starting "Generated illustration:") are attached.

## 0.4.6 (2026-11-10)

- A slide with a picture gives the picture the right half of the frame; skill: phases are never Earth's shadow.
