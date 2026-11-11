---
name: create-tutorial
description: Create a short application tutorial using actual computer-use actions, timestamped steps, user-selected speech resources and checked video export.
---

On first use read the [bundled LLM wiki](../../llmwiki/index.md), then load
only the domain references needed for this task.


Use Automatic Tutorial Creator's executable tools to demonstrate the user's
requested task in a real application. Choose a small, useful task that can be
shown clearly within89 seconds of edited footage.

At first setup ask in ordinary chat about the target OS/display/audio server,
installed capture/editing tools, CPU/RAM/GPU/VRAM, local models/runtimes, remote
services/native host tools, subscriptions, separately verified API credits,
privacy and maximum spend per tutorial/month (including zero). Reuse known
answers. Recommend a route from actual resources; capture is currently X11 plus
FFmpeg/Pulse-compatible audio, not universal platform support. A different
platform requires its supported capture/target/action contract and a validated
adapter; stop that capability if unavailable and continue script/edit planning.

Narration defaults to `narration_backend: gemini`: Gemini 3.8 Flash TTS through the person's own Google
Cloud login (no downloads, one request per narration line, a spend guard of 0.50 USD per tutorial, usage
recorded in the narration result). `capture_sources` returns a `speech` section that lists whether Gemini is
ready and all 30 named voices with gender, trait and measured pitch: read it, then pick one voice by name to
fit the content and set `gemini_voice`. Other routes remain available: `host` for an explicitly selected
registered native speech tool, `local_http` for a selected speech service, and legacy `higgs`.
No provider downloads, starts, paid calls or fallback merely to test wiring.
Subscription membership alone is not API entitlement. Before remote/paid use
confirm uploads, estimates, remaining quota and enforceable spending limits.
Host failures with uncertain spend are retained; changing `host_tts_retry_nonce`
is an explicit user-requested retry, never an automatic repair.

1. Identify the application, intended outcome, allowed edits, and safe demo data.
   Use existing user authorization. Keep approval requirements for consequential
   app actions; recording does not authorize purchases, publication or messages.
2. Inspect the application with native computer use. Call `capture_sources` and
   select its exact visible X11/XWayland window. If audio is wanted, select only
   that application's listed audio stream. Explain that the stream is temporarily
   muted while captured. Native Wayland and Windows are not supported yet.
3. Start a bounded take. While it records, never call `computer_use` directly for a demonstrated action: every
   action goes through `tutorial_step`, otherwise the step is not marked and the tutorial has no step list. Allow generous time: every step waits for the person's approval and for your own
   reasoning, so use `max_seconds` of 1800 (the maximum; each approved action and each thinking pause counts) and stop the take as soon as the steps are done; export cuts
   the waiting out. Keyboard shortcuts into an X11 app are often refused with background delivery; the refusal
   names `delivery_mode:"foreground"`, so retry that one action with it. For each step, use the current `computer_use` schema and
   a freshly observed target in `tutorial_step`. Supply the same explicit app
   name and the exact recorded `window_id` for observation. The plugin looks up the window's
   own process ID itself (computer use needs both); you may pass `pid` to override it. An empty
   capture means the window could not be targeted and no action is sent. A window manager must
   be running on the display. Use fresh coordinates,
   not element indices. A fresh `ax` or `som` capture lists each element's `bounds` as `[x, y, width, height]`
   in the same coordinates the click uses: click the centre (x + width/2, y + height/2), and never estimate a position
   by eye. A menu or an effect dialog is a separate window, so for a take that must show it use
   `capture_mode: window_region` on a private display (the window must be fully on screen and on top). A drag
   selects a time range in an editor. Element indices are refused because the preflight recaptures the window. Run computer-use
   calls sequentially: target selection and action are not atomic. Read the returned
   fresh screen/tree before concluding that the action succeeded. A timestamp label records an attempt.
4. If a step fails or is blocked, preserve that outcome. Stop or correct the
   demonstration within the authorized task; never narrate success over a failure.
   Use `capture_mark` for meaningful manually demonstrated steps too.
5. Stop the take. Read its timeline and choose a concise sequence of actual
   source segments. Export with `capture_export`, totaling at most89 seconds.
   Disclose any compressed waiting or discontinuity that changes the impression
   of speed. Do not fabricate application results or pass fixtures off as live work.
6. Read `tutorial_timeline` for the exported video. Use `tutorial_frame` to sample
   relevant timestamps and inspect frames directly with native vision. Use the
   export clock for all narration; source-recording times change after cuts.
7. Write concise narration about the observed actions. Give `tutorial_narrate`
   ordered, non-overlapping cues with `start`, `end`, and `text`. Use the speech
   backend selected during setup through plugin settings. Do not install models,
   start unrelated GPU jobs, or fall back to a paid provider automatically.
