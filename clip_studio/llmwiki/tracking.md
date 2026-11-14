---
status: SOURCE-DERIVED
curated: 2026-11-13
---
# Following the saved face box through a clip (`clips_face_ranges`)

Vertical and square cuts keep a corner avatar or face camera in view even when a stream changes scene. Code: `clip_studio/tracking.py`,
hooked into `_cut_one` in `project.py`. Nothing is uploaded and no model is used.

This is a heuristic that follows the saved box (`clips_face`) by matching its picture. It is not face detection: it does not know what a
face is, only whether the picture (or its colours) seen in the saved box also appears somewhere in the clip.

## What happens when a clip is cut vertical or square with a saved box

1. The look to follow is the middle 70 percent of the box in the picture the model looked at when it set the box (`clips_frame` keeps it;
   `clips_face` records it). If that picture is gone, or it does not match anywhere in the clip, the first picture of the clip is used
   instead and the result says so (it then assumes the avatar is in the box at the start of the clip). A box on a flat colour cannot be
   followed; the saved box is used for the whole clip, as before.
2. The clip is read as small pictures (320 wide), one every 1.5 s (never more than 160 pictures: longer clips use a longer step).
3. In each picture, in this order: (a) normalised grey-level correlation at the box's place (a few percent of slack), which ignores brightness
   and contrast, so blinking, talking and swaying still match; (b) if not, the look is searched for in the whole picture at 16 sizes
   (0.6x to 4.3x), which finds the avatar in another corner, smaller, bigger or full screen (a small core of the look is used at large sizes);
   (c) if that fails, the colours alone (64 coarse colours) still filling a known place count as "still there" (a face-tracking avatar changes pose a
   lot, so the picture match is often low while the colours stay). Otherwise: not found.
4. Pictures are grouped into stretches. A change shorter than 2 s is ignored (no flicker). Each switch time is then placed on the first 0.2 s
   picture where the change shows (error about 0.2 s plus the 0.5 s ffmpeg frame step).
5. Each stretch gets its own layout, by that stretch's box width as always: under 30 percent wide a face panel on top with the rest of the picture
   below, 30 percent or wider one panel cropped around it. A "not found" stretch shows the whole picture with bars (nothing cropped away).
6. If every stretch uses the saved box nothing changes from before (one encode). Otherwise the layouts are laid out in a first pass, then the usual
   pass adds captions and trimming (two H.264 encodes in that case; the first uses crf 18).

A source (as filmed) cut is never touched. With no saved box and no ranges nothing changes.

## Reading the result (`face_follow` in each clip of the `clips_cut` result)

- `segments`: per stretch `from`/`to` (video time), `clip_from`/`clip_to` (seconds into the clip), the `box`, the `layout` and `how`
  (`saved box`, `found by searching the picture`, `no match`, `set by you ...`).
- `box_moved`: true when some stretch uses a box other than the saved one. `not_found`: the stretches with no match, with times.
- `look_taken_from`, `notes`, `pictures_checked`, and `held_by_colours_only` (how many pictures matched by colours only).
- When there are `not_found` stretches: say so plainly, then look at a frame from that time with `clips_frame` (at = the stretch's `from`).
  If the avatar or camera is still on screen, set its box for that stretch with `clips_face_ranges` and cut again. If it really is gone
  (a video, a cutscene, a black screen), the whole picture with bars is the right layout; leave it.
- Always look at a frame from each stretch of the result before telling the user it is right.

## `clips_face_ranges`

| Argument | Meaning |
|---|---|
| `ranges` | `[{start, end, left, top, width, height}]` or `{start, end, none: true}`; video time; percent as in `clips_face`. A range wins over the search. New ranges replace older ones they overlap. A sliver under 2 s of automatic result next to a range joins the range. |
| `follow` | `false` uses the single saved box for the whole clip, as before; `true` (default) follows. |
| `clear` | Forget all ranges. |
| (none) | Lists what is set. |

## Known limits (measured on a 5 h 39 min VTuber stream)

- A face-tracking avatar moves its head a lot. A head lean of 10 percent of the picture width in a full-screen close-up is reported as "moved" and
  the crop pans to follow it; that is correct but looks like a jump. Pictures of a different pose do not match as pictures; the colour rule
  carries them.
- When the avatar leaves the saved box but the box still shows similar colours (a pastel pink overlay behind a pink avatar), it is held as "still there".
- A move combined with a big pose change can be "not found"; the stretch is then shown whole. That is the safe failure.
- A clip of about two minutes takes 20 to 55 s to analyse on one CPU core of pure Python plus FFmpeg decoding.
