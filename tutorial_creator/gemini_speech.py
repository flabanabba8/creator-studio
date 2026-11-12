"""Gemini 3.8 Flash TTS narration through Vertex with a Google sign-in held by Hermes (common/google_signin.py).

One request per cue, no retries of the speech POST, a persistent spend ledger with a guard, and
no project or credential value ever returned, logged or written to evidence."""
import base64
import json
import re
import time

MODELS = ('gemini-3.8-flash-tts', 'gemini-3.8-flash-lite-tts')
DEFAULT_MODEL = 'gemini-3.8-flash-tts'
DEFAULT_VOICE = 'Achird'
DEFAULT_MAX_USD = 0.50
INPUT_USD = 1 / 1_000_000   # conservative full list rates; promotional credits are not assumed
OUTPUT_USD = 18 / 1_000_000
MIN_ESTIMATE_USD = 0.002
SAFETY = 2.0  # margin over the published-rate estimate


def estimate_usd(text):
    """Cost reserved for one cue, from the text length and the published per-token prices.
    Audio output is 25 tokens per second; speech is assumed slow (1.5 words per second) plus 2 s, then doubled."""
    seconds = len(text.split()) / 1.5 + 2
    tokens_in = len(text) / 2 + 50
    usd = (tokens_in * INPUT_USD + seconds * 25 * OUTPUT_USD) * SAFETY
    return max(usd, MIN_ESTIMATE_USD)
MAX_RESPONSE = 32 * 1024 * 1024
# name: (gender, measured median pitch Hz, trait). Measured on this project's own calibration take.
VOICES = {
    'Achernar': ('female', 196.7, 'soft'),
    'Achird': ('male', 145.5, 'friendly'),
    'Algenib': ('male', 138.7, 'gravelly'),
    'Algieba': ('male', 120.0, 'smooth'),
    'Alnilam': ('male', 150.9, 'firm'),
    'Aoede': ('female', 181.8, 'breezy'),
    'Autonoe': ('female', 198.3, 'bright'),
    'Callirrhoe': ('female', 179.1, 'easy-going'),
    'Charon': ('male', 127.3, 'informative'),
    'Despina': ('female', 164.4, 'smooth'),
    'Enceladus': ('male', 129.7, 'breathy'),
    'Erinome': ('female', 206.9, 'clear'),
    'Fenrir': ('male', 136.4, 'excitable'),
    'Gacrux': ('female', 158.9, 'mature'),
    'Iapetus': ('male', 121.2, 'clear'),
    'Kore': ('female', 167.8, 'firm'),
    'Laomedeia': ('female', 169.0, 'upbeat'),
    'Leda': ('female', 195.1, 'youthful'),
    'Orus': ('male', 136.4, 'firm'),
    'Puck': ('male', 146.3, 'upbeat'),
    'Pulcherrima': ('female', 128.3, 'forward'),
    'Rasalgethi': ('male', 175.2, 'informative'),
    'Sadachbia': ('male', 134.8, 'lively'),
    'Sadaltager': ('male', 121.2, 'knowledgeable'),
    'Schedar': ('male', 142.0, 'even'),
    'Sulafat': ('female', 190.5, 'warm'),
    'Umbriel': ('male', 143.7, 'easy-going'),
    'Vindemiatrix': ('female', 150.9, 'gentle'),
    'Zephyr': ('female', 196.7, 'bright'),
    'Zubenelgenubi': ('male', 117.6, 'casual'),
}


class SpeechError(RuntimeError):
    pass


def voice_options():
    return [{'voice': name, 'gender': g, 'median_pitch_hz': hz, 'trait': t} for name, (g, hz, t) in VOICES.items()]


def _signin():
    """The suite's shared sign-in module (also loadable when this part is imported on its own, as its tests do)."""
    try:
        from ..common import google_signin
        return google_signin
    except (ImportError, ValueError):
        import importlib.util, sys
        from pathlib import Path
        name = 'creator_studio_google_signin'
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'common' / 'google_signin.py')
            module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
        return sys.modules[name]


def project_id(configured=''):
    """The Google Cloud project from the plugin setting gemini_project. Never printed."""
    value = configured.strip() if isinstance(configured, str) else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value or ''):
        raise ValueError('No Google Cloud project is configured for Gemini speech (set the plugin setting gemini_project)')
    return value


def availability():
    """Setup facts for the model, without contacting Google or revealing the project."""
    google_signin = _signin()
    result = {'route': 'gemini', 'models': list(MODELS), 'default_model': DEFAULT_MODEL, 'default_voice': DEFAULT_VOICE,
              'max_usd_default': DEFAULT_MAX_USD, 'voices': voice_options()}
    result['project_configured'] = google_signin.configured_project() is not None
    result['hermes_sign_in_supported'] = google_signin.helper_available()
    result['sign_in'] = 'Hermes holds the Google sign-in; if narration reports "not signed in", run: ' + google_signin.SIGN_IN
    return result


