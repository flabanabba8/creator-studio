import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cs_t.video_short_tests', root / '__init__.py', submodule_search_locations=[str(root)])
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)
from cs_t.video_short_tests.short import render_short

HAVE = shutil.which('ffmpeg') and shutil.which('ffprobe')


def make_source(path, seconds=8):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x3060a0:s=1280x720:r=15:d={seconds}', '-f', 'lavfi', '-i', f'sine=f=440:d={seconds}',
                    '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)], check=True, stdin=subprocess.DEVNULL)


class ShortTests(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'ffmpeg and ffprobe required')
    def test_vertical_cut_has_header_footer_and_captions_in_their_bands(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); source = base / 'in.mp4'; make_source(source)
            result = render_short(base / 'out', str(source), 1, 4, header='Test Show', footer='Full episode on the channel', captions=[{'start': 0.5, 'end': 3.5, 'text': 'A short caption line'}])
            out = Path(result['output_path'])
            self.assertTrue(out.is_file()); self.assertEqual(result['size'], '1080x1920')
            self.assertAlmostEqual(result['duration_seconds'], 4, delta=1)
            frame = base / 'f.png'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '2', '-i', str(out), '-frames:v', '1', str(frame)], check=True, stdin=subprocess.DEVNULL)
            img = Image.open(frame).convert('RGB'); w, h = img.size; self.assertEqual((w, h), (1080, 1920))
            def bright_rows(y0, y1):
                return sum(1 for y in range(y0, y1) if any(sum(img.getpixel((x, y))) > 700 for x in range(0, w, 3)))
            self.assertGreater(bright_rows(150, 240), 5)      # header
            self.assertGreater(bright_rows(1730, 1810), 5)    # footer
            self.assertGreater(bright_rows(1100, 1264), 5)    # caption inside the picture band
            self.assertLess(bright_rows(300, 600), 3)         # nothing stray above the picture
            self.assertEqual(list((base / 'out').glob('*.partial.mp4')), []); self.assertEqual(list((base / 'out').glob('*.txt')), [])

    @unittest.skipUnless(HAVE, 'ffmpeg and ffprobe required')
    def test_range_outside_source_and_bad_text_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); source = base / 'in.mp4'; make_source(source, 4)
            with self.assertRaisesRegex(ValueError, 'covering'): render_short(base / 'out', str(source), 3, 5)
            with self.assertRaisesRegex(ValueError, 'single-line'): render_short(base / 'out', str(source), 0, 2, header='two\nlines')
            with self.assertRaises(ValueError): render_short(base / 'out', str(source), 0, 61)
            with self.assertRaises(ValueError): render_short(base / 'out', str(source), 0, 2, captions=[{'start': 0, 'end': 9, 'text': 'too late'}])

    def test_timeout_leaves_no_partial_or_text_files(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); source = base / 'in.mp4'; source.write_bytes(b'fixture')
            info = subprocess.CompletedProcess([], 0, stdout=json.dumps({'format': {'duration': '9'}, 'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]}).encode())
            def run(command, **kwargs):
                if command[0].endswith('ffprobe'): return info
                raise subprocess.TimeoutExpired('fixture', 300)
            with patch('cs_t.video_short_tests.short.shutil.which', side_effect=lambda n: '/usr/bin/' + n), patch('cs_t.video_short_tests.short.subprocess.run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'failed'): render_short(base / 'out', str(source), 0, 3, header='Hi', footer='There')
            self.assertEqual([x.name for x in (base / 'out').iterdir() if x.name != '.render.lock'], [])

    def test_description_assembles_chapters_sources_and_limits(self):
        chapters = [{'start': 0, 'title': 'First story'}, {'start': 30, 'title': 'Second story'}, {'start': 75, 'title': 'Wrap-up'}]
        result = json.loads(p.invoke('youtube_description', {'blurb': 'Three stories today.', 'duration': 100, 'chapters': chapters, 'sources': ['https://a.example/x', 'https://a.example/x', 'https://b.example/y'], 'footer': 'More at the channel.'}))
        self.assertEqual(result['description'], 'Three stories today.\n\n00:00 First story\n00:30 Second story\n01:15 Wrap-up\n\nSources:\nhttps://a.example/x\nhttps://b.example/y\n\nMore at the channel.')
        self.assertIn('error', json.loads(p.invoke('youtube_description', {'blurb': '', 'duration': 100, 'chapters': [], 'sources': []})))
        two = json.loads(p.invoke('youtube_description', {'blurb': 'x', 'duration': 100, 'chapters': chapters[:2], 'sources': []}))
        self.assertTrue(two['chapters_included']); self.assertIn('three chapters', two['youtube_chapter_list_note'])  # short lessons still get chapters; the note says what YouTube shows
        self.assertIn('error', json.loads(p.invoke('youtube_description', {'blurb': 'x', 'duration': 100, 'chapters': chapters[:1], 'sources': []})))
        self.assertEqual(json.loads(p.invoke('youtube_description', {'blurb': 'x', 'duration': 100, 'chapters': chapters, 'sources': []}))['youtube_chapter_list_note'], '')


if __name__ == '__main__': unittest.main()
