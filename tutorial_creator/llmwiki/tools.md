# Actual tool contracts

Registered source schemas; registration alone does not establish live backend readiness.

## capture_sources

List local X11 windows and application audio streams. Native Wayland windows are not supported.

Inputs: `display` (optional).

## capture_start

Start recording one selected visible X11 window. Optionally route ONE explicitly selected audio stream into a temporary recording sink; playback is muted until recording stops. Recording stops automatically at max_seconds.

Inputs: `window_id` (required), `display` (optional), `max_seconds` (optional), `capture_mode` (optional), `show_cursor` (optional), `audio_stream` (optional).

## capture_status

Read recording state, media duration and step markers.

Inputs: `job_id` (required).

## capture_mark

Mark a demonstration step on the current media timeline, approximately half-second precision.

Inputs: `job_id` (required), `label` (required).

## capture_stop

Stop this plugin-owned recording and restore its selected audio route.

Inputs: `job_id` (required).

## capture_export

Cut ordered segments from a completed recording into a checked H.264 MP4, at most 89 seconds. Original recording is preserved.

Inputs: `job_id` (required), `segments` (required).

## tutorial_timeline

Read source-video or exported-video timestamps, including the mapping of recorded step markers through the chosen cuts.

Inputs: `job_id` (required), `export_name` (optional).

## tutorial_frame

Decode a frame at a requested export timestamp so the agent can inspect what actually appears before writing narration. Returns a local PNG path; no image model is called.

Inputs: `job_id` (required), `export_name` (required), `seconds` (required).

## tutorial_narrate

Generate timestamped narration and mix it into a completed export. Default route: Gemini 3.8 Flash TTS through your own Google Cloud login, one request per cue, a named voice (see capture_sources, speech section) and a spend guard; other routes are a configured local speech service or a host speech tool. Measures every clip, refuses overruns without speeding/cutting speech, caches unchanged cues, and writes segment captions plus the speech credit and usage. Does not start or install a model.

Inputs: `job_id` (required), `export_name` (required), `cues` (required).

## tutorial_step

Perform ONE computer-use action through Hermes's native tool, with its approvals unchanged, while a take is recording. Mark the attempt on the media timeline and return a fresh capture for verification. A tool acknowledgment is not proof the intended UI result occurred. Use only for the user-authorized tutorial task and the selected app.

Inputs: `job_id` (required), `label` (required), `action` (required), `observe` (required).

