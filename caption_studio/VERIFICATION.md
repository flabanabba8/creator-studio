# Verification

> **Part of Creator Studio.** This is the stand-alone plugin's own verification record. The evidence in it belongs to that plugin; see the suite's VERIFICATION.md for what was checked on the bundle.

- A standalone headless browser fixture with approximate theme variables was inspected at 375 px. The initially disabled control now appears distinct and the page had no horizontal overflow; the Desktop flow test passed. This is not native Hermes Desktop or a complete accessibility review.

- Mixed-case protected-directory fixtures passed on Linux and native Windows; no real credentials were used. This is not a full platform or publication audit.

- Twelve Python tests passed in the Hermes-compatible overlay, including owner-only POSIX output permissions under a permissive umask, offset and drift correction, profile boundaries and Desktop API behavior. Hermes plugin validation passed without warnings.
- A synthetic SRT handoff from YouTube Video Studio was inspected, retimed and reinspected after the permission change. An earlier tutorial-caption offset integration and Desktop flow passed.
- A separate self-authored SRT was retimed from 1–2 seconds to 2–3 seconds and overlaid on a synthetic video cue. Frames sampled at 1.5, 2.5 and 3.5 seconds were inspected: the caption and visual cue appeared together only in the middle sample. No audio or real-media synchronization was reviewed.
- Native Windows Python 3.14 passed one synthetic SRT offset correction. Windows ACL behavior and the Desktop UI were not tested.
- Existing files are not retroactively chmodded. Real audiovisual synchronization, native visual review, full Windows coverage, reviewed demonstration and complete publication audit remain unverified.
- 2026-11-07: real-captions trial. The 18 cues of a real narrated video's SRT were given a 2.5 s offset plus 1.5% linear drift; `captions_suggest_alignment` against the original found both anchors from 18 unique phrase matches, and `captions_retime` restored every cue within 1 ms of the original. This checks text-to-text alignment only; no audio was analysed, so it is not proof of picture or sound sync.

## 0.2.0 audio review and adaptive setup — 2026-11-09

- 25 Python tests pass in the existing Hermes dependency environment. New checks
  cover timed-word formats, drift/word disagreements, omissions, confidence flags,
  bounded unmatched regions, no-speech/hallucination review, CJK word intervals,
  local command/import/host/compatible HTTP interfaces, source/profile boundaries,
  original preservation, explicit manual edits/drop/export and private new files.
- Existing manual Desktop flow and the new audio flow pass React/jsdom checks:
  no provider call on mount; explicit selection; asynchronous review; audio excerpt
  control; individual word/timing choices; explicit export; polling teardown.
- The actual Hermes admission validator passed the current 0.2.0 source, with no
  failed checks or warnings. This is not a fresh install-deps/catalog CI receipt.
- A previously generated original short speech clip was recognized offline using
  an explicitly selected cached Whisper model in an optional existing Transformers
  runtime. Fifteen word-timestamp chunks were produced. The audio-derived data
  then flagged deliberately changed words and shifted cue times, and a separate
  corrected SRT was exported while the input stayed unchanged. No model/provider
  default is implied. No paid call/upload/new speech synthesis was made.
- The optional adapter's first attempts exposed runtime keyword incompatibilities;
  those failures and the corrected successful run are retained in the private
  evidence. This is one clean synthetic-voice sample, not proof of general accuracy,
  independent-model error detection, human listening quality or all backend support.
- An optional Parakeet download begun during exploration was stopped when the user
  requested runtime/model-agnostic selection; partial cache was preserved. No model
  is bundled, auto-downloaded or installed by recognition jobs.
- HTTP transport was tested against a local fixture server, not a paid provider.
  Host-tool dispatch used a mocked timed-result contract, not a fabricated live
  service. Missing/incompatible word timing fails clearly without another backend.
- Old archives, old submission pins and accepted demo/video/thumbnail artifacts
  remain unchanged. A future 0.2.0 candidate/source bundle/catalog metadata and
  clean-install evidence must be prepared before any authorized release. Private
  installed copies were not replaced.

Evidence: kept in the maintainer's private workspace.

- User-authorized OpenAI API integration passed with a short original speech clip,
  explicit endpoint/model and word timestamps. The resulting review flagged the
  deliberately corrupted words/times and exported a separate SRT. The key was
  entered through a masked native password dialog, never printed/repo-stored, and
  its temporary private input file was removed afterwards. No live Hermes profile
  or existing media was changed. This verifies one endpoint/model/sample, not an
  independent recognition-accuracy claim.
