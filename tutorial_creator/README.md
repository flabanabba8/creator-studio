# Automatic Tutorial Creator

> **Part of Creator Studio.** This is the original README of the stand-alone plugin, kept as the detailed reference for this part. Its install lines apply to the stand-alone plugin only; install `creator-studio` instead. Paths such as `llmwiki/` and `skills/` here are inside this part's folder.

Record one application window, mark the useful steps, and cut a checked demo
under 90 seconds. Each take keeps its original recording and timestamp markers.

**At a glance**

- **Install:** `hermes plugins install flabanabba8/automatic-tutorial-creator`, then `hermes plugins enable automatic-tutorial-creator`.
- **Needs:** Hermes 0.22.3 or later, FFmpeg, and a Linux X11 or XWayland desktop. Narration: Gemini 3.8 Flash TTS with a Google sign-in held by Hermes (default), a speech server on your computer, or a speech tool you select.
- **Internet:** Nothing, except narration: with the Gemini default, the narration text goes to Google and costs money, capped by a per-tutorial spending guard. Recording and cutting are local.
- **Limits:** Only X11/XWayland windows are captured; native Wayland and Windows are not implemented. Keep the window uncovered while recording. Exported tutorials are limited to under 90 seconds.
- **Credits:** Narration voices come from the engine you choose. Licence: GPL-3.0-or-later.
- **AI assistance:** Written with AI coding assistants (Anthropic Claude and OpenAI Codex agents) under the maintainer's direction; what was actually tested is listed in VERIFICATION.md.

Development build. Linux X11/XWayland is the first implemented capture backend;
native Wayland and Windows capture are not yet implemented or verified.
Higgs TTS3 narration and native computer-use step dispatch are implemented;
see VERIFICATION.md for tested scope and remaining checks.

## Workflow

1. Ask Hermes to list capture sources. Select the exact application window and,
   optionally, one application audio stream.
2. Start a bounded take, then mark steps while demonstrating the application.
3. Stop the take. Select start/duration ranges from its timeline.
4. Export: the tool creates a new H.264/yuv420p MP4, measures its duration, and
   decodes it fully to check for errors. Combined clips may total at most89 seconds.
5. Read the exported timeline. Recorded markers are mapped through the cuts;
   sample frames at relevant timestamps and inspect them before describing a step.
6. Supply narration cues with `start`, `end`, and `text` in **export seconds**.
   Higgs generates each short cue; actual audio duration must fit its allotted
   interval. An overrun returns a timing-revision report without cutting or
   accelerating the voice. Unchanged cues are cached across revisions.
7. The narrated MP4 retains application audio, ducking it under speech. It includes
   separate SRT captions and a credit file. Captions are timed by speech segment;
   the local Higgs adapter does not claim word-level alignment.

`tutorial_step` invokes one `computer_use` action through Hermes's public dispatch,
after recapturing the exact recorded window in the same Hermes session and X11 display, then returns a fresh capture. Host approvals remain in force, and denied actions are returned without claiming success. Supply the recording window ID in `observe`. Element-index actions are not supported after recapture; use coordinates from a fresh observation. The plugin rejects overlapping tutorial steps in its own process. Coordinate other computer-use calls and processes separately: the host target is sticky and the preflight plus action are not atomic. The model must inspect the resulting state before narrating success.
The step label records an attempt, not an independently verified UI outcome.

For tutorials that use separate save/export dialogs, explicitly choose
`capture_mode=window_region` and optionally `show_cursor=true`. This records the
selected window’s fixed on-screen rectangle, including dialogs inside it. Other
overlapping windows or notifications inside that rectangle can also appear: use
a private display and keep unrelated content away. The window must be fully on
screen and must not move or resize during the take. Desktop/root selection is
still refused. The default `window` mode and hidden cursor preserve existing
recording behavior; some applications draw their dialogs outside that drawable.

Keep the window visible and uncovered: X11 capture is not an occlusion-safe GPU
capture mechanism. Native Wayland windows do not appear in the X11 inventory.
Window resizing/minimizing during capture is unsupported. Markers use FFmpeg's
media clock, refreshed approximately twice per second; they are not frame-exact.

Optional audio captures one selected PulseAudio/PipeWire playback stream. It is
temporarily routed to a private null sink and restored afterwards. You will not
hear that stream during recording. New/replaced streams are not automatically
included. The plugin never selects the microphone or system monitor by default.

