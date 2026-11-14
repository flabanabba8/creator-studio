---
status: SOURCE-DERIVED
curated: 2026-11-13
---
# Recognising a whole stream (clips_transcribe)

Use this when a project has no transcript: a stream with no caption track, or a recording on this computer. One tool does all of it.

## What it does

- `clips_transcribe` starts speech recognition for the whole video or recording from one request, with the recognizer the user chose in Caption Studio. If they have not chosen one, the Caption Studio interview comes back instead and nothing is fetched or recognised.
- For a YouTube video it fetches only the audio track (once, kept in the project folder). For a recording it reads the file where it is.
- The audio is cut into pieces of about 10 minutes (`piece_minutes`, 0.5 to 60). Each cut is made at a quiet point in the last minute before the mark (a quarter of the piece length for short pieces), so a word is not split; with no quiet point it cuts at the mark. A rest of up to 1.25 pieces is recognised as one last piece.
- Each piece is an ordinary Caption Studio job (`captions_generate`), run one after another through the same recognizer choice. Caption Studio does not split audio itself and one job allows at most two hours, which is why the splitting is done here. No second recognizer setting exists.
- The measured word times of each piece are moved to video time (piece start added) and saved. Transcripts from this route always have word times (kind `words`), because Caption Studio refuses recognizer output without them.
- It runs in the background. The call returns at once (or after `wait_seconds`, up to 120, default 20) with progress.

## The request flow for the model

1. `clips_transcribe` with `project_id`. Nothing else is needed.
2. If the result has `recognizer_interview`, ask the user the questions, save with `captions_recognizer_setup`, then call `clips_transcribe` again.
3. Otherwise read `recognition.progress` ("30.0 of 339.0 minutes recognised"), tell the user it is running and about how long is left (`minutes_left_estimate`), and call `clips_transcribe` again with the same `project_id` (use `wait_seconds` 60 to 120) until `recognition.state` is `done`.
4. When done the full transcript is already attached. Go straight to `clips_outline`. There is no export step and no `clips_use_transcript` step.

Every result carries a plain `next` instruction. While no piece is finished it says there is no transcript yet and not to suggest or guess any clips or times.

## Progress, partial transcript, resume

- After each piece the project gets a partial transcript. `clips_outline`, `clips_transcript` and `clips_propose` work on it and add `partial_transcript` (the transcript origin also says PARTIAL, with minutes covered). Nothing after the covered time may be proposed or guessed.
- Pieces are saved under the project folder (`recognition/`). If the run is interrupted (the process is closed or killed, the machine restarts, a piece fails), call `clips_transcribe` again: it carries on from the next unfinished piece and reports `resumed_from_piece`. The piece that was in flight is recognised again from its start. A piece length given on a later call is ignored while pieces exist; `restart=true` forgets them and starts over.
- A failed run reports `recognition.error` and `next`; calling again retries from the failed piece. If it fails twice the same way, report the error to the user.
- A transcript the user attached meanwhile (`clips_use_transcript`) is never overwritten: recognition stops with state `stopped`. A project that already has a transcript is left alone unless `restart=true`.
- If another Caption Studio job is running in the profile (it allows one at a time) the run waits for it.

## Limits and where things stay

- Needs ffmpeg and ffprobe, and a Caption Studio recognizer the user has chosen. A stream that is still on air is refused until it ends.
- Whether audio leaves the computer depends on the route the user chose in Caption Studio (a local program stays local; an online service gets the audio pieces under its own terms). Pieces are written to the project folder in this plugin's private data and removed after use. The big audio copies Caption Studio keeps inside each finished job are deleted once the words are read; its small job records stay.
- Recognition only runs while the Hermes process is alive. Closing it pauses the work; calling the tool again resumes it.
- Speed is the recognizer's: expect a long stream to take as long as the recognizer needs per hour of audio. The estimate in the result is measured from the finished pieces.
- A hard cut (no quiet point found) can split one word at a piece edge. Check a clip's first and last words before cutting.
