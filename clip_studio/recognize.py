"""Recognise the speech of a whole recording or stream from one request, in pieces that can be resumed.

The audio is cut into pieces of about ten minutes (at a quiet point, never inside a word when there is a pause nearby). Each piece goes to
Caption Studio's own recognizer choice as an ordinary captions_generate job; its word times are shifted back to video time and saved. A
partly finished transcript is attached to the project after every piece (marked partial) and the final one replaces it when the last
piece is done. If the run is interrupted, calling clips_transcribe again carries on from the pieces already saved.

Caption Studio does not split audio itself (one job is one recognizer call, at most two hours), so the splitting lives here and nothing
about the recognizer is configured twice.
"""
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from . import source, transcript as T
from .project import _write

try:
    import fcntl
except ImportError:  # no cross-process lock; one process still never starts two runs for a project
    fcntl = None

TOOLS = {}  # the one tool, clips_transcribe, lives in the main table

DEFAULT_PIECE_MINUTES, MIN_PIECE_MINUTES, MAX_PIECE_MINUTES = 10.0, 0.5, 60.0
MAX_WAIT = 120
TAIL = 1.25  # a rest of up to this many pieces is recognised as the last piece, so no tiny tail piece is made
LEVELS = ('-35dB', '-28dB', '-22dB')  # silence thresholds tried in turn when looking for a quiet point
TERMINAL = ('done', 'failed', 'needs_setup', 'stopped')
POLL = 1.0  # seconds between looks at a Caption Studio job
NAP = 0.5  # seconds between looks while a call waits for progress
BUSY_NAP = 5.0
_THREADS = {}
ID = re.compile(r'^[0-9a-f]{32}$')


# pure helpers: piece planning and time shifting

def parse_silences(text, window_start, window_end):
    """Silences as (start, end) seconds in video time from FFmpeg's silencedetect lines for a window that began at window_start."""
    spans, open_at = [], None
    for line in text.splitlines():
        m = re.search(r'silence_start:\s*(-?[\d.]+)', line)
        if m:
            open_at = max(window_start, window_start + float(m.group(1)))
            continue
        m = re.search(r'silence_end:\s*(-?[\d.]+)', line)
        if m:
            spans.append((window_start if open_at is None else open_at, min(window_end, window_start + float(m.group(1)))))
            open_at = None
    if open_at is not None:
        spans.append((open_at, window_end))
    return [(a, b) for a, b in spans if b > a]


def choose_cut(spans, lo, hi):
    """The middle of the longest quiet stretch that lies inside [lo, hi], or None when there is none."""
    inside = [(max(a, lo), min(b, hi)) for a, b in spans if b > lo and a < hi]
    inside = [(a, b) for a, b in inside if b > a]
    if not inside:
        return None
    a, b = max(inside, key=lambda s: s[1] - s[0])
    return (a + b) / 2


