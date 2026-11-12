"""Read-only, bounded discovery of an installed Camoufox runtime for source research. Starts nothing, installs nothing."""
import json
import os
from pathlib import Path
import subprocess
import time

SKIP = {'node_modules', '.git', '.hermes', '.cache', 'site-packages', '__pycache__', '.npm', '.cargo', '.rustup', 'snap'}


try:
    from ..common.camoufox import camoufox_browsers, camoufox_pythons, camoufox_runtime
except (ImportError, ValueError):   # this module is also loaded on its own (tests)
    import importlib.util as _u
    _spec = _u.spec_from_file_location('creator_studio_camoufox', Path(__file__).resolve().parents[1] / 'common' / 'camoufox.py')
    _mod = _u.module_from_spec(_spec); _spec.loader.exec_module(_mod)
    camoufox_browsers, camoufox_pythons, camoufox_runtime = _mod.camoufox_browsers, _mod.camoufox_pythons, _mod.camoufox_runtime


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
