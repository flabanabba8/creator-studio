---
status: SOURCE-DERIVED (vendor pages, model cards and READMEs read on 2026-11-12; nothing here was run or benchmarked by us)
curated: 2026-11-12
---
# Speech recognition for captions: local models, online services, subscriptions

Read this before recommending a recognizer. It is what `captions_recognizer_setup` draws its suggestions from (`asr_catalog.json`, the same data).
**The plugin never picks a recognizer for the user.** It lists what it found, suggests, asks, and uses only the route the user chose.

Prices, free allowances and terms change often: every row has its source link and the date it was read (2026-11-12). Re-open the link before quoting a number.
UNVERIFIED means no primary page gave it. Subtitles need **word-level timestamps**, so that column matters most.

## 1. Online services (audio is uploaded)

| Service | Models | Free allowance | Paid | Timestamps | SRT/VTT | Speaker labels | Limits | Data use | Callable here | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| Google Gemini API (Gemini 3.5 Transcribe) | gemini-3.5-transcribe (file); gemini-3.5-transcribe-live (streaming) | Free tier: marked "Free of charge" for these models; the quota figures (requests per day) were not read: UNVERIFIED. Free tier needs an API key, no card stated. | $2.00 per 1M audio tokens (listed as $0.003 per minute); live $0.005 per minute | Word-level only (no segment-level); can reduce accuracy; not in live mode | Not covered by the page; build SRT/VTT from the word offsets | Up to 8 speakers (3+ experimental) | 85+ languages; about 1 hour per file (30 min with diarization or word timestamps); longer audio is silently truncated | Free tier: Google may use submitted content to improve its products and human reviewers may read it; do not submit sensitive audio. Paid: not used to improve products. | Not directly: Gemini has its own request format. Use the import path (transcribe elsewhere, import word-timestamp JSON) or add an adapter. | https://aistudio.google.com/docs/transcribe |
| OpenAI | gpt-transcribe (recommended); gpt-4o-transcribe, gpt-4o-mini-transcribe, whisper-1: deprecated, shut down 2027-02-26 | No free API tier found. ChatGPT Pro and eligible Business subscriptions include monthly API credits (see subscriptions). | gpt-transcribe $0.0045 per minute; gpt-4o-transcribe $0.006; gpt-4o-mini-transcribe $0.003; whisper-1 $0.006 | whisper-1: word and segment via verbose_json. gpt-transcribe: not listed: UNVERIFIED | SRT/VTT not mentioned on the page: UNVERIFIED | Only the deprecated diarize model | 25 MB per file | not read | Yes for whisper-1 style requests through the HTTP recognizer (needs word timestamps); whisper-1 shuts down 2027-02-26. | https://developers.openai.com/api/docs/guides/speech-to-text |
| Groq (hosted Whisper) | whisper-large-v3-turbo; whisper-large-v3 | Free plan limit (plan not labelled on the page): 20 requests per minute, 2,000 per day, 7,200 audio seconds per hour, 28,800 per day. 25 MB file limit on free. | Turbo $0.04 per hour; large-v3 $0.111 per hour; 10-second minimum per request | Segment or word (verbose_json) | Only json, verbose_json and text are listed | Not mentioned | 25 MB free, 100 MB developer tier | not read | Yes: the HTTP recognizer can call it with verbose_json and word timestamps and your key (kept in the plugin secret setting). | https://console.groq.com/docs/speech-to-text |
| Deepgram | Nova-3 (mono, multilingual); Flux STT (streaming only) | $200 credit that does not expire, no card needed. | Nova-3 pre-recorded $0.0043 per minute mono, $0.0052 multilingual; streaming $0.0077-$0.0092 | Word-level with confidence; sentence and paragraph times | SRT/VTT not mentioned: UNVERIFIED | Yes (included for pre-recorded) | 2 GB per file | not read | Not directly (own request format and auth); import path or adapter. | https://deepgram.com/pricing |
| AssemblyAI | Universal-3.5 Pro; Universal-2 | $50 credit, no card needed. | Universal-3.5 Pro $0.21 per hour; Universal-2 $0.15 per hour; diarization +$0.02 per hour | Word timestamps: not read: UNVERIFIED | Subtitle export: UNVERIFIED (the docs URL returned 404) | Yes (extra cost) | not read | not read | Not directly; import path or adapter. | https://www.assemblyai.com/pricing |
| ElevenLabs Scribe | Scribe v3; Scribe v2 | The free plan gives 10,000 credits per month; the page does not state speech-to-text hours: UNVERIFIED. | Batch $0.20 per hour; realtime $0.22 per hour | Word-level | SRT/VTT not mentioned: UNVERIFIED | Up to 32 speakers | 90+ languages; 5 GB / 15 hours per file | not stated: UNVERIFIED | Not directly; import path or adapter. | https://elevenlabs.io/docs/overview/capabilities/speech-to-text |
| Google Cloud Speech-to-Text | Chirp (V2 standard models) | 60 minutes per month free (V1 table, per account); billing must be enabled. | V2 dynamic batch $0.003 per minute (first tier); V1 with data logging $0.016 per minute above 60 minutes | not read | not read | not read | not read | not read | Not directly. | https://cloud.google.com/speech-to-text/pricing |
| Microsoft Azure Speech | Standard real-time and batch transcription | Free tier: 5 audio hours per month of standard real-time transcription; batch is not on the free tier. | Prices show "$-" on the page: UNVERIFIED | not read | not read | not read | not read | not read | Not directly. | https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/ |
| Amazon Transcribe | Standard batch and streaming | 60 minutes per month for 12 months from your first request. | US East examples: batch $0.006 per minute, streaming $0.01 per minute; billed per second | not read | not read | not read | not read | not read | Not directly. | https://aws.amazon.com/transcribe/pricing/ |
| Speechmatics | Melia 1; Enhanced; Standard | $100 credit, no card; free accounts get 2 concurrent real-time sessions. | Batch: Melia 1 $0.24 per hour, Enhanced $0.75, Standard $0.45; diarization free on pre-recorded | not read | not read | Yes | not read | not read | Not directly. | https://www.speechmatics.com/pricing |
| Rev AI | Reverb; Reverb Foreign Language | Credits worth 5 hours of Reverb ASR. | Reverb English $0.20 per hour; foreign language $0.30; 15-second minimum | not read | not read | not read | not read | not read | Not directly. | https://www.rev.ai/pricing |
| Gladia | Solaria-3; Solaria-1 | 50 EUR credit valid for one year; card requirement not stated. | Async from 0.16 EUR per hour (Solaria-3); real-time 0.68 EUR per hour | not read | not read | not read | not read | Self-serve: opt-in to data use by default, free opt-out at any time | Not directly. | https://www.gladia.io/pricing |
| Cloudflare Workers AI (Whisper) | @cf/openai/whisper; @cf/openai/whisper-large-v3-turbo | 10,000 Neurons per day on Workers Free and Paid. | $0.011 per 1,000 Neurons; both Whisper models $0.0005 per audio minute | not read | not read | not read | not read | not read | Not directly. | https://developers.cloudflare.com/workers-ai/platform/pricing/ |
| Mistral (Voxtral transcription) | Voxtral Mini Transcribe 2 (deprecated 2026-10-31, points to Voxtral Mini Transcribe 3) | The Free plan covers Vibe and Mistral Studio; whether it includes API usage: UNVERIFIED. | No price found on the pricing or docs pages: UNVERIFIED | Word-level (docs page) | not mentioned | Yes | 13 languages; up to 3 hours | not read | Not directly. | https://docs.mistral.ai/capabilities/audio_transcription |
| Hugging Face Inference Providers | openai/whisper-large-v3 (fal-ai, hf-inference); NVIDIA Nemotron ASR (deepinfra, together) | Free users get no credits; PRO gets $2.00 per month in credits for HF-routed requests. | Pass-through provider rates, no per-audio price read | return_timestamps flag gives chunks with start/end | not read | not read | not read | not read | Not directly. | https://huggingface.co/docs/inference-providers/tasks/automatic-speech-recognition |

