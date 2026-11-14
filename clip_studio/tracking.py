"""Keep the saved face box on the streamer through a clip, for vertical and square cuts.

This is NOT face detection and no model is used. The saved box (clips_face) is turned into a small grey picture patch, taken from the
frame the model looked at (or, failing that, from the first picture of the clip). Through the clip a few small grey pictures are read
(one every 1.5 s or so) and each is compared with the patch by normalised correlation, which ignores brightness and contrast, so an
avatar that only blinks, talks or sways still matches. Where the patch stops matching at the saved place it is searched for in the
whole picture at several sizes. The clip is then cut into stretches that each have their own box, or no box ("not found": the whole
picture is shown with bars so nothing important is cropped away). Pure Python and Pillow (already a dependency); no numpy, no OpenCV.

Boxes the model sets for time ranges (clips_face_ranges) override the search.
"""
import math
import subprocess
import shutil
from itertools import accumulate
from operator import mul
from pathlib import Path

from . import source, transcript as T

WIDTH = 320        # working picture width in pixels
STEP = 1.5         # seconds between checked pictures (longer clips use fewer, never more than MAX_SAMPLES)
MAX_SAMPLES = 160
MIN_RUN = 2.0      # a change shorter than this is ignored (no flicker)
FINE = 0.2         # resolution used to place a switch time exactly
INNER = 0.7        # only the middle of the box is compared: its edge often shows what is behind the avatar
CORE = 0.4         # a smaller middle part, used for sizes where the whole compared part would not fit in the picture (avatar full screen)
HOLD = 0.45        # at the known place a score of at least this still counts as the same picture
FOUND = 0.65       # a search over the whole picture must reach this to say "it moved there" (0.62 for the small core, which is only used at large sizes)
FOUND_CORE = 0.62
COLOUR_HOLD = 0.6  # colours alone: the box still holds about this much of the saved colours (an avatar that moves its head changes pose, not colours)
SCALES = (0.6, 0.7, 0.8, 0.9, 1.0, 1.12, 1.25, 1.4, 1.6, 1.8, 2.1, 2.5, 3.0, 3.6, 4.3)
SIZES = {'vertical': (1080, 1920), 'square': (1080, 1080)}
METHOD = 'followed the saved box by matching its picture through the clip (a heuristic, not face detection)'

TOOLS = {
    'clips_face_ranges': ('Set the face box for stretches of the video yourself, or switch the automatic following off. Vertical and square cuts normally follow the saved clips_face box through each clip (they check the clip every second or two and move the box when the avatar or camera moves; where it cannot be found the whole picture is shown with bars). '
                          'Use ranges when the cut report lists a stretch with no match, or the box moved to the wrong place: look at a frame from that time with clips_frame, then give the box (percent of the picture, as for clips_face) for start..end in video time, or none=true to show the whole picture there. '
                          'A range wins over the automatic search; new ranges replace any older range they overlap. follow=false uses the single saved box for the whole clip, as before. clear=true forgets all ranges. With only project_id it lists what is set. Changes no video.', {
        'project_id': {'type': 'string', 'description': 'Project ID returned by clips_open.'},
        'ranges': {'type': 'array', 'maxItems': 40, 'items': {'type': 'object', 'additionalProperties': False, 'required': ['start', 'end'], 'properties': {
            'start': {'type': ['number', 'string'], 'description': 'Video time in seconds or as a clock time such as 1:02:03.'}, 'end': {'type': ['number', 'string']},
            'left': {'type': 'number', 'minimum': 0, 'maximum': 100}, 'top': {'type': 'number', 'minimum': 0, 'maximum': 100}, 'width': {'type': 'number', 'minimum': 0, 'maximum': 100}, 'height': {'type': 'number', 'minimum': 0, 'maximum': 100},
            'none': {'type': 'boolean', 'description': 'No face box here: show the whole picture with bars.'}}}},
        'follow': {'type': 'boolean', 'description': 'false = do not follow the box through clips; true = follow (the default).'},
        'clear': {'type': 'boolean', 'description': 'Forget all ranges.'}}, ['project_id']),
}


