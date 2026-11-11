"""Owns one bounded FFmpeg process and restores its selected audio stream."""
import fcntl
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from core import probe, run, write_json, capture_input
from process_env import process_env


def stream_identity(stream):
    return (stream.get('client'), stream.get('properties', {}).get('application.process.id'))


def streams():
    return json.loads(run(['pactl', '--format=json', 'list', 'sink-inputs']))


def record(folder):
    request = json.loads((folder / 'request.json').read_text())
    state = {'job_id': folder.name, 'state': 'starting'}
    process = None
    module = None
    selected = None
    errors = []
    stop_requested = False

    def stop_signal(*_):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    lock = (folder.parent / 'recording.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        audio = []
        if request['audio_stream'] is not None:
            candidates = [s for s in streams() if s['index'] == request['audio_stream']]
            if len(candidates) != 1:
                raise ValueError('Selected audio stream is no longer present; list sources again')
            selected = candidates[0]
            sink_name = 'tutorial_creator_' + folder.name
            module = int(run(['pactl', 'load-module', 'module-null-sink', f'sink_name={sink_name}',
                              'rate=48000', 'channels=2']).strip())
            write_json(folder / 'audio-route.json', {'module': module, 'sink': sink_name,
                       'stream': selected['index'], 'previous_sink': selected['sink'],
                       'identity': stream_identity(selected), 'restored': False})
            run(['pactl', 'move-sink-input', str(selected['index']), sink_name])
            audio = ['-thread_queue_size', '512', '-f', 'pulse', '-i', sink_name + '.monitor']
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-progress', str(folder / 'progress.txt'),
                   *capture_input(request), *audio,
                   '-t', str(request['max_seconds']), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-pix_fmt', 'yuv420p']
        if audio:
            command += ['-c:a', 'pcm_s16le']
        command += [str(folder / 'raw.mkv')]
        with (folder / 'ffmpeg.log').open('wb') as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, env=process_env())
            started = time.monotonic()
            while process.poll() is None:
                progress = folder / 'progress.txt'
                if state['state'] == 'starting' and progress.exists() and 'frame=' in progress.read_text():
                    state['state'] = 'recording'
                    write_json(folder / 'state.json', state)
                if stop_requested or (folder / 'stop').exists() or time.monotonic() - started > request['max_seconds'] + 10:
                    state['state'] = 'stopping'
                    write_json(folder / 'state.json', state)
                    try:
                        process.communicate(b'q\n', timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                        raise RuntimeError('Recorder did not stop cleanly; raw MKV retained')
                    break
                time.sleep(.1)
            if process.returncode:
                raise RuntimeError('FFmpeg failed: ' + (folder / 'ffmpeg.log').read_text()[-1000:])
        info = probe(folder / 'raw.mkv')
        if not any(s['codec_type'] == 'video' for s in info['streams']):
            raise RuntimeError('No video stream was captured')
        state.update(state='complete', seconds=float(info['format']['duration']), audio=bool(audio))
    except Exception as exc:
        state.update(state='failed', error=str(exc))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if selected is not None and module is not None:
            try:
                current = next((s for s in streams() if s['index'] == selected['index']), None)
                if current and stream_identity(current) == stream_identity(selected):
                    run(['pactl', 'move-sink-input', str(selected['index']), str(selected['sink'])])
                route = json.loads((folder / 'audio-route.json').read_text())
                route['restored'] = True
                write_json(folder / 'audio-route.json', route)
            except Exception as exc:
                errors.append('Audio restoration: ' + str(exc))
        if module is not None:
            try:
                run(['pactl', 'unload-module', str(module)])
            except Exception as exc:
                errors.append('Audio sink cleanup: ' + str(exc))
        if errors:
            state['cleanup_errors'] = errors
        write_json(folder / 'state.json', state)
        lock.close()


if __name__ == '__main__':
    record(Path(sys.argv[1]).resolve())
