"""Clip the finished work of the other parts of Creator Studio: podcast episodes, lesson videos and narrated tutorials.

Each part records its finished result in its own plugin-data folder. This module lists exactly those results and opens one as a Clip
Studio project, with the part's own captions as the transcript when it wrote any. Nothing outside those records can be opened this
way: the file names are rebuilt from the recorded ids and must sit in the part's own folder.
"""
import json
import re
import textwrap
import time
from pathlib import Path

from . import source, transcript as T

# the plugin-data folder of each part (STORAGE_NAMESPACE in podcast_studio, youtube_studio and tutorial_creator)
FOLDERS = {'podcast': 'creator-studio-podcast', 'lesson': 'creator-studio-youtube', 'tutorial': 'creator-studio-tutorial'}
HEX = re.compile(r'^[0-9a-f]{32}$')
AUDIO = {'.wav', '.mp3', '.m4a', '.flac', '.ogg'}
VIDEO = {'.mp4', '.mkv', '.webm', '.mov'}
LIMIT = 40

TOOLS = {
    'clips_from_studio': ('Clip the finished work of this suite itself: podcast episodes (podcast_studio), lesson videos (youtube_studio) and narrated tutorials (tutorial_creator). '
                          'Without item_id it lists the finished items (title, part, date, length, media file, caption file), newest first; part limits the list to one part. With an item_id from that list it opens the item as a Clip Studio project, '
                          'with the part\'s own captions as the transcript when it wrote them (podcast_episode_files writes them for an episode), and returns the project ID to use with clips_outline, clips_transcript, clips_propose and clips_cut. '
                          'A podcast episode is audio only: its clips are cut as MP4 videos with a plain dark picture showing the clip title and a waveform. Only results the parts recorded as finished can be opened; a recording or file of your own goes through clips_open.', {
        'item_id': {'type': 'string', 'maxLength': 120, 'description': 'An id from the list (for example podcast:<32 characters>).'},
        'part': {'type': 'string', 'enum': ['podcast', 'lesson', 'tutorial'], 'description': 'Only list this part.'}}, []),
}


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _inside(path, folder):
    """The regular file at path when it lies directly in folder; links are refused."""
    path, folder = Path(path), Path(folder)
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != folder.resolve() or path.stat().st_size == 0:
        return None
    return path.resolve()


def _item(item_id, part, title, media, captions, seconds, burned=False, note=''):
    stat = media.stat()
    return {'id': item_id, 'part': part, 'title': str(title or part)[:200], 'date': time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime)), 'modified': stat.st_mtime,
            'seconds': round(float(seconds), 1) if isinstance(seconds, (int, float)) else None, 'length': T.clock(int(seconds * 1000)) if isinstance(seconds, (int, float)) else None,
            'media_path': str(media), 'media': 'audio only' if media.suffix.lower() in AUDIO else 'video', 'captions_path': str(captions) if captions else None,
            **({'note': note} if note else {})}


def _projects(root, part):
    folder = Path(root) / FOLDERS[part] / 'projects'
    if not folder.is_dir():
        return
    for meta in folder.glob('*/project.json'):
        if HEX.fullmatch(meta.parent.name) and not meta.parent.is_symlink():
            data = _read(meta)
            if data and data.get('phase') == 'assembled' and isinstance(data.get('result'), dict):
                yield meta.parent, data, data['result']


def _podcasts(root):
    for folder, data, result in _projects(root, 'podcast'):
        audio = Path(str(result.get('audio_path') or ''))
        found = _inside(folder / audio.name, folder) if re.fullmatch(r'assembled-[0-9a-f]{32}\.wav', audio.name) else None
        if found:
            captions = _inside(folder / 'captions.srt', folder)
            yield _item('podcast:' + folder.name, 'podcast', data.get('topic'), found, captions, result.get('seconds'),
                        note='' if captions else 'No caption file yet: call podcast_episode_files for this episode first to get a transcript with the script text and times; without it you can attach your own with clips_use_transcript or recognise the speech with clips_transcribe.')


def _lessons(root):
    base = Path(root) / FOLDERS['lesson']
    for folder, data, result in _projects(root, 'lesson'):
        video = result.get('video')
        name = Path(str((video or {}).get('output_path') or '')).name if isinstance(video, dict) else ''
        found = _inside(base / name, base) if re.fullmatch(r'[0-9a-f]{32}\.mp4', name) else None
        if found:
            captions = _inside(folder / 'captions.srt', folder) if Path(str(result.get('captions_srt_path') or '')).name == 'captions.srt' else None
            yield _item('lesson:' + folder.name, 'lesson', data.get('topic'), found, captions, (video or {}).get('duration_seconds') or result.get('seconds'), burned=bool(result.get('captions_burned')),
                        note='The captions are already drawn into this video; cut with captions none or file, not burned, or they will be doubled.' if result.get('captions_burned') else '')


def _tutorials(root):
    base = Path(root) / FOLDERS['tutorial']
    if not base.is_dir():
        return
    for receipt in base.glob('*/narrated-*.json'):
        job, match = receipt.parent, re.fullmatch(r'narrated-([0-9a-f]{32})\.json', receipt.name)
        if not match or not HEX.fullmatch(job.name) or job.is_symlink():
            continue
        data = _read(receipt)
        found = _inside(job / ('narrated-%s.mp4' % match.group(1)), job)
        if data and data.get('state') == 'complete' and found:
            cues = data.get('cues') if isinstance(data.get('cues'), list) else []
            first = next((c.get('text') for c in cues if isinstance(c, dict) and c.get('text')), '')
            yield _item('tutorial:%s:%s' % (job.name, match.group(1)), 'tutorial', 'Tutorial: ' + re.sub(r'\s+', ' ', first)[:80] if first else 'Narrated tutorial',
                        found, _inside(job / ('narrated-%s.srt' % match.group(1)), job), data.get('seconds'))


