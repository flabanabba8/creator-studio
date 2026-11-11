"""Explicit local narration/music mix; never opens an audio device."""
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import uuid
from ..common import locking

PRIVATE = {'.ssh', '.gnupg', '.aws', '.azure', '.codex', '.docker', '.kube', '.pki', '.config', '.hermes'}


def media(value, root, allow_profile_media):
    if not isinstance(value, str) or len(value) > 4096: raise ValueError('Choose an absolute local audio path')
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or any(x.casefold() in PRIVATE - {'.hermes'} for x in path.parts):
        raise ValueError('Choose a non-symlink audio file outside private configuration')
    original = path.parts; path = path.resolve(strict=True)
    data = Path(root).resolve().parent; profile = data.parent if data.name.casefold() == 'plugin-data' else None
    allowed = allow_profile_media and profile is not None and path.is_relative_to(data)
    protected = any(x.casefold() == '.hermes' for x in (*original, *path.parts)) or profile is not None and path.is_relative_to(profile)
    if any(x.casefold() in PRIVATE - {'.hermes'} for x in path.parts) or protected and not allowed or not path.is_file() or path.suffix.lower() not in ('.wav', '.mp3', '.m4a'):
        raise ValueError('Unsupported or private audio file')
    if path.stat().st_size > 512 * 1024**2: raise ValueError('Audio source exceeds 512 MiB')
    return path


def mix(root, narration_path, music_path, music_db=-18, voice_db=0, allow_profile_media=False, loudness_lufs=None, import_from_project=False):
    result = _mix(root, narration_path, [{'music_path': music_path, 'start_ms': 0, 'end_ms': None, 'music_db': music_db}], voice_db, allow_profile_media, allow_open_end=True, loudness_lufs=loudness_lufs, import_from_project=import_from_project)
    result['music_db'] = music_db
    return result


def mix_timeline(root, narration_path, beds, voice_db=0, allow_profile_media=False, loudness_lufs=None, import_from_project=False):
    return _mix(root, narration_path, beds, voice_db, allow_profile_media, allow_open_end=False, loudness_lufs=loudness_lufs, import_from_project=import_from_project)


