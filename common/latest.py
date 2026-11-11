"""Find the newest finished video, podcast episode or tutorial in the suite's own project data.

Read-only: nothing is run, sent or recognized here. The Caption part decides what to do with the result.
"""
import json
import re
from pathlib import Path

ID = re.compile(r'^[0-9a-f]{32}$')
KINDS = ('video', 'podcast', 'tutorial')


def _srt_time(sec):
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d,%03d' % (h, m, s, ms)


def _regular(path):
    path = Path(path)
    return path.is_file() and not path.is_symlink() and path.stat().st_size > 0


def _timeline_srt(timeline):
    cues = []
    for section in timeline:
        for turn in section.get('turns', []):
            text = re.sub(r'\s+', ' ', str(turn.get('text', ''))).strip().replace('-->', '->')
            if text and turn['end'] > turn['start']:
                cues.append('%d\n%s --> %s\n%s\n' % (len(cues) + 1, _srt_time(turn['start']), _srt_time(turn['end']), text))
    return '\n'.join(cues)


def _projects(root, kind):
    base = Path(root) / 'projects'
    if not base.is_dir():
        return
    for folder in base.iterdir():
        meta = folder / 'project.json'
        if not ID.fullmatch(folder.name) or folder.is_symlink() or not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        result = data.get('result') or {}
        if data.get('phase') != 'assembled' or not result:
            continue
        media = (result.get('video') or {}).get('output_path') if kind == 'video' else result.get('audio_path')
        if not media or not _regular(media):
            continue
        yield meta.stat().st_mtime, kind, folder, data, result, str(media)


def _from_project(item):
    mtime, kind, folder, data, result, media = item
    script = None
    existing = folder / 'captions.srt'  # written by podcast_episode_files
    if kind == 'podcast' and _regular(existing):
        script = {'path': str(existing), 'made_by': 'podcast_episode_files'}
    elif result.get('timeline'):
        target = folder / 'script-captions.srt'
        body = _timeline_srt(result['timeline'])
        if body:
            target.write_text(body, encoding='utf-8')
            target.chmod(0o600)
            script = {'path': str(target), 'made_by': 'the project script and its measured take timing'}
    return {'kind': kind, 'project_id': data['project_id'], 'topic': data.get('topic'), 'media_path': media, 'finished': mtime, 'script_captions': script}


def _from_tutorials(root):
    root = Path(root)
    if not root.is_dir():
        return
    for job in root.iterdir():
        if not ID.fullmatch(job.name) or job.is_symlink() or not job.is_dir():
            continue
        for video in job.glob('narrated-*.mp4'):
            if _regular(video):
                srt = video.with_suffix('.srt')
                yield video.stat().st_mtime, {'kind': 'tutorial', 'job_id': job.name, 'topic': None, 'media_path': str(video), 'finished': video.stat().st_mtime,
                                              'script_captions': {'path': str(srt), 'made_by': 'tutorial_narrate (one cue per narrated line)'} if _regular(srt) else None}
        for video in job.glob('export-*.mp4'):
            if _regular(video) and not list(job.glob('narrated-*.mp4')):  # a silent or app-audio export: no script
                yield video.stat().st_mtime, {'kind': 'tutorial', 'job_id': job.name, 'topic': None, 'media_path': str(video), 'finished': video.stat().st_mtime, 'script_captions': None}


def find_latest(kind, youtube_root, podcast_root, tutorial_root):
    """Newest finished item of kind 'video', 'podcast', 'tutorial' or 'any'; None when the suite has made none."""
    if kind not in KINDS + ('any',):
        raise ValueError('kind must be video, podcast, tutorial or any')
    found = []
    if kind in ('video', 'any'):
        found += [(i[0], _from_project(i)) for i in _projects(youtube_root, 'video')]
    if kind in ('podcast', 'any'):
        found += [(i[0], _from_project(i)) for i in _projects(podcast_root, 'podcast')]
    if kind in ('tutorial', 'any'):
        found += list(_from_tutorials(tutorial_root))
    if not found:
        return None
    return max(found, key=lambda x: x[0])[1]
