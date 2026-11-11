# Verification

> **Part of Creator Studio.** This is the stand-alone plugin's own verification record. The evidence in it belongs to that plugin; see the suite's VERIFICATION.md for what was checked on the bundle.

- Mixed-case private-directory boundaries were checked using synthetic paths on Linux and native Windows; no real credentials were used.

- An initial native Windows check exposed the POSIX-locking limitation. After adding Windows locking, Python 3.14 and FFmpeg rendered synthetic still and clip segments, retained a segment subtitle, joined video with one original audio track, omitted joined subtitles and preserved tested tone transitions. Paths with spaces and an apostrophe worked, and a separate process was refused while the lock was held. A synthetic Podcast Studio mix also passed through the join. No audio or video was perceptually reviewed; Windows ACLs, real footage and broader Windows coverage remain unverified.

- Literal WebVTT caption text escapes markup characters; an FFmpeg synthetic MP4 mov_text mux and decode preserved a comparison containing angle brackets and an ampersand. SRT angle brackets are flagged because readers differ in how they interpret them. Captions still require display and timing review in the intended player.

- Unit checks cover chapter formatting and bounds, caption ordering and overlap, non-finite duration, and malformed titles.
- Hermes manifest validation, Plugin Doctor, and actual runtime skill discovery passed.
- A private CPU-only fixture generated WebVTT captions, muxed them with a synthetic video using ffmpeg, and confirmed video, subtitle stream and duration with ffprobe. No visual or audio quality review was performed.
- A synthetic 30-second still-image, silent-audio and caption render passed stream and duration checks using one CPU encoder thread; its visuals and audio were not reviewed. The plugin does not verify claims or interact with YouTube. Platform eligibility and release readiness remain unverified. This candidate is not a completed contest submission.
- A synthetic two-clip CPU sequence with narration and captions passed stream and duration checks; an insufficiently long clip was rejected. The output was not visually or audibly reviewed.
- Synthetic SRT output was imported and retimed by the separate Caption Repair plugin; actual speech alignment was not tested.
- Synthetic five-second still-image and clip exports without chapters passed metadata checks; no visual or audio review was performed.
- A synthetic two-segment join selected later clip and audio offsets, preserved tested video order and audio signal positions using one original audio track, and rejected incompatible video formats. Paths containing an apostrophe and timeout cleanup were tested. This is not a long-form, audiovisual-quality or synchronization certification.
- A temporary CPU-only ten-minute black-video/silence fixture rendered five two-minute segments and joined them with expected reported duration and estimated boundaries. It does not measure realistic footage performance, audiovisual quality, caption coverage or synchronization.
- A sparse synthetic 50-minute WAV larger than 512 MiB was accepted under the audio-only 2 GiB limit, and a late segment rendered successfully. This does not establish real-episode performance or playback quality.
- A ten-segment synthetic check confirmed selected original-audio transitions stayed within 50 ms of the intended times and video order was preserved. A previous stream-copy-audio approach showed a 376 ms shift on a low-sample-rate fixture and was replaced. No perceptual, full-length or universal synchronization guarantee is implied.
- A separate CPU-only integration mixed an existing fictional six-second PageCast export from an earlier live Inworld/Flite test, rendered two still segments and joined them using the mixed audio once. No new provider request, playback or perceptual review occurred.
- A separate two-segment synthetic still-image join used one selected original tone file and produced one audio stream. Frames sampled at 0.5 and 1.5 seconds were visually inspected and showed the expected red-then-blue order. No audio was played; this is not a real-footage, full-timeline or audiovisual-quality review.

- 2026-11-07: added `youtube_render_short` and `youtube_description`. A synthetic 1280x720 source rendered to a 1080x1920 cut; pixel checks found the header, footer and burned caption inside their expected bands and nothing stray above the picture. Range, text and caption validation, timeout cleanup (no partial or text files left) and description assembly are tested; 21 tests pass in the Hermes venv. Not checked: real footage, phone legibility, human review of picture or sound, other fonts or platforms, Windows. No upload.

