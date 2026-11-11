"""Cut a vertical 9:16 promo clip from a horizontal video with a header, a footer and optional burned captions.

CPU-only FFmpeg, one local input, private output. Nothing is uploaded.
"""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from ..common import locking
from .render import media

FONTS = ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
         '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf')


def single_line(value, name, limit=60):
    if not isinstance(value, str) or len(value) > limit or value.splitlines() not in ([], [value]) or any(ord(c) < 32 for c in value):
        raise ValueError(f'{name} must be single-line text of at most {limit} characters')
    return value.strip()


def render_short(root, video_path, start, duration, header='', footer='', captions=None, allow_profile_media=False):
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Video rendering requires supported file locking')
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    for name, value, low, high in (('start', start, 0, 86400), ('duration', duration, 1, 60)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high: raise ValueError(f'Invalid {name}')
    header, footer = single_line(header, 'header'), single_line(footer, 'footer')
    captions = captions or []
    if not isinstance(captions, list) or len(captions) > 500: raise ValueError('Provide at most 500 caption cues')
    from . import check_timeline
    timeline = check_timeline(duration, [], captions)  # cue times are relative to the short and must fit its duration
    source = media(video_path, {'.mp4', '.mkv', '.mov', '.webm'}, root, allow_profile_media, max_bytes=2 * 1024**3)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Install ffmpeg and ffprobe')
    font = next((f for f in FONTS if os.path.isfile(f)), None)
    if (header or footer) and not font: raise ValueError('No supported bold font was found for the header and footer text')
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True); root = root.resolve(strict=True)
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    def identity(path):
        v = path.stat(); return (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns)
    before = identity(source)
    ident = uuid.uuid4().hex
    partial, output = root / (ident + '.partial.mp4'), root / (ident + '.mp4')
    made = [partial]
    with locking.exclusive_lock(root / '.render.lock', 'Another video render is running'):
        try:
            info = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(source)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=env, timeout=20, check=False)
            data = json.loads(info.stdout) if info.returncode == 0 and len(info.stdout) < 65536 else {}
            length = float(data.get('format', {}).get('duration', 0))
            types = {x.get('codec_type') for x in data.get('streams', [])}
            if not {'video', 'audio'} <= types or not math.isfinite(length) or length < start + duration - 0.05: raise ValueError('The source needs video and audio covering the selected range')
            filters = ['color=c=0x0a0a0a:s=1080x1920:r=30[bg]', '[0:v]scale=1080:-2[v]', '[bg][v]overlay=(W-w)/2:(H-h)/2[base]']
            last = 'base'
            for label, text, y, size in (('head', header, 160, 54), ('foot', footer, 1740, 40)):
                if not text: continue
                path = root / f'{ident}.{label}.txt'; made.append(path)
                path.write_text(text, encoding='utf-8')
                filters.append(f"[{last}]drawtext=fontfile='{font}':textfile='{path.name}':fontcolor=white:fontsize={size}:x=(w-text_w)/2:y={y}:borderw=3:bordercolor=black[{label}]")
                last = label
            if captions:
                srt = root / f'{ident}.srt'; made.append(srt)
                srt.write_text(timeline['captions_srt'], encoding='utf-8')
                filters.append(f"[{last}]subtitles='{srt.name}':force_style='Alignment=2,FontSize=7,MarginV=105,Outline=2,Bold=1'[capt]")
                last = 'capt'
            command = [ffmpeg, '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-ss', str(start), '-t', str(duration), '-i', str(source), '-filter_complex', ';'.join(filters),
                       '-map', f'[{last}]', '-map', '0:a:0', '-t', str(duration), '-c:v', 'libx264', '-preset', 'veryfast', '-threads', '2', '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
                       '-movflags', '+faststart', '-f', 'mp4', str(partial)]
            result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=300, check=False)
            if result.returncode or not partial.is_file() or not partial.stat().st_size: raise RuntimeError('Short render failed')
            probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(partial)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env, timeout=20, check=False)
            result_info = json.loads(probe.stdout)
            actual = float(result_info['format']['duration'])
            video = [s for s in result_info['streams'] if s.get('codec_type') == 'video']
            if abs(actual - duration) > 1 or not video or (video[0].get('width'), video[0].get('height')) != (1080, 1920) or not any(s.get('codec_type') == 'audio' for s in result_info['streams']):
                raise RuntimeError('Short duration, size or streams do not match the request')
            if identity(source) != before: raise RuntimeError('The source changed while rendering; output discarded')
            os.replace(partial, output)
            return {'output_path': str(output), 'segment_id': ident, 'duration_seconds': actual, 'size': '1080x1920', 'captions_burned': bool(captions), 'header': bool(header), 'footer': bool(footer),
                    'notice': 'CPU-only vertical cut; metadata checked but picture, text legibility, caption sync and audio were not reviewed. Nothing was uploaded.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError('Short render or metadata check failed') from exc
        finally:
            for path in made: path.unlink(missing_ok=True)
