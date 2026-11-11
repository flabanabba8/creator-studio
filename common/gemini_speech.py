"""Gemini 3.8 Flash TTS on Vertex AI as a speech route: a Google sign-in held by Hermes (see google_signin.py),
one request per part, no retries, a spend ledger with a guard. Additive: the local-server route is unchanged.
The Google Cloud project id comes from the plugin setting gemini_project and is never returned, logged or
written into a result. No credential file of any other tool is read."""
import base64
import json
import time
from pathlib import Path

MODEL = 'gemini-3.8-flash-tts'
MODELS = (MODEL, 'gemini-3.8-flash-lite-tts')
MAX_WORDS = 100
# Conservative full list rates (USD per token); promotional credits are not assumed.
INPUT_USD = 1 / 1_000_000
OUTPUT_USD = 18 / 1_000_000
RESERVATION = 8192 * INPUT_USD + 16384 * OUTPUT_USD  # old flat reservation: now only the upper bound of one estimate
MIN_ESTIMATE_USD = 0.002
SAFETY = 2.0  # margin over the published-rate estimate


def estimate_usd(text):
    """Cost reserved for one request, from the text length and the published per-token prices.
    Audio output is 25 tokens per second; speech is assumed slow (1.5 words per second) plus 2 s, then doubled."""
    words = len(text.split())
    seconds = words / 1.5 + 2
    tokens_in = len(text) / 2 + 50
    usd = (tokens_in * INPUT_USD + seconds * 25 * OUTPUT_USD) * SAFETY
    return min(max(usd, MIN_ESTIMATE_USD), RESERVATION)


def guard_message(estimate, spent, max_usd, ledger=()):
    return ('Spend guard: %d earlier cues were recorded with %.4f USD charged or reserved for them; the total spent or reserved is %.4f USD, and this cue was refused without being sent (estimated %.4f USD; projected total %.4f USD exceeds the %.4f USD cap).'  % (sum(r.get('status') == 'received' for r in ledger), sum(r.get('reserved_or_actual_usd',0) for r in ledger if r.get('status') == 'received'), spent, estimate, spent+estimate, max_usd))
VOICES = {'Achernar': ('female', 'soft'), 'Achird': ('male', 'friendly'), 'Algenib': ('male', 'gravelly'), 'Algieba': ('male', 'smooth'),
          'Alnilam': ('male', 'firm'), 'Aoede': ('female', 'breezy'), 'Autonoe': ('female', 'bright'), 'Callirrhoe': ('female', 'easy-going'),
          'Charon': ('male', 'informative'), 'Despina': ('female', 'smooth'), 'Enceladus': ('male', 'breathy'), 'Erinome': ('female', 'clear'),
          'Fenrir': ('male', 'excitable'), 'Gacrux': ('female', 'mature'), 'Iapetus': ('male', 'clear'), 'Kore': ('female', 'firm'),
          'Laomedeia': ('female', 'upbeat'), 'Leda': ('female', 'youthful'), 'Orus': ('male', 'firm'), 'Puck': ('male', 'upbeat'),
          'Pulcherrima': ('female', 'forward'), 'Rasalgethi': ('male', 'informative'), 'Sadachbia': ('male', 'lively'),
          'Sadaltager': ('male', 'knowledgeable'), 'Schedar': ('male', 'even'), 'Sulafat': ('female', 'warm'), 'Umbriel': ('male', 'easy-going'),
          'Vindemiatrix': ('female', 'gentle'), 'Zephyr': ('female', 'bright'), 'Zubenelgenubi': ('male', 'casual')}


class GeminiSpeechError(RuntimeError):
    pass


def project():
    """The Google Cloud project from the plugin setting gemini_project; None when not configured."""
    from . import google_signin
    return google_signin.configured_project()


def transport(url, headers, body):
    """Send one signed request through Hermes; returns (status, content). Raises google_signin.NotSent when nothing left this computer."""
    from . import google_signin
    return google_signin.post(url, body, headers['x-goog-user-project'])


def available():
    """Read-only check used by the setup tool: no request is sent and no project id or credential is returned."""
    from . import google_signin
    if not google_signin.helper_available():
        return {'available': False, 'reason': 'This Hermes version has no plugin sign-in support (0.22.3 or later is needed).'}
    if project() is None:
        return {'available': False, 'reason': 'No Google Cloud project is set (plugin setting gemini_project). ' + google_signin.SETUP}
    return {'available': True, 'model': MODEL, 'billing': 'Cloud billing applies (cents per short lesson); the plugin keeps a spend guard and a usage ledger.',
            'sign_in': 'Hermes holds the Google sign-in; if a request reports "not signed in", run: ' + google_signin.SIGN_IN,
            'voices': [{'name': n, 'gender': g, 'trait': t} for n, (g, t) in VOICES.items()],
            'use': 'youtube_narrate with engine "gemini" and a voice name (the voice is the same on every request)'}


