"""Higgs TTS3 narration placed on an existing video's measured timeline."""
import hashlib
import json
import ipaddress
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

from .core import Director, number, probe, run, write_json, clean_export_name
from .loopback import LoopbackHTTPHandler
from .reference_paths import resolve_reference
from . import host_speech
from . import gemini_speech

CREDIT = "This audio was created with Boson AI's Higgs Audio — https://www.boson.ai/higgs-audio"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def loopback_host(host):
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except (TypeError, ValueError): return False


def endpoint(base):
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or not loopback_host(parsed.hostname) or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Configure a compatible loopback speech server origin, for example http://localhost:8000')
    return base.rstrip('/') + '/v1/audio/speech'


def synthesize(base, model, text, voice, reference_audio='', reference_text='', *, extra_fields=None, higgs_defaults=True):
    url = endpoint(base)
    payload = {'model': model, 'input': text, 'voice': voice, 'response_format': 'wav'}
    if higgs_defaults:payload.update(stream=False,temperature=.8,top_k=50,top_p=.8,max_new_tokens=2048)
    if isinstance(extra_fields,str):extra_fields=json.loads(extra_fields)
    if extra_fields is not None:
        if not isinstance(extra_fields,dict) or set(extra_fields)&set(payload) or len(json.dumps(extra_fields,allow_nan=False))>4000:raise ValueError('Extra speech fields must be bounded JSON and cannot replace model/input/voice/audio format')
        payload.update(extra_fields)
    if reference_audio:
        # The user's local server owns reference access; no voice files are bundled
        # or read by this client. Server-side allowlisting remains in force.
        payload['references'] = [{'audio_path': reference_audio, 'text': reference_text}]
    opener = build_opener(ProxyHandler({}), NoRedirect(), LoopbackHTTPHandler())
    try:
        with opener.open(Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}), timeout=120) as response:
            data = response.read(32 * 1024 * 1024 + 1)
    except HTTPError as exc:
        raise RuntimeError(f'Local speech service returned HTTP {exc.code}; no automatic retry was made') from None
    except (URLError, TimeoutError):
        raise RuntimeError('Selected local speech service unavailable or timed out; inspect its status before explicitly retrying') from None
    if len(data) > 32 * 1024 * 1024 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise RuntimeError('Selected local speech service did not return a bounded WAV file')
    return data


def validate_cues(cues, duration):
    if not isinstance(cues, list) or not 1 <= len(cues) <= 20:
        raise ValueError('Provide 1–20 timestamped narration cues')
    previous_end = 0
    total_text = 0
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) != {'start', 'end', 'text'}:
            raise ValueError('Each cue needs exactly start, end and text')
        start = number(cue['start'], 0, duration, 'cue start')
        end = number(cue['end'], .1, duration, 'cue end')
        if start < previous_end or end <= start:
            raise ValueError('Cues must be ordered, non-overlapping and have positive duration')
        text = cue['text']
        if not isinstance(text, str) or not text.strip() or len(text) > 300 or len(text.split()) > 60:
            raise ValueError('Each narration cue must contain 1–300 characters and at most60 words')
        if '<|reset|>' in text or any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise ValueError('Unsupported control text in narration')
        total_text += len(text)
        previous_end = end
    if total_text > 4000:
        raise ValueError('Narration script exceeds4000 characters')


