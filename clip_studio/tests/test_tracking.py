"""Clip Studio: following the saved face box through a clip. FFmpeg makes small real videos with a textured red "avatar" that moves, grows and disappears."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('creator_studio_tracking_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_tracking_test import clip_studio  # noqa: E402
from creator_studio_tracking_test.clip_studio import tracking as K  # noqa: E402

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')
BOX = {'left': 78.0, 'top': 63.0, 'width': 19.0, 'height': 33.5}   # where the avatar sits in scene one: x 500-620, y 230-350 of 640x360

SPRITE = ("color=c=red:s=120x120:r=25,drawgrid=x=10:y=10:w=20:h=20:t=2:c=0x700000,drawbox=x=30:y=40:w=20:h=12:c=white:t=fill,drawbox=x=75:y=40:w=20:h=12:c=white:t=fill,"
          "drawbox=x=30:y=40:w=20:h=12:c=red:t=fill:enable='lt(mod(t,2.5),0.2)',drawbox=x=75:y=40:w=20:h=12:c=red:t=fill:enable='lt(mod(t,2.5),0.2)',"
          "drawbox=x=42:y=84:w=36:h=10:c=black:t=fill:enable='lt(mod(t,0.5),0.25)'")


def make_video(path, seconds, scenes, wobble=0):
    """Blue noisy picture. scenes: (from, to, x, y, size): the avatar is drawn there during that time; wobble sways it by that many pixels."""
    parts = ['[1:v]split=%d%s' % (len(scenes), ''.join('[s%d]' % n for n in range(len(scenes))))]
    last = '0:v'
    for n, (a, b, x, y, size) in enumerate(scenes):
        pad = '[s%d]' % n
        if size != 120:
            parts.append('[s%d]scale=%d:%d[z%d]' % (n, size, size, n))
            pad = '[z%d]' % n
        sway = ("+%d*sin(2*PI*t*0.7)" % wobble) if wobble else ''
        parts.append("[%s]%soverlay=x='%d%s':y='%d%s':enable='between(t,%s,%s)'[o%d]" % (last, pad, x, sway, y, sway.replace('sin', 'cos') if sway else '', a, b, n))
        last = 'o%d' % n
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=0x1e4a8c:s=640x360:r=25:d=%s,noise=alls=18:allf=t' % seconds, '-f', 'lavfi', '-i', SPRITE,
                    '-f', 'lavfi', '-i', 'sine=frequency=300:duration=%s' % seconds, '-filter_complex', ';'.join(parts), '-map', '[%s]' % last, '-map', '2:a', '-t', str(seconds),
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(path)], check=True)


def colour(path, t, x, y):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', str(path), '-frames:v', '1', '-vf', 'crop=8:8:%d:%d,scale=1:1' % (x, y), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    r, g, b = raw[:3]
    return 'red' if r > 140 and g < 90 and b < 90 else 'black' if max(r, g, b) < 40 else 'blue' if b > r + 40 else 'other'


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        storage = types.ModuleType('plugins.plugin_storage')

        def plugin_data_dir(name):
            folder = self.base / 'profile' / 'plugin-data' / name
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        storage.plugin_data_dir = plugin_data_dir
        patcher = mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def call(self, name, **args):
        return json.loads(clip_studio.invoke(name, args))

    def open(self, path, seconds, box=BOX, looked_at=2):
        pid = self.call('clips_open', media_path=str(path))['project_id']
        if looked_at is not None:
            self.call('clips_frame', project_id=pid, at=looked_at)
        if box:
            self.assertEqual(self.call('clips_face', project_id=pid, **box)['face']['left'], box['left'])
        self.call('clips_propose', project_id=pid, clips=[{'start': 0, 'end': seconds, 'title': 'Whole', 'exact': True}])
        return pid

    def cut(self, pid, **extra):
        out = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none', **extra)
        self.assertNotIn('error', out, out)
        return out['clips'][0]


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class FollowTests(Fixture):
    def scene_video(self):
        media = self.base / 'stream.mp4'
        # 0-8 bottom right, 8-16 top left, 16-22 bigger in the middle, 22-28 gone, 28-34 bottom right again
        make_video(media, 34, [(0, 8, 500, 230, 120), (8, 16, 20, 20, 120), (16, 22, 220, 60, 200), (28, 34, 500, 230, 120)])
        return media

    def test_box_follows_the_avatar_through_a_changing_stream(self):
        media = self.scene_video()
        pid = self.open(media, 34)
        cut = self.cut(pid)
        follow = cut['face_follow']
        rows = follow['segments']
        self.assertEqual(len(rows), 5, rows)
        for row, edge in zip(rows[1:], (8, 16, 22, 28)):
            self.assertAlmostEqual(row['clip_from'], edge, delta=1.0, msg=rows)
        self.assertTrue(follow['box_moved'])
        self.assertEqual([r['how'] for r in rows], ['saved box', 'found by searching the picture', 'found by searching the picture', 'no match', 'saved box'])
        self.assertEqual(follow['not_found'][0]['clip_from'], rows[3]['clip_from'])
        self.assertAlmostEqual(follow['not_found'][0]['clip_to'], 28, delta=1.0)
        self.assertIn('clips_frame', follow['next'])
        self.assertIn('clips_face_ranges', follow['next'])
        self.assertIn('not face detection', follow['method'])
        self.assertAlmostEqual(rows[1]['box']['left'], 3.1, delta=3)       # top-left corner
        self.assertGreater(rows[2]['box']['width'], 25)                    # it grew
        self.assertIn('one panel', rows[2]['layout'])
        self.assertIn('panel on top', rows[0]['layout'])
        self.assertEqual(rows[3]['layout'], 'whole picture with bars')
        self.assertEqual((cut['width'], cut['height']), (1080, 1920))
        self.assertIn('5 stretches', cut['face_layout'])
        out = cut['video_path']
        mid = lambda r: (r['clip_from'] + r['clip_to']) / 2   # noqa: E731
        self.assertEqual(colour(out, mid(rows[0]), 540, 500), 'red')       # avatar fills the top panel
        self.assertEqual(colour(out, mid(rows[1]), 540, 500), 'red')       # it moved to the other corner and the panel followed
        self.assertEqual(colour(out, mid(rows[2]), 540, 853), 'red')       # one panel around the big avatar
        self.assertEqual(colour(out, mid(rows[3]), 540, 130), 'black')     # no match: whole picture with bars, nothing cropped away
        self.assertEqual(colour(out, mid(rows[3]), 540, 960), 'blue')
        self.assertEqual(colour(out, mid(rows[4]), 540, 500), 'red')

    def test_a_still_avatar_that_only_animates_is_not_moved(self):
        media = self.base / 'sway.mp4'
        make_video(media, 14, [(0, 14, 500, 230, 120)], wobble=4)           # sways by 4 pixels, blinks and talks
        cut = self.cut(self.open(media, 14))
        follow = cut['face_follow']
        self.assertEqual(len(follow['segments']), 1, follow)
        self.assertFalse(follow['box_moved'])
        self.assertNotIn('not_found', follow)
        self.assertIn('panel on top', cut['face_layout'])
        self.assertIn('red', [colour(cut['video_path'], 7, 540, y) for y in (130, 300, 500, 700)])   # the avatar is in the top panel

    def test_a_short_disappearance_is_ignored(self):
        media = self.base / 'blip.mp4'
        make_video(media, 14, [(0, 6, 500, 230, 120), (7, 14, 500, 230, 120)])   # gone for one second
        follow = self.cut(self.open(media, 14))['face_follow']
        self.assertEqual(len(follow['segments']), 1, follow)

    def test_your_own_ranges_win_over_the_search(self):
        media = self.scene_video()
        pid = self.open(media, 34)
        for bad in ({'ranges': [{'start': 5, 'end': 3, 'none': True}]}, {'ranges': [{'start': 1, 'end': 3}]}, {'ranges': [{'start': 1, 'end': 3, 'left': 90, 'top': 0, 'width': 30, 'height': 20}]},
                    {'ranges': [{'start': 1, 'end': 3, 'none': True, 'left': 1, 'top': 1, 'width': 10, 'height': 10}]}, {'follow': 'no'}, {'extra': 1}):
            self.assertIn('error', self.call('clips_face_ranges', project_id=pid, **bad), bad)
        self.assertEqual(self.call('clips_face_ranges', project_id=pid)['ranges'], [])
        # the gone stretch is declared a box (the model looked at it), and the first scene is declared "whole picture"
        listed = self.call('clips_face_ranges', project_id=pid, ranges=[{'start': 22.5, 'end': 27.5, 'left': 78, 'top': 63, 'width': 19, 'height': 33.5}, {'start': 1, 'end': 5, 'none': True}])
        self.assertEqual(len(listed['ranges']), 2)
        again = self.call('clips_face_ranges', project_id=pid, ranges=[{'start': 2, 'end': 4, 'none': True}])['ranges']
        self.assertEqual([(r['start'], r['end']) for r in again], [(2.0, 4.0), (22.5, 27.5)])  # overlapping: replaced, not stacked
        cut = self.cut(pid)
        rows = cut['face_follow']['segments']
        by_how = {r['how'] for r in rows}
        self.assertIn('set by you (clips_face_ranges)', by_how)
        self.assertIn('set by you: whole picture', by_how)
        self.assertNotIn('not_found', cut['face_follow'])          # the stretch 22.5-27.5 is set; only the 0.5 s edges at 22-22.5 and 27.5-28 could be lost, and they are under 2 s
        whole = next(r for r in rows if r['how'] == 'set by you: whole picture')
        self.assertAlmostEqual(whole['clip_from'], 2, delta=0.1)
        self.assertEqual(colour(cut['video_path'], 3, 540, 130), 'black')
        gone = next(r for r in rows if r['how'] == 'set by you (clips_face_ranges)')
        self.assertIn('panel on top', gone['layout'])                      # the box you gave is used; nothing is there, so the panel shows the noisy picture
        self.assertEqual(colour(cut['video_path'], 25, 540, 130), 'blue')
        self.assertEqual(self.call('clips_face_ranges', project_id=pid, clear=True)['ranges'], [])

    def test_following_can_be_switched_off(self):
        media = self.scene_video()
        pid = self.open(media, 34)
        self.assertFalse(self.call('clips_face_ranges', project_id=pid, follow=False)['follow'])
        cut = self.cut(pid)
        self.assertEqual(len(cut['face_follow']['segments']), 1)
        self.assertIn('switched off', ' '.join(cut['face_follow']['notes']))
        self.assertIn('panel on top', cut['face_layout'])

    def test_no_saved_box_nothing_changes(self):
        media = self.scene_video()
        cut = self.cut(self.open(media, 34, box=None))
        self.assertNotIn('face_follow', cut)
        self.assertIn('no face box', cut['face_layout'])
        # source shape ignores the box as well
        pid = self.open(media, 34)
        source_cut = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='source', captions='none')['clips'][0]
        self.assertNotIn('face_follow', source_cut)
        self.assertNotIn('face_layout', source_cut)

    def test_a_flat_box_cannot_be_followed_and_is_used_as_before(self):
        media = self.base / 'flat.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=blue:size=640x360:rate=25:duration=6', '-vf', 'drawbox=x=480:y=216:w=160:h=144:color=red:t=fill',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-y', str(media)], check=True)
        cut = self.cut(self.open(media, 6, box={'left': 75, 'top': 60, 'width': 25, 'height': 40}))
        self.assertIn('panel on top', cut['face_layout'])
        self.assertIn('almost flat', ' '.join(cut['face_follow']['notes']))
        self.assertEqual(len(cut['face_follow']['segments']), 1)

    def test_the_look_is_taken_from_the_clip_when_the_looked_at_picture_is_another_scene(self):
        media = self.scene_video()
        pid = self.open(media, 34, looked_at=25)   # the model looked at the empty stretch: its picture has no avatar
        follow = self.cut(pid)['face_follow']
        self.assertIn('first picture of this clip', follow['look_taken_from'])
        self.assertIn('was not found anywhere', ' '.join(follow['notes']))
        self.assertEqual(follow['segments'][0]['how'], 'saved box')


class UnitTests(unittest.TestCase):
    def test_runs_ignore_a_change_shorter_than_two_seconds(self):
        a, b = {'left': 70.0, 'top': 60.0, 'width': 20.0, 'height': 30.0}, {'left': 5.0, 'top': 5.0, 'width': 20.0, 'height': 30.0}
        times = [n * 1.5 for n in range(10)]
        runs = K._runs(times, [(a, 1)] * 4 + [(b, 1)] + [(a, 1)] * 5, 15.0)
        self.assertEqual([(r[0], r[1], r[2]) for r in runs], [(a, 0.0, 15.0)])
        runs = K._runs(times, [(a, 1)] * 4 + [(None, 0)] * 3 + [(a, 1)] * 3, 15.0)
        self.assertEqual([(r[0] is None, r[1], r[2]) for r in runs], [(False, 0.0, 6.0), (True, 6.0, 10.5), (False, 10.5, 15.0)])

    def test_same_box_tolerates_small_differences_only(self):
        a = {'left': 70.0, 'top': 60.0, 'width': 20.0, 'height': 30.0}
        self.assertTrue(K.same_box(a, {'left': 71.0, 'top': 61.0, 'width': 21.0, 'height': 30.0}))
        self.assertFalse(K.same_box(a, {'left': 10.0, 'top': 60.0, 'width': 20.0, 'height': 30.0}))
        self.assertFalse(K.same_box(a, {'left': 70.0, 'top': 60.0, 'width': 40.0, 'height': 30.0}))
        self.assertTrue(K.same_box(None, None) and not K.same_box(a, None))

    def test_layout_is_chosen_per_stretch_by_box_width(self):
        small, big = {'left': 75.0, 'top': 60.0, 'width': 25.0, 'height': 40.0}, {'left': 60.0, 'top': 20.0, 'width': 40.0, 'height': 80.0}
        self.assertIn('vstack', K.chain(small, 640, 360, 'vertical', 'fit', '3')[0])
        self.assertIn('[fa3]', K.chain(small, 640, 360, 'vertical', 'fit', '3')[0])
        self.assertEqual(K.chain(big, 640, 360, 'vertical', 'fit', '0')[1], 'one panel cropped around the box')
        self.assertTrue(K.chain(None, 640, 360, 'vertical', 'crop', '0')[0].startswith('crop='))
        self.assertIn('pad=1080:1080', K.chain(None, 640, 360, 'square', 'fit', '0')[0])


if __name__ == '__main__':
    unittest.main()
