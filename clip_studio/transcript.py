"""Timed transcripts for clipping: parse caption tracks, find sentence boundaries, outline, search and snap cut points.

Pure text and arithmetic: no network, no process, no model. Times inside this module are integer milliseconds.
A unit is {'s': start_ms, 'e': end_ms, 't': text}; units are words when the track carries word times, else cues.
"""
import html
import json
import re
from collections import Counter

MAX_UNITS = 400_000
TAG = re.compile(r'<[^>]*>')
STAMP = r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})'
TIMING = re.compile(r'^\s*' + STAMP + r'\s+-->\s+' + STAMP)
INLINE = re.compile(r'<' + STAMP + r'>')
MARKER = re.compile(r'[\[(]\s*(laughter|laughs|laughing|applause|cheering|cheers|music|silence|crosstalk|inaudible)\s*[\])]', re.I)
STOP = set('''a about after again all also am an and any are as at be because been before being but by can could did do does doing down
for from get go going gonna got had has have he her here him his how i if in into is it its just kind know like me more my no not now of
off on one only or other our out over really right said say see she so some such than that the their them then there these they thing
things think this those to too two up us very want was way we well were what when where which who why will with would yeah you your
actually basically okay something sort lot much many even still let make made little bit mean look back come because uh um oh'''.split())


def _ms(h, m, s, ms):
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def _clean(text):
    return re.sub(r'\s+', ' ', html.unescape(TAG.sub('', text)).replace(chr(0x200b), '')).strip()


def parse_json3(text):
    """YouTube json3: speech-recognized tracks carry per-word offsets, creator tracks carry whole cues."""
    events = json.loads(text).get('events')
    if not isinstance(events, list):
        raise ValueError('The caption track is not in the expected format')
    events = [e for e in events if isinstance(e, dict) and isinstance(e.get('segs'), list) and isinstance(e.get('tStartMs'), int)]
    if any('tOffsetMs' in seg for e in events for seg in e['segs'] if isinstance(seg, dict)):
        starts = []
        for e in events:
            for seg in e['segs']:
                word = _clean(str(seg.get('utf8', ''))) if isinstance(seg, dict) else ''
                if word:
                    starts.append((e['tStartMs'] + int(seg.get('tOffsetMs', 0)), word))
        starts.sort(key=lambda x: x[0])
        units = [{'s': s, 'e': min(starts[i + 1][0], s + 1200) if i + 1 < len(starts) else s + 600, 't': w} for i, (s, w) in enumerate(starts)]
        return 'words', [u for u in units if u['e'] > u['s']] if units else []
    units = []
    for e in events:
        line = _clean(''.join(str(seg.get('utf8', '')) for seg in e['segs'] if isinstance(seg, dict)))
        if line and e.get('dDurationMs', 0) > 0:
            units.append({'s': e['tStartMs'], 'e': e['tStartMs'] + int(e['dDurationMs']), 't': line})
    return 'cues', units


def parse_cues(text):
    """SRT or WebVTT. A YouTube speech-recognized VTT (inline word times, rolling repeats) becomes word units."""
    blocks, current = [], None
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        m = TIMING.match(line)
        if m:
            current = [_ms(*m.groups()[:4]), _ms(*m.groups()[4:]), []]
            blocks.append(current)
        elif line == '':
            current = None
        elif not line.strip():
            continue  # YouTube pads rolling captions with a line holding one space
        elif current is not None:
            current[2].append(line)
    if any(INLINE.search(x) for b in blocks for x in b[2]):
        starts = []
        for start, _end, lines in blocks:
            for line in lines:
                if not INLINE.search(line):
                    continue  # the repeated previous line of a rolling caption
                at, pos = start, 0
                for m in INLINE.finditer(line):
                    word = _clean(line[pos:m.start()])
                    if word:
                        starts.append((at, word))
                    at, pos = _ms(*m.groups()), m.end()
                word = _clean(line[pos:])
                if word:
                    starts.append((at, word))
        starts.sort(key=lambda x: x[0])
        return 'words', [{'s': s, 'e': min(starts[i + 1][0], s + 1200) if i + 1 < len(starts) else s + 600, 't': w}
                         for i, (s, w) in enumerate(starts) if i + 1 == len(starts) or starts[i + 1][0] > s]
    units, last = [], None
    for start, end, lines in blocks:
        line = _clean(' '.join(lines))
        if line and end > start and line != last:
            units.append({'s': start, 'e': end, 't': line})
            last = line
    return 'cues', units


