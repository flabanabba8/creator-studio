"""Explicit-anchor SRT retiming; never overwrite the input."""
import hashlib
import os
import stat
from collections import Counter
from fractions import Fraction
from statistics import median
from pathlib import Path
import re
import uuid

STAMP = r'(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})'
TIMING = re.compile(r'^' + STAMP + r'\s+-->\s+' + STAMP + r'(\s+.*)?$')
PRIVATE = {'.ssh', '.gnupg', '.aws', '.azure', '.codex', '.docker', '.kube', '.pki', '.config', '.hermes'}
MAX_BYTES = 8 * 1024 * 1024
MAX_TIMESTAMP_MS = 10_000 * 3_600_000 - 1


def stamp(parts):
    h, m, s, ms = map(int, parts)
    if h > 9999 or m >= 60 or s >= 60:
        raise ValueError('Invalid SRT timestamp')
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def format_stamp(value):
    if value < 0:
        raise ValueError('Retiming would create a negative timestamp')
    if value > MAX_TIMESTAMP_MS:
        raise ValueError('Retiming would exceed the supported timestamp range')
    h, rem = divmod(value, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def read_source(source_path, allowed_root=None, profile_home=None):
    p = Path(source_path).expanduser()
    if p.is_symlink() or any(x.casefold() in PRIVATE - {'.hermes'} for x in p.parts):
        raise ValueError('Private paths and symlink inputs are unsupported')
    resolved = p.resolve(strict=True)
    own_output = allowed_root is not None and resolved.is_relative_to(Path(allowed_root).resolve())
    protected = any(x.casefold() == '.hermes' for x in p.parts) or any(x.casefold() == '.hermes' for x in resolved.parts) or (profile_home is not None and resolved.is_relative_to(Path(profile_home).resolve()))
    if (any(x.casefold() in PRIVATE - {'.hermes'} for x in resolved.parts) or protected and not own_output or not resolved.is_file()):
        raise ValueError('Choose a subtitle outside private configuration or an output of this plugin')
    p = resolved
    fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode): raise ValueError('Choose a regular subtitle file')
        raw = f.read(MAX_BYTES + 1)
        after = os.fstat(f.fileno())
    if len(raw) > MAX_BYTES:
        raise ValueError('SRT exceeds 8 MiB')
    identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
    current = p.lstat()
    if identity(before) != identity(after) or identity(after) != identity(current) or not stat.S_ISREG(current.st_mode):
        raise ValueError('Subtitle changed while reading')
    text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n[ \t]*\n', text.strip())
    if not text.strip() or len(blocks) > 100000:
        raise ValueError('Empty SRT or too many cues')
    cues = []
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError('Invalid SRT cue index or missing text')
        match = TIMING.fullmatch(lines[1])
        if not match:
            raise ValueError('Invalid SRT cue timing')
        start, end = stamp(match.groups()[:4]), stamp(match.groups()[4:8])
        if end <= start:
            raise ValueError('SRT cue end must follow start')
        cues.append({'index': lines[0], 'start_ms': start, 'end_ms': end,
                     'settings': match.group(9) or '', 'text': '\n'.join(lines[2:])})
    return hashlib.sha256(raw).hexdigest(), cues


