"""Bounded local window recordings. No shell, network, or credential access."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import threading
import uuid

if __package__:
    from .process_env import process_env
else:
    from process_env import process_env


def run(argv, timeout=15):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=process_env())
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed: {result.stderr[-1200:]}")
    return result.stdout


def clean_export_name(name):
    """Accept the export file name, its full path, or the name without .mp4; return the canonical file name."""
    if isinstance(name, str):
        base = Path(name).name
        if re.fullmatch(r'export-[a-f0-9]{32}', base): base += '.mp4'
        return base
    return name


def window_pid(display, window_id):
    """Process ID that owns an X11 window (_NET_WM_PID), or None when it is not advertised."""
    local_display(display)
    try:
        match = re.search(r'=\s*(\d+)', run(['xprop', '-display', display, '-id', str(int(window_id)), '_NET_WM_PID']))
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return None
    return int(match[1]) if match and int(match[1]) > 0 else None


def raise_window(display, window_id):
    """Best effort: bring the selected window above overlapping windows. Without a compositor
    X11 returns black for covered parts of a window, so the take would record black frames."""
    exe = shutil.which('xdotool')
    if not exe:
        return False
    try:
        run([exe, 'windowraise', str(int(window_id))], timeout=5)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return False
    return True


def window_title(display, window_id):
    local_display(display)
    try:
        match = re.search(r'Window id: \S+ "(.*)"', run(['xwininfo', '-display', display, '-id', str(int(window_id))]))
    except (RuntimeError, OSError, ValueError, IndexError, subprocess.SubprocessError):
        return ''
    return match[1] if match else ''


def is_spreadsheet_grid(display, window_id):
    """LibreOffice Calc: Hermes computer-use `type` makes soffice grow without bound there (known limit)."""
    return 'libreoffice calc' in window_title(display, window_id).casefold()


def set_clipboard(display, text):
    """Put plain text on the X11 clipboard of the recorded display with xclip."""
    local_display(display)
    exe = shutil.which('xclip')
    if not exe:
        raise ValueError('Typing into a spreadsheet grid is refused (it can exhaust memory); install xclip so the plugin can paste instead, or enter the data with single key actions')
    if not isinstance(text, str) or not text or len(text) > 2000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
        raise ValueError('Paste text must be 1-2000 characters of plain text')
    subprocess.run([exe, '-selection', 'clipboard', '-i'], input=text.encode(), check=True, timeout=10,
                   env={**process_env(), 'DISPLAY': display}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def write_json(path, value):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def identity(pid):
    try:
        # /proc stat names may contain spaces or parentheses.
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return None


def local_display(display):
    if not isinstance(display, str) or not re.fullmatch(r':\d+(?:\.\d+)?', display):
        raise ValueError('A local X11 display such as :0 is required; native Wayland is not supported yet')
    return display


def window_info(display, window_id, capture_mode='window'):
    local_display(display)
    if capture_mode not in ('window', 'window_region'):
        raise ValueError('Choose window or window_region capture')
    if isinstance(window_id, str) and re.fullmatch(r'0x[0-9a-fA-F]+', window_id):
        window_id = int(window_id, 16)
    number(window_id, 1, 2**32 - 1, 'window_id')
    if int(window_id) != window_id:
        raise ValueError('window_id must be an integer')
    info = run(['xwininfo', '-display', display, '-id', str(window_id)])
    width = int(re.search(r'Width:\s+(\d+)', info).group(1))
    height = int(re.search(r'Height:\s+(\d+)', info).group(1))
    if not 2 <= width <= 4096 or not 2 <= height <= 4096:
        raise ValueError('Window must be 2–4096 pixels in each dimension')
    if 'Map State: IsViewable' not in info:
        raise ValueError('Window is not viewable')
    root = run(['xwininfo', '-display', display, '-root'])
    root_id = re.search(r'Window id:\s+(0x[0-9a-fA-F]+)', root).group(1)
    if int(root_id, 16) == int(window_id):
        raise ValueError('Desktop/root capture is not supported; select an application window')
    result = {'window_id': int(window_id), 'width': width, 'height': height, 'display': display}
    if capture_mode == 'window_region':
        x = re.search(r'Absolute upper-left X:\s+(-?\d+)', info)
        y = re.search(r'Absolute upper-left Y:\s+(-?\d+)', info)
        rw = re.search(r'Width:\s+(\d+)', root)
        rh = re.search(r'Height:\s+(\d+)', root)
        if not all((x, y, rw, rh)):
            raise ValueError('Window screen bounds are unavailable')
        left, top = int(x[1]), int(y[1])
        if left < 0 or top < 0 or left + width > int(rw[1]) or top + height > int(rh[1]):
            raise ValueError('Window region must be fully on screen')
        result.update(left=left, top=top)
    return result


def capture_input(request):
    """FFmpeg input for a selected drawable or its explicit fixed screen region."""
    mode = request.get('capture_mode', 'window')
    cursor = request.get('show_cursor', False)
    if type(cursor) is not bool:
        raise ValueError('show_cursor must be a boolean')
    display = local_display(request['display'])
    args = ['-f', 'x11grab', '-draw_mouse', '1' if cursor else '0', '-framerate', '30',
            '-video_size', f"{request['width']}x{request['height']}"]
    if mode == 'window':
        return args + ['-window_id', str(request['window_id']), '-i', display]
    if mode != 'window_region':
        raise ValueError('Choose window or window_region capture')
    if any(type(request.get(k)) is not int or request[k] < 0 for k in ('left', 'top')):
        raise ValueError('Window region needs validated screen coordinates')
    return args + ['-i', f"{display}+{request['left']},{request['top']}"]


def sources(display=None):
    if sys.platform != 'linux': raise ValueError('Window capture requires Linux X11/XWayland')
    display = local_display(display or os.environ.get('DISPLAY', ''))
    listing = run(['xwininfo', '-display', display, '-root', '-tree'])
    windows = []
    for line in listing.splitlines():
        match = re.search(r'(0x[0-9a-fA-F]+) "(.*?)".*?\s(\d+)x(\d+)\+', line)
        if match and match[2]:
            windows.append({'window_id': match[1], 'title': match[2],
                            'width': int(match[3]), 'height': int(match[4])})
    audio = []
    audio_error = None
    if shutil.which('pactl'):
        try:
            for stream in json.loads(run(['pactl', '--format=json', 'list', 'sink-inputs'])):
                props = stream.get('properties', {})
                audio.append({'stream_id': stream['index'], 'application': props.get('application.name'),
                              'pid': props.get('application.process.id'), 'media': props.get('media.name')})
        except (RuntimeError, ValueError) as exc:
            audio_error = str(exc)
    return {'display': display, 'windows': windows, 'audio_streams': audio, 'audio_error': audio_error,
            'capture_limitations': 'X11/XWayland only. Keep the selected window visible and uncovered. Audio is optional; select one listed stream explicitly.'}


class Director:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def job(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Invalid recording ID')
        path = self.root / job_id
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Recording does not exist')
        return path

    def start(self, window_id, display=None, max_seconds=180, audio_stream=None,
              capture_mode='window', show_cursor=False):
        if sys.platform != 'linux': raise ValueError('Window capture requires Linux X11/XWayland')
        max_seconds = number(max_seconds, 1, 1800, 'max_seconds')
        for binary in ['ffmpeg', 'ffprobe', 'xwininfo']:
            if not shutil.which(binary):
                raise ValueError(f'Install {binary} before recording')
        if type(show_cursor) is not bool:
            raise ValueError('show_cursor must be a boolean')
        source = window_info(display or os.environ.get('DISPLAY', ''), window_id, capture_mode)
        source.update(capture_mode=capture_mode, show_cursor=show_cursor)
        if audio_stream is not None:
            number(audio_stream, 0, 2**32 - 1, 'audio_stream')
            if int(audio_stream) != audio_stream:
                raise ValueError('audio_stream must be an integer')
            if not shutil.which('pactl'):
                raise ValueError('pactl is required for application audio')
        local_display(source['display'])
        raise_window(source['display'], source['window_id'])
        job_id = uuid.uuid4().hex
        folder = self.root / job_id
        folder.mkdir(mode=0o700)
        write_json(folder / 'request.json', {**source, 'max_seconds': max_seconds, 'audio_stream': audio_stream})
        write_json(folder / 'state.json', {'state': 'starting', 'job_id': job_id})
        with (folder / 'worker.log').open('wb') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker.py')), str(folder)],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, env=process_env())
        threading.Thread(target=child.wait, daemon=True).start()
        write_json(folder / 'owner.json', {'pid': child.pid, 'identity': identity(child.pid)})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = self.status(job_id)
            if state['state'] != 'starting':
                return state
            time.sleep(.1)
        return self.status(job_id)

    def status(self, job_id):
        folder = self.job(job_id)
        state = json.loads((folder / 'state.json').read_text())
        owner_path = folder / 'owner.json'
        if state['state'] in ('starting', 'recording', 'stopping') and owner_path.exists():
            owner = json.loads(owner_path.read_text())
            if owner['identity'] is None or identity(owner['pid']) != owner['identity']:
                state['state'] = 'interrupted'
                state['error'] = 'Recorder exited without finalizing. The raw MKV may be recoverable; inspect audio-route.json for any route needing restoration.'
        progress = folder / 'progress.txt'
        seconds = 0.0
        if progress.exists():
            matches = re.findall(r'^out_time_us=(\d+)$', progress.read_text(), re.M)
            if matches:
                seconds = int(matches[-1]) / 1_000_000
        marks = folder / 'marks.jsonl'
        return {**state, 'job_id': job_id, 'media_seconds': seconds,
                'marks': [json.loads(line) for line in marks.read_text().splitlines()] if marks.exists() else []}

    def mark(self, job_id, label):
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 160:
            raise ValueError('Marker label must contain 1–160 characters')
        state = self.status(job_id)
        if state['state'] != 'recording':
            raise ValueError('Markers require an active recording')
        mark = {'seconds': state['media_seconds'], 'label': label.strip()}
        # One atomic append per marker; media progress updates approximately twice per second.
        fd = os.open(self.job(job_id) / 'marks.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(mark) + '\n').encode())
        finally:
            os.close(fd)
        return mark

    def stop(self, job_id):
        state = self.status(job_id)
        if state['state'] in ('starting', 'recording', 'stopping'):
            (self.job(job_id) / 'stop').touch(mode=0o600, exist_ok=True)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                state = self.status(job_id)
                if state['state'] not in ('starting', 'recording', 'stopping'):
                    break
                time.sleep(.1)
        return state

    def export(self, job_id, segments):
        folder = self.job(job_id)
        state = self.status(job_id)
        if state['state'] != 'complete':
            raise ValueError('Export requires a successfully completed recording')
        raw = folder / 'raw.mkv'
        metadata = probe(raw)
        duration = float(metadata['format']['duration'])
        if not isinstance(segments, list) or not 1 <= len(segments) <= 20:
            raise ValueError('Provide 1–20 segments, each with start and duration')
        total = 0.0
        for part in segments:
            if not isinstance(part, dict) or set(part) != {'start', 'duration'}:
                raise ValueError('Each segment needs exactly start and duration')
            start = number(part['start'], 0, duration, 'start')
            length = number(part['duration'], .1, 89, 'duration')
            if start + length > duration + .02:
                raise ValueError('Segment exceeds the source duration')
            total += length
        if total > 89:
            raise ValueError('The combined demo must be at most 89 seconds')
        out = folder / ('export-' + uuid.uuid4().hex + '.mp4')
        has_audio = any(s['codec_type'] == 'audio' for s in metadata['streams'])
        filters, labels = [], []
        for i, part in enumerate(segments):
            s, d = part['start'], part['duration']
            filters.append(f'[0:v]trim=start={s}:duration={d},setpts=PTS-STARTPTS,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[v{i}]')
            labels.append(f'[v{i}]')
            if has_audio:
                filters.append(f'[0:a]atrim=start={s}:duration={d},asetpts=PTS-STARTPTS[a{i}]')
                labels.append(f'[a{i}]')
        filters.append(''.join(labels) + f'concat=n={len(segments)}:v=1:a={int(has_audio)}[v]' + ('[a]' if has_audio else ''))
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-i', str(raw),
                   '-filter_complex', ';'.join(filters), '-map', '[v]']
        if has_audio:
            command += ['-map', '[a]', '-c:a', 'aac', '-b:a', '128k']
        command += ['-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                    '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart', str(out)]
        try:
            run(command, timeout=300)
            result = probe(out)
            actual = float(result['format']['duration'])
            if actual >= 90 or abs(actual - total) > .25:
                raise RuntimeError('Export duration check failed')
            # Decode the whole output; a container header alone is not a playable-video check.
            run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(out), '-f', 'null', '-'], timeout=180)
        except Exception:
            out.unlink(missing_ok=True)
            raise
        receipt = {'path': str(out), 'export_name': out.name, 'seconds': actual, 'bytes': out.stat().st_size,
                   'audio': has_audio, 'segments': segments, 'decoded': True,
                   'estimated_upload_seconds_at_93_KiB_s': round(out.stat().st_size / (93 * 1024), 1)}
        write_json(out.with_suffix('.json'), receipt)
        return receipt

    def timeline(self, job_id, export_name=None):
        export_name = clean_export_name(export_name)
        state = self.status(job_id)
        if export_name is None:
            return {'clock': 'recording media seconds', 'state': state['state'], 'seconds': state['media_seconds'], 'steps': state['marks']}
        folder = self.job(job_id)
        if not isinstance(export_name, str) or not re.fullmatch(r'export-[a-f0-9]{32}\.mp4', export_name):
            raise ValueError('Select an export filename returned by capture_export')
        receipt = json.loads((folder / export_name).with_suffix('.json').read_text())
        offset, clips, steps = 0.0, [], []
        for index, segment in enumerate(receipt['segments']):
            start, length = segment['start'], segment['duration']
            clips.append({'clip': index, 'source_start': start, 'output_start': offset, 'duration': length})
            for mark in state['marks']:
                if start <= mark['seconds'] < start + length:
                    steps.append({'label': mark['label'], 'source_seconds': mark['seconds'],
                                  'seconds': offset + mark['seconds'] - start, 'clip': index})
            offset += length
        return {'clock': 'export media seconds', 'export_name': export_name, 'seconds': receipt['seconds'],
                'clips': clips, 'steps': steps,
                'precision': 'Markers use approximately0.5-second progress updates; cut boundaries are quantized to video frames.'}

    def frame(self, job_id, export_name, seconds):
        export_name = clean_export_name(export_name)
        timeline = self.timeline(job_id, export_name)
        number(seconds, 0, max(0, timeline['seconds'] - .05), 'frame time')
        folder = self.job(job_id)
        output = folder / ('frame-' + uuid.uuid4().hex + '.png')
        run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-ss', str(seconds), '-i', str(folder / export_name),
             '-frames:v', '1', str(output)], timeout=20)
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError('No frame could be decoded at that timestamp')
        return {'path': str(output), 'requested_seconds': seconds,
                'timing': 'Decoded video frame at the requested seek; frame-rate quantization applies',
                'instruction': 'Inspect this frame with native vision before describing what the UI shows.'}


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))
