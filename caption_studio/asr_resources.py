"""Caption Studio: find the speech recognizers this computer and this profile can use, interview the user, recommend, and remember the choice.

Nothing here uploads audio, starts a model, installs software or spends money. It looks at installed programs, loopback servers that answer,
which service keys exist (yes/no, never the value), the hardware, and the plugin's dated catalog of local and online recognizers, then ASKS the
user which one to use. The plugin never picks a recognizer for the user. Its knowledge is checked for staleness and the user may approve online
research to refresh it (freshness block below)."""
import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

LOOPBACK_PORTS = (8000, 8080, 9000, 2022, 8880)


def profile_path(root):
    return Path(root) / 'asr-profile' / 'profile.json'


def _opener():
    from urllib.request import HTTPRedirectHandler

    class Stop(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    return build_opener(ProxyHandler({}), Stop)


def _is_loopback_http(url):
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(url)
        return parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1') and not parts.username and not parts.password
    except ValueError:
        return False


def _server_models(url, timeout=1.0):
    if not _is_loopback_http(url):
        return None
    try:
        with _opener().open(url.rstrip('/') + '/v1/models', timeout=timeout) as response:
            data = json.loads(response.read(200000))
        return [m.get('id') for m in data.get('data', []) if isinstance(m, dict) and m.get('id')][:5]
    except Exception:
        return None


def find_servers(extra_urls=(), probe=True):
    """Loopback OpenAI-style speech servers that answer /v1/models. Only http on this computer is ever probed."""
    urls = [u for u in extra_urls if isinstance(u, str) and u]
    urls += ['http://127.0.0.1:%d' % p for p in LOOPBACK_PORTS]
    seen, found = set(), []
    for url in urls:
        key = url.rstrip('/').replace('//localhost', '//127.0.0.1')
        if key in seen or not _is_loopback_http(key):
            continue
        seen.add(key)
        models = _server_models(key) if probe else None
        if models is not None:
            found.append({'url': key, 'models': models})
    return found


# ---- knowledge freshness (generic block; identical in modlab/resources.py) ----
import datetime as _dt
MAX_AGE_DAYS = 30
UPDATE_FIELDS = ('free_tier', 'paid', 'needs', 'caveats', 'models', 'min_vram_gb', 'vram_basis', 'min_ram_gb', 'license', 'commercial', 'cloning', 'languages',
                 'status', 'notes', 'openai_endpoint', 'openai_style', 'install', 'platforms', 'how_to_run', 'smaller_variants', 'gpu_requirements', 'recommend',
                 'cost', 'price', 'limits', 'finding', 'rules', 'meaning', 'transparent_background', 'reference_image_edit', 'timestamps', 'subtitle_output', 'diarization',
                 'data_use', 'works_with_this_plugin', 'word_timestamps', 'rtf', 'free_minutes')


def _today(today=None):
    return today or _dt.date.today()


def _parse_day(text):
    try:
        return _dt.date.fromisoformat(str(text))
    except ValueError:
        return None


def freshness(verified, expiries=(), last_refresh=None, today=None, max_age_days=MAX_AGE_DAYS):
    """Is the shipped knowledge out of date? Returns {'verified', 'age_days', 'stale', 'reasons', 'coming_up', 'offer'}.
    Stale when older than max_age_days (counting the latest user-approved research refresh) or when a known deadline has passed."""
    now = _today(today)
    days = [d for d in (_parse_day(verified), _parse_day(last_refresh)) if d]
    newest = max(days) if days else None
    age = (now - newest).days if newest else None
    reasons, coming = [], []
    if age is None:
        reasons.append('the knowledge has no verification date')
    elif age > max_age_days:
        reasons.append('it was last checked %d days ago (checked %s; this plugin treats more than %d days as stale)' % (age, newest.isoformat(), max_age_days))
    for e in expiries:
        d = _parse_day(e.get('date'))
        if not d:
            continue
        if d <= now:
            if newest is None or d > newest:   # a deadline that passed before the last check is already reflected in what was checked
                reasons.append('a known deadline has passed (%s): %s' % (d.isoformat(), e.get('what')))
        elif (d - now).days <= max_age_days:
            coming.append('%s (%s): %s' % (d.isoformat(), '%d days away' % (d - now).days, e.get('what')))
    stale = bool(reasons)
    offer = None
    if stale or coming:
        offer = ('Some of this built-in knowledge may be out of date%s. Tell the user plainly what may have changed and ASK whether they want you to research '
                 'the current facts on the internet now, using the source links in the wiki (primary pages only). Do not research without their yes. If they say yes, '
                 'read the primary pages, then save only what you verified with the setup tool\'s knowledge_updates argument (each with its source link and date), '
                 'and tell the user what changed and what you could not verify. If they say no, carry on and say the numbers may be old.') % (' (' + '; '.join(reasons) + ')' if reasons else '')
    return {'verified': newest.isoformat() if newest else None, 'age_days': age, 'stale': stale, 'reasons': reasons, 'coming_up': coming, 'offer': offer}


def _updates_path(root):
    return profile_path(root).parent / 'knowledge-updates.json'


def load_updates(root):
    try:
        data = json.loads(_updates_path(root).read_text())
        return data if isinstance(data, dict) and isinstance(data.get('updates'), list) else {'updates': [], 'last_refresh': None}
    except (OSError, ValueError):
        return {'updates': [], 'last_refresh': None}


def save_updates(root, updates, known_ids, today=None):
    """Store research results the user approved. Each update: {id, field, value, source (https URL), date}. Nothing is trusted blindly:
    unknown ids/fields, non-https sources, future dates and oversized values are refused. Returns the stored file contents."""
    now = _today(today)
    if not isinstance(updates, list) or not 1 <= len(updates) <= 100:
        raise ValueError('knowledge_updates must be a list of 1 to 100 items')
    clean = []
    for u in updates:
        if not isinstance(u, dict) or set(u) - {'id', 'field', 'value', 'source', 'date', 'note'}:
            raise ValueError('each update needs id, field, value, source and date (note is optional)')
        if u.get('id') not in known_ids:
            raise ValueError('unknown id "%s"; use an id from the wiki tables' % u.get('id'))
        if u.get('field') not in UPDATE_FIELDS:
            raise ValueError('field "%s" cannot be updated; allowed: %s' % (u.get('field'), ', '.join(UPDATE_FIELDS)))
        value = u.get('value')
        if not (isinstance(value, (str, bool, int, float, list)) or value is None) or len(json.dumps(value)) > 1500:
            raise ValueError('value is too large or not plain data')
        src = u.get('source')
        if not isinstance(src, str) or not src.startswith('https://') or len(src) > 500:
            raise ValueError('every update needs the https source page it was verified on')
        day = _parse_day(u.get('date'))
        if not day or day > now:
            raise ValueError('every update needs the date you read the source (not in the future)')
        clean.append({'id': u['id'], 'field': u['field'], 'value': value, 'source': src, 'date': day.isoformat(), 'note': str(u.get('note', ''))[:300]})
    data = load_updates(root)
    data['updates'] = (data['updates'] + clean)[-500:]
    data['last_refresh'] = max(c['date'] for c in clean)
    path = _updates_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(path)
    return data


def apply_updates(rows, updates):
    """Overlay approved research on catalog rows (the shipped catalog file is never modified). Later updates win."""
    by = {r['id']: r for r in rows}
    for u in updates:
        r = by.get(u['id'])
        if r is not None:
            r[u['field']] = u['value']
            r.setdefault('updated_by_research', {})[u['field']] = {'source': u['source'], 'date': u['date']}
    return rows
# ---- end knowledge freshness ----

def minimal_env(extra=None):
    """Environment for every subprocess this module starts: no provider keys or other secrets from the host. PATH, HOME and LANG only."""
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': os.path.expanduser('~'), 'LANG': 'C'}
    env.update(extra or {})
    return env


def hardware(run=subprocess.run, platform=None, which=shutil.which, read_text=None):
    """Numbers only about THIS computer: operating system, CPU threads, RAM, GPUs with memory, Apple Silicon.
    No hostname, serial number or account detail. Reads local files and runs local programs; sends nothing."""
    platform = platform or sys.platform
    def _read(path):
        with open(path) as f:
            return f.read()
    read_text = read_text or _read
    hw = {'os': 'windows' if platform.startswith('win') else 'macos' if platform == 'darwin' else 'linux',
          'cpu_threads': os.cpu_count() or 1, 'ram_gb': None, 'gpus': [], 'apple_silicon': False}

    def out(argv, timeout=15):
        try:
            r = run(argv, capture_output=True, text=True, timeout=timeout, env=minimal_env())
            return r.stdout if r.returncode == 0 else ''
        except Exception:
            return ''
    try:
        if hw['os'] == 'linux':
            for line in read_text('/proc/meminfo').splitlines():
                if line.startswith('MemTotal:'):
                    hw['ram_gb'] = round(int(line.split()[1]) / 1024 / 1024, 1)
        elif hw['os'] == 'macos':
            mem = out(['sysctl', '-n', 'hw.memsize']).strip()
            hw['ram_gb'] = round(int(mem) / 1024 ** 3, 1) if mem.isdigit() else None
            brand = out(['sysctl', '-n', 'machdep.cpu.brand_string'])
            hw['apple_silicon'] = 'Apple' in brand
        else:
            mem = out(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory']).strip()
            hw['ram_gb'] = round(int(mem) / 1024 ** 3, 1) if mem.isdigit() else None
    except Exception:
        pass
    if which('nvidia-smi'):
        text = out([which('nvidia-smi'), '--query-gpu=name,memory.total,compute_cap', '--format=csv,noheader,nounits'])
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 3 and parts[1].isdigit():
                try:
                    cc = float(parts[2])
                except ValueError:
                    cc = None
                hw['gpus'].append({'vendor': 'nvidia', 'name': parts[0], 'vram_gb': round(int(parts[1]) / 1024, 1), 'compute_capability': cc})
        if not hw['gpus']:   # older drivers do not know compute_cap
            for line in out([which('nvidia-smi'), '--query-gpu=name,memory.total', '--format=csv,noheader,nounits']).splitlines():
                name, _, mem = line.rpartition(',')
                if name and mem.strip().isdigit():
                    hw['gpus'].append({'vendor': 'nvidia', 'name': name.strip(), 'vram_gb': round(int(mem) / 1024, 1), 'compute_capability': None})
    if which('rocm-smi') and not hw['gpus']:
        try:
            data = json.loads(out([which('rocm-smi'), '--showmeminfo', 'vram', '--json']) or '{}')
            for card, info in data.items():
                total = info.get('VRAM Total Memory (B)')
                if total and str(total).isdigit():
                    hw['gpus'].append({'vendor': 'amd', 'name': card, 'vram_gb': round(int(total) / 1024 ** 3, 1)})
        except Exception:
            pass
    return hw


def usable_gpu_memory(hw):
    """GB a model could use: the biggest single GPU's VRAM, or on Apple Silicon about 70 percent of unified memory."""
    best = max((g['vram_gb'] for g in hw['gpus']), default=0)
    if hw['apple_silicon'] and hw['ram_gb']:
        best = max(best, round(hw['ram_gb'] * 0.7, 1))
    return best




# ---------------------------------------------------------------- catalog
def load_catalog(path=None, update_root=None):
    path = Path(path) if path else Path(__file__).resolve().parent / 'asr_catalog.json'
    try:
        cat = json.loads(path.read_text())
    except (OSError, ValueError):
        return {'verified': None, 'remote': [], 'local': [], 'servers': [], 'subscriptions': [], 'expiries': []}
    if update_root is not None:
        data = load_updates(update_root)
        for key in ('remote', 'local', 'servers', 'subscriptions'):
            apply_updates(cat.get(key, []), data['updates'])
        cat['last_refresh'] = data.get('last_refresh')
    return cat


def known_ids():
    cat = load_catalog()
    return {r['id'] for k in ('remote', 'local', 'servers', 'subscriptions') for r in cat.get(k, [])}


def asr_freshness(root, today=None):
    cat = load_catalog(update_root=root)
    return freshness(cat.get('verified'), cat.get('expiries', []), cat.get('last_refresh'), today)


# ---------------------------------------------------------------- discovery
# Remote services this plugin can call through its HTTP recognizer (OpenAI-style multipart transcription with word timestamps).
# The key is the one declared plugin setting asr_api_key (secret CAPTION_STUDIO_ASR_KEY); the owner says which provider it belongs to in asr_provider.
CALLABLE_REMOTE = {'groq': {'endpoint': 'https://api.groq.com/openai/v1/audio/transcriptions', 'model': 'whisper-large-v3-turbo'}}
DECLARED_SECRETS = ('CAPTION_STUDIO_ASR_KEY', 'CAPTION_REPAIR_ASR_KEY')
PATH_TOOLS = ('whisper-cli', 'whisper', 'faster-whisper', 'whisper-server', 'sherpa-onnx-offline', 'moonshine')


def read_secret(name):
    """One of THIS plugin's declared secrets through Hermes's profile scope; '' when absent or undeclared. Never reads the environment or another service's key."""
    if name not in DECLARED_SECRETS:
        return ''
    try:
        from agent.secret_scope import get_secret
        value = get_secret(name)
    except Exception:
        return ''
    return value.strip() if isinstance(value, str) else ''


def find_transcription_servers(extra_urls=(), probe=True):
    urls = [u for u in extra_urls if isinstance(u, str) and u] + ['http://127.0.0.1:%d' % p for p in LOOPBACK_PORTS]
    seen, found = set(), []
    for url in urls:
        key = url.rstrip('/').replace('//localhost', '//127.0.0.1')
        if key in seen or not _is_loopback_http(key):
            continue
        seen.add(key)
        models = _server_models(key) if probe else None
        if models is not None:
            found.append({'url': key, 'models': models})
    return found


def _owner_command(settings):
    """The recognizer command the OWNER put in the plugin settings: a JSON array of strings, or nothing."""
    value = (settings or {}).get('asr_command')
    if isinstance(value, str) and value.strip():
        try: value = json.loads(value)
        except ValueError: return None
    if isinstance(value, list) and value and len(value) <= 80 and all(isinstance(x, str) and 0 < len(x) <= 4000 for x in value): return value
    return None


def _owner_endpoint(settings):
    """The HTTP recognizer the OWNER put in the plugin settings (asr_endpoint, with optional asr_fields, asr_auth_header, asr_auth_prefix, asr_allow_upload), as the recognizer dict the machinery runs, or None."""
    from urllib.parse import urlsplit
    s = settings or {}
    endpoint = s.get('asr_endpoint')
    if not isinstance(endpoint, str) or not endpoint.strip(): return None
    host = urlsplit(endpoint).hostname or ''
    loopback = host in ('localhost', '127.0.0.1', '::1')
    fields = s.get('asr_fields') or {}
    if isinstance(fields, str):
        try: fields = json.loads(fields)
        except ValueError: return None
    if not isinstance(fields, dict): return None
    rec = {'kind': 'http', 'endpoint': endpoint.strip(), 'language': s.get('asr_language', 'en'), 'fields': fields,
           'allow_upload': str(s.get('asr_allow_upload', 'false')).lower() == 'true',
           'use_api_key': (not loopback) or bool(s.get('asr_auth_header'))}
    if s.get('asr_auth_header'): rec['auth_header'] = s['asr_auth_header']
    if 'asr_auth_prefix' in s: rec['auth_prefix'] = s['asr_auth_prefix']
    return rec


TTS_MODEL = re.compile(r'(?i)tts|text-to-speech|kokoro|piper|orpheus|higgs|xtts|bark|vits|voxcpm|cosyvoice|f5-|chatterbox|zonos|outetts|maya1|soprano|dia-')


def _only_speech_synthesis(models):
    """A server whose every model is a speech SYNTHESIS model cannot transcribe, so it is not offered as a recognizer."""
    return bool(models) and all(isinstance(m, str) and TTS_MODEL.search(m) for m in models)


def discover(settings=None, secret_present=None, which=shutil.which, probe=True, local_commands=()):
    """Every recognizer route this computer can use or could use with a small step. Nothing is ranked or chosen."""
    s = settings or {}
    has = secret_present or (lambda name: bool(read_secret(name)))   # only this plugin's declared secrets
    routes = [{'id': 'import', 'kind': 'import', 'ready': True, 'free': True, 'local': True, 'detail': 'import word-timestamp JSON from a recognizer you already ran yourself; nothing is uploaded or run here'}]
    argv = _owner_command(s)
    if argv:
        routes.append({'id': 'configured:command', 'kind': 'command', 'ready': True, 'free': True, 'local': True, 'detail': 'the local recognizer command you set in the plugin settings (asr_command); it runs on this computer with a clean environment',
                       'recognizer': {'kind': 'command', 'argv': argv, 'model': str(s.get('asr_model', '')), 'language': str(s.get('asr_language', 'en')), 'output': str(s.get('asr_command_output', 'stdout'))}})
    endpoint = _owner_endpoint(s)
    if endpoint:
        from urllib.parse import urlsplit
        local = (urlsplit(endpoint['endpoint']).hostname or '') in ('localhost', '127.0.0.1', '::1')
        usable = local or endpoint['allow_upload']
        routes.append({'id': 'configured:endpoint', 'kind': 'endpoint', 'ready': usable, 'free': None, 'local': local, 'recognizer': endpoint,
                       'detail': ('the speech endpoint you set in the plugin settings (asr_endpoint)' + ('; it is on this computer' if local else '; audio is uploaded to it') +
                                  ('' if usable else '; the setting asr_allow_upload is not true, so it will not be used'))})
    for server in [x for x in find_transcription_servers([s.get('asr_server_url', '')], probe) if not _only_speech_synthesis(x.get('models'))]:
        routes.append({'id': 'server:' + server['url'], 'kind': 'server', 'ready': True, 'free': True, 'local': True, 'models': server['models'], 'detail': 'a server on this computer that answered; used through its OpenAI-style /v1/audio/transcriptions if it has one'})
    for cmd in local_commands:
        routes.append({'id': 'command:%s' % cmd['recognizer'].get('model', 'transformers'), 'kind': 'command', 'ready': True, 'free': True, 'local': True, 'recognizer': cmd['recognizer'], 'detail': 'a local Whisper model already cached on this computer, run by the bundled adapter' + ('. ' + cmd['device_reason'] if cmd.get('device_reason') else '')})
    for tool in PATH_TOOLS:
        path = which(tool)
        if path:
            routes.append({'id': 'program:' + tool, 'kind': 'program', 'tool': tool, 'ready': False, 'free': True, 'local': True, 'detail': 'installed (%s) but it needs a small wrapper that prints word-timestamp JSON before this plugin can drive it; the setup tool explains how' % tool})
    key_present = has('CAPTION_STUDIO_ASR_KEY') or has('CAPTION_REPAIR_ASR_KEY')
    provider = str(s.get('asr_provider', '') or '').strip().lower()
    if key_present and provider in CALLABLE_REMOTE:
        routes.append({'id': 'remote:' + provider, 'kind': 'remote', 'service': provider, 'ready': True, 'free': False, 'local': False,
                       'detail': 'an online service with the key you set in the plugin settings (asr_api_key, provider %s); audio is uploaded to it' % provider})
    elif key_present:
        routes.append({'id': 'remote:configured-endpoint', 'kind': 'remote', 'service': 'configured', 'ready': True, 'free': None, 'local': False,
                       'detail': 'the speech endpoint and key you configured for this plugin (asr_api_key); audio is uploaded to it. Set asr_provider to groq if the key is a Groq key.'})
    return {'routes': routes, 'advice': advice(routes)}


def advice(routes):
    ready = [r for r in routes if r['ready']]
    if len(ready) <= 1:
        return ('Only the import route is available right now. To transcribe here, start a local OpenAI-style speech server (Speaches or whisper.cpp), cache a Whisper model, '
                'or put an API key in the plugin setting asr_api_key (and set asr_provider to groq for a Groq key). Nothing was uploaded or started.')
    return 'Found %d usable route(s): %s. The user chooses which one to use.' % (len(ready), ', '.join(r['id'] for r in ready))


def filter_routes(report, settings):
    if str((settings or {}).get('asr_allow_upload', 'true')).lower() == 'false':
        return {**report, 'routes': [r for r in report['routes'] if r.get('local')]}
    return report


def ready_options(report):
    out = []
    for r in report['routes']:
        if not r['ready']:
            continue
        where = 'stays on this computer' if r.get('local') else 'audio is uploaded to an online service'
        cost = 'free' if r.get('free') else 'may cost money' if r.get('free') is False else 'cost unknown'
        out.append({'id': r['id'], 'what': r['detail'], 'where_audio_goes': where, 'cost': cost})
    return sorted(out, key=lambda o: o['id'])


def chosen(report, profile):
    route = (profile or {}).get('route')
    for r in report['routes']:
        if route and r['ready'] and r['id'] == route:
            return r
    return None


def recognizer_for(route, settings=None):
    """Turn the route the user chose into the recognizer dict the existing machinery runs. Word timestamps are required for captions."""
    s = settings or {}
    kind = route['kind']
    if kind == 'server':
        model = (route.get('models') or [s.get('asr_model', 'whisper-1')])[0]
        return {'kind': 'http', 'endpoint': route['id'].split(':', 1)[1] + '/v1/audio/transcriptions', 'language': s.get('language', 'en'),
                'fields': {'model': model, 'response_format': 'verbose_json', 'timestamp_granularities[]': 'word'}}
    if kind in ('command', 'endpoint'):
        return dict(route['recognizer'])
    if kind == 'remote' and route.get('service') in CALLABLE_REMOTE:
        c = CALLABLE_REMOTE[route['service']]
        return {'kind': 'http', 'endpoint': c['endpoint'], 'allow_upload': True, 'use_api_key': True, 'language': s.get('language', 'en'),
                'fields': {'model': c['model'], 'response_format': 'verbose_json', 'timestamp_granularities[]': 'word'}}
    if kind == 'remote' and route.get('service') == 'configured':
        raise ValueError('Give the endpoint of your configured speech service in the recognizer (kind http, allow_upload true, use_api_key true); the setup only recorded that you chose it.')
    raise ValueError('The chosen route "%s" cannot be run directly; use the import route with word-timestamp JSON.' % route['id'])


# ---------------------------------------------------------------- recommendations
def recommend(hw, catalog=None, allow_upload=True, minutes=None, subscriptions=()):
    cat = catalog or load_catalog()
    gpu = usable_gpu_memory(hw)
    ram = hw.get('ram_gb') or 0
    local = []
    for m in cat.get('local', []):
        if m.get('recommend') is False:
            continue
        need, cpu_ok, need_ram = m.get('min_vram_gb'), m.get('cpu_ok'), m.get('min_ram_gb') or 0
        if need is not None and gpu >= need and ram >= need_ram:
            fit = 'fits your GPU (%.0f GB available, needs about %s GB)' % (gpu, need)
        elif cpu_ok and ram >= need_ram:
            fit = 'runs on CPU (%s GB RAM here, needs about %s GB)' % (ram, need_ram or 'little')
        else:
            continue
        servers = [{'name': sv['name'], 'install': sv.get('install'), 'openai_style_endpoint': sv.get('openai_style'), 'source': sv.get('source')} for sv in cat.get('servers', []) if m['id'] in sv.get('models', [])]
        local.append({'id': m['id'], 'name': m['name'], 'fit': fit, 'tier': m.get('tier', 9), 'word_timestamps': m.get('word_timestamps'), 'diarization': m.get('diarization'), 'license': m.get('license'),
                      'commercial': m.get('commercial'), 'languages': m.get('languages'), 'vram_basis': m.get('vram_basis'), 'how_to_run': m.get('how_to_run'), 'servers_that_can_run_it': servers,
                      'works_with_this_plugin': 'yes, through a speech server it can call (ask the user before installing anything)' if any(str(x['openai_style_endpoint']).startswith('yes') for x in servers) else 'needs a small wrapper or server first (ask the user before installing anything)',
                      'notes': m.get('notes'), 'status': m.get('status'), 'source': m['source'], 'verified': m.get('verified')})
    local.sort(key=lambda m: (m['tier'], m['name']))
    remote = []
    if allow_upload:
        for r in cat.get('remote', []):
            row = {k: r.get(k) for k in ('id', 'name', 'models', 'free_tier', 'paid', 'timestamps', 'subtitle_output', 'diarization', 'limits', 'data_use', 'works_with_this_plugin', 'source', 'verified')}
            fm = r.get('free_minutes')
            if minutes and fm:
                row['free_allowance_covers_your_audio'] = 'yes (about %s minutes; %s)' % (fm['minutes'], fm['basis']) if fm['minutes'] >= minutes else 'no (about %s minutes; %s)' % (fm['minutes'], fm['basis'])
            remote.append(row)
    subs = [s for s in cat.get('subscriptions', []) if not subscriptions or s['id'] in subscriptions]
    return {'hardware': hw, 'local_that_fit_this_computer': local[:10], 'online_services': remote, 'subscriptions': subs, 'catalog_verified': cat.get('verified'),
            'for_subtitles': 'Subtitles need word-level timestamps. Best documented: WhisperX (forced alignment), faster-whisper, Parakeet/Canary, Qwen3-ASR with its aligner; whisper.cpp word timestamps are experimental; Ollama gives none.',
            'note': 'Suggestions only; the user chooses. Prices, free allowances and subscription terms were read on the dates shown and change often: re-check the source link before quoting. Nothing was downloaded, installed or uploaded.'}


# ---------------------------------------------------------------- interview / profile
SUBS = ('chatgpt-pro-business', 'claude-max-team', 'google-ai-pro', 'huggingface-pro', 'none')
QUESTIONS = [
    {'key': 'languages', 'ask': 'Which language(s) is the audio in?', 'type': 'text'},
    {'key': 'minutes', 'ask': 'Roughly how many minutes of audio do you want captioned (per project, and per month)?', 'type': 'number'},
    {'key': 'allow_upload', 'ask': 'Is it OK to upload the audio to an online service? (A local recognizer sends nothing anywhere.)', 'type': 'yes/no'},
    {'key': 'priority', 'ask': 'What matters most: the most accurate word timing, speed, or lowest cost?', 'type': 'choice', 'choices': ['accurate timing', 'speed', 'lowest cost']},
    {'key': 'speakers', 'ask': 'Do you need speaker labels (who said what)?', 'type': 'yes/no'},
    {'key': 'subscriptions', 'ask': 'Which paid plans or credits do you have that could include API access? (never paste a key into chat)', 'type': 'list', 'choices': list(SUBS)},
    {'key': 'has', 'ask': 'What do you already have: a speech server on this computer, a cached Whisper model, an API key in this plugin\'s settings, a recognizer you already ran?', 'type': 'text'},
]


def save_profile(root, answers, route_ids=None, local_ids=()):
    if not isinstance(answers, dict):
        raise ValueError('answers must be an object with the interview keys')
    out = {'answered': True}
    langs = answers.get('languages')
    if not isinstance(langs, str) or not langs.strip() or len(langs) > 200:
        raise ValueError('languages: name the language(s) of the audio')
    out['languages'] = langs.strip()
    minutes = answers.get('minutes')
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 < minutes <= 1_000_000:
        raise ValueError('minutes must be a number above 0')
    out['minutes'] = float(minutes)
    for key in ('allow_upload', 'speakers'):
        if type(answers.get(key)) is not bool:
            raise ValueError('%s must be true or false' % key)
        out[key] = answers[key]
    if answers.get('priority') not in ('accurate timing', 'speed', 'lowest cost'):
        raise ValueError('priority must be: accurate timing, speed or lowest cost')
    out['priority'] = answers['priority']
    subs = answers.get('subscriptions', [])
    if not isinstance(subs, list) or any(x not in SUBS for x in subs):
        raise ValueError('subscriptions must list only: ' + ', '.join(SUBS))
    out['subscriptions'] = sorted(set(subs))
    has = answers.get('has', '')
    if not isinstance(has, str) or len(has) > 400:
        raise ValueError('has: up to 400 characters')
    out['has'] = has.strip()
    route = answers.get('route')
    if route is not None:
        if not isinstance(route, str) or len(route) > 300:
            raise ValueError('route must be the id of one of the options you were shown')
        if route_ids is not None and route not in route_ids:
            raise ValueError('route "%s" is not one of the available options: %s' % (route, ', '.join(sorted(route_ids)) or 'none'))
        if route and not out['allow_upload'] and not (route == 'import' or route.startswith('server:') or route.startswith('command:') or route == 'configured:command' or route in local_ids):
            raise ValueError('You said audio must not be uploaded, so choose a route that stays on this computer')
    out['route'] = route or None
    path = profile_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, indent=2))
    tmp.chmod(0o600)
    tmp.replace(path)
    return out


