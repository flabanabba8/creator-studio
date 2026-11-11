"""register() must expose exactly the tools, hooks and skills the manifest declares."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('creator_studio_register_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)


class FakeCtx:
    def __init__(self):
        self.tools, self.skills, self.hooks, self.other = [], [], [], []

    def register_tool(self, name, **kw):
        self.tools.append(name)
        assert kw['schema']['name'] == name and callable(kw['handler'])

    def register_skill(self, name, path, **kw):
        self.skills.append(name)
        assert Path(path).is_file(), path

    def register_hook(self, *a, **kw):
        self.hooks.append(a)

    def __getattr__(self, name):
        if name.startswith('register_'):
            return lambda *a, **kw: self.other.append(name)
        raise AttributeError(name)


def manifest_tools():
    out, active = [], False
    for line in (ROOT / 'plugin.yaml').read_text().splitlines():
        if line.startswith('provides_tools:'):
            active = True
        elif active and line.startswith('  - '):
            out.append(line[4:].strip())
        elif active:
            break
    return out


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeCtx()
        suite.register(self.ctx)

    def test_tools_match_manifest_exactly(self):
        declared = manifest_tools()
        self.assertEqual(len(declared), 62)
        self.assertEqual(len(set(self.ctx.tools)), len(self.ctx.tools), 'a tool name was registered twice')
        self.assertEqual(sorted(self.ctx.tools), sorted(declared))

    def test_no_hooks_middleware_commands_or_other_surfaces(self):
        self.assertEqual(self.ctx.hooks, [])
        self.assertEqual(self.ctx.other, [])
        text = (ROOT / 'plugin.yaml').read_text()
        for key in ('provides_hooks', 'provides_middleware', 'provides_commands'):
            self.assertNotIn(key, text)

    def test_four_skills_registered_with_files(self):
        self.assertEqual(sorted(self.ctx.skills), ['create-podcast', 'create-tutorial', 'create-youtube-video', 'repair-captions'])

    def test_tool_reference_lists_exactly_the_registered_tools(self):
        import re
        listed = re.findall(r'^## (\w+)$', (ROOT / 'llmwiki' / 'tools.md').read_text(), re.M)
        self.assertEqual(sorted(listed), sorted(self.ctx.tools))

    def test_each_part_uses_its_own_data_folder(self):
        names = {p.STORAGE_NAMESPACE for p in suite.PARTS}
        self.assertEqual(names, {'creator-studio-youtube', 'creator-studio-podcast', 'creator-studio-captions', 'creator-studio-tutorial'})


if __name__ == '__main__':
    unittest.main()
