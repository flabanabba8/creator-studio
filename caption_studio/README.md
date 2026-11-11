# Caption Studio

> **Part of Creator Studio.** This is the original README of the stand-alone plugin, kept as the detailed reference for this part. Its install lines apply to the stand-alone plugin only; install `creator-studio` instead. Paths such as `llmwiki/` and `skills/` here are inside this part's folder.

Create captions for interviews, tutorials, meetings or other recordings, then
listen, check the words and adjust their timing. You can also review and repair
an existing SRT. Choose a speech recognizer that fits your computer, privacy and
budget; no particular model, paid service or runtime is selected automatically.

**At a glance**

- **Install:** `hermes plugins install flabanabba8/caption-repair`, then `hermes plugins enable caption-studio`.
- **Needs:** Hermes 0.22.3 or later, FFmpeg, and a speech recognizer you choose (a local command, an imported transcript, or an HTTP service). No model or paid service is selected for you.
- **Internet:** Nothing by default. If you select an HTTP recognizer, the audio is sent to that service, only after you confirm; an optional API key is stored by Hermes.
- **Limits:** Linux is the only platform checked. Draft captions are not proof of accuracy: a recognizer cannot check its own mistakes, so listen or use a second recognizer. Originals are never overwritten.
- **Credits:** Formerly named Caption Repair. The recognizers you pick bring their own terms. Licence: GPL-3.0-or-later.
- **AI assistance:** Written with AI coding assistants (Anthropic Claude and OpenAI Codex agents) under the maintainer's direction; what was actually tested is listed in VERIFICATION.md.

For a new recording, call `captions_generate` with `media_path` and the chosen
`recognizer`. No source SRT is required. Poll the job and review its generated
cues through the existing audio status/review/preview tools. Export with explicit
decisions, or `decisions: []` to save an honestly labeled unreviewed SRT draft.
Silence produces no invented captions. Draft boundaries use measured word times;
layout grouping does not establish transcription accuracy. The same recognizer
cannot independently detect its own errors: listen or explicitly select another
recognizer for a second opinion. Originals remain untouched.

Former name: Caption Repair. The maintained package is now `caption-studio`
(0.4.6). Existing `captions_*` tools and the legacy `caption-repair` storage
namespace remain compatible; private reviews are not moved or overwritten.
`CAPTION_STUDIO_ASR_KEY` is preferred for an explicitly selected HTTP service;
the declared `CAPTION_REPAIR_ASR_KEY` remains a legacy fallback. Disable the old
plugin before enabling the renamed package to avoid duplicate tool registrations.
Private installations/settings and GitHub remotes are not automatically changed.

For an existing SRT, align it to selected audio/video and review possible transcription
errors. Choose a recognizer and runtime that suit your hardware, language, budget
and privacy needs. No model, paid provider or inference runtime is required by
the repair engine itself. The original anchor/reference-SRT tools still work.

## Check and fix, blind (default)

Give Hermes a recording and its subtitles and ask it to "check these captions and
fix them". You do not name words, cues or offsets. Hermes analyses the whole file
once, then `captions_audio_propose` classifies every cue as unchanged, clear
(decision ready, with evidence) or ambiguous (not applied, with reasons). Then
`captions_audio_export` with `apply_proposed: true` writes a separate SRT with only
the clear corrections and returns what changed, what was left and which cues need
a human. Ambiguous and unchanged cues stay byte-for-byte original; the source SRT
is never modified.

"Clear" is a deliberately conservative evidence rule (constants in `alignment.py`):
only flags `word_disagreement`/`timing_change` qualify. Text: exactly one caption
word replaced by one heard word, not a name, number or CJK, with at least 3 matched
words and >= 0.75 cue coverage, and the heard word confident (>= 0.8) or spelled
similarly (>= 0.6). Timing: matched words cover the cue (same thresholds) and start
and end move by the same amount (within 600 ms, at most 10 s) without overlapping a
neighbour; new times are the recognizer's measured word times, never invented.
Names/proper nouns, low coverage, multi-word rewrites, unheard or missing words and
conflicting evidence are ambiguous. Clear fixes are alignment-backed, not listened
to; a recognizer can be wrong, so report them as such and let people spot-check.

## User workflow

1. Select the SRT and recording. Use **Help me choose a setup**, or ask Hermes to
   inspect the available hardware/tools and your reported API access. Prefer a
   genuinely local free recognizer when practical. Some subscriptions offer
   claimable API credits; verify activation and limits rather than assuming any
   subscription provides unlimited transcription or the right endpoint.
2. Select one recognition source: a trusted local command, word-timestamp JSON
   from an existing recognizer, a compatible HTTP speech service, or an existing
   host speech tool through the agent. Choose its model/runtime explicitly.
   Hermes can help assemble/configure a compatible adapter from existing tools.
   Models and optional runtimes are installed/downloaded only with your consent.
3. Analyse audio and captions. A background job snapshots the selected input,
   obtains timed words once, and compares them with the subtitle text. It suggests
   cue timing and flags word disagreements, caption omissions, words not heard,
   low supplied recognizer confidence and weak/ambiguous alignment evidence.