def parse(text, suffix=''):
    text = text.lstrip(chr(0xfeff))
    kind, units = parse_json3(text) if suffix == '.json3' or text.lstrip().startswith('{') else parse_cues(text)
    if not units:
        raise ValueError('No timed text was found in this transcript')
    if len(units) > MAX_UNITS:
        raise ValueError('This transcript is too long to handle')
    units.sort(key=lambda u: u['s'])
    return kind, units


def segments(kind, units):
    """Sentence-like spans: units are grouped up to end punctuation, a pause of 0.8 s, 60 units or 20 s."""
    out, first = [], 0
    for i, u in enumerate(units):
        nxt = units[i + 1] if i + 1 < len(units) else None
        if nxt is None or u['t'][-1:] in '.?!' or nxt['s'] - u['e'] >= 800 or i - first >= 59 or nxt['s'] - units[first]['s'] >= 20000:
            out.append({'s': units[first]['s'], 'e': u['e'], 't': ' '.join(x['t'] for x in units[first:i + 1]), 'a': first, 'b': i})
            first = i + 1
    return out


def clock(ms):
    s = ms // 1000
    h, rem = divmod(s, 3600)
    return '%d:%02d:%02d' % (h, rem // 60, rem % 60) if h else '%d:%02d' % (rem // 60, rem % 60)


def seconds(value, label='time'):
    """Accept seconds as a number, or text like 1:02:03.5 or 12:34."""
    if isinstance(value, bool):
        raise ValueError('%s must be seconds or a clock time' % label)
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str) and re.fullmatch(r'\s*(?:(\d+):)?(\d{1,3}):(\d{1,2}(?:\.\d+)?)\s*', value):
        h, m, s = re.fullmatch(r'\s*(?:(\d+):)?(\d{1,3}):(\d{1,2}(?:\.\d+)?)\s*', value).groups()
        out = (int(h or 0) * 60 + int(m)) * 60 + float(s)
    elif isinstance(value, str) and re.fullmatch(r'\s*\d+(?:\.\d+)?\s*', value):
        out = float(value)
    else:
        raise ValueError('%s must be seconds or a clock time such as 12:34' % label)
    if not 0 <= out <= 172800:
        raise ValueError('%s is out of range' % label)
    return out


def _row(seg):
    return {'start': round(seg['s'] / 1000, 2), 'end': round(seg['e'] / 1000, 2), 'at': clock(seg['s']), 'text': seg['t']}


def page(segs, start=None, end=None, max_chars=6000):
    """Sentences between two times, cut off at max_chars with the time to continue from."""
    lo = 0 if start is None else int(seconds(start, 'start') * 1000)
    hi = None if end is None else int(seconds(end, 'end') * 1000)
    rows, used, more = [], 0, None
    for seg in segs:
        if seg['e'] <= lo or (hi is not None and seg['s'] >= hi):
            continue
        if rows and used + len(seg['t']) > max_chars:
            more = round(seg['s'] / 1000, 2)
            break
        rows.append(_row(seg))
        used += len(seg['t'])
    return {'sentences': rows, 'continue_from': more}


def _norm(text):
    return re.sub(r'[^\w\s]', '', text.casefold()).split()


def search(segs, query, limit=20):
    words = _norm(query)
    if not words or len(query) > 200:
        raise ValueError('Give a word or short phrase to look for')
    needle = ' ' + ' '.join(words) + ' '
    hits, skip = [], -1
    for i, seg in enumerate(segs):
        if i <= skip:
            continue
        own = ' ' + ' '.join(_norm(seg['t'])) + ' '
        if needle in own:
            hits.append(_row(seg))
        elif i + 1 < len(segs) and needle not in ' ' + ' '.join(_norm(segs[i + 1]['t'])) + ' ' and needle in own + ' '.join(_norm(segs[i + 1]['t'])) + ' ':
            hits.append({**_row(seg), 'end': round(segs[i + 1]['e'] / 1000, 2), 'text': seg['t'] + ' ' + segs[i + 1]['t']})
            skip = i + 1
        if len(hits) >= limit:
            break
    return hits


