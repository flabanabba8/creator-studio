# youtube-video-studio: setup and task guide

Source-reviewed 2026-11-09. Use [actual schemas](contracts.json) for argument details.

## Match the production route to the user

A CPU-only/offline setup can make sourced diagrams, charts, tables, slides and a video from existing media plus recorded or selected lightweight speech. Native image generation is optional for original illustrations/photos; it requires an actually available main-session image tool and the user's privacy/cost choice. A GPU or hosted service changes asset/speech options, not the editorial goal. No second reasoning model/API, default paid tool or fixed image runtime is required. FFmpeg/ffprobe handle actual rendering; Pillow handles deterministic slides/visuals. Presentation output is PNG stills plus notes/data sidecars; an editable PPTX requires a separately selected actual deck authoring tool.

## Worked topic-to-video lesson

For a beginner lesson on framing photos, create a project with the intended audience. Read a legitimate primary photography guide through available tools or selected Camoufox; preserve the actual source and page it. Verify completeness and write a short researched lesson with source IDs. Make an original illustrative photograph through a native image tool in the MAIN session and review composition; do not copy the guide's copyrighted photos. Create a flowchart for the decision process, a table comparing compositions and slides with simple titles/notes. Make a graph only when relevant real data or clearly labeled illustrative data exists; never invent a benchmark as measured evidence.

Use youtube_make_visual with sourced/measurement/illustrative provenance, actual numeric values and readable bounds. It renders bar/line/table/acyclic flowcharts and retains data; it does not verify claims or implement every chart/layout. For publication-grade scientific plots, select a real plotting tool and attach its output. youtube_make_slides can incorporate pictures. Native image generation returns its original host content, which must be saved as an actual file before material import. A refused/missing native tool is a blocked image capability, not a text-only substitute.

Attach reviewed PNG/JPEG per section and one real normalized PCM WAV per turn. Assemble into a measured narrated video; longer material is divided into bounded slide segments and joined. Original materials, data provenance, source snapshots and notes remain available. Existing clip rendering can replace sections with genuine screen/game footage; caption and chapter timing must use the finished timeline.

## Diagnose and accept

Camoufox can time out or meet a challenge; use another legitimate source explicitly and preserve the failure. Text-only image responses cannot satisfy artwork creation. Bad chart values/cycles/long labels stop generation rather than silently omitting content. An attached image review note is self-attested; inspect the actual image. Speech count/rate mismatches or changed assets stop assembly. Watch and listen to the final file, check readability, actual claims, synchronization, image rights and attribution before calling the video ready. Rendering metadata checks do not establish storytelling or perceptual quality.

Read the [verification record](../VERIFICATION.md) for dated tested scope. This guide does not install tools or claim new live execution.

## Graphic input provenance

For `youtube_make_visual`, put the data fields in `data` and describe their origin in `provenance`. For example:

```json
{"kind":"flowchart","title":"Plan a lesson","data":{"nodes":[{"id":"a","label":"Research"},{"id":"b","label":"Review"}],"edges":[{"from":"a","to":"b"}]},"provenance":{"kind":"illustrative","note":"Conceptual teaching sequence, not measured research data"}}
```

`provenance.kind` accepts `sourced`, `measurement`, or `illustrative`; `note` is required. Flowcharts use unique node IDs and directed `from`/`to` edges without cycles. An illustrative label does not turn invented values into research evidence.

## Plain language and visible research

Beginner audiences get everyday words on every slide and in every script line; define a specialist term the first time it appears or avoid it. Keep a short source list (title, address, what was used from each) in the final answer; error pages do not count as sources.

## Continuing earlier work and reviewing pictures

`youtube_assemble_project` refuses a section whose picture has an empty `review_note`. The note is self-attested, so view the picture first (host image tool such as vision_analyze) and describe what you saw. Attach pictures and recordings in section order.