4. Page the review, listen at original/proposed timing, and edit the words or
   timestamps. Another recognizer is a second opinion, not ground truth. A second
   Whisper pass can repeat the first pass's errors. Check names and uncertain
   words by listening; user-approved hallucinated captions can be removed.
5. Export to a new SRT. Unselected cues stay original. Only explicit decisions or
   the clear proposals (`apply_proposed`) are applied. Input changes invalidate export.

The Desktop page provides this flow; `repair-captions` guides an agent through
resource selection, setup, analysis and review. Source files remain unchanged.

## Recognizer contracts and portability

The core needs words with actual start/end timestamps. It accepts a top-level
`words` list (seconds or explicit `start_ms`/`end_ms`), Whisper/WhisperX-style
`segments[].words`, Transformers-style word `chunks[].timestamp`, and whisper.cpp
full JSON `transcription[].tokens` with millisecond offsets. Explicit empty word
lists mean no recognized speech and produce review flags, not invented timings.
Plain text and segment-only results cannot supply word timing and are refused.

- **Local command:** `recognizer.kind=command`, `argv` is a string array, never an
  implicitly parsed shell string. Placeholders: `{audio}`, `{model}`, `{language}`,
  `{output}`, `{output_base}`. Choose `output: stdout` or `file`. JSON stdin also
  supplies `audio_path`, user-selected `model`, `language`, `options`, `output_path`.
  Configure the actual executable/model appropriate to the machine. The optional
  [Transformers adapter](examples/transformers_asr.py) is one example, not a default
  or dependency; it uses only already-cached models and accepts user model/device
  selection. No new reasoning agent is launched as a speech recognizer.
- **Import:** `kind=import`, `transcript_path` points to timed JSON you already have.
  It runs no model or service. The recording is still used for bounded listening.
- **HTTP:** `kind=http`, explicitly selected `endpoint`, provider-specific `fields`
  and, for remote HTTPS, `allow_upload: true`. This is a multipart `file` request
  for word-JSON output. There is no vendor/model default. Local compatible servers
  need no cloud subscription. Remote services may charge and have retention rules.
  Set the dedicated optional `CAPTION_REPAIR_ASR_KEY` only through Hermes settings;
  use `use_api_key: true` and its dedicated credential header when needed. Keys are never read
  from another app or put in argv, job receipts or URLs. Changing the Desktop
  endpoint resets upload/key consent. Redirects and automatic retries are refused.
- **Host tool:** `kind=host`, a selected registered `tool` and its `arguments` with
  placeholders. Hermes owns that tool's runtime/model/auth and approvals. This
  needs agent context; the plain dashboard cannot manufacture that context. Its
  result must provide actual word timing, not just a transcript.

## Audio and bounds

Compatible mono 16 kHz 16-bit PCM WAV works with the standard library. Other media
uses an installed FFmpeg by default; `decoder_argv` can select another tool that
writes the same WAV contract with `{media}`/`{audio}`. Nothing is installed silently.
Listening excerpts use standard-library WAV slicing, not a required media player.
No host speakers, microphone, device defaults or unrelated applications are used.

Each job handles up to two hours, 8 GiB source media and 100,000 spoken words.
HTTP uploads are bounded to 64 MiB of decoded WAV; use a local recognizer or a
shorter recording for larger inputs. Copying/decoding and local recognition take
CPU/RAM/disk and possibly GPU time. On a slow uplink remote recognition can be
much slower than local processing. Local command/model execution is the user's
trusted code, not a filesystem/network sandbox; audit its own privacy behaviour.
The engine scrubs inherited API credentials and does not prompt ASR with the old
caption text. A local adapter may require separately installed dependencies.

Unique matching phrases anchor an ordered word comparison; smaller gaps are
compared with a bounded sequence matcher. Weak/ambiguous matches remain flagged.
`matched_word_coverage` measures text-matching evidence, not calibrated accuracy.
This is ASR-derived alignment, not a guarantee of frame/phoneme-exact forced
alignment. Different cuts, overlapping speech, poor audio, paraphrases and language
segmentation can require manual review. The selected recognizer's own limits apply.

Jobs and private diagnostics persist in profile-local plugin data, with owner-only
new files on POSIX. Recognition runs once per requested job, without provider/model
fallback. Cancellation stops owned local commands; a host/network request already
sent may finish, but its result is discarded. Jobs do not resume inference after
host restart; inspect retained evidence before retrying interrupted work. Windows
process-tree cleanup/ACLs and full native Desktop integration remain unverified.

## Existing retiming tools

`captions_inspect`, `captions_suggest_alignment` and `captions_retime` retain their
original explicit offset/linear-drift and trusted-reference-SRT behaviour. They
preserve wording, cue order and the source file. Reference suggestions require
unique normalized phrases of at least three words and must be reviewed.

See [verification](VERIFICATION.md) for actual checks. No media publication,
provider signup, live-profile replacement or contest submission is performed.