def usage_summary(path):
    if not path.exists(): return {'requests': 0, 'spent_or_reserved_usd': 0.0}
    try: rows = json.loads(path.read_text())
    except (OSError, ValueError): return {'available': False}
    return {'requests': len(rows), 'received': sum(r.get('status') == 'received' for r in rows),
            'unknown_requests': sum(r.get('status') in ('pending', 'unknown') for r in rows),
            'input_tokens': sum(r.get('input_tokens', 0) for r in rows), 'output_tokens': sum(r.get('output_tokens', 0) for r in rows),
            'spent_or_reserved_usd': round(sum(r.get('reserved_or_actual_usd', 0) for r in rows), 4)}


def _save(path, ledger):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(ledger, indent=2)); temporary.chmod(0o600)
    temporary.replace(path)


def synthesize(text, voice, model, *, project, ledger_path, max_usd=DEFAULT_MAX_USD, transport=None):
    """Return WAV bytes for one cue. Hermes signs the request; `transport` exists for tests with a mocked network."""
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) // 2 > 2000:
        raise ValueError('Gemini speech text must contain 1-2000 UTF-16 code units')
    if voice not in VOICES:
        raise ValueError('Choose a listed Gemini voice name, for example ' + DEFAULT_VOICE)
    if model not in MODELS:
        raise ValueError('Gemini speech requires gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts')
    if isinstance(max_usd, bool) or not isinstance(max_usd, (int, float)) or not 0 < max_usd <= 100:
        raise ValueError('Set a Gemini speech budget between 0 and 100 USD')
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    estimate = estimate_usd(text); spent = sum(row['reserved_or_actual_usd'] for row in ledger)
    if spent + estimate > max_usd:
        raise SpeechError('The spending guard: %d earlier cues were recorded with %.4f USD charged or reserved for them; the total spent or reserved is %.4f USD, and this cue was refused without being sent (estimated %.4f USD; projected total %.4f USD exceeds the %.4f USD cap).'  % (sum(r.get('status') == 'received' for r in ledger), sum(r.get('reserved_or_actual_usd',0) for r in ledger if r.get('status') == 'received'), spent, estimate, spent+estimate, max_usd))
    url = f'https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent'
    body = {'contents': [{'role': 'user', 'parts': [{'text': text}]}],
            'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'voice': voice}}}}
    headers = {'x-goog-user-project': project}
    row = {'started': time.time(), 'status': 'pending', 'model': model, 'voice': voice, 'reserved_or_actual_usd': estimate}
    ledger.append(row); _save(ledger_path, ledger)
    try:
        if transport is None:
            google_signin = _signin()
            status_code, content = google_signin.post(url, body, project)
            class _Response:
                pass
            response = _Response(); response.status_code = status_code; response.content = content
            response.json = lambda: json.loads(content)
        else:
            response = transport(url, headers, body)
    except Exception as exc:
        google_signin = _signin()
        if isinstance(exc, google_signin.NotSent):
            ledger.remove(row); _save(ledger_path, ledger)
            raise SpeechError(str(exc)) from None
        row['status'] = 'unknown'; _save(ledger_path, ledger)
        raise SpeechError('Gemini transport failure; the billed outcome is unknown; no retry was made') from None
    if response.status_code != 200:
        row['status'] = 'rejected' if 400 <= response.status_code < 500 else 'unknown'
        try: message = str(response.json().get('error', {}).get('message', ''))[:600]
        except Exception: message = ''
        message = message.replace(project, '<project>')
        row['error_message'] = message
        if row['status'] == 'rejected': row['reserved_or_actual_usd'] = 0
        _save(ledger_path, ledger)
        raise SpeechError(f'Gemini speech HTTP {response.status_code}: {message}; no retry was made')
    try:
        if len(response.content) > MAX_RESPONSE: raise ValueError('response too large')
        result = response.json(); meta = result.get('usageMetadata', {})
        tin, tout = meta.get('promptTokenCount'), meta.get('candidatesTokenCount')
        if type(tin) is int and type(tout) is int and tin >= 0 and tout >= 0:
            row.update(input_tokens=tin, output_tokens=tout, reserved_or_actual_usd=tin * INPUT_USD + tout * OUTPUT_USD)
        row['status'] = 'received'; _save(ledger_path, ledger)
        candidates = result.get('candidates', [])
        if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP': raise ValueError('incomplete response')
        parts = [p['inlineData'] for p in candidates[0].get('content', {}).get('parts', []) if 'inlineData' in p]
        if len(parts) != 1: raise ValueError('missing audio')
        audio = base64.b64decode(parts[0]['data'], validate=True)
        if audio[:4] != b'RIFF' or audio[8:12] != b'WAVE': raise ValueError('expected WAV')
    except Exception:
        row['status'] = 'audio_invalid'; _save(ledger_path, ledger)
        raise SpeechError('Gemini returned incomplete or invalid audio; no retry was made') from None
    return audio


def _find_audio(node):
    if isinstance(node, dict):
        if node.get('type') == 'audio' and isinstance(node.get('data'), str): return node
        for value in node.values():
            found = _find_audio(value)
            if found: return found
    elif isinstance(node, list):
        for value in node:
            found = _find_audio(value)
            if found: return found
    return None


def synthesize_developer(text, voice, model, *, api_key, ledger_path, max_usd=DEFAULT_MAX_USD, post=None):
    """Gemini speech with the user's own Gemini API key (no Cloud project, no Google sign-in).

    Same request shape as pagecast-director's hosted Gemini route (Interactions API). Same spend guard and
    ledger as the Vertex route, one request per cue, no retries. The key is never written anywhere.
    NOT live-tested in this plugin (no key was spent); `post` lets tests supply a fake network."""
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) // 2 > 2000:
        raise ValueError('Gemini speech text must contain 1-2000 UTF-16 code units')
    if voice not in VOICES: raise ValueError('Choose a listed Gemini voice name, for example ' + DEFAULT_VOICE)
    if model not in MODELS: raise ValueError('Gemini speech requires gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts')
    if not isinstance(api_key, str) or not api_key.strip() or any(not 32 < ord(c) < 127 for c in api_key.strip()):
        raise SpeechError('Set the Gemini API key (gemini_api_key) in this plugin\'s Hermes settings; nothing was sent')
    if isinstance(max_usd, bool) or not isinstance(max_usd, (int, float)) or not 0 < max_usd <= 100:
        raise ValueError('Set a Gemini speech budget between 0 and 100 USD')
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    estimate = estimate_usd(text); spent = sum(row['reserved_or_actual_usd'] for row in ledger)
    if spent + estimate > max_usd:
        raise SpeechError('The spending guard: %.4f USD spent or reserved so far; this cue (estimated %.4f USD) was refused without being sent (cap %.4f USD).' % (spent, estimate, max_usd))
    body = {'model': model, 'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': text}]}],
            'response_format': {'type': 'audio', 'mime_type': 'audio/wav', 'sample_rate': 24000},
            'generation_config': {'speech_config': [{'voice': voice}]}}
    row = {'started': time.time(), 'status': 'pending', 'model': model, 'voice': voice, 'route': 'developer', 'reserved_or_actual_usd': estimate}
    ledger.append(row); _save(ledger_path, ledger)
    if post is None:
        import http.client
        def post(url_host, path, headers, payload):
            conn = http.client.HTTPSConnection(url_host, timeout=90)
            try:
                conn.request('POST', path, body=json.dumps(payload).encode(), headers={**headers, 'Content-Type': 'application/json'})
                resp = conn.getresponse()
                return resp.status, resp.read(MAX_RESPONSE + 1)
            finally:
                conn.close()
    try:
        status, content = post('generativelanguage.googleapis.com', '/v1beta/interactions', {'x-goog-api-key': api_key.strip()}, body)
    except Exception:
        row['status'] = 'unknown'; _save(ledger_path, ledger)
        raise SpeechError('Gemini transport failure; the billed outcome is unknown; no retry was made') from None
    if status != 200:
        row['status'] = 'rejected' if 400 <= status < 500 else 'unknown'
        if row['status'] == 'rejected': row['reserved_or_actual_usd'] = 0
        _save(ledger_path, ledger)
        raise SpeechError('Gemini speech HTTP %d (%s); no retry was made' % (status, {401: 'key rejected', 403: 'access denied', 404: 'model or voice not found', 429: 'quota reached'}.get(status, 'request failed')))
    row['status'] = 'received'; _save(ledger_path, ledger)
    try:
        if len(content) > MAX_RESPONSE: raise ValueError('response too large')
        audio = base64.b64decode(_find_audio(json.loads(content))['data'], validate=True)
        if audio[:4] != b'RIFF' or audio[8:12] != b'WAVE': raise ValueError('expected WAV')
    except Exception:
        row['status'] = 'audio_invalid'; _save(ledger_path, ledger)
        raise SpeechError('Gemini returned no valid WAV audio; no retry was made') from None
    return audio