def finished_items(root, part=None):
    """The finished items of the three parts, newest first. root is the plugin-data folder that holds each part's own folder."""
    out = []
    for name, make in (('podcast', _podcasts), ('lesson', _lessons), ('tutorial', _tutorials)):
        if part in (None, name):
            out.extend(make(root))
    return sorted(out, key=lambda i: -i['modified'])


def open_item(clips, item_id):
    """Open one finished item as a Clip Studio project; captions become its transcript."""
    from .project import _write
    if not isinstance(item_id, str) or not re.fullmatch(r'(podcast|lesson):[0-9a-f]{32}|tutorial:[0-9a-f]{32}:[0-9a-f]{32}', item_id):
        raise ValueError('Give an item id from clips_from_studio (for example podcast:<32 characters>)')
    item = next((i for i in finished_items(clips.root.parent, item_id.split(':')[0]) if i['id'] == item_id), None)
    if item is None:
        raise ValueError('That is not a finished item of this suite (it is missing, or its part did not record it as finished). clips_from_studio lists them.')
    opened = clips.open(media_path=item['media_path'])
    folder, data = clips._load(opened['project_id'])
    data.update({'title': item['title'], 'origin': {'part': item['part'], 'item_id': item_id}})
    audio = item['media'] == 'audio only'
    if audio:
        data['audio_picture'] = True
    else:
        data.pop('audio_picture', None)
    _write(folder / 'project.json', data)
    result = {**opened, 'title': item['title'], 'item': {k: v for k, v in item.items() if k != 'modified'}}
    if item['captions_path'] and not data.get('transcript'):
        attached = clips.use_transcript(opened['project_id'], item['captions_path'])
        result.update(transcript=attached['transcript'], next=attached['next'])
    elif data.get('transcript'):
        result['transcript'] = data['transcript']
    if audio:
        result['audio_only'] = ('This is audio only. Every clip is cut as an MP4 video: a plain dark picture with the clip title and a moving waveform, in the shape you choose (source, vertical or square). '
                                'There is no face or frame to look at, so clips_frame and clips_face do not apply.')
    if item['part'] == 'podcast' and item['captions_path']:
        result['transcript_note'] = 'These captions are the written script split into sentences with measured turn times, one speaker label per cue; they are not word-aligned, so cut points can be a fraction of a second off the speech.'
    if item.get('note'):
        result['item_note'] = item['note']
    return result


def handle(clips, name, args, ctx, **context):
    if name != 'clips_from_studio':
        raise ValueError('Unknown tool ' + name)
    unknown = set(args) - {'item_id', 'part'}
    if unknown:
        raise ValueError('Unknown argument: ' + ', '.join(sorted(unknown)))
    if args.get('item_id') is not None:
        return open_item(clips, args['item_id'])
    if args.get('part') not in (None, 'podcast', 'lesson', 'tutorial'):
        raise ValueError('part is podcast, lesson or tutorial')
    items = finished_items(clips.root.parent, args.get('part'))
    return {'items': [{k: v for k, v in i.items() if k != 'modified'} for i in items[:LIMIT]], 'count': len(items),
            'next': ('Ask the user which item to clip, then call clips_from_studio again with its item_id.' if items else
                     'Nothing finished was found. Make a podcast episode, lesson video or tutorial first, or open a recording with clips_open.')}


# ---------------------------------------------------------------- audio-only items: a generated picture so every shape works

def _picture(path, size, title, subtitle):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    image = Image.new('RGB', size, (18, 24, 34))
    draw = ImageDraw.Draw(image)
    big = max(18, min(w, h) // 14)
    font = ImageFont.load_default(size=big)
    lines = textwrap.wrap(title, max(8, int(w * 0.84 / (big * 0.55)))) [:6] or ['']
    y = int(h * 0.1)
    for line in lines:
        draw.text((w * 0.08, y), line, fill=(240, 244, 250), font=font)
        y += int(big * 1.3)
    small = ImageFont.load_default(size=max(12, big // 2))
    draw.text((w * 0.08, y + big // 3), subtitle[:90], fill=(150, 165, 185), font=small)
    image.save(path)


def audio_picture_video(clips, data, clip, shape, work, raw):
    """Cut one clip of an audio recording into an MP4 with a generated picture (clip title and waveform) in the shape's size."""
    from .project import SHAPES
    media = source.local_media(data['media_path'], clips.profile_home, [clips.root.parent])
    stat = media.stat()
    if [stat.st_size, stat.st_mtime_ns] != data['identity']:
        raise ValueError('The recording changed since it was opened; open it again')
    w, h = SHAPES.get(shape) or (1280, 720)
    picture = Path(work) / (clip['clip_id'] + '-picture.png')
    _picture(picture, (w, h), clip['title'], data.get('title') or '')
    start, end = clip['start'], clip['end']
    graph = '[1:a]asplit=2[a][w];[w]volume=3,showwaves=s=%dx%d:mode=cline:draw=full:colors=0x7fd1ff:rate=25,format=rgba,colorkey=black:0.3:0.1[wv];[0:v][wv]overlay=0:%d,format=yuv420p[v]' % (w, h // 4, h * 5 // 8)
    source.ffmpeg(['-protocol_whitelist', 'file,pipe', '-loop', '1', '-framerate', '25', '-i', str(picture), '-ss', '%.3f' % start, '-i', str(media), '-t', '%.3f' % (end - start),
                   '-filter_complex', graph, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-shortest',
                   '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart', '-y', str(raw)])
