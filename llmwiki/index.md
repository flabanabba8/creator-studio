---
status: SOURCE-DERIVED
curated: 2026-11-11
---
# Creator Studio LLM wiki

Read this index first, then only the part you need. This wiki ships inside the plugin and
gives the active host model domain knowledge; it is not a separate LLM service.

Creator Studio bundles five parts that make media. Each keeps its own skill, tool names and
rules. Tool names start with `youtube_`, `podcast_`, `captions_`, `capture_`/`tutorial_`, or `clips_`.

| Part | Use it for | Skill | Wiki |
|---|---|---|---|
| YouTube Studio | Researched, narrated lesson videos with slides, charts and stills | `create-youtube-video` | [index](../youtube_studio/llmwiki/index.md), [task guide](../youtube_studio/llmwiki/task-guide.md) |
| Podcast Studio | Source-backed two-host podcast episodes with show notes | `create-podcast` | [index](../podcast_studio/llmwiki/index.md), [task guide](../podcast_studio/llmwiki/task-guide.md) |
| Caption Studio | Captions for a recording, and repair of existing subtitles | `repair-captions` | [index](../caption_studio/llmwiki/index.md), [task guide](../caption_studio/llmwiki/task-guide.md) |
| Tutorial Creator | Record a selected X11 window and export a narrated tutorial under 90 seconds | `create-tutorial` | [index](../tutorial_creator/llmwiki/index.md), [task guide](../tutorial_creator/llmwiki/task-guide.md) |
| Clip Studio | Find the best moments of a YouTube video or stream from its transcript and cut them into clips | `clip-youtube-video` | [index](../clip_studio/llmwiki/index.md), [task guide](../clip_studio/llmwiki/task-guide.md) |

- [Tool reference for all 85 tools](tools.md)
- [Speech models: online services, free allowances, local models by hardware](speech-models.md) - read before suggesting a voice; figures are dated and must be re-checked before quoting
- [Suite README](../README.md), [manifest](../plugin.yaml), [verification](../VERIFICATION.md)

## How the parts fit

- YouTube Studio and Podcast Studio use the same Gemini speech code (`common/gemini_speech.py`); the
  Tutorial Creator has its own speech code with extra backends. Caption Studio can caption the audio
  that any of them produces: `captions_for_latest` finds the newest finished item by itself, and
  `podcast_start_from_video` turns a finished lesson's saved research into a podcast project.
- Each part stores its files in its own folder under the Hermes `plugin-data` directory:
  `creator-studio-youtube`, `creator-studio-podcast`, `creator-studio-captions`, `creator-studio-tutorial`,
  `creator-studio-clips`.
- Clip Studio works on other people's or your own finished YouTube videos (the YouTube Studio part makes new
  videos; it does not read YouTube). When a video has no captions, Clip Studio hands its audio to Caption
  Studio's recognizer (`clips_transcribe`).
- The per-part wikis are the original ones; where they say "this plugin" they mean that part.
- [Speech recognition for captions: local models, online services, subscriptions](../caption_studio/llmwiki/recognizer-models.md) - dated, source-linked; read before suggesting a recognizer