class Captions:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.profile_home = self.root.parent.parent if self.root.parent.name.casefold() == 'plugin-data' else None

    def inspect(self, source_path, offset=0, limit=20, allow_profile_captions=False):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid page bounds')
        if type(allow_profile_captions) is not bool: raise ValueError('allow_profile_captions must be boolean')
        allowed = self.root.parent if allow_profile_captions and self.root.parent.name.casefold() == 'plugin-data' and Path(source_path).suffix.lower() == '.srt' else self.root
        fingerprint, cues = read_source(source_path, allowed, self.profile_home)
        return {'fingerprint': fingerprint, 'total': len(cues), 'offset': offset, 'cues': cues[offset:offset + limit]}

    def retime(self, source_path, fingerprint, anchors, allow_profile_captions=False):
        if type(allow_profile_captions) is not bool: raise ValueError('allow_profile_captions must be boolean')
        allowed = self.root.parent if allow_profile_captions and self.root.parent.name.casefold() == 'plugin-data' and Path(source_path).suffix.lower() == '.srt' else self.root
        actual, cues = read_source(source_path, allowed, self.profile_home)
        if actual != fingerprint:
            raise ValueError('Source changed; inspect it again')
        if not isinstance(anchors, list) or len(anchors) not in (1, 2):
            raise ValueError('Provide one or two timestamp anchors')
        for anchor in anchors:
            if not isinstance(anchor, dict) or set(anchor) != {'source_ms', 'target_ms'} or any(type(anchor[k]) is not int or not 0 <= anchor[k] <= MAX_TIMESTAMP_MS for k in anchor):
                raise ValueError('Anchor times must be supported nonnegative integer milliseconds')
        a = anchors[0]
        if len(anchors) == 2:
            b = anchors[1]
            ds, dt = b['source_ms'] - a['source_ms'], b['target_ms'] - a['target_ms']
            if ds <= 0 or dt <= 0:
                raise ValueError('Both anchors must be strictly increasing')
        else:
            ds = dt = 1
        def convert(t):
            # Integer rounding avoids drift from floating-point calculations.
            numerator = (t - a['source_ms']) * dt
            transformed = a['target_ms'] + (numerator + ds // 2) // ds
            return format_stamp(transformed)
        blocks = []
        for cue in cues:
            start, end = convert(cue['start_ms']), convert(cue['end_ms'])
            if start == end:
                raise ValueError('Retiming would collapse a cue to zero duration')
            blocks.append(f"{cue['index']}\n{start} --> {end}{cue['settings']}\n{cue['text']}")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        out = self.root / f'{uuid.uuid4().hex}.srt'
        with os.fdopen(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n\n'.join(blocks) + '\n')
        return {'output_path': str(out), 'cues': len(cues), 'source_fingerprint': actual,
                'method': 'offset' if len(anchors) == 1 else 'linear drift', 'scale_numerator': dt, 'scale_denominator': ds}


    def suggest_alignment(self, source_path, reference_path, allow_profile_captions=False):
        if type(allow_profile_captions) is not bool: raise ValueError('allow_profile_captions must be boolean')
        def read(path):
            allowed = self.root.parent if allow_profile_captions and self.root.parent.name.casefold() == 'plugin-data' and Path(path).suffix.lower() == '.srt' else self.root
            return read_source(path, allowed, self.profile_home)
        source_sha, source = read(source_path)
        reference_sha, reference = read(reference_path)
        def canonical(text):
            without_markup = re.sub(r'<[^>]*>', '', text)
            words = re.findall(r'\w+', without_markup.casefold())
            return ' '.join(words) if len(words) >= 3 else ''
        source_keys = [canonical(cue['text']) for cue in source]
        reference_keys = [canonical(cue['text']) for cue in reference]
        source_counts, reference_counts = Counter(source_keys), Counter(reference_keys)
        reference_unique = {key: cue for key, cue in zip(reference_keys, reference) if key and reference_counts[key] == 1}
        matches = [{'source_ms': cue['start_ms'], 'target_ms': reference_unique[key]['start_ms'],
                    'source_index': cue['index'], 'reference_index': reference_unique[key]['index']}
                   for key, cue in zip(source_keys, source) if key and source_counts[key] == 1 and key in reference_unique]
        matches.sort(key=lambda x: x['source_ms'])
        if not matches: raise ValueError('No uniquely matching subtitle phrases of at least three words')
        total_matches = len(matches)
        if total_matches > 100:
            matches = [matches[round(i * (total_matches-1) / 99)] for i in range(100)]
        if len(matches) == 1:
            anchors = [{k: matches[0][k] for k in ('source_ms', 'target_ms')}]
            return {'source_fingerprint': source_sha, 'reference_fingerprint': reference_sha, 'method': 'single-match offset',
                    'suggested_anchors': anchors, 'matched_phrases': total_matches, 'matches_used': 1, 'samples': matches,
                    'notice': 'A single match cannot estimate drift. Verify against the video before applying.'}
        slopes = [Fraction(b['target_ms']-a['target_ms'], b['source_ms']-a['source_ms'])
                  for i,a in enumerate(matches) for b in matches[i+1:]
                  if b['source_ms']-a['source_ms'] >= 1000 and b['target_ms'] > a['target_ms']]
        if not slopes: raise ValueError('Matching phrases do not provide two ordered timestamps at least one second apart')
        slope = median(slopes)
        offset = median([Fraction(m['target_ms']) - slope*m['source_ms'] for m in matches])
        left, right = matches[0]['source_ms'], matches[-1]['source_ms']
        if left == right: raise ValueError('Matching timestamps do not span time')
        first, last = round(slope*left+offset), round(slope*right+offset)
        if first < 0 or last <= first or last > MAX_TIMESTAMP_MS: raise ValueError('Suggested timeline would be invalid')
        residuals = [abs(Fraction(m['target_ms']) - (slope*m['source_ms']+offset)) for m in matches]
        return {'source_fingerprint': source_sha, 'reference_fingerprint': reference_sha, 'method': 'median-pair linear estimate',
                'suggested_anchors': [{'source_ms':left,'target_ms':first}, {'source_ms':right,'target_ms':last}],
                'matched_phrases': total_matches, 'matches_used': len(matches), 'sampled': total_matches > len(matches),
                'median_residual_ms': round(float(median(residuals)), 1), 'max_residual_ms': round(float(max(residuals)), 1),
                'samples': matches[:20], 'samples_omitted': max(0,len(matches)-20),
                'notice': 'Exact text matches and a linear estimate can be wrong, especially across edits. Review residuals and verify against the video before applying.'}
