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

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cs_t.video_deck_tests', root / '__init__.py', submodule_search_locations=[str(root)])
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)
from cs_t.video_deck_tests.deck import make_slides
from cs_t.video_deck_tests.slides import render_slides


class DeckTests(unittest.TestCase):
    def test_slides_are_1080p_with_text_inside_margins_and_distinct_themes(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp)
            picture = base / 'pic.png'; Image.new('RGB', (400, 300), (10, 120, 200)).save(picture)
            slides = [{'title': 'Why the sky is blue', 'bullets': ['Sunlight holds every color.', 'Small air molecules bounce blue light the most.'], 'image_path': str(picture), 'notes': 'Say it slowly.'},
                      {'title': 'The end'}]
            light = make_slides(base / 'out', slides, 'light'); dark = make_slides(base / 'out2', slides, 'dark')
            first = Image.open(light['slides'][0]['path']).convert('RGB')
            self.assertEqual(first.size, (1920, 1080)); self.assertEqual(light['notes'][0], 'Say it slowly.')
            self.assertIn('Sunlight holds every color', light['slides'][0]['alt_text'])
            self.assertNotEqual(first.getpixel((1000, 1000)), Image.open(dark['slides'][0]['path']).convert('RGB').getpixel((1000, 1000)))
            self.assertEqual(first.getpixel((1490, 540)), (10, 120, 200))                 # picture scaled into the right-hand box
            def ink_rows(img, x0, x1): return sum(1 for y in range(0, 1080, 2) if any(sum(img.getpixel((x, y))) < 200 for x in range(x0, x1, 4)))
            self.assertGreater(ink_rows(first, 100, 1100), 20)                          # text is drawn

    def test_terminal_theme_code_block_is_drawn_inside_its_box_and_limits_hold(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp)
            code = '> podcast_preflight\n  episode_dir: /path/to/episode\n\nstatus: passed\nfiles: 8\nwarnings: 0'
            out = make_slides(base / 'o', [{'title': 'Pre-audio gate', 'code': code}], 'terminal')
            im = Image.open(out['slides'][0]['path']).convert('RGB')
            self.assertEqual(im.size, (1920, 1080)); self.assertEqual(im.getpixel((960, 1050)), (14, 17, 23))
            self.assertEqual(im.getpixel((400, 330)), (4, 6, 10))                       # the dark code box starts below the title
            lit = sum(1 for y in range(300, 700, 2) for x in range(120, 1000, 3) if sum(im.getpixel((x, y))) > 560)
            self.assertGreater(lit, 300)                                                # text pixels are drawn in the box
            for bad in ('x' * 121, '\n'.join(['line'] * 40), 'bell\x07'):
                with self.assertRaises(ValueError): make_slides(base / 'o2', [{'title': 'T', 'code': bad}], 'terminal')

    def test_overflowing_text_and_bad_input_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp)
            from PIL import Image
            picture = base / 'p.png'; Image.new('RGB', (100, 100), (1, 2, 3)).save(picture)
            long = ' '.join(['wonderful'] * 14)
            make_slides(base / 'fits', [{'title': 'T', 'bullets': [long] * 6}])        # full width: text shrinks to fit
            with self.assertRaisesRegex(ValueError, 'too much text'): make_slides(base / 'o', [{'title': 'T' * 99, 'bullets': [long] * 6, 'image_path': str(picture)}])
            for slides in ([], [{'bullets': ['x']}], [{'title': 'x', 'bullets': ['x'] * 7}], [{'title': 'x', 'extra': 1}]):
                with self.assertRaises(ValueError): make_slides(base / 'o', slides)
            with self.assertRaisesRegex(ValueError, 'theme'): make_slides(base / 'o', [{'title': 'x'}], 'neon')
            self.assertEqual(list((base / 'o').glob('*.png')) if (base / 'o').exists() else [], [])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg required')
    def test_outline_to_narrated_video_without_any_video_model(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); audio = base / 'a.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=300:d=10', str(audio)], check=True, stdin=subprocess.DEVNULL)
            deck = make_slides(base / 'deck', [{'title': 'First idea', 'bullets': ['One thing.']}, {'title': 'Second idea', 'bullets': ['Another thing.']}], 'kids')
            result = render_slides(base / 'out', [{'path': s['path'], 'seconds': 3, 'motion': 'zoom_in'} for s in deck['slides']], str(audio), [], [])
            self.assertAlmostEqual(result['duration_seconds'], 6, delta=1)


if __name__ == '__main__': unittest.main()
