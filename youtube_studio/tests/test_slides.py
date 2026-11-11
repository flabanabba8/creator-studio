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
spec = importlib.util.spec_from_file_location('cs_t.video_slides_tests', root / '__init__.py', submodule_search_locations=[str(root)])
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)
from cs_t.video_slides_tests.slides import render_slides
HAVE = shutil.which('ffmpeg') and shutil.which('ffprobe')


def fixtures(base):
    from PIL import Image, ImageDraw
    paths = []
    for i, color in enumerate(((200, 40, 40), (40, 160, 60))):
        img = Image.new('RGB', (1600, 900), color); d = ImageDraw.Draw(img)
        d.rectangle((600, 300, 1000, 600), fill=(250, 250, 250)); path = base / f'slide{i}.png'; img.save(path); paths.append(path)
    audio = base / 'a.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=300:d=8', str(audio)], check=True, stdin=subprocess.DEVNULL)
    return paths, audio


def frame(video, at, out):
    from PIL import Image
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(at), '-i', str(video), '-frames:v', '1', str(out)], check=True, stdin=subprocess.DEVNULL)
    return Image.open(out).convert('RGB')


class SlideTests(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'ffmpeg and ffprobe required')
    def test_two_slides_with_zoom_change_picture_over_time(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); (a, b), audio = fixtures(base)
            result = render_slides(base / 'out', [{'path': str(a), 'seconds': 3, 'motion': 'zoom_in'}, {'path': str(b), 'seconds': 3, 'motion': 'pan_right'}], str(audio), [], [{'start': 0, 'end': 2, 'text': 'Hello'}])
            out = Path(result['output_path']); self.assertAlmostEqual(result['duration_seconds'], 6, delta=1); self.assertTrue(result['captions_included'])
            first, early, late, second = (frame(out, t, base / f'f{t}.png') for t in (0.1, 0.2, 2.8, 4))
            self.assertEqual(first.size, (1280, 720))
            red = lambda img: img.getpixel((20, 20))[0] > 150 and img.getpixel((20, 20))[1] < 90
            self.assertTrue(red(first)); self.assertFalse(red(second))      # slide order and cut
            def box_width(img):
                row = [img.getpixel((x, 360)) for x in range(1280)]
                return sum(1 for r in row if min(r) > 230)
            self.assertGreater(box_width(late), box_width(early) + 20)        # zoom_in enlarges the white box
            self.assertEqual(list((base / 'out').glob('*.partial.mp4')) + list((base / 'out').glob('*.vtt')), [])

    @unittest.skipUnless(HAVE, 'ffmpeg and ffprobe required')
    def test_burned_captions_appear_in_the_picture_only_while_the_cue_is_active(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); (a, b), audio = fixtures(base)
            result = render_slides(base / 'out', [{'path': str(a), 'seconds': 3}, {'path': str(b), 'seconds': 3}], str(audio), [],
                                   [{'start': 0.2, 'end': 2.0, 'text': 'Burned caption line'}], burn_captions=True)
            out = Path(result['output_path']); self.assertTrue(result['captions_burned'])
            streams = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(out)], capture_output=True, text=True).stdout.split()
            self.assertNotIn('subtitle', streams)
            def bottom_white(t):
                f = base / f'b{t}.png'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', str(out), '-frames:v', '1', str(f)], check=True, stdin=subprocess.DEVNULL)
                im = Image.open(f).convert('RGB')
                return sum(1 for y in range(620, 710, 2) for x in range(300, 980, 3) if min(im.getpixel((x, y))) > 235)
            self.assertGreater(bottom_white(1.0), 40)       # caption text during the cue
            self.assertLess(bottom_white(2.6), 5)           # gone afterwards

    def test_validation_and_stitchable_output_contract(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); img = base / 'x.png'; img.write_bytes(b'x'); aud = base / 'a.wav'; aud.write_bytes(b'x')
            for slides, message in (([], 'one to twelve'), ([{'path': str(img), 'seconds': 0}], '1 to 120'), ([{'path': str(img), 'seconds': 5, 'motion': 'spin'}], 'motion must be'),
                                    ([{'path': str(img), 'seconds': 100}, {'path': str(img), 'seconds': 30}], 'Total slide duration')):
                with self.assertRaisesRegex(ValueError, message): render_slides(base / 'out', slides, str(aud), [], [])
            from unittest.mock import patch
            import types
            storage=types.ModuleType('plugins.plugin_storage');storage.plugin_data_dir=lambda name:base/'private'
            with patch.dict(sys.modules,{'plugins':types.ModuleType('plugins'),'plugins.plugin_storage':storage}):
                self.assertIn('error', json.loads(p.invoke('youtube_render_slides', {'slides': [], 'audio_path': str(aud), 'chapters': [], 'captions': []})))


if __name__ == '__main__': unittest.main()
