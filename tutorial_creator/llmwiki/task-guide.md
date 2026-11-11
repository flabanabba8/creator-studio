---
status: SOURCE-REVIEWED
curated: 2026-11-09
---
# automatic-tutorial-creator setup and task guide

This is a source-reviewed operating guide, not a claim of a new live test.
Resolve exact parameter shapes from [tool contracts](tools.md) and
[registration schemas](contracts.json) before calling a tool.

## Setup decisions

Identify the app, task, safe demo data and allowed actions. Require the current X11/XWayland capture path with FFmpeg/ffprobe/xwininfo; selected app audio additionally needs a Pulse-compatible server. Choose speech only after discussing hardware, installed runtimes, privacy, subscriptions/API entitlement and budget. Native Wayland capture is not supplied.

## Worked task flow

List capture_sources, select the exact window and start a bounded take. Mark a real operation with capture_mark or use tutorial_step with the same observed window and fresh coordinates. Stop, read timing, and capture_export selected segments totaling at most 89 seconds. Inspect tutorial_frame samples, then place tutorial_narrate cues on the exported clock, not the source clock.

## Failure diagnosis

A recapture invalidates old element indices; capture plus action is not atomic across other clients. If the selected audio stream is muted during routing, explain that intended side effect and verify restoration. A narration overrun needs revised wording or time allocation; do not cut speech, accelerate it or automatically reroll. Window resize, occlusion or minimization can invalidate the take.

## Acceptance and evidence limits

Accept a fully decoded export of the intended observed actions, actual narration fitting each interval, correct source/export time mapping and preserved credits. Mechanical duration and dispatch acknowledgment do not prove UI success or accurate spoken words. Keep contest narration on its already-authorized local Higgs3 path.

## Source trail

Derived from the packaged [README](../README.md), [manifest](../../plugin.yaml),
registered tool schemas and the tests listed in provenance.json. Existing
verification records describe their own dated scope; no new live capability
was inferred from this documentation review.

### The app is visible but its export dialog is missing

A selected X11 drawable can omit a separate application dialog. For a tutorial that must show menus/save dialogs and pointer clicks, explicitly select `capture_mode=window_region` and `show_cursor=true` before starting. It records only the selected window’s fixed screen rectangle, not a whole desktop selection. Any overlapping pixels in that rectangle can be recorded; use a private display, keep unrelated content away and do not move/resize the window. Inspect a frame while the dialog is actually open, not just the beginning/end of the clip. Default window capture remains available for existing tasks. A generated caption file must be checked at its actual returned path before claiming it is missing.

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
