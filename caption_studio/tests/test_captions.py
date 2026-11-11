import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('caption_core', Path(__file__).parents[1] / 'core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.srt'
        self.source.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:11,000 --> 00:00:12,000\nWorld\n')
        self.plugin = core.Captions(self.root / 'output')
        self.fingerprint = self.plugin.inspect(str(self.source))['fingerprint']

    def tearDown(self):
        self.tmp.cleanup()

    def test_replacement_while_reading_is_rejected(self):
        replacement = self.root/'replacement.srt'; replacement.write_text('1\n00:00:00,000 --> 00:00:01,000\nChanged\n')
        original = core.os.fstat; calls = 0
        def replace(fd):
            nonlocal calls
            calls += 1
            value = original(fd)
            if calls == 2: os.replace(replacement, self.source)
            return value
        with patch.object(core.os, 'fstat', side_effect=replace):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                self.plugin.inspect(str(self.source))

    def test_offset_preserves_input(self):
        before = self.source.read_bytes()
        result = self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 1000, 'target_ms': 1500}])
        self.assertIn('00:00:01,500 --> 00:00:02,500', Path(result['output_path']).read_text())
        self.assertEqual(self.source.read_bytes(), before)

    def test_new_caption_output_is_private_under_permissive_umask(self):
        previous = os.umask(0)
        try:
            result = self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 0, 'target_ms': 0}])
            self.assertEqual(Path(result['output_path']).stat().st_mode & 0o777, 0o600)
        finally:
            os.umask(previous)

    def test_linear_drift(self):
        result = self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 1000, 'target_ms': 2000}, {'source_ms': 11000, 'target_ms': 12000 + 1000}])
        output = Path(result['output_path']).read_text()
        self.assertIn('00:00:02,000 --> 00:00:03,100', output)
        self.assertIn('00:00:13,000 --> 00:00:14,100', output)

    def test_bad_anchors_negative_and_stale_input(self):
        with self.assertRaisesRegex(ValueError, 'negative'):
            self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 5000, 'target_ms': 0}])
        with self.assertRaisesRegex(ValueError, 'supported'):
            self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 0, 'target_ms': core.MAX_TIMESTAMP_MS + 1}])
        with self.assertRaisesRegex(ValueError, 'increasing'):
            self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 1, 'target_ms': 1}, {'source_ms': 1, 'target_ms': 2}])
        self.source.write_text(self.source.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 0, 'target_ms': 0}])

    def test_own_hermes_output_can_be_reopened_but_other_private_files_cannot(self):
        private = self.root / '.HeRmEs'
        plugin = core.Captions(private / 'plugin-data' / 'caption-repair')
        result = plugin.retime(str(self.source), self.fingerprint, [{'source_ms': 0, 'target_ms': 100}])
        self.assertEqual(plugin.inspect(result['output_path'])['total'], 2)
        unrelated = private / 'unrelated.srt'
        unrelated.write_bytes(self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, 'private configuration'):
            plugin.inspect(str(unrelated))

    def test_malformed_timing(self):
        self.source.write_text('1\n00:99:00,000 --> 00:99:01,000\nInvalid\n')
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            self.plugin.inspect(str(self.source))

if __name__ == '__main__':
    unittest.main()
