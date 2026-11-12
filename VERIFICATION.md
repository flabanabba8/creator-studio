# Verification of Creator Studio 0.3.0

This file says what was checked on the bundle. Each part's live evidence (real Gemini runs, real recordings, real captions, demos) belongs to that part's own record: see `VERIFICATION.md` inside `youtube_studio/`, `podcast_studio/`, `caption_studio/` and `tutorial_creator/`. Nothing in those records was re-run live for the bundle, and the bundle adds no new claim about speech, picture or recognizer quality.

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
- Tested here: 252 Python tests across the suite plus the speech-resources tests; real offline narration through flite and ffmpeg for YouTube and podcast. NOT tested here: the Gemini API-key route against Google (no key was used; it copies PageCast's request shape), macOS `say`, Windows speech, Piper, the free-tier figures (read from vendor pages), any local model other than Flite.
