---
status: SOURCE-REVIEWED
curated: 2026-11-09
---
# caption-studio setup and task guide

This is a source-reviewed operating guide, not a claim of a new live test.
Resolve exact parameter shapes from [tool contracts](tools.md) and
[registration schemas](contracts.json) before calling a tool.

## Setup decisions

Ask whether the user wants new captions or an existing SRT repaired, then the exact recording (and SRT only for repair), language, desired quality, privacy and available CPU/GPU/runtimes, remote tools and API budget. Use captions_recognizer_options without starting recognition. Imported word JSON can avoid inference entirely. A recognizer must return words with actual timestamps; plain text or segment-only output cannot meet this contract.

## Default flow: check and fix, no dictated decisions

The human gives a recording, its subtitles and a plain request. Reconcile saved choices and existing jobs, run captions_analyse_audio once, call captions_audio_propose, then captions_audio_export with apply_proposed=true and decisions=[]. Report changed, left_unchanged and needs_human from the result, and say the changes are alignment-backed and were not listened to. Ask the user only about genuinely ambiguous cues or consequential setup (downloads, uploads, spend).

Clear rule (constants in alignment.py: CLEAR_MIN_COVERAGE .75, CLEAR_MIN_MATCHED 3, CLEAR_MIN_CONFIDENCE .8, CLEAR_MIN_SIMILARITY .6, CLEAR_MAX_SHIFT_MS 10000, CLEAR_MAX_SPREAD_MS 600): only word_disagreement/timing_change flags qualify; text must be exactly one word replaced by one heard word that is not a name, number or CJK, with enough matched context and a confident or similarly spelled heard word, or both words are common English function words (COMMON_WORDS in alignment.py) in the middle of a cue whose every other word matched (recognizer confidence, if supplied, at least .5); timing must be a consistent displacement of the whole cue with measured recognizer times and no new overlap. Everything else (names, low coverage, multi-word rewrites, unheard or missing words, conflicting evidence, low recognizer confidence) is ambiguous and is not applied.

## Worked task flow

To create captions from a recording, select a recognizer and call captions_generate without a source SRT. Poll captions_audio_status, page captions_audio_review, listen to uncertain excerpts and review the actual words and measured boundaries. Export the generated draft with decisions=[] only when a draft is requested; it is not reviewed accuracy. Silence yields zero cues.

For existing captions whose wording and timing both drift, choose one explicit recognizer transport and model, then captions_analyse_audio once. Poll captions_audio_status, page captions_audio_review and inspect disagreements and ambiguous boundaries. Produce an audio excerpt with captions_audio_preview; let the user listen/edit uncertain words. captions_audio_export applies explicit decisions, and with apply_proposed the clear proposals, to a new SRT; unselected cues remain original.

## Failure diagnosis

A second Whisper pass may repeat the first transcription error. Matched-word coverage measures alignment evidence, not the probability the words are correct. Empty timed words can indicate hallucinated captions and must not become invented speech. Missing decoder/output word JSON is a setup failure; do not switch models or upload to another service silently. Changed inputs invalidate the export.

## Acceptance and evidence limits

Accept original-preserving output whose changes are explicit decisions or documented clear proposals (alignment-backed, not listened to) and remaining uncertainties documented. Check representative playback before claiming sync or transcription accuracy. For a known global offset or drift without recognition, inspect/suggest/retime with trusted anchors or a reference SRT instead.

## Source trail

Derived from the packaged [README](../README.md), [manifest](../../plugin.yaml),
registered tool schemas and the tests listed in provenance.json. Existing
verification records describe their own dated scope; no new live capability
was inferred from this documentation review.