def srt_time(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def narrate(root, job_id, export_name, cues, settings, dispatch=None):
    export_name = clean_export_name(export_name)
    director = Director(root)
    timeline = director.timeline(job_id, export_name)
    validate_cues(cues, timeline['seconds'])
    folder = director.job(job_id)
    backend=settings.get('narration_backend','gemini')
    if backend not in ('higgs','local_http','host','gemini'):raise ValueError('Select Gemini 3.8 speech, a configured compatible local speech service or an available host speech tool')
    gem_model=settings.get('gemini_model') or gemini_speech.DEFAULT_MODEL
    gem_voice=settings.get('gemini_voice') or gemini_speech.DEFAULT_VOICE
    gem_ledger=folder/'gemini-usage.json'
    if backend=='gemini':
        gem_project=gemini_speech.project_id(settings.get('gemini_project',''))
        try:gem_max=float(settings.get('gemini_max_usd') or gemini_speech.DEFAULT_MAX_USD)
        except (TypeError,ValueError):raise ValueError('Set a Gemini speech budget between 0 and 100 USD') from None
    base = settings.get('speech_http_url','') if backend=='local_http' else settings.get('higgs_url', 'http://localhost:8000')
    selected=host_speech.binding(settings) if backend=='host' else None
    if backend not in ('host','gemini'):endpoint(base)
    model = settings.get('speech_http_model','') if backend=='local_http' else settings.get('higgs_model', 'bosonai/higgs-tts-3-4b')
    if backend=='local_http' and not model:raise ValueError('Choose the model actually served by the selected local speech endpoint')
    voice = gem_voice if backend=='gemini' else settings.get('host_tts_voice','default') if backend=='host' else settings.get('speech_http_voice','default') if backend=='local_http' else settings.get('higgs_voice', 'default')
    reference_audio = settings.get('speech_http_reference_audio','') if backend=='local_http' else settings.get('higgs_reference_audio', '')
    reference_text = settings.get('speech_http_reference_text','') if backend=='local_http' else settings.get('higgs_reference_text', '')
    reference_digest = ''
    if reference_audio and backend not in ('host','gemini'):
        reference = resolve_reference(reference_audio, root)
        if reference.suffix.lower() not in ('.wav', '.flac', '.mp3') or not reference.is_file() or reference.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('Choose a local WAV/FLAC/MP3 voice reference of at most20 MiB')
        if not any(s['codec_type'] == 'audio' for s in probe(reference)['streams']):
            raise ValueError('Voice reference has no audio stream')
        reference_audio = str(reference)
        reference_digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    cache = folder / 'narration-cache'
    cache.mkdir(exist_ok=True, mode=0o700)
    rendered, problems, credits = [], [], []
    for i, cue in enumerate(cues):
        revision=settings.get('speech_http_revision','') if backend=='local_http' else settings.get('higgs_revision','')
        identity=['gemini-speech-v1',gem_model,voice,cue['text']] if backend=='gemini' else [base, model, revision, voice, cue['text'], reference_audio, reference_digest, reference_text] if backend!='host' else ['host-speech-v1',selected,voice,cue['text']]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        audio = cache / (key + '.wav')
        reused = audio.exists()
        if not reused:
            if backend=='host':
                attempt=audio.with_suffix('.attempt.json');nonce=str(settings.get('host_tts_retry_nonce',''))
                if attempt.exists():
                    previous=json.loads(attempt.read_text())
                    if previous.get('state') in ('pending','unknown','received') and previous.get('retry_nonce')==nonce:raise RuntimeError('A previous host speech attempt has no usable cache; review it and explicitly change host_tts_retry_nonce before retrying this failed cue')
                def observe(state,metadata):write_json(attempt,{'state':state,'retry_nonce':nonce,'metadata':metadata})
                data,metadata=host_speech.synthesize(settings,dispatch,cue['text'],voice,root,observe)
                write_json(audio.with_suffix('.metadata.json'),metadata)
            elif backend=='gemini':data=gemini_speech.synthesize(cue['text'],voice,gem_model,project=gem_project,ledger_path=gem_ledger,max_usd=gem_max)
            elif backend=='local_http':data=synthesize(base,model,cue['text'],voice,reference_audio,reference_text,extra_fields=settings.get('speech_http_fields'),higgs_defaults=False)
            else:data = synthesize(base, model, cue['text'], voice, reference_audio, reference_text)
            temporary = cache / (uuid.uuid4().hex + '.tmp')
            temporary.write_bytes(data)
            temporary.chmod(0o600)
            temporary.replace(audio)
        measured = float(probe(audio)['format']['duration'])
        if backend=='host' and audio.with_suffix('.metadata.json').exists():
            credit=json.loads(audio.with_suffix('.metadata.json').read_text()).get('credit','')
            if credit and credit not in credits:credits.append(credit)
        available = cue['end'] - cue['start']
        rendered.append({'cue': i, 'start': cue['start'], 'end': cue['end'], 'text': cue['text'],
                         'measured_seconds': measured, 'cache_reused': reused, 'path': str(audio)})
        if measured > available + .02:
            problems.append({'cue': i, 'available_seconds': available, 'measured_seconds': measured,
                             'correction': 'Shorten this cue or allocate more time; speech was not cut or sped up.'})
    if problems:
        return {'state': 'needs_timing_revision', 'problems': problems,
                'cues': [{k: v for k, v in r.items() if k != 'path'} for r in rendered]}
    video = folder / export_name
    info = probe(video)
    has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
    output = folder / ('narrated-' + uuid.uuid4().hex + '.mp4')
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(video)]
    filters, inputs = [], []
    for i, clip in enumerate(rendered, 1):
        command += ['-i', clip['path']]
        delay = round(clip['start'] * 1000)
        filters.append(f'[{i}:a]aresample=48000,adelay={delay}:all=1[n{i}]')
        inputs.append(f'[n{i}]')
    filters.append(''.join(inputs) + f'amix=inputs={len(inputs)}:normalize=0,apad,atrim=duration={timeline["seconds"]}[narration]')
    if has_audio:
        # Duck the application under narration and retain it between spoken cues.
        filters += ['[narration]asplit=2[voice][key]',
                    '[0:a][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[app]',
                    '[app][voice]amix=inputs=2:normalize=0,alimiter=limit=0.95:latency=1[a]']
    else:
        filters += ['[narration]alimiter=limit=0.95:latency=1[a]']
    command += ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[a]', '-map_metadata', '-1',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-t', str(timeline['seconds']), '-movflags', '+faststart', str(output)]
    try:
        run(command, timeout=240)
        final = probe(output)
        if float(final['format']['duration']) >= 90:
            raise RuntimeError('Narrated export exceeded the contest duration limit')
        run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(output), '-f', 'null', '-'], timeout=120)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    captions = output.with_suffix('.srt')
    caption_lines = []
    for i, clip in enumerate(rendered, 1):
        text = re.sub(r'<\|[^|]+\|>', '', clip['text']).strip().replace('-->', '→')
        caption_lines.append(f'{i}\n{srt_time(clip["start"])} --> {srt_time(clip["start"] + clip["measured_seconds"])}\n{text}\n')
    captions.write_text('\n'.join(caption_lines), encoding='utf-8')
    result = {'state': 'complete', 'path': str(output), 'captions': str(captions), 'caption_timing': 'segment-level, measured audio duration; not word alignment',
              'seconds': float(final['format']['duration']), 'credit': CREDIT if backend=='higgs' else 'Speech by Google Gemini 3.8 Flash TTS (voice '+gem_voice+')' if backend=='gemini' else '\n'.join(credits) if backend=='host' else str(settings.get('speech_http_credit','')),
              'cues': [{k: v for k, v in r.items() if k != 'path'} for r in rendered]}
    if backend=='gemini':result['usage']=gemini_speech.usage_summary(gem_ledger);result['voice']=gem_voice;result['model']=gem_model
    write_json(output.with_suffix('.json'), result)
    output.with_suffix('.credit.txt').write_text(result['credit'] + '\n', encoding='utf-8')
    return result
