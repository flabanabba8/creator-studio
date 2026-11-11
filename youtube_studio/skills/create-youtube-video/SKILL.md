---
name: create-youtube-video
description: Turn a research topic into a narrated video, creating its stills, illustrations, diagrams, charts, tables, slides and presentation materials with available native tools.
---

## Checklist for a lesson video (do these in order; each is required)

1. `youtube_start_topic`, then read at least three relevant sources fully (`youtube_research_fetch`, `youtube_source_read`).
2. `youtube_write_script`: five or six sections, each with `source_ids`, spoken parts of 100 words or fewer.
3. ILLUSTRATIONS: run `tool_search` for "image_generate". If the host has it, you MUST call it three times (one picture for each of
   three sections; subjects in the section "Moon-phase style lesson" below; no text inside the pictures; one redo at most if a picture
   is physically wrong). Copy each result into the working folder, look at it with `vision_analyze`, then attach it with
   `youtube_material_add` or as the `image_path` of a `youtube_make_slides` slide next to the bullets. Skipping this step when the
   tool exists makes the lesson unfinished.
4. `youtube_make_visual` (kind `cycle` for a repeating cycle, table or flowchart for the rest), attached with `project_id` and
   `section_index`; `youtube_make_slides` with `project_id` for the remaining sections; look at every picture and re-send its note.
5. `youtube_narrate` (Gemini, no questions), `youtube_assemble_project` (set `image_tool_available` to true when `tool_search` found `image_generate`; assembly then refuses until two generated illustrations are attached, each with a review_note starting "Generated illustration:"), `youtube_description` saved to a file.
6. Finish with your own summary: video, captions and description paths, each source with what you took from it, the pictures made, the
   narration voice, requests and cost.

First list the working folder (`ls -lL`): files and folders the user mentions (a voice sample, notes, existing media) are inside it; do not search the home folder or the whole disk for them. Read the [bundled wiki](../../llmwiki/index.md). Begin with topic, audience, purpose and format, then youtube_start_topic. Research through native tools or selected installed Camoufox; preserve/read sources using youtube_source_add/source_read and write the actual sections with youtube_write_script. Reason and write in the active host.

Create materials suited to the explanation: youtube_make_visual draws real bounded bar/line charts, tables and flowcharts from explicit provenance-bearing data; youtube_make_slides creates presentation stills and notes. For photographs/illustrations/stills, use the MAIN session's native image tools directly, or youtube_generate_image only when an actual supported host-native tool has been explicitly configured. This bridge preserves original host results/refusals; no image backend or worker fallback is bundled. Review full assets, data labels and source rights before attaching them with youtube_material_add.

Narration: the default engine is Gemini 3.8 Flash TTS when youtube_start_topic reports it available (gemini_speech lists the named voices with gender and trait): call youtube_narrate with engine "gemini" and a voice name that fits the lesson (for a calm beginner lesson, a clear, friendly or informative voice such as Charon, Erinome or Sulafat); it makes one request per spoken part (100 words or fewer), keeps the raw takes, attaches them in order, keeps a 0.50 USD spend guard and returns the usage. Never print or look up the Google Cloud project; the plugin reads it from the machine's own configuration. Otherwise, when the user says a speech server is on this computer (youtube_start_topic lists the ones it finds), call youtube_narrate with the project ID, plus reference_audio and reference_text if the user keeps a voice sample (WAV and its transcript) in the working folder. The plugin sends one request per spoken turn itself (60 words or fewer each, no rerolls), keeps the raw takes, normalizes them and attaches them in order; do not write your own speech requests or shell commands for this. Keep every spoken turn to 60 words or fewer when you write the script. Slides stay still on purpose (no zoom or pan) so no title or table text is ever cropped. For another speech system, select it from user resources, normalize actual WAVs and attach one per spoken turn. youtube_assemble_project creates actual audio and slide-based video from reviewed materials. Existing still/clip/slide/short/stitch tools support more detailed editing. Export final captions, chapters, description and presentation materials, then watch/listen. A project/script/slide outline alone is not an assembled video; nothing is published.

Start from the user's intended result. Reuse known resource choices; ask missing questions only in ordinary chat. Establish hardware, available local/remote tools, subscriptions versus verified API entitlements, privacy, acceptable waiting time and maximum API spend (zero is valid). Prefer free paths that meet quality needs. A subscription does not prove API access. Save non-secret choices in the private task, never credentials. Do not silently install/download, upload private inputs, switch providers or spend money. Reason/write in the active host; no secondary reasoning API or agent worker. Images are inspected/generated/edited directly in the MAIN session using native tools. Preserve accepted work, pauses and original inputs. Publishing requires separate explicit authorization.

