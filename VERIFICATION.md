# Verification of Creator Studio 0.5.0

## 0.5.2 - no browser cookies in Clip Studio (2026-11-14)

Removed the owner setting `clip_cookies_browser` and the `--cookies-from-browser` option it passed to yt-dlp. Reading another tool's login (a browser profile) is not allowed for listed plugins (catalog rule 11), even through yt-dlp. A video that asks for a sign-in now gets a plain message telling the person to download it themselves and open it with `media_path`. Nothing else changed. Checked: the whole suite passes (Clip Studio now has 91 tests, including a new test that no cookie option reaches yt-dlp), `hermes plugins validate --install-deps`, and a search of the tree for any remaining `cookies` option.

## 0.5.1 - recognizer device choice (2026-11-13)

- Caption Studio's setup scan never passed the graphics cards it found to the device choice, so every scanned local Whisper route was set to CPU even with a free card. It now does, and each scanned route says why it was given the GPU or the CPU. The bundled Transformers adapter, when run as an owner-set command with no device named, uses the graphics card when it has at least 5 GiB free and the CPU otherwise.
- Checked: the 84 Caption Studio tests pass; on this computer (24 GiB card, 21 GiB free) the scan now lists the cached Whisper routes with device cuda. See the release notes below for the rest.

## 0.5.0 - Clip Studio (2026-11-13)

### Added before release (2026-11-13): 17 Clip Studio tools, 85 in the suite

Six tools were added to Clip Studio the same day (`clips_chat`, `clips_join`, `clips_post_facts`, `clips_post_save`, `clips_face_ranges`, `clips_from_studio`), plus `clips_burn`, and `clips_transcribe` now recognises a whole recording in resumable pieces. Where this section and the older paragraphs below disagree (tool counts, "not tested" items), this section is the current one.

Tests: `tests/run_all.sh` runs 422 tests (6 + 13 + 17 + 62 + 72 + 43 + 84 + 38 + 87; the last number is Clip Studio). All pass with the system FFmpeg 8.0.1 and with the FFmpeg 9.0.1 that Hermes ships. `hermes plugins validate` passes.

Live checks on one real 5 h 39 min VTuber stream that has no caption track (Linux, yt-dlp 2026.08.19):

- Clip job outside Hermes: 31 clips and 11 clips of super chat readings cut from YouTube sections with dead-air removal (`max_pause` 0.5), each checked against a second recognizer through Caption Studio, captions burned with `clips_burn`, joined to 27:27 and 32:06 videos. Picture and sound lengths of the joined files agree within 0.05 s. Nobody listened to the clips.
- `clips_chat` through the plugin: one yt-dlp request, 3.5 minutes, 77 MB replay reduced to 1.4 MB (43,046 messages, 341 paid). Five spikes and five paid-message readings were checked against the transcript and were right; two "no reading found" results were right.
- `clips_transcribe`: 20 minutes of the stream in five pieces through the bundled Transformers adapter (whisper-large-v3-turbo on CPU, 79 minutes wall time while other jobs ran): 2,779 words, times in order, sentences read on across every seam, Caption Studio's audio copies removed. A separate 4-minute run was killed mid-piece and resumed from the finished pieces.
- `clips_join` and `clips_post_facts` on three real clips: 47.5 s expected and measured; title card frame inspected.
- Face following: four 2 to 3 minute vertical cuts from parts of the stream where the avatar is full-screen, moves to a corner, or the screen goes black; frames inspected. A head lean of about 10 percent was reported as a move (correct but visible as a jump).
- Through a Hermes session (throwaway profile, default model, plain requests): chat spikes and super chat readings listed with `clips_chat`; three clips joined with title cards with `clips_join`; title, description and thumbnail saved with `clips_post_facts` and `clips_post_save`, with the source credit line added by the tool.

Bugs these runs found and fixed: the reel passed its filter graph with an option FFmpeg 9 removed (it failed only inside Hermes, which ships FFmpeg 9); Caption Studio's bundled Transformers adapter returned repeated, out-of-order word times on audio over 30 seconds (it now recognises in windows cut at quiet points); the setup scan picked CPU without saying why when a graphics card was busy; the vertical face-panel layout left black gaps.