def load_profile(root):
    try:
        data = json.loads(profile_path(root).read_text())
        return data if isinstance(data, dict) and data.get('answered') else None
    except (OSError, ValueError):
        return None


def apply_profile(settings, profile):
    s = dict(settings or {})
    if profile and not profile['allow_upload']:
        s['asr_allow_upload'] = 'false'
    if profile:
        s['language'] = (profile['languages'].split(',')[0].strip().lower()[:8] or 'en')
    return s


def gaps(report, profile):
    notes = []
    word_ok = [r for r in report['routes'] if r['ready'] and r['kind'] in ('server', 'command', 'remote', 'endpoint')]
    if not word_ok:
        notes.append('No route that can transcribe here is ready, only import. ' + report['advice'])
    if profile['speakers']:
        notes.append('You want speaker labels: the HTTP recognizer returns words only; WhisperX (pyannote) or an online service with diarization is needed, then use the import route.')
    if not profile['allow_upload']:
        online = [r['id'] for r in report['routes'] if not r.get('local')]
        if online:
            notes.append('Online routes exist (%s) but you said audio must not be uploaded, so they will not be used.' % ', '.join(online))
    return notes


def interview(settings, root, report, answers=None, hw=None):
    options = ready_options(filter_routes(report, settings))
    if answers is not None:
        if options and not (isinstance(answers, dict) and answers.get('route')):
            raise ValueError('Ask the user which of these routes to use and pass it as route (nothing was saved): ' + ', '.join(o['id'] for o in options))
        profile = save_profile(root, answers, {o['id'] for o in options}, {r['id'] for r in report['routes'] if r.get('local')})
        return {'state': 'saved', 'profile': profile, 'you_chose': profile['route'], 'gaps': gaps(report, profile), 'found': report['routes']}
    existing = load_profile(root)
    cat = load_catalog(update_root=root)
    state = 'interview_needed' if not existing or not existing.get('route') else 'answered'
    questions = list(QUESTIONS) + [{'key': 'route', 'ask': 'Which of these do you want to use? I will use only the one you pick.', 'type': 'choice', 'choices': options}]
    return {'state': state, 'profile': existing, 'found': report['routes'], 'options': options, 'advice': report['advice'],
            'recommendations': recommend(hw or hardware(), cat, allow_upload=not existing or existing.get('allow_upload', True), minutes=(existing or {}).get('minutes'), subscriptions=(existing or {}).get('subscriptions', ())),
            'knowledge_freshness': asr_freshness(root), 'questions': questions,
            'instructions_for_agent': 'Do not choose a speech recognizer for the user. Show them the options found on this computer in plain words (what each is, whether the audio stays here or is uploaded, whether it is free). Then show `recommendations` as suggestions, not a decision: local models that fit this computer, online services with their free allowance, price, timestamp support, data-use terms, source link and verified date, and which of their paid plans (if any) include API access (say plainly when a plan does not, e.g. chat plans are separate from API billing). Quote prices only with source and date and tell the user to re-check the link. Read knowledge_freshness: if stale or something is coming up, tell the user what may be old and ask whether they want you to research the current facts online; never research without their yes. Ask which one they want, together with the other questions, in one short message. Do not ask for or accept key values in chat. Then call the setup tool again with answers = {languages, minutes, allow_upload, priority, speakers, subscriptions, has, route}. Do not start transcription until the answers are saved.'}


def apply_setup(root, report, settings, answers=None, knowledge_updates=None, hw=None):
    saved = None
    if knowledge_updates is not None:
        saved = len(save_updates(root, knowledge_updates, known_ids())['updates'])
    out = interview(settings, root, report, answers, hw)
    if saved is not None:
        out['knowledge_updates_saved'] = saved
    return out
