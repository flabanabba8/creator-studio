# Automatic Tutorial Creator verification

> **Part of Creator Studio.** This is the stand-alone plugin's own verification record. The evidence in it belongs to that plugin; see the suite's VERIFICATION.md for what was checked on the bundle.

- Narration reads its declared Higgs settings through Hermes's keyed `get_config` interface. A strict-context regression checks forwarding; an isolated installed-Hermes runtime dispatched and correctly rejected a nonexistent tutorial job without starting a model or contacting a service.

Development checks on2026-11-05. Nothing published or installed into a user's
active Hermes profile. No Windows/native-Wayland support claim.

## Passed

- Mixed-case protected-directory fixtures passed on Linux; no real credentials were used. This is not a full platform or publication audit.

- Catalog validation for the capture/timeline/narration/computer-use tool package:
  manifest, isolated registration, declared tools, security and no core overrides.
- Real isolated Xvfb application capture using original animated video and a sine
  tone: selected window recorded; selected audio stream captured; marker timestamp
  advanced; recording stopped; the original audio route was restored; exported
  video and audio decoded. No desktop contents or other app audio were recorded.
- Invalid duration/display/ID boundaries and cue overlap/length rejection.
- Multi-cut export with markers mapped onto the edited timeline and a decoded
  timestamp frame. Frame-rate and approximately0.5-second marker quantization apply.
- Native computer-use dispatch fixture: a denied action stays denied, host context
  is forwarded, a successful action gets a fresh observation, and the returned
  observation still requires review. This is not a live desktop-control test.
- Additional private Katz, podcast and video rehearsals were captured and
  exported on isolated X11 displays with no host audio selected. Sampled frames
  were inspected; this did not exercise live Hermes computer-use actions or
  constitute complete visual or listening review.
- Native Windows Python 3.14 loaded the plugin and confirmed window discovery
  and recording report their Linux X11/XWayland requirement before invoking any
  desktop command. This does not implement or test Windows capture.
- Local HTTP TTS fixture: requests, WAV duration checks, audio mixing/ducking,
  timed segment SRT, cache reuse and overrun rejection.
- Real local Higgs TTS3 at revision239f63fb7b02b1aa085f98d9efae5e35cc5523e8:
  one original narration sentence produced5.16 seconds of audio, placed at1.0s in
  a13.0-second synthetic test video. Complete export decoded and captions/credit
  were generated. Speech/export stage took2.4s after server readiness.
- The temporary Higgs server used existing cached weights, offline mode, the
  existing GPU lock, an11GiB RAM ceiling, no swap, and a10-minute lifetime cap.
  It stopped after synthesis. No other model service was adopted or stopped.

- Independent cached Whisper large-v3-turbo transcription matched the original
  narration sentence exactly. It ran after Higgs stopped, with a4GiB RAM cap;
  this is an ASR check, not a human listening-quality judgment. The first ASR
  invocation used an unavailable `whisper` package; the successful check used
  the already-installed Transformers pipeline documented by the source project.

## Remaining

- Full end-to-end tutorial of an actual application driven through a running
  Hermes computer-use backend, plus human/visual review of the finished demo.
- Subjective narration quality and more voices/languages. One short synthesis is
  not a guarantee against dropped/repeated words; captions are not word-aligned.
- Native Wayland and Windows capture. The existing Windows recorder is a research
  foundation, not a shipped or tested backend. The Legion Go was reachable for
  the unsupported-path check above.
- Interruptions by power loss/SIGKILL can leave an MKV and require audio-route
  recovery. Graceful stop is covered; hard-kill recovery is not automated.
- Public content/history audit, install documentation review, demo publication,
  catalog submission and contest form.

Local receipts and synthetic media are in the contest workspace's ignored
evidence directory; they are not part of the plugin distribution.
- 2026-11-07: live isolated-desktop trial (Hermes Bot Desktop in a disposable profile, a real xterm printing numbered lines). `capture_sources` listed X11 windows on the private display; `capture_start` recorded the chosen window for 21.5 s with two `capture_mark` steps; `capture_stop` completed; `capture_export` cut two segments into a decoded 14 s H.264 MP4 (424x212, the real window size); `tutorial_timeline` mapped the step markers through the cuts correctly (6.7 s to 5.7 s in clip 0; 14.7 s to 10.7 s in clip 1) and `tutorial_frame` decoded a frame. Frame comparison showed the terminal content changing between 0.5 s and 6 s. No Higgs narration, no input actions, no audio and no human review. The host desktop, game and audio were not used; the temporary desktop and profile were removed.

## Guided application tutorial capture — 2026-11-10

