"""Read-only, bounded discovery of an installed Camoufox runtime for source research. Starts nothing, installs nothing."""
import json
import os
from pathlib import Path
import subprocess
import time

SKIP = {'node_modules', '.git', '.hermes', '.cache', 'site-packages', '__pycache__', '.npm', '.cargo', '.rustup', 'snap'}


def camoufox_browsers():
    """Camoufox browser binaries in the standard cache/data folders."""
    home = Path.home(); found = []
    for base in (os.environ.get('XDG_CACHE_HOME'), str(home / '.cache'), os.environ.get('XDG_DATA_HOME'), str(home / '.local/share')):
        if not base: continue
        for name in ('camoufox/camoufox-bin', 'camoufox/camoufox'):
            path = Path(base) / name
            if path.is_file() and os.access(path, os.X_OK) and str(path) not in found: found.append(str(path))
    return found


def camoufox_pythons(limit=4):
    """PATH pythons and virtual environments up to four folders under home that can import camoufox."""
    candidates = []
    for folder in os.environ.get('PATH', '').split(os.pathsep):
        for name in ('python3', 'python'):
            path = Path(folder) / name
            if folder and path.is_file() and str(path) not in candidates: candidates.append(str(path))
    home = Path.home(); visited = 0; started = time.monotonic()
    for base, dirs, files in os.walk(home):
        visited += 1; depth = len(Path(base).relative_to(home).parts)
        dirs[:] = [d for d in dirs if d not in SKIP and depth < 4]
        if 'pyvenv.cfg' in files:
            dirs[:] = []
            if (Path(base) / 'bin/python').exists(): candidates.append(str(Path(base) / 'bin/python'))
        if visited > 60000 or len(candidates) > 60 or time.monotonic() - started > 6: break
    candidates.sort(key=lambda c: 'camoufox' not in c.lower())  # environments named for Camoufox first
    found = []
    for python in candidates:
        if len(found) >= limit: break
        try:
            r = subprocess.run([python, '-I', '-c', 'import importlib.util as u;print(u.find_spec("camoufox") is not None)'], capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip() == 'True': found.append(python)
        except (OSError, subprocess.TimeoutExpired): pass
    return found


def camoufox_runtime():
    """{'python':..., 'browser_executable':...} for the first match, or None. Nothing is launched."""
    pythons, browsers = camoufox_pythons(), camoufox_browsers()
    if pythons and browsers: return {'python_executable': pythons[0], 'browser_executable': browsers[0], 'other_pythons': pythons[1:]}
    return None


def short_model(model_id):
    """A model id that is a local Hugging Face cache path becomes its org/name form."""
    for part in str(model_id).split('/'):
        if part.startswith('models--'): return part.removeprefix('models--').replace('--', '/', 1)
    return model_id


def speech_servers(ports=(8000, 8001, 8080, 5000, 8880, 7860)):
    """Loopback OpenAI-style speech servers (a /v1/audio/speech route). Only read-only GET requests to this computer."""
    from urllib.request import build_opener, ProxyHandler
    opener = build_opener(ProxyHandler({})); found = []
    for port in ports:
        base = f'http://127.0.0.1:{port}'
        try:
            with opener.open(base + '/openapi.json', timeout=1.5) as response: paths = json.loads(response.read(2000000)).get('paths', {})
        except Exception: continue
        if '/v1/audio/speech' not in paths: continue
        models = []
        try:
            with opener.open(base + '/v1/models', timeout=1.5) as response: models = [short_model(m.get('id')) for m in json.loads(response.read(200000)).get('data', [])][:5]
        except Exception: pass
        found.append({'base_url': base, 'models': models, 'speech_route': base + '/v1/audio/speech',
                      'request_example': {'model': '<one of models>', 'input': '<one line, at most 60 words>', 'voice': 'default', 'response_format': 'wav', 'stream': False,
                                          'references': [{'audio_path': '<reference voice file the user gave you>', 'text': '<exactly what that reference says>'}]},
                      'notes': 'POST JSON, one request at a time, one take per line. The openapi file does not list the request fields; this example is the working shape. A reference is sent per request; do not upload it into the server voice store. If the server rejects a path, its error names the folder it allows; links are resolved by the server.'})
    return found
