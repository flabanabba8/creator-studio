"""Slideshow video from explicitly selected still images with optional slow zoom or pan. CPU-only; no video model needed."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from ..common import locking
from .render import media

MOTIONS = {
    'none': "zoompan=z=1:d={f}:s=1280x720:fps=25",
    'zoom_in': "zoompan=z='min(1+0.15*on/{f},1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f}:s=1280x720:fps=25",
    'zoom_out': "zoompan=z='max(1.15-0.15*on/{f},1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f}:s=1280x720:fps=25",
    'pan_left': "zoompan=z=1.15:x='(iw-iw/zoom)*(1-on/{f})':y='ih/2-(ih/zoom/2)':d={f}:s=1280x720:fps=25",
    'pan_right': "zoompan=z=1.15:x='(iw-iw/zoom)*on/{f}':y='ih/2-(ih/zoom/2)':d={f}:s=1280x720:fps=25",
}


def render_slides(root, slides, audio_path, chapters, captions, allow_profile_media=False, audio_start=0, burn_captions=False):
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Video rendering requires supported file locking')
    from . import check_timeline
    if type(allow_profile_media) is not bool or type(burn_captions) is not bool: raise ValueError('allow_profile_media and burn_captions must be boolean')
    if type(audio_start) not in (int, float) or not math.isfinite(audio_start) or not 0 <= audio_start <= 7200: raise ValueError('Invalid audio start')
    if not isinstance(slides, list) or not 1 <= len(slides) <= 12: raise ValueError('Choose one to twelve slides')
    images, seconds, motions = [], [], []
    for slide in slides:
        if not isinstance(slide, dict) or not {'path', 'seconds'} <= set(slide) or not set(slide) <= {'path', 'seconds', 'motion'}: raise ValueError('Each slide needs path and seconds (motion optional)')
        length, motion = slide['seconds'], slide.get('motion', 'none')
        if type(length) not in (int, float) or not math.isfinite(length) or not 1 <= length <= 120: raise ValueError('Each slide must last 1 to 120 seconds')
        if motion not in MOTIONS: raise ValueError('motion must be one of: ' + ', '.join(MOTIONS))
        images.append(media(slide['path'], {'.png', '.jpg', '.jpeg'}, root, allow_profile_media)); seconds.append(length); motions.append(motion)
    duration = sum(seconds)
    if not 1 <= duration <= 120: raise ValueError('Total slide duration must be 1 to 120 seconds; render longer videos as segments and stitch them')
    timeline = check_timeline(duration, chapters, captions)
    audio = media(audio_path, {'.wav', '.mp3', '.m4a'}, root, allow_profile_media, max_bytes=2 * 1024**3)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Install ffmpeg and ffprobe')
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    def identity(path):
        v = path.stat(); return (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns)
    before = [identity(x) for x in (*images, audio)]
    ident = uuid.uuid4().hex
    partial, output, vtt = root / (ident + '.partial.mp4'), root / (ident + '.mp4'), root / (ident + '.vtt')
    with locking.exclusive_lock(root / '.render.lock', 'Another video render is running'):
        try:
            with os.fdopen(os.open(vtt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream: stream.write(timeline['captions_webvtt'])
            command = [ffmpeg, '-v', 'error', '-nostdin', '-y']
            for image in images: command += ['-protocol_whitelist', 'file,pipe', '-i', str(image)]  # one frame each; zoompan emits the slide's frames
            command += ['-ss', str(audio_start), '-protocol_whitelist', 'file,pipe', '-i', str(audio)]
            audio_index = len(images)
            if captions and not burn_captions: command += ['-protocol_whitelist', 'file,pipe', '-i', str(vtt)]
            parts = []
            for i, (length, motion) in enumerate(zip(seconds, motions)):
                frames = max(1, round(length * 25))
                band = ',scale=1280:624:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:0:color=0x101820' if captions and burn_captions else ''  # burned captions get their own bottom band so they never cover a picture
                parts.append(f"[{i}:v]scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,{MOTIONS[motion].format(f=frames)}{band},setsar=1,format=yuv420p[s{i}]")
            parts.append(''.join(f'[s{i}]' for i in range(len(images))) + f'concat=n={len(images)}:v=1:a=0[v]')
            if captions and burn_captions:
                parts.append(f"[v]subtitles='{vtt.name}':force_style='Alignment=2,FontSize=11,MarginV=14,Outline=2,Bold=1'[vb]")
            video_label = '[vb]' if captions and burn_captions else '[v]'
            command += ['-filter_complex', ';'.join(parts), '-map', video_label, '-map', f'{audio_index}:a:0']
            if captions and not burn_captions: command += ['-map', f'{audio_index + 1}:0', '-c:s', 'mov_text']
            command += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-f', 'mp4', str(partial)]
            result = subprocess.run(command, cwd=root if burn_captions else None, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=600, check=False)
            if result.returncode or not partial.is_file() or not partial.stat().st_size: raise RuntimeError('Slideshow render failed')
            info = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration', '-of', 'json', str(partial)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=20, check=False)
            data = json.loads(info.stdout); actual = float(data['format']['duration']); types = {s.get('codec_type') for s in data['streams']}
            if not math.isfinite(actual) or abs(actual - duration) > 1 or not {'video', 'audio'} <= types: raise RuntimeError('Slideshow duration or streams do not match the request')
            if before != [identity(x) for x in (*images, audio)]: raise RuntimeError('An input changed while rendering; output discarded')
            os.replace(partial, output)
            return {'output_path': str(output), 'segment_id': ident, 'duration_seconds': actual, 'slides': len(images), 'chapters_description': timeline['chapters_description'], 'captions_included': bool(captions), 'captions_burned': bool(captions and burn_captions),
                    'notice': 'CPU-only slideshow with optional slow zoom or pan; metadata checked but picture quality, caption sync and audio were not reviewed. The returned segment can be stitched. Nothing was uploaded.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError('Slideshow render or metadata check failed') from exc
        finally:
            partial.unlink(missing_ok=True); vtt.unlink(missing_ok=True)
