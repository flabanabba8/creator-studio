# Actual tool contracts

Registered source schemas; registration alone does not establish live backend readiness.

## capture_sources

List local X11 windows and application audio streams. Native Wayland windows are not supported.

Inputs: `display` (optional).

## capture_start

Start recording one selected visible X11 window. Optionally route ONE explicitly selected audio stream into a temporary recording sink; playback is muted until recording stops. Recording stops automatically at max_seconds.

Inputs: `window_id` (required), `display` (optional), `max_seconds` (optional), `capture_mode` (optional), `show_cursor` (optional), `audio_stream` (optional).

## capture_status

Read recording state, media duration and step markers. With no job_id it lists the newest recordings with what each still needs (the resume path for "carry on"): export, narrate or nothing; already spoken cues are cached and never paid for twice.

Inputs: `job_id` (optional).

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

Generate timestamped narration and mix it into a completed export. The route is the one the USER chose in the first-use interview (narration_backend chosen); the plugin never picks a voice engine itself. Until a route is chosen this returns interview_needed with the options found and the questions to ask (call tutorial_speech_setup with the answers, including route). The speech_route field of the result says which route really ran. One request per cue; a named voice for online routes.

Inputs: `job_id` (required), `export_name` (required), `import_from_project` (optional), `cues` (required).

## tutorial_speech_setup

First-use interview and speech check. Without answers: returns what speech resources this computer has and the questions to ask the user (what they want to make, natural vs plain voice, whether online and paid services are OK and a budget, what they already have). With answers: saves them and says which route narration will use and what is missing. Sends nothing, spends nothing.

Inputs: `answers` (optional).

## tutorial_step

Perform ONE computer-use action through Hermes's native tool, with its approvals unchanged, while a take is recording. Mark the attempt on the media timeline and return a fresh capture for verification. A tool acknowledgment is not proof the intended UI result occurred. Use only for the user-authorized tutorial task and the selected app.

Inputs: `job_id` (required), `label` (required), `action` (required), `observe` (required).
