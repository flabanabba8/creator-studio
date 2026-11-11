---
status: IMPLEMENTED; offline fixture checks, not universal backend validation
curated: 2026-11-09
---
# Create, review and export captions

Use for a meeting, interview, tutorial, recorded talk or clip with no subtitles.
Ask/reuse language, user resources, privacy and spending preferences, then choose
an actually available word-timestamp recognizer. No model/API default is implied.

1. `captions_generate` takes selected media and a configured command, import,
   compatible HTTP endpoint or native host recognizer. It needs no source SRT.
2. Poll status, then page the draft review. Sentence punctuation, gaps, measured
   duration and line budgets group recognized words. These are editable defaults,
   not invented word timestamps or pixel-accurate layout guarantees.
3. Listen/check names and uncertain words. Agreement with the same recognizer's
   output is not independent accuracy evidence. A deliberately selected second
   recognizer can review the exported draft through the existing repair flow.
4. Export selected reviewed decisions to a separate SRT. `decisions: []` can save
   an explicitly unreviewed generated draft; the result carries `draft: true`.
   Silence creates no captions, and an empty export remains a draft requiring review.

Missing tools, word times or permission are concrete setup failures, never a
silent paid upload/fallback. Original media and legacy review jobs remain intact.
The frontend opens in Create mode and separately offers existing-caption review.
Legacy storage/tool identities are intentional compatibility, not a second plugin.
