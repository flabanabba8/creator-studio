"""Read an episode folder (NN-slug.txt segments + meta.json + editorial-review.json) without running anything.

Layout, matching a daily show: one text file per story/chapter, sorted by filename; headers
`# title:` and one or more `# paper:` or `# source:` lines; spoken lines `SPEAKER: text` with untagged
continuation lines; a closing file such as `98-wrapup.txt` that makes no source claims.
"""
import hashlib
import json
import os
import re
from pathlib import Path

MAX_FILES = 100
MAX_FILE_BYTES = 256 * 1024
CLOSING = re.compile(r'(?:^|-)(?:wrap-?up|outro|closing|credits)(?:$|-)', re.I)
LINE = re.compile(r'^([A-Z][A-Z0-9_ ]{0,39}):\s*(.*)$')
PRIVATE_PARTS = {'.ssh', '.gnupg', '.aws', '.kube', '.docker', '.codex', '.hermes', '.claude', '.netrc', '.git'}


def episode_files(directory):
    root = Path(directory)
    if not root.is_absolute(): raise ValueError('Use an absolute episode folder path')
    if any(part in PRIVATE_PARTS for part in root.resolve().parts): raise ValueError('Private configuration folders cannot be read as episodes')
    if root.is_symlink() or not root.is_dir(): raise ValueError('Episode folder must be a real directory')
    files = sorted(p for p in root.iterdir() if p.suffix == '.txt')
    if not 1 <= len(files) <= MAX_FILES: raise ValueError(f'Episode folder needs 1 to {MAX_FILES} .txt segment files')
    for p in files:
        if p.is_symlink() or not p.is_file(): raise ValueError('Segment files must be regular files, not links')
        if p.stat().st_size > MAX_FILE_BYTES: raise ValueError(f'{p.name} is larger than {MAX_FILE_BYTES // 1024} KiB')
    return root, files


def read_bytes(path):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        return stream.read(MAX_FILE_BYTES + 1)[:MAX_FILE_BYTES]


def parse_segment(name, text):
    """Return (title, sources, turns, header_lines); turns are [line_number, speaker, text]."""
    title, sources, turns = '', [], []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip(): continue
        if line.lstrip().startswith('#'):
            body = line.lstrip()[1:].strip()
            key, _, value = body.partition(':')
            key, value = key.strip().lower(), value.strip()
            if key == 'title' and value: title = value
            elif key in ('paper', 'source') and value: sources.append(value)
            continue
        match = LINE.match(line)
        if match: turns.append([number, match.group(1).strip(), match.group(2).strip()])
        elif turns: turns[-1][2] += ' ' + line.strip()
        else: raise ValueError(f'{name}:{number}: text before the first SPEAKER: line')
    return title, sources, turns


def load_episode(episode_dir, require_sources=True):
    if type(require_sources) is not bool: raise ValueError('require_sources must be boolean')
    root, files = episode_files(episode_dir)
    segments, hashes = [], {}
    for path in files:
        data = read_bytes(path)
        try: text = data.decode('utf-8')
        except UnicodeDecodeError: raise ValueError(f'{path.name} is not UTF-8') from None
        title, sources, turns = parse_segment(path.name, text)
        if not title: raise ValueError(f'{path.name}: add a "# title:" header (it becomes the chapter title)')
        if not turns: raise ValueError(f'{path.name}: no SPEAKER: lines')
        if not sources:
            if not require_sources: sources = ['(no sources declared for this format)']
            elif not CLOSING.search(path.stem): raise ValueError(f'{path.name}: add "# paper:" or "# source:" references (only a wrap-up/outro file may have none)')
            else: sources = ['(closing segment; makes no source claims)']
        hashes[path.name] = hashlib.sha256(data).hexdigest()
        segments.append({'title': title, 'sources': sources, 'turns': [{'speaker': s, 'text': t} for _, s, t in turns]})
    meta = None
    meta_path = root / 'meta.json'
    if meta_path.is_file() and not meta_path.is_symlink() and meta_path.stat().st_size <= MAX_FILE_BYTES:
        try: value = json.loads(read_bytes(meta_path))
        except ValueError: raise ValueError('meta.json is not valid JSON') from None
        if isinstance(value, dict): meta = {k: v for k, v in value.items() if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 2000}
    return {'files': [p.name for p in files], 'segment_sha256': hashes, 'segments': segments, 'meta': meta,
            'speakers': sorted({t['speaker'] for s in segments for t in s['turns']}),
            'notice': 'Loaded from local files only; sources and claims are unverified.'}


def check_review_file(episode_dir, hashes=None):
    """Validate editorial-review.json against the exact current segment files. Self-attested, never automatic."""
    root, files = episode_files(episode_dir)
    current = hashes or {p.name: hashlib.sha256(read_bytes(p)).hexdigest() for p in files}
    path = root / 'editorial-review.json'
    if not path.is_file() or path.is_symlink(): raise ValueError('Missing editorial-review.json; complete the full editorial pass first')
    try: review = json.loads(read_bytes(path))
    except ValueError: raise ValueError('editorial-review.json is not valid JSON') from None
    if not isinstance(review, dict) or review.get('status') != 'passed': raise ValueError('Editorial review has not passed')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip(): raise ValueError('Review must name who performed it')
    records = review.get('segments')
    if not isinstance(records, dict) or set(records) != set(current): raise ValueError('Review must cover exactly the current segment files')
    for name, digest in current.items():
        record = records[name]
        if not isinstance(record, dict) or record.get('sha256') != digest: raise ValueError(f'Stale or missing review for {name}; the dialogue changed after review')
        for field in ('purpose', 'opening_check', 'source_check', 'edits'):
            if not isinstance(record.get(field), str) or not record[field].strip(): raise ValueError(f'{name}: review needs a substantive {field} note')
    return {'status': 'review_matches_files', 'files': len(current), 'reviewer': review['reviewer'],
            'notice': 'Self-attested. Matching hashes do not verify sources or editorial quality.'}