def plan_end(start_ms, total_ms, piece_ms, find_cut):
    """Where the piece that begins at start_ms ends (ms). find_cut(lo_s, hi_s) returns a quiet point in seconds or None."""
    if total_ms - start_ms <= piece_ms * TAIL:
        return total_ms
    target = start_ms + piece_ms
    lo = target - min(60000, piece_ms // 4)
    cut = find_cut(lo / 1000, target / 1000)
    end = round(cut * 1000) if cut else target
    return end if start_ms + piece_ms // 2 <= end <= target else target


def shift_words(words, offset_ms, floor_ms=0):
    """Caption Studio words (times inside one piece) as transcript units in video time, in order and never overlapping the earlier ones."""
    units, last = [], floor_ms
    for w in words:
        text = str(w.get('text', '')).strip()
        if not text:
            continue
        s = max(int(w['start_ms']) + offset_ms, last)
        e = max(int(w['end_ms']) + offset_ms, s + 1)
        units.append({'s': s, 'e': e, 't': text})
        last = s
    return units


def _model_name(model):
    """A model id or cache path as a short name, for the transcript's origin line."""
    m = re.search(r'models--([^/]+?)--([^/]+)', str(model))
    return (m.group(1) + '/' + m.group(2)) if m else Path(str(model)).name[:60]


def minutes(ms):
    return round(ms / 60000, 1)


# Caption Studio seams (replaced in tests)

def _caption(name, args, ctx, context):
    from .. import caption_studio
    out = json.loads(caption_studio.invoke(name, args, ctx, **context))
    if isinstance(out, dict) and 'error' in out:
        raise ValueError(out['error'])
    return out


def _read_words(job_id):
    """The measured words of a finished Caption Studio job. The big audio copies the job keeps are removed; the review is never exported."""
    from plugins.plugin_storage import plugin_data_dir
    from .. import caption_studio
    if not isinstance(job_id, str) or not ID.fullmatch(job_id):
        raise ValueError('Caption Studio returned an unexpected job id')
    folder = Path(plugin_data_dir(caption_studio.STORAGE_NAMESPACE)) / 'audio-reviews' / job_id
    words = json.loads((folder / 'words.json').read_text(encoding='utf-8'))
    for stale in [*folder.glob('source.*'), folder / 'audio.wav', *folder.glob('preview-*.wav')]:
        try:
            stale.unlink()
        except OSError:
            pass
    return words


# audio

def _quiet_point(media):
    def find(lo, hi):
        for level in LEVELS:
            try:
                done = subprocess.run([_ffmpeg(), '-hide_banner', '-nostdin', '-protocol_whitelist', 'file,pipe', '-ss', '%.3f' % lo, '-t', '%.3f' % (hi - lo), '-i', str(media), '-vn',
                                       '-af', 'silencedetect=noise=%s:d=0.3' % level, '-f', 'null', '-'],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=source.process_env(), timeout=source.LONG, check=False)
            except subprocess.TimeoutExpired:
                return None
            cut = choose_cut(parse_silences(done.stderr.decode('utf-8', 'replace'), lo, hi), lo, hi)
            if cut:
                return cut
        return None
    return find


def _ffmpeg():
    import shutil
    program = shutil.which('ffmpeg')
    if not program:
        raise ValueError('Install ffmpeg and ffprobe')
    return program


def _extract(media, start_ms, end_ms, target):
    target.unlink(missing_ok=True)
    source.ffmpeg(['-y', '-protocol_whitelist', 'file,pipe', '-ss', '%.3f' % (start_ms / 1000), '-t', '%.3f' % ((end_ms - start_ms) / 1000), '-i', str(media), '-vn', '-map', '0:a:0?',
                   '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(target)])
    if not target.is_file() or target.stat().st_size < 100:
        raise RuntimeError('The audio piece could not be cut')


# state on disk

def _dir(folder):
    d = Path(folder) / 'recognition'
    d.mkdir(mode=0o700, exist_ok=True)
    return d


def _state(folder):
    try:
        return json.loads((Path(folder) / 'recognition' / 'state.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _save(folder, st):
    st['updated'] = time.time()
    _write(_dir(folder) / 'state.json', st)


def _alive(folder):
    """True when a worker (in this or another process) holds the project's recognition lock."""
    if fcntl is None:
        thread = _THREADS.get(str(folder))
        return bool(thread and thread.is_alive())
    with (_dir(folder) / '.worker.lock').open('a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def _take_lock(folder):
    """The open lock file (keep it open while working) or None when someone else holds it."""
    stream = (_dir(folder) / '.worker.lock').open('a+b')
    if fcntl is None:
        thread = _THREADS.get(str(folder))
        if thread and thread.is_alive():
            stream.close()
            return None
        return stream
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        return None
    return stream


def _load_pieces(folder, st):
    out = []
    for piece in st.get('pieces', []):
        out.extend(json.loads((Path(folder) / 'recognition' / piece['file']).read_text(encoding='utf-8')))
    return out


def _attach(clips, project_id, folder, st, final):
    """Put the recognised units so far on the project: marked partial until the last piece. False when the user attached something else meanwhile."""
    units = _load_pieces(folder, st)
    _folder, data = clips._load(project_id)
    current = data.get('transcript')
    if current and current.get('recognition') != st['run'] and current != st.get('replaces'):
        return False
    if not units:
        return True
    done_ms, total_ms = st['pieces'][-1]['end_ms'], st['duration_ms']
    label = 'speech recognition with Caption Studio' + (' (%s)' % st['recognizer'] if st.get('recognizer') else '')
    origin = label if final else 'PARTIAL %s: only the first %s of %s minutes so far' % (label, minutes(done_ms), minutes(total_ms))
    clips._set_transcript(folder, data, 'words', units, origin, None)
    data['transcript'].update(recognition=st['run'], partial=not final)
    if not final:
        data['transcript']['partial_note'] = ('This transcript is PARTIAL: only the first %s of %s minutes have been recognised so far. Everything after %s is not in it yet, so nothing can be said '
                                              'about that part and no clip may be placed there. Call clips_transcribe to see progress; the rest is added automatically.' % (minutes(done_ms), minutes(total_ms), T.clock(done_ms)))
    _write(Path(folder) / 'project.json', data)
    return True


# the worker

def _generate(piece, rec, ctx, context, folder, st):
    """Start one Caption Studio job for the piece, waiting while another job in the profile is still running."""
    args = {'media_path': str(piece), 'recognizer': rec, 'allow_profile_media': True}
    while True:
        try:
            return _caption('captions_generate', args, ctx, context)
        except ValueError as exc:
            if 'already running' not in str(exc):
                raise
            st.update(state='waiting', phase='Waiting for another Caption Studio job in this profile to finish')
            _save(folder, st)
            time.sleep(BUSY_NAP)


def _finish_job(job_id, ctx, context):
    while True:
        status = _caption('captions_audio_status', {'job_id': job_id}, ctx, context)
        if status.get('state') == 'ready':
            return status, _read_words(job_id)
        if status.get('state') in ('failed', 'cancelled'):
            raise RuntimeError('Caption Studio could not recognise this piece: ' + str(status.get('error') or status.get('state')))
        time.sleep(POLL)


def _work(clips, project_id, folder, rec, ctx, context, lock):
    st = _state(folder)
    try:
        st.update(state='preparing', phase='Getting the audio' + (' (the audio track is fetched from YouTube once)' if st.get('youtube') else ''), error=None)
        _save(folder, st)
        media = clips.audio_for_recognition(project_id)
        facts = source.probe(media)
        stat = Path(media).stat()
        identity = [stat.st_size, stat.st_mtime_ns]
        if st.get('identity') not in (None, identity):  # not the same sound as the pieces on disk: start over
            for p in st['pieces']:
                (Path(folder) / 'recognition' / p['file']).unlink(missing_ok=True)
            st['pieces'] = []
        total_ms = int(facts['duration'] * 1000)
        if total_ms < 500:
            raise ValueError('There is hardly any sound in this recording')
        st.update(identity=identity, duration_ms=total_ms, state='recognising')
        find_cut = _quiet_point(media)
        work = _dir(folder) / 'work'
        work.mkdir(mode=0o700, exist_ok=True)
        piece_wav = work / 'piece.wav'
        while True:
            pos = st['pieces'][-1]['end_ms'] if st['pieces'] else 0
            if total_ms - pos < 300:
                break
            n = len(st['pieces'])
            st.update(state='recognising', phase='Cutting piece %d' % (n + 1))
            _save(folder, st)
            end = plan_end(pos, total_ms, st['piece_ms'], find_cut)
            _extract(media, pos, end, piece_wav)
            began = time.monotonic()
            st['phase'] = 'Recognising piece %d (%s to %s)' % (n + 1, T.clock(pos), T.clock(end))
            _save(folder, st)
            job = _generate(piece_wav, rec, ctx, context, folder, st)
            if 'job_id' not in job:
                st.update(state='needs_setup', phase='The user has not chosen a recognizer yet', interview=job)
                _save(folder, st)
                return
            st.update(state='recognising', phase=st['phase'], job_id=job['job_id'])
            _save(folder, st)
            status, words = _finish_job(job['job_id'], ctx, context)
            units = shift_words(words, pos)
            name = 'piece-%04d.json' % n
            _write(_dir(folder) / name, units)
            st['pieces'].append({'n': n, 'start_ms': pos, 'end_ms': end, 'words': len(units), 'seconds_taken': round(time.monotonic() - began, 1), 'file': name})
            st.pop('job_id', None)
            if not st.get('recognizer') and status.get('model'):
                st['recognizer'] = '%s, %s' % (status.get('recognizer_kind', 'recognizer'), _model_name(status['model']))
            if not _attach(clips, project_id, folder, st, final=False):
                st.update(state='stopped', phase='Stopped: another transcript was attached to this project meanwhile, and it was left alone')
                _save(folder, st)
                return
            _save(folder, st)
        if not _load_pieces(folder, st):
            raise ValueError('No speech was recognised in this recording')
        if not _attach(clips, project_id, folder, st, final=True):
            st.update(state='stopped', phase='Stopped: another transcript was attached to this project meanwhile, and it was left alone')
        else:
            st.update(state='done', phase='The whole transcript is attached to the project')
        _save(folder, st)
        for leftover in (_dir(folder) / 'work').glob('*'):
            leftover.unlink(missing_ok=True)
    except Exception as exc:  # the thread must never die silently: the next call reads this and resumes
        message = str(exc)[:400] if isinstance(exc, (ValueError, RuntimeError, OSError, KeyError)) else 'Recognition stopped unexpectedly (%s)' % type(exc).__name__
        st.update(state='failed', phase='Stopped', error=message)
        _save(folder, st)
    finally:
        lock.close()


# the tool

def _number(value, low, high, default, label):
    if value is None:
        return default
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError('%s must be a number from %s to %s' % (label, low, high))
    return value


def _report(clips, project_id, folder, started=False, resumed=False, note=None):
    st = _state(folder)
    _folder, data = clips._load(project_id)
    t = data.get('transcript') or {}
    out = {'project_id': project_id}
    if st is None:
        out['transcript'] = t or None
        return out
    pieces = st.get('pieces', [])
    total_ms = st.get('duration_ms') or int((data.get('duration') or 0) * 1000)
    done_ms = pieces[-1]['end_ms'] if pieces else 0
    took = sum(p['seconds_taken'] for p in pieces)
    audio_min = sum(p['end_ms'] - p['start_ms'] for p in pieces) / 60000
    rec = {'state': st['state'], 'phase': st.get('phase'), 'recognised_minutes': minutes(done_ms), 'total_minutes': minutes(total_ms),
           'progress': '%s of %s minutes recognised' % (minutes(done_ms), minutes(total_ms)), 'pieces_done': len(pieces),
           'words_so_far': sum(p['words'] for p in pieces), 'piece_minutes': minutes(st['piece_ms'])}
    if total_ms:
        rec['percent'] = round(100 * done_ms / total_ms)
    if audio_min and st['state'] not in ('done',):
        rec['minutes_left_estimate'] = round(took / 60 * (total_ms - done_ms) / 60000 / audio_min, 1)
    if st.get('resumed_from'):
        rec['resumed_from_piece'] = st['resumed_from']
    if st.get('error'):
        rec['error'] = st['error']
    if st.get('recognizer'):
        rec['recognizer'] = st['recognizer']
    out['recognition'] = rec
    if note:
        out['note'] = note
    stage = st['state']
    if stage == 'needs_setup':
        out['recognizer_interview'] = st.get('interview')
        out['next'] = 'There is no transcript, and none can be made until the user has chosen how speech is recognised. Ask the user the interview questions and save their answers with captions_recognizer_setup. Then call clips_transcribe again with this project_id. Do not guess any moments from the title or length in the meantime.'
    elif stage == 'done':
        out['transcript'] = t
        out['next'] = 'Done: the whole transcript (every word timed) is attached to the project. Call clips_outline next. Nothing else needs to be saved or attached.'
    elif stage == 'failed':
        out['next'] = ('Recognition stopped: %s The %d finished piece(s) are kept. Call clips_transcribe again with this project_id to carry on from piece %d. If it stops the same way a second time, tell the user the error and stop; '
                       'do not suggest clips from a transcript that does not exist.' % (st.get('error', 'no reason was recorded.'), len(pieces), len(pieces) + 1))
        if t.get('partial'):
            out['transcript'] = t
    elif stage == 'stopped':
        out['next'] = 'Recognition was stopped because the project got another transcript. Use clips_outline. Call clips_transcribe with restart=true only if the user wants speech recognition instead.'
    else:
        wait = 'Call clips_transcribe again with the same project_id (wait_seconds up to %d makes the call wait for news) to see progress; nothing else needs to be called to finish. ' % MAX_WAIT
        if t.get('partial'):
            out['transcript'] = t
            out['next'] = ('Recognition is running in the background: %s. The transcript is PARTIAL: clips_outline and clips_transcript can read the first %s minutes only, and nothing can be said about the rest yet. '
                           'Do not propose clips beyond %s and do not guess what is said there. ' % (rec['progress'], minutes(done_ms), T.clock(done_ms))) + wait + 'The transcript is attached automatically when the last piece is done.'
        else:
            out['next'] = ('Recognition is running in the background (%s). There is no transcript yet, so do not suggest or guess any clips, moments or times. ' % rec['progress']) + wait + 'Tell the user it is running and roughly how long it will take.'
    return out


def transcribe(clips, args, ctx, **context):
    project_id = args['project_id']
    folder, data = clips._load(project_id)
    rec = args.get('recognizer') or {'kind': 'chosen'}
    if not isinstance(rec, dict) or rec.get('kind') == 'import':
        raise ValueError('Recognizing a long recording works with the recognizer the user chose (kind chosen, configured or host). To use a transcript that already exists, give its SRT or WebVTT file to clips_use_transcript')
    piece_minutes = _number(args.get('piece_minutes'), MIN_PIECE_MINUTES, MAX_PIECE_MINUTES, None, 'piece_minutes')
    wait = _number(args.get('wait_seconds'), 0, MAX_WAIT, 20, 'wait_seconds')
    restart = args.get('restart', False)
    if type(restart) is not bool:
        raise ValueError('restart is true or false')
    if data['kind'] == 'youtube' and data.get('live_status') == 'is_live':
        raise ValueError('This stream is still on air; its audio can be recognized after it ends.')
    alive = _alive(folder)
    st = _state(folder)
    if restart and alive:
        raise ValueError('Recognition is still running for this project; wait for it to finish, then ask again with restart=true')
    existing = data.get('transcript')
    if restart and st is not None:
        for p in (_dir(folder)).glob('piece-*.json'):
            p.unlink(missing_ok=True)
        (_dir(folder) / 'state.json').unlink(missing_ok=True)
        st = None
    if not alive and existing and not existing.get('partial') and not (st and st.get('run') == existing.get('recognition')) and not restart:
        return {'project_id': project_id, 'transcript': existing, 'note': 'This project already has a transcript (%s), so nothing was recognised.' % existing.get('from'),
                'next': 'Use it: call clips_outline. Only if the user wants speech recognition instead, call clips_transcribe again with restart=true (this replaces the current transcript when the new one is complete).'}
    if not alive and st is not None and st['state'] == 'done':
        return _report(clips, project_id, folder)
    resumed = False
    if not alive:
        if rec.get('kind') == 'chosen':  # the interview comes back before any audio is fetched
            setup = _caption('captions_recognizer_setup', {}, ctx, context)
            if setup.get('state') != 'answered':
                return {'project_id': project_id, 'recognizer_interview': setup,
                        'next': 'There is no transcript, and none can be made until the user has chosen how speech is recognised. Ask the user the interview questions and save their answers with captions_recognizer_setup. Then call clips_transcribe again with this project_id. Do not guess any moments from the title or length in the meantime.'}
        lock = _take_lock(folder)
        if lock is None:
            alive = True
        else:
            fresh = st is None
            if fresh:
                st = {'run': uuid.uuid4().hex, 'pieces': [], 'piece_ms': int(60000 * (piece_minutes or DEFAULT_PIECE_MINUTES)), 'replaces': existing,
                      'youtube': data['kind'] == 'youtube', 'started': time.time()}
            else:
                resumed = bool(st['pieces'])
                st['resumed_from'] = len(st['pieces']) + 1 if resumed else None
                if piece_minutes and int(60000 * piece_minutes) != st['piece_ms'] and st['pieces']:
                    args = {**args, '_note': 'The piece length of the first request (%s minutes) is kept so the finished pieces stay valid; use restart=true to change it.' % minutes(st['piece_ms'])}
            st.update(state='preparing', phase='Starting', error=None)
            _save(folder, st)
            thread = threading.Thread(target=_work, args=(clips, project_id, folder, rec, ctx, context, lock), name='clip-recognize-' + project_id[:8], daemon=True)
            _THREADS[str(folder)] = thread
            thread.start()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        now = _state(folder)
        if now is None or now['state'] in TERMINAL or not _alive(folder):
            break
        time.sleep(NAP)
    return _report(clips, project_id, folder, resumed=resumed, note=args.get('_note'))


def handle(clips, name, args, ctx, **context):
    raise ValueError('Unknown tool ' + name)
