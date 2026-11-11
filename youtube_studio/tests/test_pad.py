import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cs_t.video_pad_tests', root / '__init__.py', submodule_search_locations=[str(root)])
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)
from cs_t.video_pad_tests.slides import render_slides
from cs_t.video_pad_tests.render import stitch_segments
HAVE = shutil.which('ffmpeg') and shutil.which('ffprobe')


class PadTests(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'ffmpeg and ffprobe required')
    def test_silent_tail_lets_the_picture_outlast_the_narration(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); img = base / 'a.png'; Image.new('RGB', (1280, 720), (80, 120, 200)).save(img)
            audio = base / 'a.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=300:d=7.0', str(audio)], check=True, stdin=subprocess.DEVNULL)
            ids = [render_slides(base / 'out', [{'path': str(img), 'seconds': 4}], str(audio), [], [], False, 0)['segment_id'],
                   render_slides(base / 'out', [{'path': str(img), 'seconds': 3.8}], str(audio), [], [], False, 3.2)['segment_id']]
            with self.assertRaisesRegex(ValueError, 'does not cover'): stitch_segments(base / 'out', ids, str(audio))
            with self.assertRaisesRegex(ValueError, 'audio_pad_seconds'): stitch_segments(base / 'out', ids, str(audio), audio_pad_seconds=11)
            result = stitch_segments(base / 'out', ids, str(audio), audio_pad_seconds=1)
            self.assertAlmostEqual(result['duration_seconds'], 7.8, delta=0.4)


if __name__ == '__main__': unittest.main()
