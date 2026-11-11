# Podcast Studio

> **Part of Creator Studio.** This is the original README of the stand-alone plugin, kept as the detailed reference for this part. Its install lines apply to the stand-alone plugin only; install `creator-studio` instead. Paths such as `llmwiki/` and `skills/` here are inside this part's folder.

Research and write a podcast from a topic, select compatible speech resources and assemble an episode with editorial review and optional music.

**At a glance**

- **Install:** `hermes plugins install flabanabba8/podcast-studio`, then `hermes plugins enable podcast-studio`.
- **Needs:** Hermes 0.22.3 or later. For spoken audio, either a speech server already running on your computer, or Gemini 3.8 Flash TTS with a Google sign-in held by Hermes (your own OAuth client, `hermes auth add creator-studio:google`, and the `gemini_project` setting on your computer). FFmpeg for mixing. Page research can use an installed Camoufox browser; otherwise use your Hermes web tools.
- **Internet:** Research pages are fetched through the tools you choose. If you use the Gemini voice route, each spoken line is sent to Google, costs money (a 0.50 USD spend guard is on by default) and uses a Google sign-in that Hermes holds for your own OAuth client; the project comes from the `gemini_project` setting and is never shown in results. Nothing is uploaded or published.
- **Limits:** Linux is the only platform checked. Hermes writes and checks the script; the plugin cannot verify that sources are true. The review checks are self-attested and mechanical. You should listen to the finished episode and check show notes and captions before sharing.
- **Credits:** Voices come from the engine you choose; its terms apply. Any music you add must be music you have rights to use. Licence: GPL-3.0-or-later.
- **AI assistance:** Written with AI coding assistants (Anthropic Claude and OpenAI Codex agents) under the maintainer's direction; what was actually tested is listed in VERIFICATION.md.

Read the [setup/task guide](llmwiki/task-guide.md) and [skill](skills/create-podcast/SKILL.md) for the production workflow, resource choices and observable acceptance.

## Supporting tools and detailed limits

A Hermes skill for source-first podcast production, with tools that fingerprint structured dialogue and check that a self-attested editorial review covers the current text. Inspired by the Breach Protocol editorial workflow, generalized to any show and voice cast. Speech is produced with a selected external/native tool; these mechanical checks do not verify claims or upload content; use a separately configured speech tool for production. No account or credentials are required.

Each segment contains `title`, `sources` (a list of references), and `turns` (speaker/text objects). `podcast_check_script` returns hashes; `podcast_check_review` compares a review against the ordered segment hashes and checks for substantive notes. Neither tool independently reads sources or certifies that a review took place. `podcast_show_notes` formats caller-supplied measured chapter starts and deduplicated source references without inspecting audio. `podcast_caption_cues` turns explicitly supplied, passage-timed PageCast text into draft cues, optionally removing Higgs delivery tags. For PageCast, pass the handoff and timeline fingerprints as `expected_source_sha256` and `actual_source_sha256`; a mismatch is rejected. You may also pass the timeline's `source_text_status`: `changed` and `unavailable` are rejected, while `unchanged` records a stronger point-in-time text comparison. Older PageCast books lack this baseline. The values are caller-supplied and not independently authenticated; neither comparison verifies speaker assignments or later changes. These cues are not a transcript or word-level alignment; listen and check the final video. After review, `podcast_pagecast_plan` produces import text and a paragraph-to-speaker and segment-index map for the optional PageCast Director plugin; assign all resulting passage IDs manually after inspecting them, because a turn may split into multiple passages. Compare the handoff `source_sha256` and PageCast text status before rendering and captioning. `pagecast_timeline` can report cached WAV passage boundaries; derive segment starts from the map and verify the final export timing. Update and review the structured script again after PageCast text edits.

Example `podcast_check_script` input:

```json
{"segments":[{"title":"The experiment","sources":["https://example.org/paper"],"turns":[{"speaker":"Host A","text":"The researchers compared two approaches."},{"speaker":"Host B","text":"The comparison only covered one task."}]}]}
```

After checking the sources and reviewing the complete segment, copy its returned `sha256` into a review entry and add nonempty `purpose`, `opening_check`, `source_check`, and `edits` notes. Send those entries in order with a `reviewer` to `podcast_check_review`. Re-run the review if the script or its source references change.

After assigning speakers in PageCast, `podcast_check_pagecast_cast` compares the
complete passage list with the handoff's paragraph-to-speaker map. Collect all
`pagecast_book` pages for the same book revision, then supply its total,
`book.source_hash`, `source_text_status`, the handoff `source_sha256` and
assignments. The check accepts at most 10,000 passages and 1,000 assignment
paragraphs. Missing passage IDs or paragraphs, mismatched source hashes and
changed or unavailable text baselines are rejected. Speaker mismatches are
reported without changing them; at most 100 details are returned with an
omitted count. The inputs are caller-supplied, not authenticated, and a match
does not verify voices, source claims or changes after the check.