def outline(segs, duration_ms, chapters=(), heatmap=(), offset=0, limit=60):
    """Time-bucket summary and plain signals for choosing clips. Signals are measurements, not judgements."""
    total = max(duration_ms, segs[-1]['e'] if segs else 0, 1)
    window = 30000
    while total / window > 120:
        window *= 2
    rows = []
    for k in range(0, (total + window - 1) // window):
        lo, hi = k * window, min((k + 1) * window, total)
        inside = [s for s in segs if lo <= s['s'] < hi]
        words = sum(len(s['t'].split()) for s in inside)
        text = ' '.join(s['t'] for s in inside)
        row = {'start': lo // 1000, 'end': hi // 1000, 'at': clock(lo), 'words': words, 'questions': sum(s['t'].rstrip().endswith('?') for s in inside),
               'text': text[:200] + ('...' if len(text) > 200 else '')}
        marks = sorted({m.group(1).lower() for m in MARKER.finditer(text)})
        if marks:
            row['sounds'] = marks
        heat = [h['value'] for h in heatmap if h['start_time'] * 1000 < hi and h['end_time'] * 1000 > lo]
        if heat:
            row['replay'] = round(sum(heat) / len(heat), 2)
        chapter = [c['title'] for c in chapters if c['start_time'] * 1000 <= lo < c.get('end_time', 1e12) * 1000]
        if chapter:
            row['chapter'] = chapter[-1]
        rows.append(row)
    pauses = sorted(({'after': round(a['e'] / 1000, 2), 'until': round(b['s'] / 1000, 2), 'seconds': round((b['s'] - a['e']) / 1000, 1)}
                     for a, b in zip(segs, segs[1:]) if b['s'] - a['e'] >= 3000), key=lambda p: -p['seconds'])[:8]
    peaks, bins = [], [h for h in heatmap if h['start_time'] * 1000 > total * 0.03]  # the opening seconds are always the most played
    for h in sorted(bins, key=lambda h: -h['value']):
        if len(peaks) < 6 and h['value'] >= 0.3 and all(abs(h['start_time'] - p['start']) >= 30 for p in peaks):
            peaks.append({'start': round(h['start_time'], 1), 'end': round(h['end_time'], 1), 'at': clock(int(h['start_time'] * 1000)), 'replay': round(h['value'], 2)})
    counts = Counter(w for s in segs for w in _norm(s['t']) if len(w) > 2 and w not in STOP and not w.isdigit())
    sounds = [{'at': clock(s['s']), 'start': round(s['s'] / 1000, 2), 'sound': m.group(1).lower()} for s in segs for m in MARKER.finditer(s['t'])][:30]
    return {'window_seconds': window // 1000, 'rows': rows[offset:offset + limit], 'total_rows': len(rows), 'offset': offset,
            'signals': {'most_replayed': sorted(peaks, key=lambda p: p['start']), 'longest_pauses': pauses, 'sounds': sounds,
                        'frequent_words': [w for w, _ in counts.most_common(15)]},
            'how_to_read': 'replay is YouTube\'s most-replayed curve (0 to 1) when the video has one; pauses are gaps in speech and make clean cut points; sounds are markers written in the captions. These are measurements. Read the transcript around a spot before proposing a clip.'}


def snap(kind, units, segs, start_ms, end_ms, duration_ms=None):
    """Move a rough start and end to speech boundaries so no word is cut, then add a short breath of padding."""
    def nearest(points, value, reach):
        best = min(points, key=lambda p: abs(p - value), default=None)
        return best if best is not None and abs(best - value) <= reach else None
    def edge(key, value, after=None):
        # a time given right on a word edge is deliberate (unpunctuated speech has few sentence edges): keep that word edge
        word = nearest([u[key] for u in units], value, 120) if kind == 'words' else None
        sentence = nearest([g[key] for g in segs if after is None or g[key] > after], value, 2500)
        if word is not None and (sentence is None or abs(sentence - value) > 600):
            return word
        if sentence is None and kind == 'words':
            return nearest([u[key] for u in units], value, 1000)
        return sentence
    s = edge('s', start_ms)
    e = edge('e', end_ms, s if s is not None else start_ms)
    s, e = (start_ms if s is None else s), (end_ms if e is None else e)
    before = max((u['e'] for u in units if u['e'] <= s), default=None)
    after = min((u['s'] for u in units if u['s'] >= e), default=None)
    s = max(0, s - (150 if before is None else min(150, max(0, (s - before) // 2))))
    e = e + (250 if after is None else min(250, max(0, (after - e) // 2)))
    if duration_ms:
        e = min(e, duration_ms)
    return s, e


def text_between(units, start_ms, end_ms):
    return ' '.join(u['t'] for u in units if u['s'] >= start_ms - 50 and u['e'] <= end_ms + 50)


def _srt(ms):
    h, ms = divmod(max(0, ms), 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d,%03d' % (h, m, s, ms)


def clip_srt(kind, units, start_ms, end_ms, line_chars=42):
    """Captions for one clip, with times counted from the clip's first frame."""
    # a word belongs to the clip when it starts inside it (word ends are estimates); a caption line when it overlaps
    inside = [u for u in units if u['s'] < end_ms and (u['s'] >= start_ms - 50 if kind == 'words' else u['e'] > start_ms)]
    cues = []
    if kind == 'words':
        group = []
        for i, u in enumerate(inside):
            group.append(u)
            nxt = inside[i + 1] if i + 1 < len(inside) else None
            length = len(' '.join(x['t'] for x in group))
            if nxt is None or length + 1 + len(nxt['t']) > line_chars or nxt['s'] - u['e'] >= 700 or nxt['s'] - group[0]['s'] >= 4000 or u['t'][-1:] in '.?!':
                cues.append((group[0]['s'], max(u['e'], min(group[0]['s'] + 700, nxt['s'] if nxt else u['e'] + 700)), ' '.join(x['t'] for x in group)))
                group = []
    else:
        import textwrap
        for u in inside:
            count = -(-len(u['t']) // (line_chars * 2))  # balanced pieces of at most two lines, so no single word is left over
            parts = textwrap.wrap(u['t'], width=max(line_chars, -(-len(u['t']) // count) + line_chars // 3), break_long_words=False) or [u['t']]
            span = (u['e'] - u['s']) / len(parts)
            for n, part in enumerate(parts):
                cues.append((int(u['s'] + n * span), int(u['s'] + (n + 1) * span), '\n'.join(textwrap.wrap(part, width=line_chars, break_long_words=False))))
    out = []
    for s, e, text in cues:
        s, e = max(s, start_ms) - start_ms, min(e, end_ms) - start_ms
        if e - s >= 100:
            out.append('%d\n%s --> %s\n%s\n' % (len(out) + 1, _srt(s), _srt(e), text.replace('-->', '->')))
    return '\n'.join(out)


def keep_ranges(total, removed):
    """What is left of 0..total (seconds) after taking out the removed (start, end) spans."""
    keep, at = [], 0.0
    for s, e in sorted((max(0.0, s), min(total, e)) for s, e in removed):
        if e - s <= 0.02 or e <= at:
            continue
        if s - at > 0.05:
            keep.append((at, s))
        at = max(at, e)
    if total - at > 0.05:
        keep.append((at, total))
    return keep


def compact_units(units, start_ms, keep, dropped=()):
    """Units of a clip moved onto the shortened timeline. Words inside a dropped span go; the rest shift left by what was removed before them."""
    def shift(ms):
        t, gone, last = ms / 1000, 0.0, 0.0
        for s, e in keep:
            if t < s:
                return int((s - gone - (s - last)) * 1000)
            gone += s - last
            if t <= e:
                return int((t - gone) * 1000)
            last = e
        return int((last - gone) * 1000) if keep else 0
    out = []
    for u in units:
        s, e = u['s'] - start_ms, u['e'] - start_ms
        if e <= 0 or any(a * 1000 <= s + 1 < b * 1000 for a, b in dropped):
            continue
        ns, ne = shift(max(0, s)), shift(e)
        if ne > ns:
            out.append({'s': ns, 'e': ne, 't': u['t']})
    return out