Not tested: `clips_transcribe` on hours of audio in one run (longest: 20 minutes), on a graphics card, or through a Hermes session; `clips_from_studio` against items made by a live run of the other parts (file shapes were checked against real project records only); `clips_face_ranges` and face following through a Hermes session; title cards with non-Latin titles; the word-level accuracy of any recognizer; a stream on air; `clip_cookies_browser`; Windows and macOS. In the Hermes session the image-viewing tool timed out, so the model chose a thumbnail without looking at it.

New part `clip_studio/` (8 tools `clips_*`, skill `clip-youtube-video`, data folder `creator-studio-clips`, owner setting `clip_ytdlp`; a `clip_cookies_browser` setting existed in 0.5.0 and 0.5.1 and was removed in 0.5.2). The other four parts are unchanged; the manifest now declares 78 tools and 5 skills (the count grew the same day: `clips_frame` and `clips_face` were added, see below).

Tightening (added the same day): `clips_propose` takes `skip` spans and `clips_cut` takes `remove_pauses`/`max_pause`. Offline test with a generated recording (tone, 3 s of silence, tone): one pause removed, length shorter by the expected 2.7 s, captions shifted to match, a skipped caption line absent from the result, and refused skips (opening, past the end, overlapping). Live: a 57 s span of the same public video with one skipped sentence (10.9 s) and three pauses removed came out 44.0 s; a local Whisper pass read the speech straight through with the skipped sentence gone, and the re-timed captions were within about half a second of the recognized words (the source track was YouTube speech recognition).

Offline tests (23, in `clip_studio/tests`, run by `tests/run_all.sh`): parsing of YouTube json3 (word-timed and uploader tracks), a rolling speech-recognized VTT and SRT; sentence grouping; search, paging and outline; moving cut points to speech boundaries without entering a neighbouring word; clip captions timed from the clip start; accepted and refused links (playlists, other hosts, option-like text); caption-track choice; refusal of private, profile and symlink files; the project flow with YouTube replaced by a fake (open, reopen, propose, edit, cut vertical with burned captions, a short download refused with nothing kept, a stream on air, hand-over of audio to Caption Studio with a mocked job); and a real FFmpeg cut of a generated local recording with its own SRT. The whole suite passes (see the run in the table below for the other parts).