`podcast_mix` requires local FFmpeg and ffprobe with the `alimiter` latency-compensation option and supported POSIX or Windows file locking (synthetic checks passed on Linux and Windows) and combines explicitly selected trusted narration and music files into a private 48 kHz stereo WAV. Music loops under the narration; `music_db` defaults to -18 dB and `voice_db` to 0 dB, with a peak limiter. It does not play audio, generate music, automatically duck or certify loudness. Each input is limited to 512 MiB and two hours; output is limited to 2 GiB, with a 120-second encode timeout. Selected active-profile plugin media requires `allow_profile_media`. Mixing may shift timing, so recheck passage captions against the final audio. Check the final mix, timing, metadata, source rights and any required voice/music attribution before sharing.

Example `podcast_mix` arguments, using files you selected and have rights to use:

```json
{"narration_path":"/path/to/narration.wav","music_path":"/path/to/music.wav","music_db":-18,"voice_db":0}
```

For a PageCast output inside the active profile's plugin-data directory, add
`"allow_profile_media":true`. This opt-in does not allow unrelated profile
configuration files.

For different beds across an episode, `podcast_mix_timeline` accepts 1–20
non-overlapping, ordered intervals in milliseconds. Each selected music file
loops only within its interval; gaps have no music. For example:

```json
{"narration_path":"/path/to/narration.wav","beds":[{"music_path":"/path/to/intro.wav","start_ms":0,"end_ms":30000,"music_db":-18,"fade_in_ms":500,"fade_out_ms":500},{"music_path":"/path/to/second.wav","start_ms":30000,"end_ms":60000,"music_db":-20}]}
```

Intervals must fit the narration. Each bed can optionally specify `fade_in_ms` and `fade_out_ms`; their total must fit the bed. There are no automatic fades, crossfades or ducking, so check boundaries and balance by listening. Both mix tools use the
same private-output, profile opt-in, source-size and timeout limits described
above.

Windows tests used synthetic media and did not verify Windows ACLs, perceptual quality, or real episodes. The Windows PageCast handoff was tested with a mocked provider, not live speech. Review the output directory’s access controls.


## Episode folders, linting and the pre-audio gate

`podcast_load_episode`, `podcast_lint_episode` and `podcast_preflight` work on a folder of `NN-slug.txt` segments (with `# title:` and `# paper:`/`# source:` headers and `SPEAKER: text` lines), an optional `meta.json`, `editorial-review.json` and a separate fact-check `source-check.md`. Lint rules come from a daily show's script linter but are a style profile you set per show: tag handling, banned tags and phrases, spoken-number rule, disabled rules, source requirement, and a `kids` preset (reading grade, sentence length, sensitive words, no spoken contact details). Lint and the review gate are mechanical and self-attested; they do not verify sources, listen to audio or judge quality. Any dialogue edit changes the file hashes and needs a fresh review.

## 0.2.1 (2026-11-10): returning to earlier work, clearer research gates

Found by real owned Hermes runs: a returning user could not continue an earlier project because no tool listed projects; a mistyped project ID silently saved nothing; error pages were saved as sources; and a script using `sources` instead of `source_ids` got a misleading error.
- `podcast_project_status` with no `project_id` lists existing projects (ID, topic, phase, counts), newest first.
- A wrong or mistyped project ID returns an error listing the existing IDs.
- Pages with HTTP status 400 or above, and short pages that say "page not found", are not saved as sources (`page_unavailable`).
- A factual section without `source_ids` gets a message naming the exact key.
- Material from the Hermes profile cache is refused with a message saying to save it in the task folder or plugin data folder.
- Camoufox reader: guard against the Playwright pageError crash, stdout isolation, and a hard deadline.
- Skill and wiki: plain-language rule and a three-source research rule.
- Attaching the exact same file again (same SHA-256 and kind) reuses the existing material instead of adding a second copy (found when a returning session re-attached a take that was already in the project).

## 0.3.0 (2026-11-10)

- `podcast_narrate`: Gemini 3.8 Flash TTS (Vertex AI, Google sign-in held by Hermes) as a supported speech route. `podcast_start_topic` reports `gemini_speech` (availability or reason, 30 named voices with gender and trait). One request per spoken turn, named voice per speaker, 0.50 USD spend guard, usage returned, no retries, raw takes kept; the Google Cloud project is read from the machine configuration and never shown. The local-server how-to remains for other engines.