- Current wide/narrow fixture-host UI was inspected directly in the main session:
  review choices, wording, listening controls and disabled export state are legible;
  no horizontal overflow at 1280 or 375 px. This is not native Desktop integration.

## 0.4.0 blind check-and-repair — 2026-11-10

- Offline only. 32 Python tests pass in the managed Hermes interpreter, including a
  blind fixture (8 cues from saved word-timing JSON, `tests/fixtures/`) with one
  wrong word (confident heard word) and one cue displaced 2 s among correct cues:
  both are found and applied by one `captions_audio_export(apply_proposed=true)`;
  a name-like word and a low-coverage multi-word cue are surfaced as ambiguous and
  not applied; the other cues are byte-for-byte unchanged; the source SRT bytes are
  unchanged; explicit decisions win over a proposal for the same cue.
- No recognizer ran, no model/network/GPU was used, and no audio was listened to. The
  fixture words are synthetic with confidence 0.9. The thresholds are a documented
  conservative judgement, not calibrated on real recognizer error rates; a real
  recording with a real recognizer has not yet been re-run with this version.
- Review reports now carry `matched_words`, `caption_words` and `edits`; reviews made
  by earlier versions report that they must be re-run before proposing.

## 0.4.1 common-word swaps — 2026-11-10

- Why: the first real blind run (saved Whisper word timing, no confidence values) left
  the wrong word "in" (heard "and") for a human because the two spellings are not
  similar and the imported timing has no confidence. A common function word swapped
  inside a cue whose every other word matched is now clear (COMMON_WORDS in
  alignment.py, not at either end of the cue, supplied confidence if any >= .5).
  Names, numbers, content words, edge words, partly matched cues and low-confidence
  words stay ambiguous. 33 Python tests pass offline, including these boundaries.
- Still alignment-backed, not listened to. The word list is an English-only judgement
  and not calibrated on real recognizer error rates: Whisper can mishear short
  function words, so the export still reports every fix for a human to confirm.

## 0.4.2 local speech discovery — 2026-11-10

- Why: a first-time user with a cached Whisper model and a Python that can run it had no
  way to learn that from the plugin; `captions_recognizer_options` only reported modules
  of the Hermes interpreter. It now also returns `local_speech_resources`: cached speech
  models in the standard Hugging Face cache folders, PATH pythons and virtual
  environments (up to four folders under the home folder, bounded by count and time)
  that have torch/transformers/faster-whisper, library versions via the bundled
  adapter's `--probe`, and ready `recognizer` objects. Read-only; nothing is loaded,
  run, installed or downloaded. No machine-specific path is in plugin source.
- Four new offline tests (tests/test_discovery.py) use temporary folders and stub
  interpreters. A real recognition through the discovered command is verified only by
  the demo run records, not by these tests.

## 0.4.3 keep polling until the job is ready — 2026-11-10

- Why: in a first-time creation run the agent ended its turn while the recognizer was still working and reported "still running" without a caption file. The skill now tells the agent to keep polling `captions_audio_status` and to finish and export in the same turn. Text-only change; checked by the next demo run, not by a unit test.

## 0.4.4 GPU when memory allows — 2026-11-10

- Why: a first-time creation run's CPU recognition (about 6.3 GiB of RAM for a 31 s video) was ended by the machine's low-memory guard, so the job failed. Discovery now reports free GPU memory and sets the ready command's device to cuda when a CUDA torch build and enough free GPU memory exist (cpu otherwise); the adapter runs cuda in half precision. `choose_device` is unit-tested; the real GPU recognition is checked only by the next demo run.

## 0.4.5 low host memory on GPU — 2026-11-10

- Why: with 0.4.4 the cuda run still used 6.5 GiB of host RAM and the machine's low-memory guard ended it. The adapter now loads the model directly to the GPU in half precision (`device_map`, `dtype`, low CPU memory). Not unit-tested (needs the model and a GPU); checked only by the demo run.

## 0.4.6 late start with an agreeing end — 2026-11-10

- Why: in a live repair a fully matched cue that started 620 ms late (its end was right, the recognizer end differed by 60 ms) was left for a human because start and end shifts differed by 680 ms, just over the 600 ms spread limit. A cue whose start is at least 300 ms off while its end agrees within 150 ms is now clear and only the start moves (`start_only` in the evidence). Two new offline tests; 40 tests pass. Still alignment-backed, not listened to.