- 2026-11-07: added `youtube_make_slides` and `youtube_render_slides` (CPU-only, no video model). Tests check 1920x1080 output, text drawn inside the margins, theme difference, the picture scaled into its box, overflow rejection, slide order and cut timing, a zoom measurably enlarging a shape over time, cleanup of partial files, and an outline-to-narrated-video run. 26 tests pass in the Hermes venv. Not checked: real artwork, fonts other than DejaVu, readability on phones, human review, Windows.
- 2026-11-07: end-to-end kids-story trial (Benny the Bear, 6 scenes, 106.9 s, local Flite draft voices, Pillow placeholder art): lint preset kids clean, review gate passed, slide video with zoom/pan, chapters, soft captions, description and a 20 s 1080x1920 Short rendered. A programmatic frame check found the first build clipped titles at the top during zoom; titles were moved into the safe area and rechecked at every scene start and end. Narration measured -20.2 LUFS (no loudness target applied). Nobody has watched or listened to it; the art is crude placeholder drawing; the voices are robotic drafts.
- 2026-11-07: `youtube_stitch_segments` accepts `audio_pad_seconds` (0 to 10) which appends silence to the supplied audio so the picture may outlast the narration; found when a Hermes agent run failed to stitch a closing slide that ran 0.8 s past the narration. Test: a 7.8 s join of a 7.0 s audio fails without padding and passes with 1 s. 27 tests pass.
- 2026-11-07: slide maker gained a `terminal` theme and an optional `code` block (monospace, up to 30 lines of 120 characters, auto-shrunk to fit, rejected if it cannot fit) so tool calls and real results can be shown as terminal-style slides. Pixel test checks the dark code box and drawn text; 28 tests pass.
- 2026-11-07: `youtube_render_slides` gained `burn_captions` (captions drawn into the picture instead of a soft subtitle track, so they show on autoplay-muted social video). Test: no subtitle stream in the output; caption pixels appear in the bottom band while a cue is active and are gone afterwards. 29 tests pass. Used by a private demo maker to make silent captioned plugin demos; OCR of frames from two of them read the titles, tool names, arguments and captions correctly.

## 2026-11-10 maintained scope revision

Thirty-three offline/mocked tests pass, including actual FFmpeg fixture video assembly, source-read gating, provenance-bearing charts/tables/flowcharts, invalid-data rejection and native-image refusal/context preservation. No live native image provider or paid speech call was made merely to test wiring. End-to-end real researched lesson quality remains a separate review. Hermes admission and retirement preflight pass; detailed local receipts are retained in the contest maintenance evidence. Old evidence above keeps its original scope.

2026-11-10: A real owned Hermes creation job exposed missing provenance-field guidance. Registration now describes each data shape and explicitly requires provenance.kind (sourced/measurement/illustrative) and note. After inspecting the existing native source contract, one corrected real flowchart call succeeded; prior malformed calls produced no image and remain in evidence. Main-session review confirmed three native illustrated slides and the successful three-node flowchart. No image model, worker, speech generation, private install or publication was used for these lesson assets.

## 0.2.2 (2026-11-10): returning to earlier work, clearer research gates

Found by real owned Hermes runs: a returning user could not continue an earlier project because no tool listed projects; a mistyped project ID silently saved nothing; error pages were saved as sources; and a script using `sources` instead of `source_ids` got a misleading error.
- `youtube_project_status` with no `project_id` lists existing projects (ID, topic, phase, counts), newest first.
- A wrong or mistyped project ID returns an error listing the existing IDs.
- Pages with HTTP status 400 or above, and short pages that say "page not found", are not saved as sources (`page_unavailable`).
- A factual section without `source_ids` gets a message naming the exact key.
- Material from the Hermes profile cache is refused with a message saying to save it in the task folder or plugin data folder.
- Camoufox reader: guard against the Playwright pageError crash, stdout isolation, and a hard deadline.
- Skill and wiki: plain-language rule and a three-source research rule.

Checks for 0.2.2 (2026-11-10): 38 offline tests pass (new: status listing, wrong-ID hint, reader guard); tools/check-plugin-workflows.py ok on the package; offline dry check on a copy of a real earlier project: list projects, attach six slide images and five narration WAVs from the task folder, assemble (78.16 s, 6 slides). Live results are kept in the maintainer's private evidence folder, which is not part of this repository.
- Attaching the exact same file again (same SHA-256 and kind) reuses the existing material instead of adding a second copy (found when a returning session re-attached a take that was already in the project).

## 0.2.7 (2026-11-10)

- A first-time run stopped after the script: it could not tell how to call the local speech server (its API file does not list the request fields) and ended its turn with a status. `youtube_start_topic` now reports `speech_servers` (read-only loopback probe for a `/v1/audio/speech` route, with a working request shape; a cache-path model id is shown as org/name) and a reminder that one request covers the finished video. Test added (local stub server); the real narration is checked only by the demo run.