8. If a cue overruns, shorten that cue or revise its allocated interval. Reuse
   unchanged cached speech. Do not cut off or accelerate speech to hide an overrun.
   Listen/check the resulting narration; duration checks do not prove word accuracy.
9. Report the verified duration and file paths, caption timing limitations, and
   selected backend's credit file. The captions are measured segments, not word alignment.
   Review captured personal information before sharing. Publish only when the
   user has explicitly instructed publication to the particular destination.

## Driving an application by keyboard (general advice)

Coordinate clicks on menu items are unreliable on a bare virtual display; keys are not.
- Prefer keyboard for menus, dialogs and text entry. Send keys to the window with `delivery_mode:"foreground"`.
- One action per `tutorial_step` (one key chord, or one short `type` string). After each, read the fresh capture
  before the next. A tick in the capture is not enough: confirm the screen shows the expected change.
- A menu opens with its FIRST item highlighted, so `alt+<menu letter>` then `Down` N-1 times then `Return` picks item N.
  Read the menu from a capture (or its accessibility tree) to count items instead of guessing.
- Dialogs have accelerator letters (for example `alt+f` for Finish); read the button labels first.
- A menu or dialog is its own window, so for a take that must show it use `capture_mode: window_region`.
- Editors: `ctrl+Home` goes to the start, `shift+arrows` extend a selection, `ctrl+b` toggles bold, `Escape`
  leaves a mode. Worked example in a spreadsheet: type text, `Tab` to the next column, `Return` for the next row,
  a formula such as `=SUM(B2:B6)`, `ctrl+Home`, `shift+Right` then `ctrl+b` for a bold header, `ctrl+Home` and
  `shift+Right` then `shift+Down` x5 to select the data, `alt+i`, `Down`, `Return` to open the chart wizard,
  `alt+f` to finish it, then `Escape` until the chart is deselected.

- Known limit: do not use `type` in LibreOffice Calc. The plugin pastes the text instead (clipboard + ctrl+v); in a terminal or text editor `type` is fine.

## Teaching a command-line or terminal lesson

Order of work for a terminal lesson: `capture_sources`, pick the terminal window, `capture_start`, then every key press and every
typed line through `tutorial_step`. Never send a raw `computer_use` `type` or `key` to the lesson terminal before the take has
started and never outside `tutorial_step`. A terminal on X11 refuses background input: pass `delivery_mode:"foreground"` on every
`tutorial_step` action from the first one, and if an action is refused, retry it as the refusal says. A refusal is never a reason to
stop and report that the lesson could not be made: carry on until the export is narrated.

A beginner must be able to follow every step on screen.
- ONE command per `tutorial_step`, one idea per step, each step marked and then narrated. `tutorial_step` refuses a typed
  line with chained `&&` or `;`, embedded newlines, or more than 110 characters.
- Use the plainest command a learner would type (for example `echo 'text' > notes.txt`, `git status`, `git add notes.txt`,
  `git commit -m "message"`, `git diff`, `git restore notes.txt`, `git switch -c idea`, `git log --oneline --graph --all`),
  never `printf` with backslash escapes or long one-liners.
- Press Return as its own step action, then let the output stay on screen for 2-3 seconds (a `wait` action) before the next command.
- Run `clear` between chapters so the screen never scrolls or wraps in a confusing way.
- Work in the short folder the person gave you; do not run `pwd` or print long paths.
- Narrate each step: name the command and say what its output shows, using only what a frame of the export shows.
- Every typed command is two steps: `type` the line, then `key` `return` as its own step, then read the capture and confirm the
  output appeared before the next command. Never type the next line before the previous one has run. If the person says the
  terminal is already in the lesson folder with Git ready, do not run `mkdir`, `cd` or `git config`. A typing slip is not a
  reason to abandon the take: press `ctrl+c`, retype and carry on; export only the clean segments.
- Plan the whole command list BEFORE the take and keep it to 16 or fewer commands. Spend them on the idea the person asked
  for, in order, and finish with the payoff the person named (for Git: save, change and `git diff`, second save, undo a
  mistake, branch, merge back, `git log --oneline --graph --all`). Do not spend steps on `cd`, `pwd`, `git config`, `git status`
  or other setup the learner does not need; the identity and folder are already prepared.
- Export contiguous, complete segments: every command that you narrate must be shown typed, run and with its output, inside one
  segment. Never cut away between a command and its output. The cuts may only remove waiting and the `clear` steps.
- Narrate only what a frame of the export shows. NEVER say that a clip "skips", "omits" or "shortens" anything and never
  mention the cutting, the recording or the plugin; the lesson must read as one smooth walk-through.
- Each cue is one short sentence (about 4 seconds of speech) that names the command and what its output means.