def _mix(root, narration_path, beds, voice_db, allow_profile_media, *, allow_open_end, loudness_lufs=None, import_from_project=False):
    if type(import_from_project) is not bool: raise ValueError('import_from_project must be true or false')
    if loudness_lufs is not None and (type(loudness_lufs) not in (int, float) or not math.isfinite(loudness_lufs) or not -30 <= loudness_lufs <= -10): raise ValueError('loudness_lufs must be -30 to -10 (spoken word is commonly about -16)')
    if locking.fcntl is None and locking.msvcrt is None: raise ValueError('Audio mixing requires supported file locking')
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    if type(voice_db) not in (int, float) or not math.isfinite(voice_db) or not -12 <= voice_db <= 0:
        raise ValueError('Use voice gain -12 to 0 dB')
    if not isinstance(beds, list) or not 1 <= len(beds) <= 20:
        raise ValueError('Provide 1–20 music beds')
    selected, previous_end = [], 0
    for bed in beds:
        if not isinstance(bed, dict) or not {'music_path', 'start_ms', 'end_ms', 'music_db'} <= set(bed) or not set(bed) <= {'music_path', 'start_ms', 'end_ms', 'music_db', 'fade_in_ms', 'fade_out_ms'}:
            raise ValueError('Each bed needs music_path, start_ms, end_ms and music_db')
        start, end, gain = bed['start_ms'], bed['end_ms'], bed['music_db']
        fade_in, fade_out = bed.get('fade_in_ms', 0), bed.get('fade_out_ms', 0)
        if type(start) is not int or start < previous_end or start > 7_200_000:
            raise ValueError('Music beds must be ordered and non-overlapping')
        if end is None:
            if not allow_open_end or len(beds) != 1 or start != 0: raise ValueError('Music bed end is required')
        elif type(end) is not int or not start < end <= 7_200_000:
            raise ValueError('Music bed end must follow its start')
        if type(gain) not in (int, float) or not math.isfinite(gain) or not -30 <= gain <= 0:
            raise ValueError('Use music gain -30 to 0 dB')
        if any(type(value) is not int or value < 0 for value in (fade_in, fade_out)) or end is not None and fade_in + fade_out > end-start or end is None and (fade_in or fade_out):
            raise ValueError('Fades must be nonnegative and fit within the bed')
        selected.append((media(bed['music_path'], root, allow_profile_media or import_from_project), start, end, gain, fade_in, fade_out))
        previous_end = end if end is not None else 7_200_001
    narration = media(narration_path, root, allow_profile_media)
    def owner(path):
        for parent in path.parents:
            meta = parent / 'project.json'
            if meta.is_file():
                data = json.loads(meta.read_text())
                if data.get('project_id'): return parent, data
        return None
    target = owner(narration)
    if target:
        bound=[]
        for path, start, end, gain, fade_in, fade_out in selected:
            origin = owner(path)
            if origin and origin[1]['project_id'] != target[1]['project_id']:
                if not import_from_project: raise ValueError('Asset belongs to project %s (%s), not project %s (%s); set import_from_project to copy it.' % (origin[1].get('topic','untitled'),origin[1]['project_id'],target[1].get('topic','untitled'),target[1]['project_id']))
                dest = target[0] / ('import-' + uuid.uuid4().hex + path.suffix)
                shutil.copyfile(path, dest); dest.chmod(0o600)
                receipt = dest.with_suffix(dest.suffix + '.origin.json')
                receipt.write_text(json.dumps({'project_id':origin[1]['project_id'],'topic':origin[1].get('topic',''),'path':str(path)})); receipt.chmod(0o600)
                path = dest
            bound.append((path,start,end,gain,fade_in,fade_out))
        selected=bound
    sources = [narration] + [item[0] for item in selected]
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Install ffmpeg and ffprobe')
    def identity(path):
        value = path.stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    before = [identity(path) for path in sources]
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ident = uuid.uuid4().hex; partial = root/(ident+'.partial.wav'); output = root/(ident+'.wav')
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8'}
    if os.name == 'nt' and 'SystemRoot' in os.environ: env['SystemRoot'] = os.environ['SystemRoot']
    with locking.exclusive_lock(root/'.mix.lock', 'Another podcast mix is running'):
        try:
            def probe(path):
                result = subprocess.run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=10, check=False)
                if result.returncode or len(result.stdout) > 65536: raise RuntimeError('Audio metadata check failed')
                info = json.loads(result.stdout); duration = float(info.get('format', {}).get('duration', 0))
                if not math.isfinite(duration) or not 0 < duration <= 7200 or not any(x.get('codec_type') == 'audio' for x in info.get('streams', [])):
                    raise ValueError('Audio duration or stream is unsupported')
                return duration
            duration = probe(narration)
            if any(end is not None and end > round(duration * 1000) for _, _, end, _, _, _ in selected):
                raise ValueError('Music bed extends beyond narration')
            for path in dict.fromkeys(item[0] for item in selected): probe(path)
            if duration * 48000 * 4 + 1024 > 2 * 1024**3: raise ValueError('WAV output would exceed 2 GiB')
            os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            command = [ffmpeg, '-v', 'error', '-nostdin', '-filter_complex_threads', '1', '-protocol_whitelist', 'file,pipe', '-i', str(narration)]
            for path, _, _, _, _, _ in selected: command += ['-stream_loop', '-1', '-protocol_whitelist', 'file,pipe', '-i', str(path)]
            filters = [f'[0:a:0]aresample=48000,volume={voice_db}dB[voice]']
            for index, (_, start, end, gain, fade_in, fade_out) in enumerate(selected, 1):
                length = duration if end is None else (end-start)/1000
                source = f'[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={length:.3f},asetpts=PTS-STARTPTS,volume={gain}dB'
                if fade_in: source += f',afade=t=in:st=0:d={fade_in/1000:.3f}'
                if fade_out: source += f',afade=t=out:st={length-fade_out/1000:.3f}:d={fade_out/1000:.3f}'
                if start:
                    filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={start/1000:.3f},asetpts=PTS-STARTPTS[silence{index}]')
                    filters.append(source + f'[music{index}]')
                    filters.append(f'[silence{index}][music{index}]concat=n=2:v=0:a=1[bed{index}]')
                else:
                    filters.append(source + f'[bed{index}]')
            filters.append('[voice]' + ''.join(f'[bed{i}]' for i in range(1,len(selected)+1)) + f'amix=inputs={len(selected)+1}:duration=first:dropout_transition=0:normalize=0' + (f',loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11' if loudness_lufs is not None else '') + ',alimiter=limit=0.95:level=0:latency=1[out]')
            command += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-t', str(duration), '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', '-threads', '1', '-map_metadata', '-1', '-map_chapters', '-1', '-fs', str(2 * 1024**3), '-y', str(partial)]
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=120, check=False)
            if result.returncode or not partial.stat().st_size: raise RuntimeError('Audio mix failed; verify FFmpeg supports limiter latency compensation')
            actual = probe(partial)
            if abs(actual-duration) > 0.25: raise RuntimeError('Mixed audio duration does not match narration')
            if before != [identity(path) for path in sources]: raise RuntimeError('An input changed during mixing; output discarded')
            measured = subprocess.run([ffmpeg, '-nostats', '-nostdin', '-i', str(partial), '-af', 'ebur128=framelog=quiet', '-f', 'null', '-'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, timeout=120, check=False)
            summary = re.findall(r'I:\s*(-?\d+(?:\.\d+)?)\s*LUFS', measured.stderr.decode('utf-8', 'replace')[-4000:])
            integrated = float(summary[-1]) if summary else None
            os.replace(partial, output)
            return {'output_path': str(output), 'duration_seconds': actual, 'beds': len(selected), 'voice_db': voice_db, 'integrated_lufs': integrated, 'loudness_target_lufs': loudness_lufs,
                    'notice': 'Music loops within each selected bed; there is no automatic ducking. A loudness target is a one-pass approximation, and the measured integrated loudness is reported; neither is an editorial review. Mixing may shift timing. Check licensing, attribution, balance and final audio before sharing.'}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise RuntimeError('Audio mix or metadata check failed') from exc
        finally:
            partial.unlink(missing_ok=True)