## 0.2.6 (2026-11-10)

- A first-time run searched the whole home folder for the user's "voice folder" instead of listing its working folder, then asked the user for a sample that was there. The skill now starts by listing the working folder and says not to search wider for files the user mentions. Text-only change, checked by the demo run.

## 0.2.5 (2026-11-10)

- A first-time run could not read full pages: `youtube_research_fetch` demanded the Camoufox Python and browser paths, so the agent fell back to short search snippets as sources. Both arguments are now optional: `discovery.py` finds an installed Camoufox (a Python that imports it plus the browser in the standard cache folder; bounded, read-only, nothing launched) and `youtube_start_topic` reports it as `research_tools`. The skill now requires a table or flowchart for ordered/cyclic/comparative lessons and says reference-voice links show with `ls -l`/`find -L`. One new test; the real page read is checked only by the demo run.

## 0.2.4 (2026-11-10)

- `youtube_assemble_project` (video) now also returns measured-time captions (burned in, plus SRT/VTT files in the project folder), gentle zoom/pan motion on each section picture and whole-second chapters when the sections allow. The skill now says pictures, captions and a description are part of a finished video and how to find a named speech server. Tests: `test_assembly_writes_measured_captions_chapters_and_moves_the_pictures` and `test_caption_cues_follow_turn_times_and_chapters_need_three_long_sections`; 41 tests pass offline. Caption sync was checked only from measured audio lengths, not by listening.

## 0.2.3 (2026-11-10)

Skill and wiki now say how a returning session finds its project, attaches existing recordings and reviews pictures before assembly. Offline dry run on a copy of a real earlier project: list projects, attach six recordings (take 1 reused), six numbered slide pictures with review notes, assemble -> 78.16 s h264/aac mp4 (ffprobe).

## 0.2.8 (2026-11-10)

New offline tests (tests/test_narrate_and_static_slides.py): narration against a local fake server (request count, reference data URI, order, raw takes kept, resume without rerolls, 60-word and loopback refusals) and a decoded first/middle/last frame check that content touching the left edge is not cropped. Full folder: 48 tests pass. No live speech or model request in these tests.

## 0.2.9 (2026-11-10)

Chapter rule test updated (two chapters, 5 seconds) and the description note covered by the full folder run. Text-only skill changes are not machine-tested.

## 0.3.0 (2026-11-10)

Offline tests added for the source-ID error (none saved, wrong ID lists the real ones, unambiguous prefix accepted) and for a drawn visual becoming its section picture. The make_visual attach path itself (needs the Hermes storage helper) is covered by the live run only.

## 0.3.1 (2026-11-10)

Offline tests: slide images attach to sections and the tool schema/skill carry the new rule. The in-tool attach path itself (needs the Hermes storage helper) is covered by the live run only.

## 0.3.2 (2026-11-10)

New offline tests: flowchart/table fill the frame with large text (measured box coverage and stroke height; the old layout covered about 8% of the frame against a 22% threshold) and a decoded frame shows the caption band does not cover picture content. Full folder: 54 tests pass.

## 0.4.0 (2026-11-10)

Mocked-transport tests (tests/test_gemini_route.py): one request per part with a named voice, ledger and token usage, no project id in results, no rerolls on resume, spend guard before any request, rejected request not retried and project replaced with <project>, unavailable reason, review-note rewrite and the assembly gate. Full folder: 61 tests pass. No live Gemini request in these tests.

## 0.4.1 (2026-11-10)

Text-only skill change; a five-node cycle flowchart was rendered with the large layout without error. Illustration flow is verified only by the live run.

## 0.4.2 (2026-11-10)

Text-only skill change after a live run stopped to ask for a spending limit and finished with two sources.

## 0.4.3 (2026-11-10)

Tests: cycle of eight draws large boxes with the accent first box and rejects fewer than three steps; short slides reach below 55% of the frame height. 63 tests pass.

## 0.4.4 (2026-11-10)

Text-only skill change after a live run found the image tool but did not use it.

## 0.4.5 (2026-11-10)

Test: with the image tool available assembly is refused until two generated illustrations are attached, and passes when no image tool exists. 64 tests pass.

## 0.4.6 (2026-11-10)

Test: the picture on a slide starts at the middle and spans at least 40% of the width. 65 tests pass.