## Requirements and installation

Python3.11+, FFmpeg with x11grab/libx264, ffprobe, xwininfo. Application audio also
requires pactl and a working PulseAudio-compatible server. Install these with
your normal package manager. The plugin downloads nothing.

Install this directory through Hermes's normal local plugin installation flow.
No API key is required for capture and editing. Persistent takes live in the
active profile's plugin-data/automatic-tutorial-creator directory. Only one take per profile
may run at once; the worker auto-stops within ten minutes plus bounded shutdown.

## Gemini 3.8 speech (default)

Narration defaults to Gemini 3.8 Flash TTS with a Google sign-in held by Hermes (your own OAuth client, `hermes auth add creator-studio:google`; no gcloud file is read). `capture_sources` lists readiness and 30 named voices with gender, trait and measured pitch;
set `gemini_voice` to pick one. One request is sent per narration line and never retried; a ledger
(`gemini-usage.json` in the take folder) enforces `gemini_max_usd` (default 0.50) and the narration result
reports usage. The Google Cloud project comes from the `gemini_project` setting and is never
shown. Unchanged lines are reused from cache. Cost is cents per tutorial.

## Known limit: LibreOffice Calc

Hermes computer-use `type` into a LibreOffice Calc window makes the app grow without bound until the system
kills it. `tutorial_step` pastes the text instead (clipboard plus the ctrl+v key action, which keeps its
normal approval). Typing in a terminal, Writer or a text editor is unaffected.

## Higgs setup (legacy route)

Use your existing local SGLang-Omni Higgs TTS3 service. In plugin settings, set
`higgs_url` to its loopback origin, `higgs_model` to the served model ID, and
optionally a voice name. The plugin never starts the service, downloads weights
or reads provider credentials. The API adapter requests a bounded WAV response
from `/v1/audio/speech`; remote origins and redirects are refused.

Each cue is limited to300 characters and60 words because earlier local Higgs
evaluation found unreliable long-turn synthesis. Those limits reduce exposure;
they do not prove the spoken transcript is correct. Listen before publishing.

An optional user-selected local WAV/FLAC/MP3 reference and transcript may be
configured; it must be allowed by the server too. Reference bytes are hashed so
changes invalidate cached speech. Set `higgs_revision` to the model revision and
change it when replacing the server weights. No reference clips are shipped.

Higgs model licensing is separate from this plugin's code. The published model's
Creator Use Grant permits qualifying creator content with Boson attribution;
other uses may require a separate license. Every narrated export writes the
credit alongside the video for its description. See the
[model card and license](https://huggingface.co/bosonai/higgs-tts-3-4b).

## Disclosure

Runs local xwininfo, FFmpeg, ffprobe and optional pactl commands, without a shell.
Reads window titles, window pixels, and only the audio stream explicitly selected.
Starts one bounded background recording worker per take. Stores video, audio,
markers and process receipts locally. Narration sends the supplied script and
optional reference-file path/transcript to the configured loopback Higgs server;
the reference file is read to hash and validate it. Computer-use steps invoke the
host's existing tool and can change the selected application as requested.
No telemetry, external service calls, self-update, credential access or automatic
publication. Abrupt SIGKILL/power loss may leave an
unfinished MKV and audio routing requiring manual recovery; status reports this.
Recorded private content must be reviewed before any publication.

GPL-3.0-or-later. See LICENSE. Other applications and codecs keep their own licenses.

## Resource-driven speech setup (maintained source)

The registered workflow asks about local/remote resources, installed runtimes,
subscriptions vs verified API entitlement, privacy, and per-tutorial/month budget
in ordinary chat. `narration_backend=host` selects a registered native speech tool
with explicit arguments/model/revision, PCM WAV result field and credit.
`narration_backend=local_http` selects a compatible loopback speech service/model
without imposing Higgs sampling controls or Boson attribution. Neither downloads
weights or silently falls back. Legacy Higgs settings/cache stay compatible.
Uncertain host attempts require an explicit `host_tts_retry_nonce` change; valid
cached cues remain reused. Duration-fit checks still refuse overruns.

Capture remains X11/FFmpeg with Pulse-compatible app audio. Native Wayland,
Windows/macOS capture adapters are not supplied by this maintenance. The generic
speech transports were fixture-tested; no new speech/model/production recording
was generated. Existing contest narration remains local Higgs3 only.