Live check on Linux with yt-dlp 2026.08.19, Node as its JavaScript runtime and FFmpeg, calling the tool functions directly (plugin storage stubbed, no Hermes session): `clips_open` on a public 18-minute video with uploader captions (page and caption track only), `clips_outline` (38 windows, six most-replayed spots, four pauses), `clips_transcript` by range and by phrase, `clips_propose` of two clips (both moved to sentence edges), `clips_cut` vertical 1080x1920 with burned captions (10.47 s, about 11 s to make) and as filmed at 480p (22.9 s, about 4 s). One frame of the vertical clip was looked at (caption readable; the centre crop cut off the slide's sides, which is why the skill tells Hermes to use `fit` for slides). Both clips were run through a local Whisper model: each starts on the first word and ends on the last word of the proposal. A separate download showed the speech-recognized json3 track carries per-word times as the parser expects.

Not tested: a run through a Hermes session (tool registration is covered only by the register test); `clips_transcribe` with a real recognizer; a video with only speech-recognized captions through the tools (only its track format was checked); a stream on air or just ended; clips longer than about a minute; pause removal on speech over music; square shape and `fit` on a real YouTube video (covered with generated media only); Windows and macOS; yt-dlp versions other than the one named.
This file says what was checked on the bundle. Each part's live evidence (real Gemini runs, real recordings, real captions, demos) belongs to that part's own record: see `VERIFICATION.md` inside `youtube_studio/`, `podcast_studio/`, `caption_studio/` and `tutorial_creator/`. Nothing in those records was re-run live for the bundle, and the bundle adds no new claim about speech, picture or recognizer quality.

## 0.4.1 - maintainer review (2026-11-12)

Maintainer review. Executables, commands and endpoints (Camoufox python/browser, ASR command/endpoint/decoder, TTS server) are owner settings in plugin.yaml, no longer tool arguments the model can set. Every subprocess gets a minimal environment (PATH, HOME, LANG). Declared secrets (GEMINI_API_KEY, CAPTION_STUDIO_ASR_KEY, CAPTION_REPAIR_ASR_KEY) are read only through agent.secret_scope. Python-runtime discovery no longer walks the home folder. Non-loopback ASR endpoints refuse private hosts. Re-tested: 334 offline tests across the suite, all passing; plugin preflight reports no findings.

Live test through Hermes 0.23.0 (2026-11-12, own profile, real local model and server): local speech discovery, a configured local recognizer (faster-whisper small.en through asr_command) chosen in the interview and run through captions_generate (two correct cues with word timing), and the model-facing refusals of executable, command and endpoint arguments. Found and fixed: a configured asr_command was not offered as a route; a TTS-only server was offered as a recognizer and the reverse. Not covered: hosted recognizers and Gemini speech (no key on the test machine).

## What was changed when the four plugins were combined

- Each part's source was copied into its own sub-package. Tool names, schemas, hooks (none), approval behaviour and defaults are unchanged.
- The only code edits: (1) imports of the three modules that YouTube Studio and Podcast Studio had as byte-identical copies (`gemini_speech.py`, `locking.py`, `browser_research.py`) now point at `common/`, and the page-reader subprocess path follows; (2) each part's storage name became its own `creator-studio-*` folder; (3) the Caption Studio dashboard route loads the Caption Studio sub-package; (4) test loaders were adjusted to load the sub-packages.
- The manifest declares the exact union of the parts' tools (64), Python dependency (Pillow 13.0.0), optional environment names and settings.

## Tests

Run from the plugin folder with the Hermes Python, the Hermes source on `PYTHONPATH` and a throwaway `HERMES_HOME`:

```
tests/run_all.sh
```

| Suite | Tests | Result |
|---|---|---|
| Suite register test (exact tools, skills, no hooks, tool reference) | 6 | pass |
| Cross-part features (caption the latest item, podcast from a lesson; tiny fixtures, no network, no speech, no recognition) | 11 | pass |
| Unplaced visuals and resume (placement, notice from a real 2-section assembly, status resume block, narration resume with a mocked speech call, reuse of a paid take, tutorial status list) | 11 | pass |
| YouTube Studio | 65 | pass |
| Podcast Studio | 38 | pass |
| Caption Studio (Python) | 40 | pass |
| Tutorial Creator | 33 | pass |
| Caption Studio Desktop flows (`node caption_studio/tests/test_desktop.cjs <hermes>/node_modules`) | 3 flows | pass |

These are the parts' own tests, run against the combined layout, plus the new register test. Most use mocked transports and synthetic media; see each part's file for the exact limits.

## Hermes admission

`hermes plugins validate <clean export> --install-deps` (Hermes v0.23.0, disposable Hermes home, throwaway Python environment): manifest, `requires_hermes`, config schema, `requires_env`, dependency check, capability probe (declared tools, hooks and middleware match what `register()` does), built-in tool collisions, security scan, no core override and desktop surface all pass. The result line and any warnings are reported in the submission notes, not repeated here. The workflow preflight (`check-plugin-workflows`) passed. A secrets and identity audit of the tree and the single commit found no credential, user or host name, personal e-mail address, cloud project id or device id; its only remaining pattern matches are loopback addresses and fixture strings in tests that the parts already contained.

## Added in 0.2.0

- `captions_for_latest` and `podcast_start_from_video` were tested only with the fixture tests above: small made-up project folders, a mocked caption job, and a check that the podcast copy opens no network connection and starts no process. Not tested: a live Hermes run, a real recognizer through `captions_for_latest`, or a real narrated podcast written from a copied lesson.
- The Desktop caption page was not opened against the new tool (it does not use it).
- Checked that the Desktop page needs the API route: its scripts post every action to `/action`, which `dashboard/plugin_api.py` serves, so the dashboard folder stays; the tab stays hidden.

## Added in 0.2.1

- Two fixes from the live test: assembly now places a drawn chart or flowchart that no section shows when its title clearly matches a section, otherwise says "N visual(s) made but not used: ..."; and `youtube_project_status` / `podcast_project_status` (no id) and `capture_status` (no id) give a resume plan so "carry on" repeats no finished step. Tested only with fixtures and mocked speech (a real ffmpeg render of two tiny slides was used for the assembly test); not re-run live in Hermes. The provider "prompt flagged" error itself is not handled, only recovered from.
- Gemini speech spend guard: the shared speech code reserved a flat about 0.30 USD per request, so a guard below about 0.31 USD refused every line. The reservation is now estimated from the text length (published per-token prices, 25 audio tokens per second, slow-speech assumption, a 2x margin, a 0.002 USD minimum); the guard is still strict (spent plus estimate must not pass it) and a refusal states the estimate, the guard and what to raise. The tutorial part's own speech copy had the same flat floor (about 0.076 USD) and got the same change. Fixture tests only (mocked transport); the estimate was not compared against a new live bill.

## Not verified

- No new live Gemini, recognizer or screen-recording run for the bundle.
- Only Linux was tested. No Windows or macOS run.
- Running the stand-alone plugin and the suite together in one profile was not tested; run only one.

## Added in 0.2.2

Assembly reports the actual section pictures and all attached images left unused without replacing an existing section picture. Script captions are copied next to the finished media without overwriting a different file.

## Added in 0.2.3

Project assets are isolated unless explicitly imported. Video assembly allocates time to all attached images and reports the actual image ranges. Resume status gives an ordered completion plan, and speech-cap refusals distinguish earlier recorded cues and their costs from the cue that was not sent. Offline fixtures cover these paths, including cross-project podcast music and tutorial voice references.

## Changed in 0.3.0: Google sign-in through Hermes

Gemini narration (YouTube Studio, Podcast Studio, Tutorial Creator) no longer uses Application Default Credentials,
`google.auth`, a token refresh of its own or `gcloud config get-value project`. `plugin.yaml` declares an `oauth:` entry
(id `google`, scope `cloud-platform`, host `aiplatform.googleapis.com`, the user's own client in two optional variables)
and every speech request goes through `hermes_cli.plugin_provider_requests.credentialed_provider_request`. The project
id comes only from the `gemini_project` setting.

Checked: the whole suite passes with the request helper faked (one request per part, ledger, spend guard, the
not-signed-in refusal that sends nothing and keeps no ledger row, and a source check that the three speech modules
contain no `google.auth`, subprocess, refresh or bearer handling).

NOT checked: a real `hermes auth add creator-studio:google` sign-in and a real signed speech request. The earlier live
Gemini runs recorded in the parts' own files used the old login route. Treat the signed-in route as untested against
Google until someone has run the four setup steps in the README.

## 0.4.0 - ask the user which voice; never pick one (2026-11-12)

- `narration_backend` now defaults to `chosen`: the speech route the USER picked in the first-use interview. The plugin never picks an engine itself. New `tutorial_speech_setup`, `youtube_speech_setup`, `podcast_speech_setup`: they find what this computer has (a speech server that answers, installed programs: espeak-ng, flite, Piper with a model, macOS `say`, Windows speech, a Gemini API key or Cloud project, a host speech tool), read the hardware, and return the options plus the questions to ask (what to make, natural vs plain voice, whether online and paid use is OK and a budget, what they already have, and which route they want). Narration returns these options and questions until a route has been chosen. A "no online services" answer blocks Gemini even when named; the budget caps the spend guard.
- Suggestions shown with the options (never a decision): online services in the order Gemini 3.8 Flash TTS, Inworld, ElevenLabs with each one's free allowance, price, source link and verification date; local models that fit the detected hardware, with licence and how to run. New wiki page `llmwiki/speech-models.md` and `common/speech_catalog.json` (51 local models and 13 local servers/runtimes, read on 2026-11-12; several figures are marked UNVERIFIED where no primary page gave them;). Each VRAM figure says whether it is stated, user-reported or an estimate. Ollama and llama.cpp speech endpoints were read from their docs only, not run.
- New Gemini route with a plain API key (`gemini_api_key`, `gemini_route`): no Cloud project and no Google sign-in. The Vertex route with the Hermes-held sign-in stays optional.
- New `system` engine for YouTube, podcast (a different installed voice per speaker) and tutorial narration.
- Knowledge freshness: the setup tool reports whether its built-in speech knowledge looks out of date (checked more than 30 days ago, or a known deadline such as Gemini's promotional pricing ending 2026-12-31 has passed) and, if so, tells the user and ASKS whether to research the current facts online; nothing is researched without their yes. Approved research is saved as dated overrides (`knowledge_updates`), never into the shipped catalog. Tested with fixtures; the research step itself is the host agent's and was not run here.
- Caption Studio (part of this suite): new `captions_recognizer_setup` finds the speech recognizers this computer can use (a local OpenAI-style transcription server, cached Whisper models, installed programs, online services with a key), reads the hardware, suggests local models that fit and online services with free allowance, price, timestamp support and data-use terms, says which of the user's paid plans include API access (ChatGPT Pro/Business and Claude Max/Team credits, Google AI Pro unverified, Hugging Face PRO), asks the user which to use and saves it; `captions_generate`, `captions_analyse_audio` and `captions_for_latest` return the interview until then, and recognizer `{"kind": "chosen"}` uses the saved route. Wiki `caption_studio/llmwiki/recognizer-models.md` and `asr_catalog.json` (21 local models, 15 online services, 6 servers, read 2026-11-12; Ollama's transcription endpoint has no SRT/VTT or timestamps and is marked unusable for subtitles). 63 Caption Studio tests. Not tested: any transcription through the new routes; the word-timestamp claims of most online services are UNVERIFIED.
- Tested here: 252 Python tests across the suite plus the speech-resources tests; real offline narration through flite and ffmpeg for YouTube and podcast. NOT tested here: the Gemini API-key route against Google (no key was used; it copies PageCast's request shape), macOS `say`, Windows speech, Piper, the free-tier figures (read from vendor pages), any local model other than Flite.


## 0.4.2 - found by running every tool through Hermes (2026-11-12)

- Ran the YouTube video, podcast, captions, capture and tutorial tools through Hermes with the real local pieces: flite narration, the owner's Camoufox for page reading (example.com and a Wikipedia page), a local faster-whisper recognizer for captions, ffmpeg renders (still, slideshow, clips, vertical short, stitch), podcast mix and timeline mix, episode lint and preflight, PageCast plan and cast checks, and a private X display for capture, export, frame, timeline and narration.
- Bugs this found and fixed: the YouTube project tools (including `youtube_research_fetch`) were registered without the plugin context, so the owner's Camoufox setting never reached them; the Camoufox page reader died with "'camoufox' is not a package" because the plugin's own `common/camoufox.py` shadowed the real package when the script started from that folder (it now starts isolated); the plugin's own podcast episode folder sits under `.hermes`, so its lint, preflight and load tools refused the episode it had just written; the slideshow was 25 fps while still and clip segments were 10 fps, so stitching segments from different tools failed (all are 25 fps now); an HTTP recognizer endpoint the owner set (`asr_endpoint`) was accepted by `captions_generate` but never offered as a route in the interview, and a local one was refused when uploads were off (it is now the route `configured:endpoint`, run through Hermes against a local stand-in server).
- Tested here: 8 suites, 343 Python tests (the tutorial capture test failed once while a manual screen capture was still running and passed on every rerun). Not tested: Gemini narration (no Google sign-in here), hosted recognizers (no key), `youtube_generate_image` through a host image tool, `tutorial_step` driving a real app other than a test terminal.
