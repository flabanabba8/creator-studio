# Clip Studio (part of Creator Studio)

Give Hermes a YouTube link and say what you want: "find the best moments for Shorts", "cut the part where she explains the budget", "clip 12:30 to 13:10". Clip Studio reads the video through its transcript, suggests clips with times and the words they open and close on, and cuts the ones you pick.

## How it works

1. **Open.** `clips_open` reads the video page and one caption track with your own `yt-dlp`: captions written by the uploader if there are any, otherwise YouTube's speech recognition (timed per word). No video is downloaded at this point. A finished live stream works like any video. A recording on your computer can be opened instead (`media_path`).
2. **Analyse.** `clips_outline` gives the shape of the whole video (what is said in each window, chapters, YouTube's most-replayed curve, pauses) and `clips_transcript` lets Hermes read any part or find a phrase. The plugin measures; Hermes, the model you are talking to, does the judging. No other model or service is called.
3. **Suggest.** `clips_propose` records the suggestions. Each start and end is moved to a sentence or word boundary so no word is cut. You get a link that plays the video from that moment, before anything is downloaded.
4. **Cut.** `clips_cut` fetches only the chosen sections and encodes them so each cut is exact: as filmed, vertical (1080x1920) or square, cropped or fitted, with a caption file or captions burned into the picture.

**Tightening.** Ask for dead air to be removed and `clips_cut` measures the real silences in the clip and shortens the long ones to a short breath. Hermes can also leave out a boring stretch in the middle of a clip (a tangent, a repeat); it shows you the exact words that will be dropped first. Captions are re-timed to match.

**Streamers and VTubers.** A vertical clip of a stream is no use if the streamer is cropped out. `clips_frame` saves a still with a percent grid; Hermes looks at it, marks where the avatar or face camera is (`clips_face`), and every vertical or square clip of that video then keeps it in view: a corner avatar gets its own panel on top with the rest of the picture below, a large one gets a crop centred on it. When the avatar moves or changes size during a clip (a scene change), the cut follows the look of that box and switches layout at that moment; where it cannot find it, the whole picture is shown and the result says when (`clips_face_ranges` sets a box for such a stretch by hand).

**Checked captions.** Cut clips with a caption file, let Caption Studio compare that file against a second recognizer and show you where they disagree, then `clips_burn` draws the reviewed captions into the clip and keeps the clean copy.

**No captions on the video?** `clips_transcribe` fetches the audio track only and recognises the whole video or stream with the speech recognizer you chose in Caption Studio, in pieces of about ten minutes. Ask again to see progress; the transcript attaches itself when the last piece is done, and a run that was interrupted carries on from where it stopped. Or give your own SRT/VTT to `clips_use_transcript`.

**What chat reacted to.** For a finished live stream, `clips_chat` fetches the chat replay and shows where chat got busy and which paid messages (super chats, memberships) the streamer read out, lined up with the transcript. It measures; Hermes still reads the transcript there before suggesting a clip.

**A highlights video.** `clips_join` joins cut clips into one video, with optional title cards, a chapter list for the description and one caption file for the whole reel.

**Ready to post.** `clips_post_facts` gathers a clip's words, the source link at the right second and a few thumbnail frames; Hermes writes a title and description and `clips_post_save` stores them with the thumbnail beside the clip. A credit line with the source link is always added for someone else's video. Nothing is uploaded.

**Your own episodes and lessons.** `clips_from_studio` lists the podcast episodes, lesson videos and tutorials you made with Creator Studio and opens one for clipping. Clips of a sound-only episode get a plain picture with the title and a waveform.

## What it needs

- `yt-dlp` on your computer for YouTube links (not installed by the plugin; keep it up to date, YouTube changes often), and a JavaScript runtime that yt-dlp supports (Deno, or Node, which the plugin selects when Deno is missing).
- FFmpeg and ffprobe.
- Optional owner setting: `clip_ytdlp` (path to the program). The model cannot set it. Clip Studio never uses browser cookies or a YouTube sign-in; for a video that needs one, download it yourself and open it with `media_path`.

## What goes over the internet

Requests to YouTube made by yt-dlp on your computer: the video page, one caption track, the audio track if you ask for recognition, the sections you cut, and, if you ask what chat reacted to, the public chat replay of a finished stream. The chat replay holds other people's messages and display names: it stays in the plugin's private project folder, the raw download is deleted once it has been counted, and names are kept only for paid messages. Nothing is uploaded, posted or sent anywhere else by this part.

## Limits

- One video per project; no playlists or channels. Clips run from 2 seconds to 15 minutes.
- A stream that is still on air cannot be cut reliably and has no finished captions; open it again after it ends, or open your own recording.
- Suggestions come from the words. Clip Studio does not look at the picture itself, so it cannot find silent visual moments. It keeps a face in view only after Hermes has looked at a frame and saved where the face is; that needs an image-viewing tool in your Hermes. Following a moving avatar compares the look of the saved box; it is not face detection, it can mistake similar colours for the avatar, and an avatar that moves and changes pose a lot at once is shown whole instead of followed.
- Recognising a long stream runs inside Hermes: it pauses if Hermes is closed and carries on at the next request. On a computer without a free graphics card it can take as long as the stream itself.
- Chat measurements exist only for finished streams whose chat replay YouTube still offers. Messages that start with `!` (chat-game commands) are left out of the counts unless asked for.
- Title cards in a joined video use a Latin font; titles in other scripts may not display.
- Dead-air removal looks for stretches without voice, measured against the clip's own voice and background levels, so it works under music or game sound; where the voice is not clearly louder than the background it removes nothing and says so. Quiet laughs or reactions can be shortened with the pauses. Every removed pause and skipped stretch is a jump cut in the picture.
- YouTube's recognized captions contain mistakes, and cut points follow caption timing, which can be a fraction of a second off. Watch each clip before posting.
- Cutting a clip does not give you the right to publish it. Clip your own videos, or get the owner's permission or a licence that allows it. This plugin is not affiliated with YouTube or yt-dlp.

Files are kept under the Hermes profile in `plugin-data/creator-studio-clips/projects/<id>/clips/` (private, mode 0600).
