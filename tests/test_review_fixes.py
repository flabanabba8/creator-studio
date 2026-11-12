"""Maintainer review asks across Creator Studio, plus the credential rule: the model cannot choose what runs or where data goes."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('creator_studio_review_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec); sys.modules[spec.name] = suite; spec.loader.exec_module(suite)
FORBIDDEN = {'python_executable', 'browser_executable', 'decoder_argv', 'command_argv', 'executable', 'endpoint', 'auth_header', 'use_api_key', 'allow_upload', 'argv'}


class Ctx:
    def __init__(self): self.schemas = {}
    def register_tool(self, name, **kw): self.schemas[name] = kw['schema']
    def register_skill(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith('register_'): return lambda *a, **k: None
        raise AttributeError(n)


class Tools(unittest.TestCase):
    def test_no_registered_tool_lets_the_model_name_a_program_a_command_an_endpoint_or_a_credential_switch(self):
        ctx = Ctx(); suite.register(ctx)
        bad = {n: FORBIDDEN & set(s['parameters']['properties']) for n, s in ctx.schemas.items() if FORBIDDEN & set(s['parameters']['properties'])}
        self.assertEqual(bad, {})

    def test_the_research_runtime_and_recognizer_settings_are_declared_for_the_owner(self):
        text = (ROOT / 'plugin.yaml').read_text()
        for key in ('camoufox_python', 'camoufox_browser', 'asr_command', 'asr_endpoint', 'asr_allow_upload', 'asr_decoder_command', 'asr_python', 'asr_provider'):
            self.assertIn(key + ':', text)


class Credentials(unittest.TestCase):
    def test_only_declared_secrets_are_read_and_only_through_hermes(self):
        from importlib import import_module
        from unittest import mock
        sr = import_module('creator_studio_review_test.common.speech_resources')
        agent = type(sys)('agent'); scope = type(sys)('agent.secret_scope'); calls = []
        scope.get_secret = lambda name: calls.append(name) or 'value-from-hermes'
        with mock.patch.dict(sys.modules, {'agent': agent, 'agent.secret_scope': scope}):
            self.assertEqual(sr.read_secret('OPENAI_API_KEY'), '')                 # not declared by this plugin: never asked for
            self.assertEqual(sr.read_secret('GEMINI_API_KEY'), 'value-from-hermes')
        self.assertEqual(calls, ['GEMINI_API_KEY'])
        text = (ROOT / 'plugin.yaml').read_text()
        self.assertIn('GEMINI_API_KEY', text); self.assertIn('CAPTION_STUDIO_ASR_KEY', text)

    def test_no_module_reads_a_credential_variable_from_the_environment_or_a_secret_file(self):
        offenders = []
        for f in ROOT.rglob('*.py'):
            if 'tests' in f.parts or '__pycache__' in f.parts: continue
            src = f.read_text()
            for needle in ("os.environ.get('GEMINI_API_KEY'", "os.environ['GEMINI_API_KEY'", "os.environ.get('OPENAI_API_KEY'", "application_default_credentials", "open('.env'", "read_text('.env'"):
                if needle in src: offenders.append((str(f.relative_to(ROOT)), needle))
        self.assertEqual(offenders, [])


class Subprocesses(unittest.TestCase):
    def test_every_subprocess_call_in_every_part_passes_an_env(self):
        missing = []
        for f in ROOT.rglob('*.py'):
            if 'tests' in f.parts or '__pycache__' in f.parts: continue
            for n in ast.walk(ast.parse(f.read_text())):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess' and n.func.attr in ('run', 'Popen', 'check_output', 'check_call', 'call'):
                    if not any(k.arg == 'env' or k.arg is None for k in n.keywords): missing.append('%s:%d' % (f.relative_to(ROOT), n.lineno))
        self.assertEqual(missing, [])


class OwnerSettingsReachEveryTool(unittest.TestCase):
    def test_research_tools_of_both_parts_read_the_owners_camoufox_setting(self):
        """Found by running the plugin through Hermes: the YouTube project tools were registered without the plugin context, so the owner's settings never reached them."""
        import json
        class Reader(Ctx):
            def __init__(self): super().__init__(); self.handlers = {}; self.asked = []
            def register_tool(self, name, **kw): self.schemas[name] = kw['schema']; self.handlers[name] = kw['handler']
            def get_config(self, key, default=None): self.asked.append(key); return default
        ctx = Reader(); suite.register(ctx)
        for name in ('youtube_research_fetch', 'podcast_research_fetch'):
            ctx.asked.clear()
            json.loads(ctx.handlers[name]({'project_id': 'x' * 32, 'url': 'https://example.com/'}))
            self.assertIn('camoufox_python', ctx.asked, name)


    def test_the_browser_reader_runs_isolated_so_the_local_camoufox_module_cannot_shadow_the_real_package(self):
        """Found through Hermes: common/camoufox.py shadowed the installed camoufox package whenever the reader script was started from common/."""
        for part in ('youtube_studio', 'podcast_studio'):
            text = (ROOT / part / 'media_project.py').read_text()
            self.assertIn("'-I',str(Path(__file__).resolve().parent.parent/'common'/'browser_research.py')", text, part)


class Release(unittest.TestCase):
    def test_no_compiled_binaries_or_bytecode_are_shipped(self):
        magic = (b'\x7fELF', b'MZ', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\x00asm')
        bad = []
        for f in ROOT.rglob('*'):
            if not f.is_file() or '.git' in f.parts or '__pycache__' in f.parts: continue
            if f.suffix in ('.pyc', '.pyo'): bad.append(str(f))
            elif f.read_bytes()[:4].startswith(magic): bad.append(str(f))
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