def handle(clips, name, args, ctx, **context):
    from .project import _write
    if name != 'clips_face_ranges':
        raise ValueError('Unknown tool ' + name)
    unknown = set(args) - {'project_id', 'ranges', 'follow', 'clear'}
    if unknown:
        raise ValueError('Unknown argument: ' + ', '.join(sorted(unknown)))
    folder, data = clips._load(args.get('project_id'))
    if args.get('clear') is True:
        data.pop('face_ranges', None)
    if 'follow' in args:
        if type(args['follow']) is not bool:
            raise ValueError('follow is true or false')
        data['face_follow'] = args['follow']
    new = []
    for item in args.get('ranges') or []:
        if not isinstance(item, dict):
            raise ValueError('Each range is {start, end, left, top, width, height} or {start, end, none: true}')
        a, b = T.seconds(item.get('start'), 'start'), T.seconds(item.get('end'), 'end')
        if b <= a or (data.get('duration') and a >= data['duration']):
            raise ValueError('A range must end after it starts and start inside the video')
        if item.get('none') is True:
            if any(k in item for k in ('left', 'top', 'width', 'height')):
                raise ValueError('Give either a box or none=true, not both')
            box = None
        else:
            left, top, width, height = (item.get(k) for k in ('left', 'top', 'width', 'height'))
            if any(type(v) not in (int, float) for v in (left, top, width, height)) or not (0 <= left < 100 and 0 <= top < 100 and 5 <= width <= 100 and 5 <= height <= 100) or left + width > 100.5 or top + height > 100.5:
                raise ValueError('Give left, top, width and height as percentages (the box at least 5 percent wide and tall, inside the picture), or none=true')
            box = {'left': round(float(left), 1), 'top': round(float(top), 1), 'width': round(float(width), 1), 'height': round(float(height), 1)}
        new.append({'start': round(a, 2), 'end': round(b, 2), 'box': box})
    if new:
        kept = [r for r in data.get('face_ranges', []) if not any(r['start'] < n['end'] and n['start'] < r['end'] for n in new)]
        data['face_ranges'] = sorted(kept + new, key=lambda r: r['start'])[:60]
    if new or 'follow' in args or args.get('clear') is True:
        _write(folder / 'project.json', data)
    rows = [{**r, 'from': T.clock(int(r['start'] * 1000)), 'to': T.clock(int(r['end'] * 1000)), 'what': 'whole picture with bars' if r['box'] is None else 'this box'} for r in data.get('face_ranges', [])]
    return {'project_id': args['project_id'], 'face': data.get('face'), 'follow': data.get('face_follow', True), 'ranges': rows,
            'next': 'Vertical and square cuts use these ranges where they apply and follow the saved box everywhere else. Cut again with clips_cut and read face_follow in the result.'}


# ---------------------------------------------------------------- picture matching (pure Python on small grey pictures)

def _image():
    from PIL import Image
    return Image