def check_voice(voice):
    if voice not in VOICES: raise ValueError('Choose one of the named Gemini voices: ' + ', '.join(VOICES))
    return voice


def usage_summary(ledger_path):
    path = Path(ledger_path)
    rows = json.loads(path.read_text()) if path.exists() else []
    return {'requests': len(rows), 'received': sum(r.get('status') == 'received' for r in rows),
            'input_tokens': sum(r.get('input_tokens', 0) for r in rows), 'output_tokens': sum(r.get('output_tokens', 0) for r in rows),
            'estimated_usd': round(sum(r.get('reserved_or_actual_usd', 0) for r in rows), 4)}


def synthesize(text, voice, ledger_path, max_usd=0.5, model=MODEL):
    """One speech request; returns WAV bytes. Never retried: a failed or unknown request keeps its ledger row."""
    check_voice(voice)
    if model not in MODELS: raise ValueError('Use a Gemini 3.8 TTS model')
    if not isinstance(text, str) or not text.strip() or len(text.split()) > MAX_WORDS: raise ValueError('Each spoken part must be 1 to %d words' % MAX_WORDS)
    if isinstance(max_usd, bool) or not isinstance(max_usd, (int, float)) or not 0 < max_usd <= 100: raise ValueError('Set a spend guard between 0 and 100 USD')
    pid = project()
    if pid is None: raise GeminiSpeechError('No Google Cloud project is set (plugin setting gemini_project); no request was sent')
    path = Path(ledger_path)
    ledger = json.loads(path.read_text()) if path.exists() else []
    estimate = estimate_usd(text); spent = sum(r['reserved_or_actual_usd'] for r in ledger)
    if spent + estimate > max_usd: raise GeminiSpeechError(guard_message(estimate, spent, max_usd, ledger))
    url = 'https://aiplatform.googleapis.com/v1/projects/%s/locations/global/publishers/google/models/%s:generateContent' % (pid, model)
    body = {'contents': [{'role': 'user', 'parts': [{'text': text}]}], 'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'voice': voice}}}}
    row = {'started': time.time(), 'status': 'pending', 'voice': voice, 'reserved_or_actual_usd': estimate}
    ledger.append(row); _save(path, ledger)
    try:
        status, content = transport(url, {'x-goog-user-project': pid}, body)
    except Exception as exc:
        from . import google_signin
        if isinstance(exc, google_signin.NotSent):
            ledger.remove(row); _save(path, ledger)
            raise GeminiSpeechError(str(exc)) from None
        row['status'] = 'unknown'; _save(path, ledger)
        raise GeminiSpeechError('The speech request did not complete; whether it was billed is unknown; no retry was made') from None
    if status != 200:
        row['status'] = 'rejected' if 400 <= status < 500 else 'unknown'
        try: message = str(json.loads(content).get('error', {}).get('message', ''))[:600]
        except Exception: message = ''
        message = message.replace(pid, '<project>')
        row['error_message'] = message
        if row['status'] == 'rejected': row['reserved_or_actual_usd'] = 0
        _save(path, ledger)
        raise GeminiSpeechError('Gemini speech returned HTTP %d: %s; no retry was made' % (status, message))
    try:
        result = json.loads(content); meta = result.get('usageMetadata', {})
        tin, tout = meta.get('promptTokenCount'), meta.get('candidatesTokenCount')
        if type(tin) is int and type(tout) is int: row.update(input_tokens=tin, output_tokens=tout, reserved_or_actual_usd=tin * INPUT_USD + tout * OUTPUT_USD)
        row['status'] = 'received'; _save(path, ledger)
        cands = result.get('candidates', [])
        if len(cands) != 1 or cands[0].get('finishReason') != 'STOP': raise ValueError('incomplete')
        audio = [p['inlineData'] for p in cands[0].get('content', {}).get('parts', []) if 'inlineData' in p]
        if len(audio) != 1: raise ValueError('missing audio')
        wav = base64.b64decode(audio[0]['data'], validate=True)
        if wav[:4] != b'RIFF' or wav[8:12] != b'WAVE': raise ValueError('not WAV')
    except Exception:
        row['status'] = 'audio_invalid'; _save(path, ledger)
        raise GeminiSpeechError('Gemini speech returned incomplete or invalid audio; no retry was made') from None
    return wav


def _save(path, ledger):
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(ledger, indent=2)); tmp.chmod(0o600); tmp.replace(path)
