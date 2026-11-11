"""Gemini 3.8 Flash TTS narration through Vertex with the user's own Application Default Credentials.

One request per cue, no retries of the speech POST, a persistent spend ledger with a guard, and
no project or credential value ever returned, logged or written to evidence."""
import base64
import json
import re
import subprocess
import time

MODELS = ('gemini-3.8-flash-tts', 'gemini-3.8-flash-lite-tts')
DEFAULT_MODEL = 'gemini-3.8-flash-tts'
DEFAULT_VOICE = 'Achird'
DEFAULT_MAX_USD = 0.50
INPUT_USD = 1 / 1_000_000   # conservative full list rates; promotional credits are not assumed
OUTPUT_USD = 18 / 1_000_000
RESERVATION = 2048 * INPUT_USD + 4096 * OUTPUT_USD
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


def project_id(configured=''):
    """The Google Cloud project from plugin settings or the machine's own gcloud default. Never printed."""
    value = configured.strip() if isinstance(configured, str) else ''
    if not value:
        try:
            value = subprocess.run(['gcloud', 'config', 'get-value', 'project'], capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            value = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value or ''):
        raise ValueError('No Google Cloud project is configured for Gemini speech (set one in gcloud or plugin settings)')
    return value


def availability():
    """Setup facts for the model, without contacting Google or revealing the project."""
    result = {'route': 'gemini', 'models': list(MODELS), 'default_model': DEFAULT_MODEL, 'default_voice': DEFAULT_VOICE,
              'max_usd_default': DEFAULT_MAX_USD, 'voices': voice_options()}
    try: project_id(); result['project_configured'] = True
    except ValueError: result['project_configured'] = False
    try:
        import google.auth  # noqa: F401
        result['adc_library'] = True
    except ImportError:
        result['adc_library'] = False
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


def synthesize(text, voice, model, *, project, ledger_path, max_usd=DEFAULT_MAX_USD, transport=None, credentials=None):
    """Return WAV bytes for one cue. `transport` and `credentials` exist for tests with a mocked network."""
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) // 2 > 2000:
        raise ValueError('Gemini speech text must contain 1-2000 UTF-16 code units')
    if voice not in VOICES:
        raise ValueError('Choose a listed Gemini voice name, for example ' + DEFAULT_VOICE)
    if model not in MODELS:
        raise ValueError('Gemini speech requires gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts')
    if isinstance(max_usd, bool) or not isinstance(max_usd, (int, float)) or not 0 < max_usd <= 100:
        raise ValueError('Set a Gemini speech budget between 0 and 100 USD')
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    if sum(row['reserved_or_actual_usd'] for row in ledger) + RESERVATION > max_usd:
        raise SpeechError('Gemini spending guard reached; no speech request sent')
    try:
        if credentials is None:
            import google.auth
            from google.auth.transport.requests import Request
            credentials = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])[0]
            if not credentials.valid: credentials.refresh(Request())
        token = credentials.token
    except Exception:
        raise SpeechError('Google credentials could not be refreshed before sending; no speech request sent') from None
    url = f'https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent'
    body = {'contents': [{'role': 'user', 'parts': [{'text': text}]}],
            'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'voice': voice}}}}
    headers = {'Authorization': 'Bearer ' + token, 'x-goog-user-project': project}
    row = {'started': time.time(), 'status': 'pending', 'model': model, 'voice': voice, 'reserved_or_actual_usd': RESERVATION}
    ledger.append(row); _save(ledger_path, ledger)
    try:
        if transport is None:
            import requests
            transport = lambda u, h, b: requests.post(u, headers=h, json=b, timeout=(60, 240), allow_redirects=False)
        response = transport(url, headers, body)
    except Exception:
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
