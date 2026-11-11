# Verification

> **Part of Creator Studio.** This is the stand-alone plugin's own verification record. The evidence in it belongs to that plugin; see the suite's VERIFICATION.md for what was checked on the bundle.

- The PageCast cast check detects a wrong speaker, duplicate or missing passage coverage, source-hash mismatch and unavailable text baseline. A separate PageCast fixture split a long turn into multiple passages, reported mismatches before assignment and matched after all passages were assigned. Inputs remain caller-supplied and point-in-time; this does not verify voice quality or later edits.

- The optional PageCast text-status handoff accepts a matching source and `unchanged` status, rejects `changed` and `unavailable`, and requires both source fingerprints when status is provided. A Linux PageCast/Podcast fixture and a native Windows text-only fixture exercised edits and missing baselines. Caller-supplied values are not independently authenticated; speaker assignments, speech and later edits still require review.
- Mixed-case private-directory boundaries were checked using synthetic paths on Linux and native Windows; no real credentials were used.

- An initial native Windows check exposed the POSIX-locking limitation. After adding Windows locking, synthetic single-bed and timed-bed mixes passed on Python 3.14 with FFmpeg; the timed check measured both beds and a silent gap, and a separate process was refused while the lock was held. A synthetic mix also fed the video plugin. No audio was played or perceptually reviewed; Windows ACLs, real episodes and broader Windows coverage remain unverified.

- Unit checks cover missing sources, incomplete reviews, and stale review detection when dialogue or source references change.
- Hermes manifest validation, Plugin Doctor, and actual runtime skill discovery passed.
- A private CPU-only integration fixture used the review-bound handoff to import two synthetic turns into PageCast Director, assigned distinct Flite voices, rendered and exported WAV. It did not use a GPU, contact a hosted voice service, or play or listen to the output. A separate longer-turn test confirmed PageCast split one turn into multiple passages with the same paragraph index. PageCast is a separate optional plugin and speaker assignment must be checked.
- Source fidelity, editorial judgment, naturalness, long-form production, and publishing are not automatically verified. This candidate is not a completed contest submission.
- A synthetic two-segment PageCast WAV timeline was mapped back to podcast segments and used to build chapter notes; its final passage boundary matched the exported WAV duration. No listening review was performed.
- A synthetic PageCast timeline with explicitly requested passage text produced draft cues accepted by YouTube Video Studio. No speech transcription, word-level alignment or listening review was performed.
- A synthetic PageCast caption handoff checks matching original-source fingerprints and rejects a mismatch. The fingerprint cannot detect later edits inside PageCast.
- A synthetic narration/music file mix verified looped audio, WAV format, duration, private output mode, source preservation, profile opt-in and timeout cleanup without opening an audio device. A separate synthetic PageCast-to-mix-to-video integration passed. No audio was listened to and no loudness or music-balance judgment was made.
- A temporary ten-minute synthetic mix and a music bed starting at nine minutes passed duration, silent-gap and signal checks on CPU. This does not establish realistic music balance, audio quality or performance for every machine.
- A mocked Inworld response passed through PageCast WAV export and this mixer; the mixer made no additional provider request. No live Inworld request or audio playback was performed by that integration fixture.
- A separate CPU-only check reused an existing fictional six-second PageCast export from an earlier live Inworld/Flite test, mixed a synthetic bed and passed the mix to the video plugin. No new provider request or playback occurred; perceptual quality remains unreviewed.
- A synthetic silent narration with two different tone beds verified the selected intervals, a silent gap, and overlap rejection. No audio device or listening review was used.
- The two-bed synthetic mix test also checks explicit fade-in and fade-out amplitudes and rejects fades longer than the bed. It does not establish perceptual quality.
- A synthetic narration impulse was about 4.8 ms late with the limiter default; enabling FFmpeg latency compensation brought the tested onset within 2 ms. This is not a general synchronization or listening-quality guarantee.

- 2026-11-07: added `podcast_load_episode`, `podcast_lint_episode` and `podcast_preflight` (episode folders, style-profile lint, kids preset, review-hash gate, optional source-check summary). Eight new fixture tests, 23 total, pass in the Hermes venv. Rules were ported from a production show's linter and have not been tuned on other formats. No audio, listening review, live service or Windows run.
- 2026-11-07: read-only parity run on 14 real Breach Protocol episode folders (2026-09-13 to 2026-11-06): the new lint reported the same error counts as the show's own linter on every one (2, 1 and zero on the rest; the show's extra benchmark-name warning is not ported), loaded all files and speakers, and `podcast_preflight` passed the 2026-11-06 news folder against its real, hash-bound review. Nothing was written to those folders.
- 2026-11-07: `podcast_mix` and `podcast_mix_timeline` accept `loudness_lufs` (-30 to -10) and always report the measured `integrated_lufs`. A quiet synthetic mix measured below -30 LUFS and the same mix with a -16 target measured within 2.5 LU of it (24 tests pass). One-pass loudnorm is approximate; no real speech or music, no listening.

## 2026-11-10 maintained scope revision

Twenty-four existing offline/mocked tests pass; shared workbench tests additionally exercise real WAV assembly and changed-material rejection. The chosen Camoufox/Playwright installation crashed on page-error handling during a real Nikon fetch and hit its bounded timeout. No fallback, private-runtime modification or successful fetch is claimed. Hermes admission and retirement preflight pass; detailed local receipts are retained in the contest maintenance evidence. Old evidence above keeps its original scope.

## 0.2.1 (2026-11-10): returning to earlier work, clearer research gates

Found by real owned Hermes runs: a returning user could not continue an earlier project because no tool listed projects; a mistyped project ID silently saved nothing; error pages were saved as sources; and a script using `sources` instead of `source_ids` got a misleading error.
- `podcast_project_status` with no `project_id` lists existing projects (ID, topic, phase, counts), newest first.
- A wrong or mistyped project ID returns an error listing the existing IDs.
- Pages with HTTP status 400 or above, and short pages that say "page not found", are not saved as sources (`page_unavailable`).
- A factual section without `source_ids` gets a message naming the exact key.
- Material from the Hermes profile cache is refused with a message saying to save it in the task folder or plugin data folder.
- Camoufox reader: guard against the Playwright pageError crash, stdout isolation, and a hard deadline.
- Skill and wiki: plain-language rule and a three-source research rule.

Checks for 0.2.1 (2026-11-10): 27 offline tests pass; tools/check-plugin-workflows.py ok on the package; offline dry check on a copy of a real earlier project: list projects, attach four narration WAVs from a task folder, assemble (54.0 s). Live runs were done in the maintainer's own private workspace.
- Attaching the exact same file again (same SHA-256 and kind) reuses the existing material instead of adding a second copy (found when a returning session re-attached a take that was already in the project).

## Skill text, 2026-11-10

Added a first-time quick path and a direct how-to for recording through a local or user-selected HTTP speech endpoint. Text only; no code changed.

## 0.3.0 (2026-11-10)

Mocked-transport tests (tests/test_gemini_route.py): two speakers with different voices, one request per turn, resume without rerolls, voice checks before any request, spend guard, route reported at topic start, episode assembles from the takes. 31 tests pass. No live Gemini request.