Research first, and show it: read at least three different legitimate sources with youtube_research_fetch (give it just the page address; the installed Camoufox runtime is found for you and the whole page is saved, so search-result snippets are never a source) and youtube_source_read (a page that returns an error or "not found" is not a source), tell the user which sources were actually read and what was taken from each, and write the script only from what was read. Where the material suits it, make a table, chart or flowchart with youtube_make_visual from facts in those sources, with provenance. Use plain language for the audience: explain or replace specialist terms (say "move your subject a little off-center" and "leave room in front of them" instead of "rule of thirds grid" or "lead room") unless the user asks for the technical words.

Before assembling, every section needs one reviewed picture: look at each slide or image with the host's image-viewing tool (for example vision_analyze), then attach it with youtube_material_add and put what you actually saw (readable text, nothing cut off) in review_note. When continuing earlier work, call youtube_project_status with no project_id to find the project, attach the user's existing recordings in script order (an identical file already attached is reused), and then assemble.

## A finished video is more than narrated text slides

Pictures, captions and a description are part of the default result, not extras.
1. Pictures: check the runtime's tool list for a native image tool; use it (and inspect each
   result) only if one really exists, otherwise say exactly that capability is missing and
   do not fake it. Never leave the lesson as plain white text slides: use a coloured
   `youtube_make_slides` theme (dark, kids or terminal), and make at least one table or
   flowchart with `youtube_make_visual` (required whenever the lesson has an order, a cycle or a comparison) from what the sources said (provenance kind
   `sourced`). Use that visual as the picture of the section it explains.
2. Speech: when the user says a speech server is on this computer, call `youtube_narrate`
   (see Narration above); it makes the one-request-per-turn recording itself, keeps the raw
   takes and attaches them. Use the voice sample and its transcript from the working folder as
   `reference_audio` and `reference_text` when one is there. Never retry a turn to pick a
   better take.
3. After `youtube_assemble_project` the result already carries measured-time captions
   (burned into the video, plus `captions_srt_path` and `captions_vtt_path`), still pictures
   (no zoom or pan, so nothing is cropped) and, when there are at least two sections of five
   seconds or more, whole-second `chapters`. Do not wait for another request to finish these.
4. Then call `youtube_description` with a plain blurb, those chapters and the sources you actually
   read, save the text next to the video, and tell the user where the video, captions and
   description are. A short vertical cut with `youtube_render_short` is optional last.

## Make the research visible, and keep the words plain (default for every lesson)

- Every lesson gets at least one research-driven visual, and it must appear in the finished video.
  Call `youtube_make_visual` with `project_id` and `section_index` (the zero-based section it
  explains, for example the section about the monthly cycle): the plugin then attaches it as THE picture of that section
  automatically. A phase table with a plain "what we see" column, or a cycle flowchart, shown full frame.
  (Without those two arguments, attach the PNG yourself with
  `youtube_material_add`.) It is THE picture of the section it explains (for a cycle or an order,
  the section that walks through it), so it appears in the finished video, full frame and
  fully legible, with the captions below it. A visual that is made but not attached is a
  defect: check that one section's picture is the visual before you assemble.
- Do not leave every slide as three bullets on an empty field. Where a table, a simple
  diagram or a picture fits a section, use it; use `youtube_make_slides` for the others.
- Any word a complete beginner would not know (for example crescent, quarter, gibbous) is
  explained in a few plain words on the slide or in a "what we see" column of the table
  (for example "thin lit curve grows"). Slide and caption wording must make sense on its own.
- Finish with your own short summary: what you made, the file paths (video, captions,
  description), the sources you read, and the video length. Save the description text in a
  file in the working folder and include the chapters and the source list in it.
- Source IDs: `youtube_research_fetch` and `youtube_source_add` return a 32-character `source_id`
  for each saved source. In `youtube_write_script` every section lists the IDs of the sources it
  uses under the key `source_ids`, copied exactly, and only after those sources were saved and read
  (do not call it in the same step as the fetches). If the tool answers with an error that lists
  the IDs saved in the project, copy from that list.
- Pictures for EVERY section, no image tool needed: after `youtube_write_script`, call
  `youtube_make_slides` once with `project_id` (one slide per section, title plus short plain
  bullets from that section; use `section_indexes` to skip the section(s) whose picture is the
  table or flowchart). The slides are attached as the section pictures for you; then look at each
  picture with the image-viewing tool and fix anything cut off or unreadable. Do NOT call
  `youtube_generate_image` and never stop because "no image-generation tool exists": slides and
  graphics are drawn by this plugin. Then `youtube_narrate`, `youtube_assemble_project`,
  `youtube_description`, and your own summary. A lesson that stops before assembly is unfinished.
- Sources: keep fetching and reading until THREE relevant sources are actually used in the
  script (a page you fetched but took nothing from, or a second copy of the same page, does not
  count). Prefer different publishers, for example a space agency, a planetarium or
  observatory, and a museum or university page. Cite them in the script's source_ids.
- Look before you attach: view every picture (slides and graphics) with the image-viewing tool
  (vision_analyze) and write what you saw in the material's review note; fix cut-off or unreadable
  text first. If you could not look at something, say so honestly in your summary.
