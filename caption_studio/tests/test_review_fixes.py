"""Maintainer review asks for Caption Studio: the model cannot choose a command, endpoint, auth, upload consent or decoder."""
import ast
import importlib.util
import json
import socket
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cap_review_pkg', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
pkg = importlib.util.module_from_spec(spec); sys.modules[spec.name] = pkg; spec.loader.exec_module(pkg)
rec = importlib.import_module('cap_review_pkg.recognizers')
A = importlib.import_module('cap_review_pkg.asr_resources')
FORBIDDEN = {'decoder_argv', 'command_argv', 'executable', 'endpoint', 'auth_header', 'use_api_key', 'allow_upload'}


class Ctx:
    def __init__(self, cfg=None): self.cfg = cfg or {}
    def get_config(self, key, default=None): return self.cfg.get(key, default)


class Schemas(unittest.TestCase):
    def test_no_tool_has_a_decoder_command_or_endpoint_argument(self):
        for name, (_d, props, _r) in pkg.TOOLS.items():
            self.assertFalse(FORBIDDEN & set(props), name)

    def test_the_recognizer_description_names_only_the_allowed_kinds(self):
        text = pkg.TOOLS['captions_generate'][1]['recognizer']['description']
        for kind in ('chosen', 'configured', 'import', 'host'):
            self.assertIn(kind, text)
        self.assertNotIn('kind=command', text); self.assertNotIn('kind=http', text)


class ModelPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.data = Path(self.tmp.name); self.addCleanup(self.tmp.cleanup)
        storage = types.ModuleType('plugins.plugin_storage'); storage.plugin_data_dir = lambda n: (self.data / n).mkdir(parents=True, exist_ok=True) or self.data / n
        p = mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage}); p.start(); self.addCleanup(p.stop)

    def call(self, name, args, cfg=None):
        return json.loads(pkg.invoke(name, args, Ctx(cfg)))

    def test_command_and_http_recognizers_from_the_model_are_refused(self):
        for rec_ in ({'kind': 'command', 'argv': ['/bin/sh', '-c', 'id']}, {'kind': 'http', 'endpoint': 'https://evil.example/x', 'allow_upload': True, 'use_api_key': True}):
            out = self.call('captions_generate', {'media_path': '/x.wav', 'recognizer': rec_})
            self.assertIn('plugin settings', out['error']); self.assertIn('never tool arguments', out['error'])

    def test_a_decoder_command_from_the_model_is_refused(self):
        out = self.call('captions_generate', {'media_path': '/x.wav', 'recognizer': {'kind': 'import', 'transcript_path': '/t.json'}, 'decoder_argv': ['/bin/sh']})
        self.assertIn('asr_decoder_command', out['error'])

    def test_configured_asks_the_owner_to_set_it_and_the_interview_comes_first(self):
        out = self.call('captions_generate', {'media_path': '/x.wav', 'recognizer': {'kind': 'configured'}})
        self.assertEqual(out['state'], 'interview_needed')           # no profile yet: the user is asked, nothing runs

    def test_configured_recognizer_is_built_from_owner_settings_only(self):
        self.assertEqual(pkg.configured_recognizer({'asr_command': '["tool", "{audio}", "{output}"]', 'asr_model': 'm'})['argv'], ['tool', '{audio}', '{output}'])
        http = pkg.configured_recognizer({'asr_endpoint': 'https://api.example.org/v1/audio/transcriptions', 'asr_allow_upload': 'true', 'asr_fields': '{"model": "x"}', 'asr_auth_header': 'X-Key'})
        self.assertTrue(http['allow_upload']); self.assertEqual(http['fields'], {'model': 'x'}); self.assertEqual(http['auth_header'], 'X-Key')
        self.assertFalse(pkg.configured_recognizer({'asr_endpoint': 'https://a.example/x'})['allow_upload'])        # consent is off unless the owner turns it on
        with self.assertRaisesRegex(ValueError, 'No recognizer is configured'):
            pkg.configured_recognizer({})
        with self.assertRaisesRegex(ValueError, 'must be JSON'):
            pkg.configured_recognizer({'asr_command': 'not json'})

    def test_owner_settings_are_read_from_config_not_args(self):
        self.assertEqual(pkg.owner_settings(Ctx({'asr_command': '["x"]', 'unrelated': 'y'})), {'asr_command': '["x"]'})


class Endpoints(unittest.TestCase):
    def test_online_recognizers_must_resolve_to_public_addresses(self):
        for ip in ('10.0.0.5', '192.168.1.9', '169.254.169.254', '172.16.0.1', '0.0.0.0', '224.0.0.1', '127.0.0.2'):
            with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', (ip, 443))]):
                with self.assertRaisesRegex(ValueError, 'private or reserved'):
                    rec.refuse_private_host('x.example')
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]):
            rec.refuse_private_host('x.example')

    def test_recognize_applies_the_check_before_any_upload(self):
        with tempfile.TemporaryDirectory() as d:
            audio = Path(d) / 'a.wav'; audio.write_bytes(b'RIFF')
            with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('169.254.169.254', 443))]), mock.patch.object(rec, 'build_opener', side_effect=AssertionError('uploaded')):
                with self.assertRaisesRegex(ValueError, 'private or reserved'):
                    rec.recognize({'kind': 'http', 'endpoint': 'https://metadata.example/x', 'allow_upload': True}, audio, Path(d), lambda *a, **k: None)

    def test_loopback_servers_are_still_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            audio = Path(d) / 'a.wav'; audio.write_bytes(b'RIFF')
            with mock.patch.object(rec, 'refuse_private_host', side_effect=AssertionError('checked')):
                try: rec.recognize({'kind': 'http', 'endpoint': 'http://127.0.0.1:1/v1/audio/transcriptions'}, audio, Path(d), lambda *a, **k: None)
                except RuntimeError: pass                       # nothing is listening: a connection failure, not the private-host refusal


class Interpreters(unittest.TestCase):
    def test_no_interpreter_is_found_by_walking_the_home_folder(self):
        src = (ROOT / 'recognizers.py').read_text()
        self.assertNotIn('os.walk', src); self.assertNotIn('pyvenv.cfg', src)


class CleanEnvironment(unittest.TestCase):
    def test_every_subprocess_call_passes_an_env(self):
        missing = []
        for f in ROOT.rglob('*.py'):
            if 'tests' in f.parts or '__pycache__' in f.parts: continue
            for n in ast.walk(ast.parse(f.read_text())):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess' and n.func.attr in ('run', 'Popen', 'check_output', 'check_call', 'call'):
                    if not any(k.arg == 'env' or k.arg is None for k in n.keywords): missing.append('%s:%d' % (f.relative_to(ROOT), n.lineno))
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
