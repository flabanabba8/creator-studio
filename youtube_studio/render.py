"""Bounded CPU-only still-image video export from explicitly selected local media."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import re
import uuid
from ..common import locking

PRIVATE = {'.ssh', '.gnupg', '.aws', '.azure', '.codex', '.docker', '.kube', '.pki', '.config', '.hermes'}


def media(value, extensions, root, allow_profile_media, max_bytes=512 * 1024**2):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Choose an absolute local media path')
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or any(x.casefold() in PRIVATE - {'.hermes'} for x in path.parts):
        raise ValueError('Choose a non-symlink file outside private configuration')
    original_parts = path.parts
    path = path.resolve(strict=True)
    data = Path(root).resolve().parent
    profile = data.parent if data.name.casefold() == 'plugin-data' else None
    allowed = allow_profile_media and profile is not None and path.is_relative_to(data)
    protected = any(x.casefold() == '.hermes' for x in (*original_parts, *path.parts)) or profile is not None and path.is_relative_to(profile)
    if any(x.casefold() in PRIVATE - {'.hermes'} for x in path.parts) or protected and not allowed or not path.is_file() or path.suffix.lower() not in extensions:
        raise ValueError('Unsupported or private media file')
    if path.stat().st_size > max_bytes:
        raise ValueError('Media exceeds the supported size limit')
    return path


def render_still(root, image_path, audio_path, duration, chapters, captions, allow_profile_media=False, audio_start=0):
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Video rendering requires supported file locking')
    from . import check_timeline
    timeline = check_timeline(duration, chapters, captions)
    if not 1 <= duration <= 120:
        raise ValueError('Use a duration from 1 to 120 seconds')
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    if type(audio_start) not in (int, float) or not math.isfinite(audio_start) or not 0 <= audio_start <= 7200: raise ValueError('Invalid audio start')
    image = media(image_path, {'.png', '.jpg', '.jpeg'}, root, allow_profile_media)
    audio = media(audio_path, {'.wav', '.mp3', '.m4a'}, root, allow_profile_media, max_bytes=2 * 1024**3)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('Install ffmpeg and ffprobe')
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    before = [(x.stat().st_dev, x.stat().st_ino, x.stat().st_size, x.stat().st_mtime_ns) for x in (image, audio)]
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    ident = uuid.uuid4().hex
    partial, output, vtt = root/(ident+'.partial.mp4'), root/(ident+'.mp4'), root/(ident+'.vtt')
    with locking.exclusive_lock(root/'.render.lock', 'Another video render is running'):
        try:
            with os.fdopen(os.open(vtt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                stream.write(timeline['captions_webvtt'])
            os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            command = [ffmpeg, '-v', 'error', '-nostdin', '-loop', '1', '-framerate', '10', '-protocol_whitelist', 'file,pipe', '-i', str(image), '-ss', str(audio_start), '-protocol_whitelist', 'file,pipe', '-i', str(audio)]
            if captions: command += ['-protocol_whitelist', 'file,pipe', '-i', str(vtt)]
            command += ['-map', '0:v:0', '-map', '1:a:0']
            if captions: command += ['-map', '2:0', '-c:s', 'mov_text']
            command += ['-t', str(duration), '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2', '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-map_metadata', '-1', '-map_chapters', '-1', '-fs', str(256 * 1024**2), '-y', str(partial)]
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=120, check=False)
            if result.returncode or not partial.is_file() or not partial.stat().st_size:
                raise RuntimeError('Video render failed')
            info = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration', '-of', 'json', str(partial)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=10, check=False)
            if info.returncode or len(info.stdout) > 65536: raise RuntimeError('Video metadata check failed')
            data = json.loads(info.stdout)
            actual = float(data.get('format', {}).get('duration', 0))
            types = {x.get('codec_type') for x in data.get('streams', [])}
            audio_lengths = [float(x.get('duration', 0)) for x in data.get('streams', []) if x.get('codec_type') == 'audio']
            if not math.isfinite(actual) or actual < duration - 0.5 or actual > duration + 1 or not {'video', 'audio'} <= types or not audio_lengths or not math.isfinite(audio_lengths[0]) or audio_lengths[0] < duration - 0.5 or captions and 'subtitle' not in types:
                raise RuntimeError('Video duration or streams do not match the requested export')
            after = [(x.stat().st_dev, x.stat().st_ino, x.stat().st_size, x.stat().st_mtime_ns) for x in (image, audio)]
            if before != after: raise RuntimeError('An input changed during rendering; output discarded')
            os.replace(partial, output)
            return {'output_path': str(output), 'segment_id': ident, 'duration_seconds': actual, 'audio_start_seconds': audio_start, 'chapters_description': timeline['chapters_description'], 'captions_included': bool(captions),
                    'notice': 'CPU-only still-image video; metadata checked but visual quality, caption sync and audio have not been reviewed. Nothing was uploaded.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError('Video render or metadata check failed') from exc
        finally:
            partial.unlink(missing_ok=True)
            vtt.unlink(missing_ok=True)


def render_clips(root, clips, audio_path, chapters, captions, allow_profile_media=False, audio_start=0):
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Video rendering requires supported file locking')
    from . import check_timeline
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    if type(audio_start) not in (int, float) or not math.isfinite(audio_start) or not 0 <= audio_start <= 7200: raise ValueError('Invalid audio start')
    if not isinstance(clips, list) or not 1 <= len(clips) <= 6:
        raise ValueError('Choose one to six video clips')
    selected, durations, starts = [], [], []
    for clip in clips:
        if not isinstance(clip, dict) or not {'path', 'seconds'} <= set(clip) or not set(clip) <= {'path', 'seconds', 'start'}:
            raise ValueError('Each clip needs path and seconds')
        seconds, start = clip['seconds'], clip.get('start', 0)
        if type(start) not in (int, float) or not math.isfinite(start) or not 0 <= start <= 7200: raise ValueError('Invalid clip start')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 120:
            raise ValueError('Each clip duration must be between 1 and 120 seconds')
        selected.append(media(clip['path'], {'.mp4', '.mkv', '.mov', '.webm'}, root, allow_profile_media))
        durations.append(seconds); starts.append(start)
    duration = sum(durations)
    if not 1 <= duration <= 120: raise ValueError('Total clip duration must be from 1 to 120 seconds')
    timeline = check_timeline(duration, chapters, captions)
    audio = media(audio_path, {'.wav', '.mp3', '.m4a'}, root, allow_profile_media, max_bytes=2 * 1024**3)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Install ffmpeg and ffprobe')
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    inputs = selected + [audio]
    def identity(path):
        value = path.stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    before = [identity(path) for path in inputs]
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    ident = uuid.uuid4().hex
    partial, output, vtt = root/(ident+'.partial.mp4'), root/(ident+'.mp4'), root/(ident+'.vtt')
    with locking.exclusive_lock(root/'.render.lock', 'Another video render is running'):
        try:
            for path, start, requested in zip(selected, starts, durations):
                probe = subprocess.run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=10, check=False)
                if probe.returncode or len(probe.stdout) > 65536: raise RuntimeError('Clip metadata check failed')
                info = json.loads(probe.stdout)
                length = float(info.get('format', {}).get('duration', 0))
                if not math.isfinite(length) or length < start + requested or not any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
                    raise ValueError('A clip is shorter than requested or has no video stream')
            with os.fdopen(os.open(vtt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                stream.write(timeline['captions_webvtt'])
            os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            command = [ffmpeg, '-v', 'error', '-nostdin', '-filter_complex_threads', '1']
            for path in selected: command += ['-protocol_whitelist', 'file,pipe', '-i', str(path)]
            command += ['-ss', str(audio_start), '-protocol_whitelist', 'file,pipe', '-i', str(audio)]
            if captions: command += ['-protocol_whitelist', 'file,pipe', '-i', str(vtt)]
            filters = [f'[{i}:v:0]trim=start={starts[i]:.6f}:duration={seconds:.6f},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=10[v{i}]' for i, seconds in enumerate(durations)]
            filters.append(''.join(f'[v{i}]' for i in range(len(selected))) + f'concat=n={len(selected)}:v=1:a=0[outv]')
            command += ['-filter_complex', ';'.join(filters), '-map', '[outv]', '-map', f'{len(selected)}:a:0']
            if captions: command += ['-map', f'{len(selected)+1}:0', '-c:s', 'mov_text']
            command += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-map_metadata', '-1', '-map_chapters', '-1', '-fs', str(256 * 1024**2), '-y', str(partial)]
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=120, check=False)
            if result.returncode or not partial.stat().st_size: raise RuntimeError('Video render failed')
            probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration', '-of', 'json', str(partial)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=10, check=False)
            if probe.returncode or len(probe.stdout) > 65536: raise RuntimeError('Video metadata check failed')
            data = json.loads(probe.stdout); actual = float(data.get('format', {}).get('duration', 0))
            streams = data.get('streams', []); types = {x.get('codec_type') for x in streams}
            lengths = [float(x.get('duration', 0)) for x in streams if x.get('codec_type') in ('video', 'audio')]
            if not math.isfinite(actual) or actual < duration - 0.5 or actual > duration + 1 or not {'video', 'audio'} <= types or len(lengths) < 2 or any(not math.isfinite(x) or x < duration - 0.5 for x in lengths) or captions and 'subtitle' not in types:
                raise RuntimeError('Video duration or streams do not match the requested export')
            if before != [identity(path) for path in inputs]: raise RuntimeError('An input changed during rendering; output discarded')
            os.replace(partial, output)
            return {'output_path': str(output), 'segment_id': ident, 'duration_seconds': actual, 'audio_start_seconds': audio_start, 'clips': len(selected), 'chapters_description': timeline['chapters_description'], 'captions_included': bool(captions), 'notice': 'CPU-only clip sequence; source clip audio is omitted. Metadata was checked, but visuals, caption sync and narration require review. Nothing was uploaded.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise RuntimeError('Video render or metadata check failed') from exc
        finally:
            partial.unlink(missing_ok=True); vtt.unlink(missing_ok=True)


def stitch_segments(root, segment_ids, audio_path, audio_start=0, allow_profile_media=False, audio_pad_seconds=0):
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Video stitching requires supported file locking')
    if not isinstance(segment_ids, list) or not 1 <= len(segment_ids) <= 60 or any(not isinstance(x, str) or not re.fullmatch(r'[0-9a-f]{32}', x) for x in segment_ids):
        raise ValueError('Choose 1–60 segment IDs in plugin storage')
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    if type(audio_start) not in (int, float) or not math.isfinite(audio_start) or not 0 <= audio_start <= 7200: raise ValueError('Invalid audio start')
    if type(audio_pad_seconds) not in (int, float) or not math.isfinite(audio_pad_seconds) or not 0 <= audio_pad_seconds <= 10: raise ValueError('audio_pad_seconds must be 0 to 10')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Install ffmpeg and ffprobe')
    audio_source = media(audio_path, {'.wav', '.mp3', '.m4a'}, root, allow_profile_media, max_bytes=2 * 1024**3)
    root = Path(root).resolve(strict=True)
    if any(c in str(root) for c in ('\n', '\r')) or os.name != 'nt' and '\\' in str(root): raise ValueError('Newlines or backslashes in plugin storage paths are unsupported')
    segments = [root/(ident + '.mp4') for ident in segment_ids]
    if any(path.is_symlink() or not path.is_file() for path in segments): raise ValueError('A selected segment is unavailable or a symlink')
    def identity(path):
        value = path.stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    before = [identity(path) for path in segments]
    audio_before = identity(audio_source)
    if sum(x[2] for x in before) > 2 * 1024**3: raise ValueError('Selected segments exceed 2 GiB')
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    ident = uuid.uuid4().hex
    partial, output, manifest = root/(ident+'.partial.mp4'), root/(ident+'.mp4'), root/(ident+'.concat.txt')
    with locking.exclusive_lock(root/'.render.lock', 'Another video render is running'):
        try:
            deadline = time.monotonic() + 120
            def run(command, capture=False):
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise RuntimeError('Stitch exceeded its time limit')
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=min(remaining, 10) if capture else remaining, check=False)
                if result.returncode or capture and len(result.stdout) > 65536: raise RuntimeError('Stitch or metadata check failed')
                return result.stdout if capture else None
            reference, total, boundaries = None, 0.0, []
            for path in segments:
                info = json.loads(run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,sample_rate,channels,channel_layout', '-of', 'json', str(path)], True))
                duration = float(info.get('format', {}).get('duration', 0))
                streams = info.get('streams', [])
                video = [x for x in streams if x.get('codec_type') == 'video']
                if not math.isfinite(duration) or not 0 < duration <= 121 or len(video) != 1:
                    raise ValueError('A segment has unsupported duration or video streams')
                signature = video[0]
                if reference is not None and signature != reference: raise ValueError('Segments have incompatible video formats')
                reference = signature
                boundaries.append({'segment_id': path.stem, 'estimated_start_seconds': total, 'estimated_end_seconds': total + duration})
                total += duration
            if total > 7200: raise ValueError('Combined duration exceeds two hours')
            audio_info = json.loads(run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(audio_source)], True))
            audio_duration = float(audio_info.get('format', {}).get('duration', 0))
            if not math.isfinite(audio_duration) or audio_duration + audio_pad_seconds + 0.01 < audio_start + total or not any(x.get('codec_type') == 'audio' for x in audio_info.get('streams', [])):
                raise ValueError('Selected audio does not cover the joined duration')
            with os.fdopen(os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                for path in segments: stream.write("file '" + path.as_posix().replace("'", "'\\''") + "'\n")
            os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            run([ffmpeg, '-v', 'error', '-nostdin', '-f', 'concat', '-safe', '0', '-protocol_whitelist', 'file,pipe', '-i', str(manifest), '-ss', str(audio_start), '-protocol_whitelist', 'file,pipe', '-i', str(audio_source), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', *(['-af', f'apad=pad_dur={audio_pad_seconds}'] if audio_pad_seconds else []), '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-threads', '1', '-t', str(total), '-map_metadata', '-1', '-map_chapters', '-1', '-fs', str(2 * 1024**3), '-y', str(partial)])
            info = json.loads(run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration', '-of', 'json', str(partial)], True))
            actual = float(info.get('format', {}).get('duration', 0)); streams = info.get('streams', []); types = {x.get('codec_type') for x in streams}
            lengths = [float(x.get('duration', 0)) for x in streams if x.get('codec_type') in ('video', 'audio')]
            if not math.isfinite(actual) or abs(actual-total) > 0.25 or not {'video', 'audio'} <= types or len(lengths) < 2 or any(not math.isfinite(x) or x < total - .15 for x in lengths):
                raise RuntimeError('Joined duration or streams do not match the selected segments')
            if before != [identity(path) for path in segments] or audio_before != identity(audio_source): raise RuntimeError('An input changed while stitching')
            os.replace(partial, output)
            return {'output_path': str(output), 'segment_id': ident, 'duration_seconds': actual, 'segments': len(segments), 'segment_boundaries': boundaries, 'audio_start_seconds': audio_start,
                    'notice': 'Video is stream-copied; the explicitly selected original audio is encoded once. Segment audio, subtitles and chapters are omitted. Ensure the selected audio matches the intended timeline; boundary times are estimates. Inspect final media and captions.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise RuntimeError('Stitch or metadata check failed') from exc
        finally:
            partial.unlink(missing_ok=True); manifest.unlink(missing_ok=True)
