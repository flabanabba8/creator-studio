"""Capture a real isolated X11 application with its own original test audio."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

from test_tutorial import Director
from tutorial_test.core import sources, run, probe


@unittest.skipUnless(all(shutil.which(x) for x in ['Xvfb', 'ffplay', 'ffmpeg', 'pactl', 'xwininfo']), 'Linux X11/audio tools required')
class Capture(unittest.TestCase):
    def test_window_audio_mark_stop_export_and_restore(self):
        try:
            run(['pactl', 'info'])
        except Exception:
            self.skipTest('PulseAudio-compatible server is unavailable')
        xvfb = player = None
        sink_module = None
        director = job_id = None
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = Path(tmp)
                video = root / 'original-fixture.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=480x270:rate=30',
                                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '10',
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(video)], check=True, timeout=20)
                xvfb = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '800x600x24', '-nolisten', 'tcp'],
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                self.assertTrue(select.select([xvfb.stdout], [], [], 5)[0], 'Xvfb did not start')
                display = ':' + xvfb.stdout.readline().strip()
                sink_name = 'tutorial_fixture_' + uuid.uuid4().hex
                sink_module = run(['pactl', 'load-module', 'module-null-sink', 'sink_name=' + sink_name]).strip()
                env = {**os.environ, 'DISPLAY': display, 'PULSE_SINK': sink_name, 'SDL_AUDIODRIVER': 'pulseaudio',
                       'SDL_VIDEODRIVER': 'x11', 'SDL_RENDER_DRIVER': 'software'}
                player = subprocess.Popen(['ffplay', '-loglevel', 'error', '-window_title', 'Tutorial Original Fixture', '-loop', '0', str(video)],
                                          env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                window = stream = None
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    inventory = sources(display)
                    window = next((w for w in inventory['windows'] if w['title'] == 'Tutorial Original Fixture'), None)
                    stream = next((s for s in inventory['audio_streams'] if str(s['pid']) == str(player.pid)), None)
                    if window and stream: break
                    time.sleep(.1)
                self.assertIsNotNone(window, 'Fixture window missing')
                self.assertIsNotNone(stream, 'Fixture audio stream missing')
                initial = next(s for s in json.loads(run(['pactl', '--format=json', 'list', 'sink-inputs'])) if s['index'] == stream['stream_id'])
                director = Director(root / 'recordings')
                take = director.start(window['window_id'], display=display, max_seconds=5, audio_stream=stream['stream_id'])
                job_id = take['job_id']
                self.assertEqual(take['state'], 'recording', take)
                time.sleep(1.2)
                marker = director.mark(job_id, 'Original animated window and tone')
                self.assertGreater(marker['seconds'], 0)
                time.sleep(.6)
                stopped = director.stop(job_id)
                self.assertEqual(stopped['state'], 'complete', stopped)
                self.assertNotIn('cleanup_errors', stopped)
                current = next(s for s in json.loads(run(['pactl', '--format=json', 'list', 'sink-inputs'])) if s['index'] == stream['stream_id'])
                self.assertEqual(current['sink'], initial['sink'], 'Fixture audio route was not restored')
                info = probe(director.job(job_id) / 'raw.mkv')
                self.assertEqual({s['codec_type'] for s in info['streams']}, {'video', 'audio'})
                output = director.export(job_id, [{'start': 0, 'duration': min(1.5, stopped['seconds'] - .1)}])
                self.assertTrue(output['decoded'])
                self.assertTrue(output['audio'])
            finally:
                if director and job_id:
                    director.stop(job_id)
                for process in (player, xvfb):
                    if process and process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
                if sink_module is not None:
                    run(['pactl', 'unload-module', sink_module])
                if xvfb and xvfb.stdout:
                    xvfb.stdout.close()


if __name__ == '__main__': unittest.main()