"Callable here" says whether this plugin can call the service itself. Groq (and OpenAI's whisper-1 style endpoint) speak the OpenAI multipart
transcription format the HTTP recognizer uses. The others have their own request formats: transcribe there and use the import route (word-timestamp
JSON), or add an adapter.

## 2. Which paid plans include API access (read 2026-11-12)

| Plan | What the vendor says | Source |
|---|---|---|
| ChatGPT Pro / eligible Business | Pro tiers ($100, $200, $500) and eligible Business subscribers get monthly API credits equal to the tier; the grant funds one linked API organization; ChatGPT and API billing stay separate; Plus and free trials do not qualify; the subscription must be active for 7 days before claiming. | https://help.openai.com/en/articles/20001626-api-credits-benefit-for-eligible-chatgpt-subscriptions |
| Claude Max / Ultra / Team | Max ($100 per month), Ultra ($200), Team Standard ($20 per seat) and Team Premium ($100 per seat) get monthly Claude API credits after linking one Console organization (7 days on the plan). Free, Pro and Enterprise are not eligible. The credits cover the Claude API, not Bedrock or Vertex. Anthropic has no speech-to-text API on the pages read, so these credits do not pay for transcription. | https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans |
| Google AI Pro | UNVERIFIED: a search summary said it includes $10 per month of Google Cloud credits for the Gemini API; the Google page returned almost nothing and forum posts say the credits did not work in AI Studio (user-reported). Do not rely on it. | https://aistudio.google.com/learn/use-google-ai-plan-credits-in-ai-studio |
| Hugging Face PRO | $2.00 per month of compute credits, shared across HF compute services and usable for Inference Providers requests routed through HF. | https://huggingface.co/docs/inference-providers/pricing |

A chat subscription is almost always billed separately from API use. Say so plainly, and never claim a plan "includes transcription" unless the row says it does.

## 3. Local recognizers (audio stays on this computer; read 2026-11-12)

The plugin reads the hardware (OS, RAM, GPU memory and compute capability, Apple Silicon) locally and lists the models that fit. Memory figures say whether
they are **stated** by the project, **estimated** from parameter count, or **user-reported**.

| Model | Hardware (basis) | Licence (commercial) | Languages | Word timestamps | Speaker labels | How to run | OpenAI-style | Status | Notes | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| WhisperX (faster-whisper + forced alignment) | 8 GB VRAM (stated: under 8 GB for large-v2 with beam_size 5) | BSD-2-Clause (pyannote diarization models need accepting a Hugging Face agreement) (yes) | Whisper languages; alignment models are per language | yes: forced alignment with wav2vec2 (best documented word timestamps) | yes (pyannote, needs a Hugging Face token) | pip; CUDA 12.8 for GPU; CPU and macOS supported | no (none stated) | maintained (v3.8.6, 2026-05) | Best documented route to tight word timestamps for subtitles. | https://github.com/m-bain/whisperX |
| NVIDIA Parakeet-TDT 0.6B v2 | 4 GB VRAM (estimate; card states at least 2 GB RAM to load) | CC-BY-4.0 (yes (attribution)) | English | yes (word, segment, char) | no | NeMo (pip) | no | maintained (2026-06) | Average WER 6.05 on the Open ASR sets (vendor). | https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2 |
| NVIDIA Parakeet-TDT 0.6B v3 | 4 GB VRAM (estimate; the card states at least 2 GB RAM to load; NVIDIA GPUs on Linux listed) | CC-BY-4.0 (yes (attribution)) | 25 European languages | yes (word and segment) | no | NeMo (pip); Transformers | no | maintained (2026-08) | Average WER 6.34 on the Open ASR sets (vendor). Mac/Windows support not stated on the card. | https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 |
| Qwen3-ASR 0.6B / 1.7B (+ Qwen3-ForcedAligner-0.6B) | 6 GB VRAM (estimate; VRAM not stated) | Apache-2.0 (yes) | 52 languages and dialects | yes via the separate ForcedAligner (11 languages, up to 5 min); not in streaming mode | no | pip qwen-asr; vLLM; qwen-asr-serve | no (/v1/chat/completions) | maintained (2026-06) | - | https://github.com/QwenLM/Qwen3-ASR |
| faster-whisper (CTranslate2) | 5 GB VRAM (stated: large-v2 fp16 4525 MB, int8 2926 MB VRAM on an RTX 3070 Ti) | MIT (yes) | Whisper languages (99) | yes: word_timestamps=True | no | pip; Docker; CUDA 12 + cuDNN 9 | no (use Speaches in front of it) | maintained (v1.2.1, pushed 2026-11-11) | CPU stated: small, int8, i7-12700K 8 threads: 13 minutes of audio in 1 min 42 s using 1477 MB RAM. | https://github.com/SYSTRAN/faster-whisper |
| whisper.cpp (GGML) | CPU (CPU model: memory tiny about 273 MB, base 388 MB, small 852 MB, medium 2.1 GB, large 3.9 GB (stated)) | MIT (yes) | Whisper languages | experimental: -ml 1 or -sow give per-word segments | experimental (tinydiarize; stereo -di) | C++ binary; Docker (cuda, rocm, vulkan, intel, musa); Metal and Core ML on Apple Silicon | whisper-server on /inference (srt and vtt supported); no /v1/audio route found | maintained (v1.9.5, 2026-10) | Word timestamps are labelled experimental. | https://github.com/ggml-org/whisper.cpp |
| IBM Granite Speech 5.0 2B | 6 GB VRAM (estimate; Ollama Q8_0 build is 3.2 GB) | Apache-2.0 (yes) | EN FR DE ES PT JA | unverified (a card cites a paper; mlx-audio says supported) | speaker attribution (card cites a paper) | Transformers; vLLM; Ollama (ibm/granite5-speech); GGUF; ONNX | yes via Ollama (no srt/vtt, no timestamps) | maintained (2026-11) | Lower-bit quants lose accuracy past about 1 minute (card). | https://huggingface.co/ibm-granite/granite-speech-5.0-2b |
| Moonshine Voice (Useful Sensors) | CPU (CPU model (34M to 245M)) | Code MIT; current models MIT; legacy non-English models non-commercial (yes (current models)) | EN ES DE ZH JA KO VI TL UK AR | unverified (summarised page only) | opt-in speaker identification (summarised page: UNVERIFIED) | pip moonshine-voice; ONNX; Linux, macOS, Windows, iOS, Android, Raspberry Pi | no | maintained (v0.1.6, 2026-11) | English WER: Tiny 12.00, Small 7.84, Medium 6.65 (average of 8 datasets). | https://github.com/moonshine-ai/moonshine |
| NVIDIA Canary-1B v2 | 6 GB VRAM (estimate (979M parameters); not stated) | CC-BY-4.0 (yes (attribution)) | 25 European + translation | yes (word and segment) | no | NeMo | no | maintained (2026-08) | - | https://huggingface.co/nvidia/canary-1b-v2 |
| OpenAI Whisper (original) | 10 GB VRAM (stated VRAM table: tiny ~1, base ~1, small ~2, medium ~5, turbo ~6, large ~10 GB) | MIT (yes) | 99 | word_timestamps supported (seen only in third-party docs: UNVERIFIED on the primary page) | no | pip; needs ffmpeg | no | maintained (push 2026-08) | Turbo is not trained for translation. | https://github.com/openai/whisper |
| Voxtral Mini 4B Realtime (Mistral) | 16 GB VRAM (stated: single GPU with at least 16 GB) | Apache-2.0 (yes) | 13 languages | not stated | no | vLLM serve | vLLM transcription endpoint (details UNVERIFIED) | maintained (2026-03) | - | https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602 |
| distil-whisper large-v3.5 | 4 GB VRAM (estimate (756M parameters); VRAM not stated) | MIT (yes) | English-focused | segment-level via return_timestamps; word-level not stated | no | Transformers; faster-whisper-compatible (v3; v3.5 not verified) | no | maintained (2026-04) | Stated: about 1.46x faster than large-v3-turbo; short-form WER 7.08 vs 7.30. | https://huggingface.co/distil-whisper/distil-large-v3.5 |
| mlx-whisper (Apple Silicon) | CPU (Apple Silicon unified memory; not stated) | MIT (yes) | Whisper languages | yes: word_timestamps=True | no | pip (Apple Silicon only) | via mlx-audio server | maintained (2025-12) | - | https://github.com/ml-explore/mlx-examples/tree/main/whisper |
| Voxtral Mini 3B (Mistral) | 10 GB VRAM (stated: about 9.5 GB GPU RAM in bf16/fp16) | Apache-2.0 (yes) | 8 languages | not stated | no | vLLM | vLLM transcription endpoint (details UNVERIFIED) | maintained (2025-07) | - | https://huggingface.co/mistralai/Voxtral-Mini-3B-2507 |
| sherpa-onnx (hosts many ASR models) | CPU (CPU focus (ONNX)) | Apache-2.0 (yes) | model-dependent | model-dependent (not verified) | yes (speaker diarization listed) | ONNX; Android, iOS, Windows, macOS, Linux, WASM | no OpenAI-style server found | maintained (2026-11) | - | https://github.com/k2-fsa/sherpa-onnx |
| NVIDIA Nemotron 3.5 Transcribe 30B-A4B [not auto-suggested] | 80 GB VRAM (stated deployment: 1x H100 80 GB (FP8 and NVFP4 variants exist)) | OpenMDW-1.1 (yes) | 40 | optional word timestamps | yes (speaker-attributed) | NeMo + vLLM | vLLM | maintained (2026-10) | English mean WER 4.71 (vendor). Data-centre class. | https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B |
| SenseVoice-Small (FunASR) | CPU (CPU-friendly; "70 ms for 10 s of audio" is a vendor claim) | Model licence "other" (MODEL_LICENSE not read: commercial use UNVERIFIED); code MIT (check) | 50+ | not stated | FunASR toolkit has diarization | FunASR pip; ONNX; GGUF | no | maintained (2026-11) | - | https://huggingface.co/FunAudioLLM/SenseVoiceSmall |
| Vosk | CPU (CPU model; models about 50 MB) | Apache-2.0 (yes) | 20+ | not stated | speaker identification (README) | pip; many language bindings; Raspberry Pi and Android | no | maintained (push 2026-10; PyPI release is old) | Light and offline; accuracy not stated. | https://github.com/alphacep/vosk-api |
| Meta Omnilingual ASR | 2 GB VRAM (stated: CTC 300M about 2 GiB VRAM; LLM 7B about 17 GiB) | Apache-2.0 shown for code and the 7B-LLM weights; GitHub reports NOASSERTION: commercial use of every checkpoint UNVERIFIED (check) | 1600+ | no; audio under 40 s per request (unlimited variants lift this) | no | pip omnilingual-asr (fairseq2) | no | maintained (2025-12) | Reports character error rate, not WER. | https://github.com/facebookresearch/omnilingual-asr |
| stable-ts (timestamp stabiliser for Whisper) [not auto-suggested] | CPU (wrapper) | MIT (yes) | Whisper languages | yes (that is its purpose) | no | pip | no | ARCHIVED ("development indefinitely paused") | - | https://github.com/jianfch/stable-ts |
| Meta MMS-1B-all [not auto-suggested] | 4 GB VRAM (estimate) | CC-BY-NC-4.0 (no) | 158 | no | no | Transformers | no | old (2023) | Non-commercial. | https://huggingface.co/facebook/mms-1b-all |

### Local servers

| Server | Runs | Platforms | Install | OpenAI-style endpoint | Status | Source |
|---|---|---|---|---|---|---|
| Speaches | faster-whisper | Docker CPU or CUDA | docker run ghcr.io/speaches-ai/speaches:latest-cpu (or compose.cuda.yaml) | yes: /v1/audio/transcriptions (srt/vtt and word timestamps: not read: UNVERIFIED) | active; latest tagged release is a 2025 release candidate | https://github.com/speaches-ai/speaches |
| whisper.cpp whisper-server | whisper-cpp | Linux, macOS, Windows; Docker | build whisper.cpp; whisper-server | no: /inference with response_format json, text, srt, vtt (word timestamps via -sow / -ml flags) | active | https://github.com/ggml-org/whisper.cpp/blob/master/examples/server/README.md |
| Ollama | granite-speech-5-2b | Linux, macOS, Windows | ollama pull ibm/granite5-speech | yes: /v1/audio/transcriptions, but srt and vtt are explicitly unchecked and timestamp_granularities is unchecked: unusable for subtitles | active (v0.40.16) | https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx |
| LocalAI | whisper-cpp | Docker CPU/CUDA/ROCm/Intel/Vulkan; macOS DMG | docker run -p 8080:8080 localai/localai:latest | README claims OpenAI-API compatibility; the transcriptions endpoint, srt/vtt and word timestamps are UNVERIFIED | active (v4.12.1) | https://github.com/mudler/LocalAI |
| vLLM | qwen3-asr, voxtral-mini-4b-realtime, voxtral-mini-3b, granite-speech-5-2b | NVIDIA CUDA | vllm serve <model> | transcription endpoint documented in one line; details UNVERIFIED | active | https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html |
| mlx-audio (Apple Silicon) | mlx-whisper, parakeet-tdt-0.6b-v3 | macOS Apple Silicon | pip install mlx-audio; mlx_audio.server | yes: /v1/audio/transcriptions shown as a curl example; srt/vtt and word timestamps UNVERIFIED | active | https://github.com/Blaizzy/mlx-audio |

### Which one for which hardware (synthesis of the rows above, not a vendor claim)

- **CPU only:** whisper.cpp (small or base, quantized) or faster-whisper int8 (stated: small, int8, 8-thread i7: 13 minutes of audio in 1 min 42 s, 1.5 GB RAM).
- **4 to 6 GB VRAM:** faster-whisper int8 with large-v2/v3 or turbo (large-v2 int8 stated at 2.9 GB); WhisperX for tighter word timing.
- **8 to 12 GB:** faster-whisper or WhisperX with large-v3 or turbo; Parakeet v3 for European languages (NVIDIA only).
- **16 to 24 GB:** Qwen3-ASR with its forced aligner, Granite Speech 5.0 2B, Voxtral Realtime (16 GB).
- **Apple Silicon:** whisper.cpp (Metal, Core ML), mlx-whisper or mlx-audio.
- **Reliable word timestamps for subtitles, ranked by the evidence read:** WhisperX (forced alignment), faster-whisper, Parakeet/Canary, Qwen3-ASR + aligner,
  whisper.cpp (experimental). Ollama's transcription endpoint explicitly has no SRT/VTT or timestamps: not usable for subtitles.
- **Speaker labels:** WhisperX (pyannote, needs a Hugging Face token) or an online service with diarization; then use the import route.
- **Licences:** MMS-1B is non-commercial; SenseVoice and Omnilingual commercial terms are UNVERIFIED; Parakeet/Canary are CC-BY-4.0 (attribution).

## 4. Staleness and refreshing

The setup tool returns `knowledge_freshness`. Knowledge is **stale** when last checked more than 30 days ago (counting approved research) or when a known deadline has passed:

| Date | What changes | Source |
|---|---|---|
| 2026-10-31 | Mistral deprecates Voxtral Mini Transcribe 2 (voxtral-mini-2602) in favour of Voxtral Mini Transcribe 3 | https://docs.mistral.ai/capabilities/audio_transcription |
| 2027-02-26 | OpenAI shuts down gpt-4o-transcribe, gpt-4o-mini-transcribe, gpt-4o-transcribe-diarize and whisper-1 (gpt-transcribe is the replacement) | https://developers.openai.com/api/docs/pricing |

If something is stale or a deadline is near, tell the user and **ask whether they want you to research the current facts online. Never research without their yes.** If they agree:
read the source link of each affected row (primary pages only), save only what you verified with the setup tool's `knowledge_updates` (`{id, field, value, source, date}`, id from the tables above;
stored as dated overrides in the user's plugin data, the shipped catalog is unchanged; unknown ids/fields, non-https sources and future dates are refused), then tell the user what changed and what you could not verify.

Still UNVERIFIED on 2026-11-12: Gemini free-tier quotas; Vertex transcription price; Google AI Pro's Cloud credit; Azure prices; word timestamps and SRT/VTT for OpenAI gpt-transcribe, Deepgram,
AssemblyAI, ElevenLabs, Speechmatics, Rev, Gladia; free-tier training terms for every service except Gemini and Gladia; Apple SpeechAnalyzer; WER for several models (images only);
Moonshine word timestamps; SenseVoice and Omnilingual commercial terms; Parakeet/Canary on Windows and macOS; LocalAI, vLLM, mlx-audio and Speaches subtitle and timestamp support.

## 5. What this plugin can run today

- **import:** word-timestamp JSON from any recognizer the user already ran. Always available.
- **a speech server on this computer** that answers OpenAI-style `/v1/audio/transcriptions` with `verbose_json` and word timestamps (the HTTP recognizer sends the audio there).
- **a cached Whisper model** through the bundled adapter (a Python with transformers and torch).
- **Groq** with the user's key in the plugin setting `asr_api_key` (audio is uploaded).
- Anything else in the tables needs a wrapper, a server or an adapter first. Say so; never claim support that is not there.

## 6. Evidence boundary

Documentation review of 21 local models, 15 online services and 6 servers. Nothing was run or listened to here. A catalog entry is not an installation and not authorization to upload audio or spend money.