Actual Writer work revealed that X11 drawable capture omitted separate save/export dialogs, although the underlying document was recorded. Explicit fixed-window-region capture and optional real pointer recording were added with default behavior preserved. Region requests require a visible selected application window fully inside the display; root and offscreen capture are refused. Focused mocked checks cover exact FFmpeg input selection, cursor choice, old requests, invalid modes and region/root bounds. Live verification completed in an owned real Hermes session: explicit window_region plus show_cursor recorded a real Writer heading, list selection and toolbar click, native Save As and PDF Export dialogs, and real pointer. Native capture_export produced a fully decoded31.5-second lesson. Native tutorial_narrate reused all four unchanged Higgs WAV caches, with measured captions and zero new speech calls. Main-session decoded-frame review confirmed controls and dialogs; earlier focus attempts and premature markers are retained as failures. The unchanged original notes and new editable/PDF outputs were checked. This verifies fixed-region capture on a private X11 display, not arbitrary occlusion/privacy safety, native Wayland, Windows, audio routing, autonomous computer use or human listening quality. Local evidence: contest/maintenance/tutorial-window-region-20261110/live-verification.json. Historical captures/packages and private installed plugins remain unchanged.

- 2026-11-10: version 0.2.1. `tutorial_step` now finds the recorded window's own process ID (X11 _NET_WM_PID) and passes it with the window ID to computer use, which otherwise returns an empty "no window" capture that looked like success. An empty preflight capture now stops the step before any action or marker. Probed live on an owned display with xfwm4 and Audacity: list_windows, ax and screenshot captures all worked (screenshot not blank) once pid and window ID were both supplied; without pid the capture was empty. Audacity must be started with GDK_BACKEND=x11 and WAYLAND_DISPLAY unset to appear on the virtual display.
- 2026-11-10 (same version 0.2.1): `capture_start` now raises the selected window (xdotool windowraise, best effort) before recording. Live finding: on a display with no compositor, a window covered by another window records as black (YAVG 16) and returns a black screenshot; raising it gave a real image (YAVG 142). The Hermes browser used for the demonstration shares the owned display, so it covered Audacity. SKILL.md now says to use max_seconds 600 and to retry a refused keyboard action with delivery_mode foreground.
- 2026-11-10 live agent trial (Audacity noise removal): agent drove Audacity through tutorial_step with per-action approval but could not complete the effect workflow; clicks on guessed coordinates hit the Record button. Not a passing end-to-end demo; details are kept in the maintainer's private evidence folder, which is not part of this repository.
- 2026-11-10 keyboard path proven by hand on an owned display (xfwm4 + LibreOffice Calc, scratch document, not recorded): header and rows typed with Tab/Return, SUM formula, ctrl+b header, shift+arrow data selection, alt+i then Down then Return opened the Chart Wizard (a separate window), alt+f finished it, Escape left chart edit mode. Advice added to SKILL.md and llmwiki/task-guide.md as general guidance.
- 2026-11-11 version 0.3.0: additive Gemini 3.8 Flash TTS narration route (gemini_speech.py, Vertex; at that time with the person's own ADC and gcloud default project, replaced in Creator Studio 0.3.0 by a Google sign-in held by Hermes and the gemini_project setting; project never returned, one POST per cue without retry, ledger gemini-usage.json with a 0.50 USD default guard, 30 named voices listed by capture_sources, default backend gemini). 30 mocked-transport tests; no live Google request was made by the tests.
- 2026-11-11 known limit (reproduced 3 times): Hermes computer-use `type` on a LibreOffice Calc window makes soffice grow about 1.8 GiB per 5 s until the system kills it; key presses and typing in Writer or a terminal are safe. tutorial_step now turns a `type` on a Calc window into a clipboard paste (xclip) followed by the ctrl+v key action, which keeps its normal approval; a multi-line paste opens the Text Import dialog (confirm with Return). Without xclip the type is refused with advice.
- 2026-11-11 version 0.3.1: capture_start max_seconds ceiling raised from 600 to 1800 (a terminal lesson with per-action approval and slow model turns outran 600 s; waiting is cut at export); capture_start result now tells Hermes to use tutorial_step for every demonstrated action.
- 2026-11-11 version 0.3.2: teaching-capture guard. tutorial_step refuses a typed line with chained && or ;, embedded newlines or over 110 characters (one command per step); SKILL.md gains a command-line lesson section (plain commands, one idea per step, clear between chapters, output left on screen 2-3 s, narrate the command and what its output shows).
- 2026-11-11 version 0.3.3: capture_export receipt now carries export_name; tutorial_timeline, tutorial_frame and tutorial_narrate accept the export file name, its full path, or the name without .mp4 (a live run lost its narration step to a name mismatch).