- The finished video keeps a dark bottom band for the burned captions, so captions never cover a
  picture or its source line; graphics and slides are drawn large for this reason.
- In your final summary list each source with what you took from it.
- A slide drawn by `youtube_make_slides` carries the note "not yet inspected". After you have looked at
  it, call `youtube_material_add` again with the SAME picture file and a `review_note` saying what you
  saw: that replaces the note, and assembly refuses a picture whose note still says "not yet inspected".

## Generated illustrations (when the host has an image tool)

- Check the tool list (tool_search "image"): if the host has an image generation tool (image_generate), make two or
  three illustrations for the sections that benefit, using that tool directly as the main session. If there is none,
  say so plainly and use slides and graphics only; never fake an illustration.
- Good subjects explain a physical idea: for Moon phases, the Sun lighting half of the Moon with Earth nearby (sunlight
  must come from the Sun's side and the lit half must face the Sun), the Moon at several points of its orbit seen from
  above, or a person holding a ball beside a lamp. Ask for 16:9, simple flat style, and no words in the picture. Keep it
  to at most three images in all; do not regenerate to chase a nicer look.
- The tool saves each image in the Hermes cache, which the plugin does not accept as material: copy the file into the
  working folder first (cp), then look at it with the image-viewing tool (vision_analyze), check it shows what the
  section says, and attach it with `youtube_material_add` (kind image, section_index of the section it explains,
  review_note saying what you saw). It is that section's picture in the video.
- A generated picture is never a chart of data. Numbers, tables and cycles come from `youtube_make_visual` with sources.
- Plan the script with enough sections that each illustration, the phase table, the cycle flowchart and a closing slide each
  have their own section (five or six sections for a short lesson).
- The cycle flowchart (new, growing, full, shrinking, new) is a second `youtube_make_visual` flowchart (a chain of nodes whose
  last node is the first phase again is not allowed in a flow with no cycles; write it as five steps: New Moon, Growing
  crescent, Full Moon, Shrinking crescent, New Moon again) attached with `project_id` and `section_index`.

## Do not stop to ask (default for a plain lesson request)

- Gemini narration through `youtube_narrate` is the standing choice for lessons: it costs a few cents and the plugin
  already caps it at 0.50 USD per project. Do NOT ask the user for a spending limit, permission or a "skip paid narration"
  decision; narrate, then report in your summary the voice, the number of requests and the cost estimate returned. Only if
  the tool itself reports that Gemini is not set up, say that plainly.
- If a source page fails to load or is unrelated, fetch another one: try up to eight pages until three relevant sources are
  read. Never finish with fewer than three sources while untried pages remain, and never stop to ask the user which sources
  to use.
- Ask the user only if something is missing that nothing in the working folder or the tools can supply.

## Moon-phase style lesson: pictures that carry the idea (default for a science lesson)

- Make THREE generated illustrations (when the host has an image tool; at most three, no more than one redo each), each for
  a picture-worthy section: (a) sunlight lighting half of the Moon, (b) the Moon circling the Earth with the Sun far to one
  side, (c) a crescent Moon in an evening sky over a landscape (what a person actually sees). Ask the image tool for NO text,
  labels or numbers inside the pictures: put the words in the slide heading, the bullets or the captions. Look at each picture
  with the image-viewing tool; if the lit side does not face the Sun, regenerate that picture once.
- The cycle is drawn with `youtube_make_visual` kind `cycle`: nodes in order, for the Moon the EIGHT phases (New Moon, waxing
  crescent, first quarter, waxing gibbous, Full Moon, waning gibbous, last quarter, waning crescent), each with a plain
  "what we see" phrase in its label; the last leads back to the first, so the loop is closed. Attach it with `project_id` and
  `section_index`.
- Do not leave a text slide mostly empty: make the type big, or pair the bullets with one of the illustrations at the side by
  passing the copied illustration as `image_path` in `youtube_make_slides`. A separate phase table is optional when the eight-
  step cycle already names the phases.
- Never describe the Moon's phases as being caused by Earth's shadow, not even as "usually" or "not usually": phases are never
  Earth's shadow (only a lunar eclipse is). Say instead that the Sun always lights half the Moon and we see different amounts of
  that lit half. A slide that has a picture gives the picture the right half of the frame.

## Visuals must be shown, and "carry on"

- Assembly checks for charts or flowcharts you drew for this project that no section shows. A clear match
  (by section title and words) is placed automatically and listed in `visuals_placed`; otherwise the result
  says "N visual(s) made but not used: ..." in `visuals_notice`. Read that line. Never hand the user a video
  with a drawn visual left out: attach it (youtube_make_visual with project_id and section_index) and assemble
  again, or tell the user plainly that it was left out.
- A stopped or failed run (provider error, closed session, "carry on") resumes from the project, not from scratch:
  call `youtube_project_status` with no project_id, take the newest unfinished project, and follow `resume.next`.
  Finished steps are not redone, `youtube_narrate` skips turns already recorded and reuses a take that was paid for
  before the stop, so speech is never paid for twice.
