# Verification of Creator Studio 0.1.0

This file says what was checked on the bundle. Each part's live evidence (real Gemini runs, real recordings, real captions, demos) belongs to that part's own record: see `VERIFICATION.md` inside `youtube_studio/`, `podcast_studio/`, `caption_studio/` and `tutorial_creator/`. Nothing in those records was re-run live for the bundle, and the bundle adds no new claim about speech, picture or recognizer quality.

## What was changed when the four plugins were combined

- Each part's source was copied into its own sub-package. Tool names, schemas, hooks (none), approval behaviour and defaults are unchanged.
- The only code edits: (1) imports of the three modules that YouTube Studio and Podcast Studio had as byte-identical copies (`gemini_speech.py`, `locking.py`, `browser_research.py`) now point at `common/`, and the page-reader subprocess path follows; (2) each part's storage name became its own `creator-studio-*` folder; (3) the Caption Studio dashboard route loads the Caption Studio sub-package; (4) test loaders were adjusted to load the sub-packages.
- The manifest declares the exact union of the parts' tools (62), Python dependency (Pillow 13.0.0), optional environment names and settings.

## Tests

Run from the plugin folder with the Hermes Python, the Hermes source on `PYTHONPATH` and a throwaway `HERMES_HOME`:

```
tests/run_all.sh
```

| Suite | Tests | Result |
|---|---|---|
| Suite register test (exact tools, skills, no hooks, tool reference) | 5 | pass |
| YouTube Studio | 65 | pass |
| Podcast Studio | 38 | pass |
| Caption Studio (Python) | 40 | pass |
| Tutorial Creator | 33 | pass |
| Caption Studio Desktop flows (`node caption_studio/tests/test_desktop.cjs <hermes>/node_modules`) | 3 flows | pass |

These are the parts' own tests, run against the combined layout, plus the new register test. Most use mocked transports and synthetic media; see each part's file for the exact limits.

## Hermes admission

`hermes plugins validate <clean export> --install-deps` (Hermes v0.23.0, disposable Hermes home, throwaway Python environment): manifest, `requires_hermes`, config schema, `requires_env`, dependency check, capability probe (declared tools, hooks and middleware match what `register()` does), built-in tool collisions, security scan, no core override and desktop surface all pass. The result line and any warnings are reported in the submission notes, not repeated here. The workflow preflight (`check-plugin-workflows`) passed. A secrets and identity audit of the tree and the single commit found no credential, user or host name, personal e-mail address, cloud project id or device id; its only remaining pattern matches are loopback addresses and fixture strings in tests that the parts already contained.

## Not verified

- No new live Gemini, recognizer or screen-recording run for the bundle.
- Only Linux was tested. No Windows or macOS run.
- Running the stand-alone plugin and the suite together in one profile was not tested; run only one.
