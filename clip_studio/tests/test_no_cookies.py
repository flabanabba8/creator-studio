"""Clip Studio never reads a browser profile: no cookie option reaches yt-dlp, and the setting no longer exists (catalog rule 11)."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('creator_studio_nocookie_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_nocookie_test import clip_studio  # noqa: E402
from creator_studio_nocookie_test.clip_studio import source as S  # noqa: E402


class NoBrowserCookies(unittest.TestCase):
    def test_settings_cannot_turn_cookies_on(self):
        seen = []

        def fake_run(args, **kwargs):
            seen.append(list(args))
            return subprocess.CompletedProcess(args, 0, stdout=b'{}', stderr=b'')

        yt = S.YouTube({'clip_ytdlp': sys.executable, 'clip_cookies_browser': 'firefox'})
        with mock.patch.object(S.subprocess, 'run', fake_run), mock.patch.object(S.shutil, 'which', lambda name: '/usr/bin/' + name):
            yt._run(['--skip-download', '-J', '--', 'https://www.youtube.com/watch?v=aaaaaaaaaaa'])
        self.assertTrue(seen)
        for args in seen:
            self.assertFalse([a for a in args if 'cookie' in a.lower()], args)

    def test_owner_keys_have_no_cookie_setting(self):
        self.assertEqual(clip_studio.OWNER_KEYS, ('clip_ytdlp',))

    def test_manifest_has_no_cookie_setting(self):
        self.assertNotIn('cookies', (ROOT / 'plugin.yaml').read_text().lower())

    def test_sign_in_message_points_to_a_local_file(self):
        message = S.YouTube({})._explain('ERROR: [youtube] x: Sign in to confirm you are not a bot')
        self.assertIn('media_path', message)
        self.assertNotIn('clip_cookies_browser', message)


if __name__ == '__main__':
    unittest.main()