class Frame:
    """One working picture (colour, and grey for matching); coarser copies and their running sums are made when first needed."""
    def __init__(self, rgb):
        self.rgb = rgb
        self.image = rgb.convert('L')
        self.w, self.h = rgb.size
        self._levels = {}

    def level(self, k):
        if k not in self._levels:
            image = self.image if k == 1 else self.image.resize((max(1, self.w // k), max(1, self.h // k)), _image().BOX)
            w, h = image.size
            data = image.tobytes()
            rows = [data[y * w:(y + 1) * w] for y in range(h)]
            total, squares = [[0] * (w + 1)], [[0] * (w + 1)]
            for row in rows:
                a = list(accumulate(row, initial=0))
                b = list(accumulate((v * v for v in row), initial=0))
                total.append([p + q for p, q in zip(total[-1], a)])
                squares.append([p + q for p, q in zip(squares[-1], b)])
            self._levels[k] = (w, h, rows, total, squares)
        return self._levels[k]


class Template:
    """The reference look: the middle part of the saved box as a picture, resized on demand to any scale."""
    def __init__(self, grey, frame_w, frame_h, box, inner=INNER):
        self.box = box
        self.inner = inner
        self.crop = grey.crop(_inner_rect(box, grey.size[0], grey.size[1], inner))
        self.iw = box['width'] / 100 * frame_w * inner   # size of the compared part, in working-picture pixels
        self.ih = box['height'] / 100 * frame_h * inner
        self._cache = {}

    def prepared(self, scale, k):
        key = (round(scale, 3), k)
        if key not in self._cache:
            pw, ph = max(2, round(self.iw * scale / k)), max(2, round(self.ih * scale / k))
            image = self.crop.resize((pw, ph), _image().LANCZOS)
            data = image.tobytes()
            n = pw * ph
            mean = round(sum(data) / n)
            values = [v - mean for v in data]
            tp = sum(values)
            energy = sum(v * v for v in values) - tp * tp / n
            self._cache[key] = None if energy < n * 16 else ([values[y * pw:(y + 1) * pw] for y in range(ph)], pw, ph, math.sqrt(energy), tp, n)  # None: almost flat, nothing to follow
        return self._cache[key]


def colour_hist(rgb):
    """Share of pixels in each of 64 coarse colours (4 levels per channel)."""
    data = rgb.tobytes()
    counts = [0] * 64
    for r, g, b in zip(data[0::3], data[1::3], data[2::3]):
        counts[(r >> 6) * 16 + (g >> 6) * 4 + (b >> 6)] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


class Look:
    """What the saved box looked like: picture templates for matching and a colour profile for when the pose changes."""
    def __init__(self, reference, size, box):
        grey = reference.convert('L')
        self.box = box
        self.main = Template(grey, size[0], size[1], box)
        self.tpls = (self.main, Template(grey, size[0], size[1], box, CORE))
        self.hist = colour_hist(reference.crop(_inner_rect(box, reference.size[0], reference.size[1])))

    def usable(self):
        return self.main.prepared(1.0, 1) is not None

    def colours(self, frame, box):
        region = frame.rgb.crop(_inner_rect(box, frame.w, frame.h))
        if region.size[0] < 2 or region.size[1] < 2:
            return 0.0
        return sum(min(a, b) for a, b in zip(self.hist, colour_hist(region)))

    def present(self, frame, box):
        """(is the streamer still in this box, how it was told): the picture matches, or only the colours do."""
        if check_at(frame, self.tpls, box) >= HOLD:
            return True, 'picture'
        return (self.colours(frame, box) >= COLOUR_HOLD), 'colours'


def _ncc(level, tpl, x, y):
    w, h, rows, total, squares = level
    prow, pw, ph, norm, tp, n = tpl
    if x < 0 or y < 0 or x + pw > w or y + ph > h:
        return -1.0
    s = total[y + ph][x + pw] - total[y][x + pw] - total[y + ph][x] + total[y][x]
    q = squares[y + ph][x + pw] - squares[y][x + pw] - squares[y + ph][x] + squares[y][x]
    var = q - s * s / n
    if var < n * 9:  # a flat window (grey levels vary by under 3): nothing to compare
        return 0.0
    dot = 0
    for j in range(ph):
        dot += sum(map(mul, prow[j], rows[y + j][x:x + pw]))
    return (dot - tp * s / n) / (norm * math.sqrt(var))


def check_at(frame, tpls, box):
    """Best score for the saved look near where this box is (a few percent of slack for swaying). The core is used when the middle part would not fit."""
    scale = box['width'] / tpls[0].box['width']
    tpl = next((t for t in tpls if t.iw * scale <= frame.w and t.ih * scale <= frame.h), None)
    prepared = tpl.prepared(scale, 1) if tpl else None
    if prepared is None:
        return 0.0
    level = frame.level(1)
    ox = round(frame.w * (box['left'] + box['width'] * (1 - tpl.inner) / 2) / 100)
    oy = round(frame.h * (box['top'] + box['height'] * (1 - tpl.inner) / 2) / 100)
    jx, jy = max(2, round(0.03 * frame.w)), max(2, round(0.03 * frame.h))
    best = -1.0
    for y in range(oy - jy, oy + jy + 1):
        for x in range(ox - jx, ox + jx + 1):
            score = _ncc(level, prepared, x, y)
            if score > best:
                best = score
    return best


def _refine(tpl, frame, scale, cx, cy, radius):
    prepared = tpl.prepared(scale, 1)
    if prepared is None:
        return -1.0, 0, 0
    level = frame.level(1)
    best = (-1.0, cx, cy)
    for y in range(cy - radius, cy + radius + 1, 2):
        for x in range(cx - radius, cx + radius + 1, 2):
            score = _ncc(level, prepared, x, y)
            if score > best[0]:
                best = (score, x, y)
    _, bx, by = best
    for y in range(by - 1, by + 2):
        for x in range(bx - 1, bx + 2):
            score = _ncc(level, prepared, x, y)
            if score > best[0]:
                best = (score, x, y)
    return best


def search(frame, tpls):
    """Look for the saved picture anywhere, at several sizes. tpls is (middle part, small core): the core is used for sizes where the middle part
    no longer fits in the picture. Returns (score, x, y, scale, template) of the best place."""
    best = (-1.0, 0, 0, 1.0, tpls[0])
    for scale in SCALES:
        tpl = next((t for t in tpls if t.iw * scale <= frame.w and t.ih * scale <= frame.h and t.iw * scale >= 5 and t.ih * scale >= 4), None)
        if tpl is None:
            continue
        pw = tpl.iw * scale
        k = max(1, round(pw / 9))  # the compared part is about 9 pixels wide in the coarse picture
        coarse = tpl.prepared(scale, k)
        if coarse is None:
            continue
        level = frame.level(k)
        w, h = level[0], level[1]
        found = []
        for y in range(0, h - coarse[2] + 1, 2):
            for x in range(0, w - coarse[1] + 1, 2):
                score = _ncc(level, coarse, x, y)
                if score > 0.3:
                    found.append((score, x, y))
        found.sort(reverse=True)
        chosen = []
        for score, x, y in found:
            if all(abs(x - a) > coarse[1] or abs(y - b) > coarse[2] for _, a, b in chosen):
                chosen.append((score, x, y))
            if len(chosen) == 3:
                break
        for _, x, y in chosen:
            score, rx, ry = _refine(tpl, frame, scale, x * k, y * k, k + 1)
            if score > best[0]:
                best = (score, rx, ry, scale, tpl)
    return best


def _box_from(frame, tpl, x, y, scale):
    """The saved box's rectangle (percent) for the compared part found at x, y with this size."""
    bw = tpl.iw * scale / tpl.inner
    bh = tpl.ih * scale / tpl.inner
    left = (x - bw * (1 - tpl.inner) / 2) / frame.w * 100
    top = (y - bh * (1 - tpl.inner) / 2) / frame.h * 100
    width, height = bw / frame.w * 100, bh / frame.h * 100
    left, top = min(max(left, 0.0), 100 - min(width, 100)), min(max(top, 0.0), 100 - min(height, 100))
    return {'left': round(left, 1), 'top': round(top, 1), 'width': round(min(width, 100), 1), 'height': round(min(height, 100), 1)}


def same_box(a, b):
    """Close enough to be the same place: centres within 3 percent of the picture (more for a big box, which sways further), sizes within a quarter."""
    if a is None or b is None:
        return a is b
    slack_x, slack_y = max(3.0, 0.15 * max(a['width'], b['width'])), max(3.0, 0.15 * max(a['height'], b['height']))
    return (abs(a['left'] + a['width'] / 2 - b['left'] - b['width'] / 2) <= slack_x and abs(a['top'] + a['height'] / 2 - b['top'] - b['height'] / 2) <= slack_y
            and 0.8 <= a['width'] / b['width'] <= 1.25 and 0.8 <= a['height'] / b['height'] <= 1.25)


def locate(frame, look, hints):
    """Where the streamer is in this picture: (box or None for not found, (score, how it was told)). A hint is tried first, so a still avatar stays on the saved box.
    Order: the picture matches at a known place, then it is found elsewhere (moved or resized), then the colours alone still fill a known place."""
    hints = [h for h in hints if h is not None]
    for hint in hints:
        score = check_at(frame, look.tpls, hint)
        if score >= HOLD:
            return hint, (score, 'picture')
    score, x, y, scale, tpl = search(frame, look.tpls)
    if score >= (FOUND if tpl is look.main else FOUND_CORE):
        box = _box_from(frame, tpl, x, y, scale)
        return next((h for h in hints if same_box(h, box)), box), (score, 'picture')
    for hint in hints:
        if look.colours(frame, hint) >= COLOUR_HOLD:
            return hint, (score, 'colours')
    return None, (score, 'none')


# ---------------------------------------------------------------- reading pictures from the clip

def _frames(path, start, length, rate, size):
    """Small pictures of path from start for length seconds, rate per second: a list of (seconds from start, Frame)."""
    program = shutil.which('ffmpeg')
    if not program:
        raise ValueError('Install ffmpeg and ffprobe')
    w, h = size
    args = [program, '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-ss', '%.3f' % start, '-i', str(path), '-t', '%.3f' % length, '-an', '-vf', 'fps=%.6f,scale=%d:%d,format=rgb24' % (rate, w, h), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    done = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=source.process_env(), timeout=source.LONG, check=False)
    image = _image()
    size_bytes = w * h * 3
    return [(n / rate, Frame(image.frombytes('RGB', (w, h), done.stdout[n * size_bytes:(n + 1) * size_bytes]))) for n in range(len(done.stdout) // size_bytes)]


def _inner_rect(box, w, h, inner=INNER):
    return (round(w * (box['left'] + box['width'] * (1 - inner) / 2) / 100), round(h * (box['top'] + box['height'] * (1 - inner) / 2) / 100),
            round(w * (box['left'] + box['width'] * (1 + inner) / 2) / 100), round(h * (box['top'] + box['height'] * (1 + inner) / 2) / 100))


def _reference(data):
    """The picture the model looked at when it set the box: (colour picture, label), or (None, None) when it is gone."""
    ref = data.get('face_ref') or {}
    path = ref.get('path')
    if path and Path(path).is_file():
        try:
            with _image().open(path) as image:
                return image.convert('RGB'), 'the picture you looked at (%s)' % T.clock(int(ref.get('at', 0) * 1000))
        except OSError:
            pass
    return None, None


def _look(reference, size, box):
    """The Look of the box in a reference picture; None when there is no picture or the middle of the box is one flat colour."""
    if reference is None:
        return None
    look = Look(reference, size, box)
    return look if look.usable() else None


# ---------------------------------------------------------------- following

def _states(frames, look, base):
    states, last = [], base
    for _t, frame in frames:
        box, score = locate(frame, look, [last, base])
        states.append((box, score))
        if box is not None:
            last = box
    return states


def _runs(times, states, duration):
    """Group sample states into stretches, drop any shorter than MIN_RUN (no flicker). Returns [[box_or_None, start, end]]."""
    runs = []
    for t, (box, _s) in zip(times, states):
        if runs and same_box(runs[-1][0], box):
            continue
        runs.append([box, t, None])
    for n, run in enumerate(runs):
        run[2] = runs[n + 1][1] if n + 1 < len(runs) else duration
    runs[0][1] = 0.0
    while len(runs) > 1:
        shortest = min(range(len(runs)), key=lambda n: runs[n][2] - runs[n][1])
        if runs[shortest][2] - runs[shortest][1] >= MIN_RUN:
            break
        into = shortest - 1 if shortest else 1
        runs[into][1], runs[into][2] = min(runs[into][1], runs[shortest][1]), max(runs[into][2], runs[shortest][2])
        del runs[shortest]
        merged = []
        for run in runs:
            if merged and same_box(merged[-1][0], run[0]):
                merged[-1][2] = run[2]
            else:
                merged.append(run)
        runs = merged
    return runs


def _place_switches(raw, runs, times, states, look, size, step):
    """Move each switch time from "somewhere in this sample gap" to the first picture where the change shows."""
    for n in range(1, len(runs)):
        before, after, edge = runs[n - 1][0], runs[n][0], runs[n][1]
        earlier = [t for t, (box, _s) in zip(times, states) if t < edge and same_box(box, before)]
        begin = max(earlier[-1] if earlier else edge - step, 0.0)
        if edge - begin < 0.3:
            continue
        for t, frame in _frames(raw, begin, edge - begin, 1 / FINE, size):
            if before is not None:
                changed = not look.present(frame, before)[0]
            else:
                changed = after is not None and look.present(frame, after)[0]
            if changed:
                runs[n - 1][2] = runs[n][1] = max(begin + t, runs[n - 1][1])
                break
    return runs


def _overrides(data, clip, duration):
    out = []
    for r in data.get('face_ranges', []):
        a, b = max(r['start'] - clip['start'], 0.0), min(r['end'] - clip['start'], duration)
        if b - a > 0.05:
            out.append((a, b, r['box']))
    return out


def _overlay(auto, overrides, duration):
    """Combine automatic stretches (box, start, end, how) with the model's ranges, which win. Returns [[box, start, end, how]]."""
    cuts = sorted({0.0, duration} | {x for a, b, _ in overrides for x in (a, b)} | {run[1] for run in auto})
    pieces = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.02:
            continue
        mid = (a + b) / 2
        over = next((o for o in overrides if o[0] <= mid < o[1]), None)
        if over is not None:
            piece = [over[2], a, b, 'set by you (clips_face_ranges)' if over[2] is not None else 'set by you: whole picture']
        else:
            run = next(r for r in auto if r[1] <= mid < r[2] or r is auto[-1])
            piece = [run[0], a, b, run[3]]
        if pieces and same_box(pieces[-1][0], piece[0]) and pieces[-1][3] == piece[3]:
            pieces[-1][2] = b
        else:
            pieces.append(piece)
    # a sliver of automatic result left between a range you set and its neighbour (under MIN_RUN) joins the range: no flicker at its edges
    n = 0
    while n < len(pieces):
        piece = pieces[n]
        near = [m for m in (n - 1, n + 1) if 0 <= m < len(pieces) and pieces[m][3].startswith('set by you')]
        if len(pieces) > 1 and near and not piece[3].startswith('set by you') and piece[2] - piece[1] < MIN_RUN:
            into = pieces[near[0]]
            into[1], into[2] = min(into[1], piece[1]), max(into[2], piece[2])
            del pieces[n]
            n = 0
            continue
        n += 1
    return pieces


def chain(box, iw, ih, shape, framing, tag):
    """The ffmpeg filters that lay one stretch out in the vertical or square frame. Same two layouts as clips_cut has always used."""
    w, h = SIZES[shape]
    if box is not None and box['width'] >= 30:  # the person fills much of the picture: one panel, cropped around them
        ch = ih
        cw = min(iw, ch * w / h)
        ch = min(ih, cw * h / w)
        cx = min(max(iw * (box['left'] + box['width'] / 2) / 100 - cw / 2, 0), iw - cw)
        cy = min(max(ih * (box['top'] + box['height'] / 2) / 100 - ch / 2, 0), ih - ch)
        return 'crop=%d:%d:%d:%d,scale=%d:%d,setsar=1' % (int(cw), int(ch), int(cx), int(cy), w, h), 'one panel cropped around the box'
    if box is not None:
        bw, bh = iw * box['width'] / 100, ih * box['height'] / 100
        tallest = max(h * 0.42, h - w * ih / iw) if framing != 'crop' else h * 0.42  # with the whole picture below, the panel may take all the space the picture leaves, so no black gap remains
        panel = int(min(max(w * bh / bw, h * 0.25), tallest)) // 2 * 2
        grow = max(bw / w, bh / panel)
        cw, ch = min(iw, w * grow), min(ih, panel * grow)
        if cw / ch > w / panel: cw = ch * w / panel
        else: ch = cw * panel / w
        cx = min(max(iw * (box['left'] + box['width'] / 2) / 100 - cw / 2, 0), iw - cw)
        cy = min(max(ih * (box['top'] + box['height'] / 2) / 100 - ch / 2, 0), ih - ch)
        rest = h - panel
        lower = ('crop=\'min(iw,ih*%d/%d)\':\'min(ih,iw*%d/%d)\',scale=%d:%d' % (w, rest, rest, w, w, rest) if framing == 'crop'
                 else 'scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2' % (w, rest, w, rest))
        return ('split=2[fa%s][fb%s];[fa%s]crop=%d:%d:%d:%d,scale=%d:%d,setsar=1[ff%s];[fb%s]%s,setsar=1[fm%s];[ff%s][fm%s]vstack=inputs=2'
                % (tag, tag, tag, int(cw), int(ch), int(cx), int(cy), w, panel, tag, tag, lower, tag, tag, tag), 'face panel on top, the rest of the picture below')
    if framing == 'crop':
        return 'crop=\'min(iw,ih*%d/%d)\':\'min(ih,iw*%d/%d)\',scale=%d:%d,setsar=1' % (w, h, h, w, w, h), 'centre crop (no face box here)'
    return 'scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1' % (w, h, w, h), 'whole picture with bars'


def _render(raw, pieces, whole, shape, framing, work, clip_id):
    graph, pads = [], ''
    for n, (box, a, b, how, fit) in enumerate(pieces):
        filters, _name = chain(None if fit else box, whole['width'], whole['height'], shape, 'fit' if fit else framing, str(n))
        last = n == len(pieces) - 1
        graph.append('[0:v]trim=start=%.3f%s,setpts=PTS-STARTPTS,%s[v%d]' % (a, '' if last else ':end=%.3f' % b, filters, n))
        pads += '[v%d]' % n
    graph.append('%sconcat=n=%d:v=1:a=0[vout]' % (pads, len(pieces)))
    out = work / (clip_id + '-follow.mp4')
    source.ffmpeg(['-protocol_whitelist', 'file,pipe', '-i', raw.name, '-filter_complex', ';'.join(graph), '-map', '[vout]', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                   '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-map_metadata', '-1', '-y', out.name], cwd=str(work))
    return out


def _describe(box, how, framing, shape, whole):
    if box is not None:
        return chain(box, whole['width'], whole['height'], shape, framing, '0')[1]
    return chain(None, whole['width'], whole['height'], shape, framing, '0')[1] if how.startswith('no face box') else 'whole picture with bars'


def follow(data, clip, raw, whole, shape, framing, work):
    """Work out and (when the layout changes inside the clip) render the per-stretch layouts for one clip.

    Returns None when nothing applies (no saved box and no ranges, source shape, no picture). Otherwise a dict with
    report (what to tell the user), rendered (a laid-out MP4 in work, or None when the one saved layout is right for the whole clip) and layout.
    """
    base = data.get('face')
    ranges = data.get('face_ranges') or []
    if shape == 'source' or not whole['video'] or data.get('audio_picture') or not (base or ranges):
        return None
    duration = whole['duration']
    overrides = _overrides(data, clip, duration)
    notes, checked, look = [], 0, None
    auto = [[base, 0.0, duration, 'saved box' if base else 'no face box']]
    covered = len(overrides) == 1 and overrides[0][0] <= 0.05 and overrides[0][1] >= duration - 0.05
    following = bool(base) and data.get('face_follow', True) and not covered
    if base and not data.get('face_follow', True):
        notes.append('Following is switched off for this project (clips_face_ranges follow=false): the saved box is used for the whole clip.')
    if following:
        try:
            _image()
        except ImportError:
            following = False
            notes.append('Pillow is not installed, so the box could not be followed; the saved box was used for the whole clip.')
    if following:
        step = max(STEP, duration / MAX_SAMPLES)
        size = (WIDTH, max(2, round(WIDTH * whole['height'] / whole['width']) // 2 * 2))
        frames = _frames(raw, 0.0, duration, 1 / step, size)
        checked = len(frames)
        if len(frames) < 2:
            following = False
            notes.append('The clip is too short to follow the box through; the saved box was used.')
    if following:
        grey, look = _reference(data)
        look_ = _look(grey, size, base)
        states = None
        if look_ is not None:
            states = _states(frames, look_, base)
            if not any(how == 'picture' for _box, (_score, how) in states):
                states = None
                notes.append('The picture you looked at when you set the box (%s) was not found anywhere in this clip (another scene or look), so the first picture of this clip was used as the look instead; this assumes the avatar is in the saved box at the start of the clip.' % look.split('(')[-1].rstrip(')'))
        elif grey is None:
            notes.append('No picture was kept from when the box was set, so the first picture of this clip was used as the look; this assumes the avatar is in the saved box at the start of the clip.')
        if states is None:
            look_ = _look(frames[0][1].rgb, size, base)
            look = 'the first picture of this clip'
            if look_ is None:
                following = False
                notes.append('The saved box shows an almost flat area (one colour), so there is nothing in it to follow; the saved box was used for the whole clip.')
            else:
                states = _states(frames, look_, base)
    if following:
        times = [t for t, _f in frames]
        runs = _runs(times, states, duration)
        if len(runs) > 1:
            runs = _place_switches(raw, runs, times, states, look_, size, step)
        auto = [[base if same_box(box, base) else box, a, b, 'saved box' if same_box(box, base) else ('found by searching the picture' if box is not None else 'no match')] for box, a, b in runs]
    pieces = _overlay(auto, overrides, duration)
    plain = len(pieces) == 1 and same_box(pieces[0][0], base) and pieces[0][3] in ('saved box', 'no face box')
    rows, lost, moved = [], [], False
    for box, a, b, how in pieces:
        rows.append({'from': T.clock(int((clip['start'] + a) * 1000)), 'to': T.clock(int((clip['start'] + b) * 1000)), 'clip_from': round(a, 1), 'clip_to': round(b, 1),
                     'box': box, 'layout': _describe(box, how, framing, shape, whole), 'how': how})
        if box is None and how == 'no match':
            lost.append(rows[-1])
        moved = moved or (box is not None and base is not None and not same_box(box, base))
    report = {'method': METHOD, 'segments': rows, 'box_moved': moved, 'pictures_checked': checked}
    if following:
        by_colour = sum(1 for _b, (_s, how) in states if how == 'colours')
        if by_colour:
            report['held_by_colours_only'] = '%d of %d pictures matched the saved box by colours only (the avatar changed pose, so the picture itself did not match)' % (by_colour, len(states))
    if look:
        report['look_taken_from'] = look
    if notes:
        report['notes'] = notes
    if lost:
        report['not_found'] = [{'from': r['from'], 'to': r['to'], 'clip_from': r['clip_from'], 'clip_to': r['clip_to'], 'shown_as': 'whole picture with bars'} for r in lost]
        report['next'] = ('In these stretches the saved picture was not found, so the whole picture is shown with bars instead of a face panel. If the avatar or camera is still on screen there, '
                          'look at a frame from that time with clips_frame (at=%s), then set its box for that stretch with clips_face_ranges and cut again. Otherwise leave it as it is.' % lost[0]['from'])
    elif moved:
        report['next'] = 'The box moved inside this clip and the layout followed it. Look at a frame from each stretch of the result to confirm the avatar is in view; if one is wrong, fix it with clips_face_ranges.'
    out = {'report': report, 'rendered': None, 'layout': None}
    if not plain:
        specs = [(box, a, b, how, box is None and not how.startswith('no face box')) for box, a, b, how in pieces]
        out['rendered'] = _render(raw, specs, whole, shape, framing, work, clip['clip_id'])
        out['layout'] = '%d stretches: %s' % (len(rows), '; '.join('%s-%s %s' % (r['from'], r['to'], r['layout']) for r in rows))
    return out
