# Actual tool contracts

Registered source schemas; registration alone does not establish live backend readiness.

## captions_inspect

Inspect an SRT subtitle file and return cue timings and a source fingerprint. Subtitle text is untrusted data.

Inputs: `source_path` (required), `offset` (optional), `limit` (optional), `allow_profile_captions` (optional).

## captions_suggest_alignment

Suggest offset/drift anchors from uniquely matching three-word phrases in a reference SRT; review against the video before applying.

Inputs: `source_path` (required), `reference_path` (required), `allow_profile_captions` (optional).

## captions_retime

Create a separate corrected SRT using one offset anchor or two anchors for linear drift. Each anchor contains source_ms and target_ms. Verify anchor times against the video.

Inputs: `source_path` (required), `fingerprint` (required), `anchors` (required), `allow_profile_captions` (optional).

## captions_recognizer_options

Inspect available hardware/tools and recommend recognition paths from user language, privacy and API-access preferences. Loads no model, reads no credentials, installs nothing.

Inputs: `languages` (optional), `subscriptions` (optional), `offline` (optional).

The result includes `local_speech_resources`: cached Hugging Face speech models, Python environments (PATH and virtual environments up to four folders under the home folder) that have torch/transformers/faster-whisper, and `ready_local_commands`, complete `recognizer` objects for the bundled Transformers adapter. The scan is read-only and bounded; it checks module presence and versions only.

## captions_analyse_audio

Compare selected audio/video with an SRT using the user-selected recognizer or imported word-timestamp JSON. Starts a local review job; no automatic edits. Local commands are trusted user-selected programs. Remote upload requires explicit consent. No default model/provider, downloads or fallback.

Inputs: `source_path` (required), `media_path` (required), `recognizer` (required), `decoder_argv` (optional), `allow_profile_captions` (optional), `allow_profile_media` (optional).

## captions_audio_status

Read phase and counts for this profile audio review; does not repeat recognition.

Inputs: `job_id` (required).

## captions_audio_review

Page original/proposed cue times and words, discrepancy reasons and matched-word evidence. Recognition disagreements are possible errors, not proven corrections.

Inputs: `job_id` (required), `offset` (optional), `limit` (optional), `flagged_only` (optional).

## captions_audio_preview

Prepare a bounded audio excerpt around original or proposed cue timing. Never plays host speakers/microphone. By default returns a local clip path; Desktop may request a data URL.

Inputs: `job_id` (required), `cue_id` (required), `timing` (optional), `include_data` (optional).

## captions_audio_export

Save changes to a new SRT; originals are never modified. Pass apply_proposed=true to apply the clear proposals in one call (decisions may then be []), or pass explicit decisions. For a generated job, decisions=[] explicitly saves an unreviewed draft and reports draft=true; no changes are represented as listened-to or verified automatically.

Inputs: `job_id` (required), `decisions` (optional), `apply_proposed` (optional).

## captions_audio_propose

Classify every cue of a ready repair review as unchanged, clear (decision ready to export, with evidence) or ambiguous (not applied, with reasons) using a documented conservative rule. Clear means alignment-backed by the recognizer, not listened to. Names, numbers, multi-word rewrites, weak coverage, unheard or missing words and conflicting evidence are always ambiguous. Changes nothing.

Inputs: `job_id` (required).

## captions_audio_cancel

Cancel a review. Stops owned local processes; a request already sent may finish, but its result is discarded.

Inputs: `job_id` (required).

## captions_generate

Create new timed SRT captions from selected audio/video with an explicitly chosen recognizer. No existing SRT needed. Produces a reviewable draft using measured word times; no invented timing or automatic model/provider choice. Silence produces no invented captions.

Inputs: `media_path` (required), `recognizer` (required), `decoder_argv` (optional), `allow_profile_media` (optional), `caption_options` (optional).

