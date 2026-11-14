"""Clip Studio highlights reel: joins of matching and mismatched clips, title cards, chapters, combined captions, limits."""
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import test_clips as base
from creator_studio_clip_test.clip_studio import reel as R, source as S

FFMPEG = base.FFMPEG
CUES = ''.join('%d\n00:00:%02d,500 --> 00:00:%02d,500\nLine number %d here.\n\n' % (n, 1 + n * 2, 2 + n * 2, n) for n in range(1, 9))


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class ReelTests(base.Fixture):
    def project(self, seconds=20, spans=((1, 6), (8, 13), (14, 19)), shape='source', captions='file'):
        media, srt = self.base / 'rec.mp4', self.base / 'rec.srt'
        base.make_media(media, seconds)
        srt.write_text(CUES)
        pid = self.call('clips_open', media_path=str(media))['project_id']
        self.call('clips_use_transcript', project_id=pid, transcript_path=str(srt))
        self.call('clips_propose', project_id=pid, clips=[{'start': a, 'end': b, 'title': 'Part %d: <the> bit' % n, 'exact': True} for n, (a, b) in enumerate(spans, 1)])
        out = self.call('clips_cut', project_id=pid, clip_ids=['c%d' % n for n in range(1, len(spans) + 1)], shape=shape, framing='fit', captions=captions)
        self.assertNotIn('error', out, out)
        return pid

    def clip_file(self, pid, cid):
        return Path(next(c for c in self.call('clips_status', project_id=pid)['clips'] if c['clip_id'] == cid)['cut']['video_path'])

    def streams(self, path):
        raw = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,duration,width,height,r_frame_rate,channels,sample_rate', '-of', 'json', str(path)], capture_output=True, check=True).stdout
        return {s['codec_type']: s for s in json.loads(raw)['streams']}

    def test_matching_clips_with_cards_chapters_and_captions(self):
        pid = self.project()
        out = json.loads(base.clip_studio.invoke('clips_join', {'project_id': pid, 'title_cards': 'between', 'fade_seconds': 0.2, 'name': 'my-reel'}))
        self.assertNotIn('error', out, out)
        self.assertTrue(out['reel_path'].endswith('/reels/my-reel.mp4'))
        parts = S.probe(self.clip_file(pid, 'c1'))['duration'] + S.probe(self.clip_file(pid, 'c2'))['duration'] + S.probe(self.clip_file(pid, 'c3'))['duration']
        self.assertAlmostEqual(out['seconds'], parts + 2 * 1.5, delta=0.2)
        check = out['duration_check']
        self.assertLessEqual(abs(check['difference']), check['allowed'])
        self.assertEqual(check['joins'], 4)
        self.assertLessEqual(abs(check['picture_vs_sound']), 0.1)
        st = self.streams(out['reel_path'])
        self.assertAlmostEqual(float(st['video']['duration']), float(st['audio']['duration']), delta=0.1)
        self.assertEqual((st['video']['width'], st['video']['height']), (640, 360))
        self.assertEqual(out['converted'][:4], 'none')
        lines = out['chapters_text'].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('0:00 Part 1'))
        self.assertNotIn('<', out['chapters_text'])
        starts = [c['at'] for c in out['chapters']]
        self.assertEqual(starts[0], 0)
        self.assertEqual(starts[1], int(S.probe(self.clip_file(pid, 'c1'))['duration'] + 0.0 + 0))  # card of clip 2 begins where clip 1 ends
        self.assertEqual([p['kind'] for p in out['parts']], ['clip', 'card', 'clip', 'card', 'clip'])
        # combined captions: clip 2 starts after clip 1 and its card
        cues = Path(out['captions_srt_path']).read_text()
        expected = []
        for part in out['parts']:
            if part['kind'] == 'clip':
                own = next(c for c in self.call('clips_status', project_id=pid)['clips'] if c['clip_id'] == part['clip_id'])['cut']['captions_path']
                expected += [int(round(part['start_seconds'] * 1000)) + s for s, _e, _t in R._cues(own)]
        got = [s for s, _e, _t in R._cues(out['captions_srt_path'])]
        self.assertEqual(len(got), len(expected), cues)
        for g, e in zip(got, expected):
            self.assertAlmostEqual(g, e, delta=30)  # part starts are rounded to 10 ms in the result
        self.assertGreater(got[-1], out['parts'][4]['start_seconds'] * 1000)
        self.assertEqual(out['uploaded'], False)

    def test_no_cards_hard_cut_and_default_order(self):
        pid = self.project()
        out = self.call('clips_join', project_id=pid)
        self.assertEqual([p['kind'] for p in out['parts']], ['clip'] * 3)
        self.assertEqual(out['chapters'][1]['at'], int(out['parts'][1]['start_seconds']))
        self.assertTrue(out['chapters_text'].startswith('0:00 '))
        reordered = json.loads(base.clip_studio.invoke('clips_join', {'project_id': pid, 'clip_ids': ['c3', 'c1'], 'title_cards': 'every', 'name': 'second'}))
        self.assertEqual([p['clip_id'] for p in reordered['parts']], ['c3', 'c3', 'c1', 'c1'])
        self.assertEqual(reordered['chapters'][0]['clip_id'], 'c3')
        self.assertEqual(len(reordered['chapters']), 2)

    def test_mismatched_size_rate_and_sound_are_converted(self):
        pid = self.project()
        # replace c2 by a smaller, 30 fps, mono 22 kHz copy of the same shape; c3 by a picture without sound
        odd = self.clip_file(pid, 'c2')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=5', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=30:duration=5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-ac', '1', '-ar', '22050', '-c:a', 'aac', '-y', str(odd)], check=True)
        mute = self.clip_file(pid, 'c3')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25:duration=5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(mute)], check=True)
        out = self.call('clips_join', project_id=pid, fade_seconds=0.3)
        self.assertNotIn('error', out, out)
        text = ' '.join(out['converted'])
        self.assertIn('c2: picture 320x180 to 640x360', text)
        self.assertIn('30.00 to 25.00 frames', text)
        self.assertIn('c3: no sound', text)
        st = self.streams(out['reel_path'])
        self.assertEqual((st['video']['width'], st['video']['height'], st['video']['r_frame_rate']), (640, 360, '25/1'))
        self.assertEqual((st['audio']['channels'], st['audio']['sample_rate']), (1, '44100'))  # the first clip's sound layout
        total = sum(S.probe(self.clip_file(pid, c))['duration'] for c in ('c1', 'c2', 'c3'))
        self.assertAlmostEqual(out['seconds'], total, delta=0.2)
        self.assertLessEqual(abs(out['duration_check']['difference']), 0.2)
        self.assertAlmostEqual(float(st['video']['duration']), float(st['audio']['duration']), delta=0.1)
        # the last join: the sound of the last part still ends with the picture, and its silence did not push anything late
        self.assertLessEqual(abs(out['duration_check']['picture_vs_sound']), 0.1)

    def test_mixed_shapes_are_refused_or_fitted(self):
        pid = self.project()
        self.call('clips_cut', project_id=pid, clip_ids=['c2'], shape='vertical', framing='fit', captions='none')
        refused = self.call('clips_join', project_id=pid)
        self.assertIn('portrait and landscape', refused['error'])
        fitted = self.call('clips_join', project_id=pid, mixed_shapes='fit')
        self.assertNotIn('error', fitted, fitted)
        self.assertLessEqual(abs(fitted['duration_check']['difference']), fitted['duration_check']['allowed'])
        self.assertIn('c2: picture 1080x1920 to 640x360', ' '.join(fitted['converted']))

    def test_versions(self):
        pid = self.project()
        burned = self.call('clips_burn', project_id=pid, clip_id='c1')
        self.assertNotIn('error', burned, burned)
        auto = self.call('clips_join', project_id=pid, clip_ids=['c1', 'c2'])
        self.assertEqual([p['file_used'] for p in auto['parts']], ['captioned', 'clean'])
        clean = self.call('clips_join', project_id=pid, clip_ids=['c1', 'c2'], version='clean')
        self.assertEqual([p['file_used'] for p in clean['parts']], ['clean', 'clean'])
        self.assertIn('no captioned copy', self.call('clips_join', project_id=pid, clip_ids=['c1', 'c2'], versions={'c2': 'captioned'})['error'])
        self.assertIn('captions_srt_path', clean)

    def test_limits_and_plain_errors(self):
        pid = self.project(spans=((1, 6), (8, 13), (14, 19)))
        self.call('clips_propose', project_id=pid, clips=[{'start': 2, 'end': 5, 'title': 'Not cut', 'exact': True}])
        self.assertIn('at least 2', self.call('clips_join', project_id=pid, clip_ids=['c1'])['error'])
        self.assertIn('not cut yet', self.call('clips_join', project_id=pid, clip_ids=['c1', 'c4'])['error'])
        self.assertIn('Unknown clip_id', self.call('clips_join', project_id=pid, clip_ids=['c1', 'c9'])['error'])
        self.assertIn('different clip ids', self.call('clips_join', project_id=pid, clip_ids=['c1', 'c1'])['error'])
        self.assertIn('error', self.call('clips_join', project_id=pid, title_cards='sparkles'))
        self.assertIn('error', self.call('clips_join', project_id=pid, fade_seconds=5))
        with mock.patch.object(R, 'MAX_REEL', 8.0):
            self.assertIn('hour limit', self.call('clips_join', project_id=pid, clip_ids=['c1', 'c2', 'c3'])['error'])
        other = self.base / 'other.mp4'
        base.make_media(other, 8)
        empty = self.call('clips_open', media_path=str(other))
        self.assertIn('at least 2', self.call('clips_join', project_id=empty['project_id'])['error'])

    def test_title_card_is_drawn_and_dark(self):
        from PIL import Image
        card = self.base / 'card.png'
        R.title_card('A rather long title that has to wrap over a few lines on a small card', 640, 360, card)
        with Image.open(card) as image:
            self.assertEqual(image.size, (640, 360))
            self.assertEqual(image.getpixel((2, 2)), (16, 22, 30))
            self.assertGreater(image.convert('L').getextrema()[1], 200)  # text is there

    def test_tools_are_listed_with_plain_descriptions(self):
        for name in ('clips_join',):
            description, props, required = clip_tools()[name]
            self.assertIn('nothing is uploaded', description)
            self.assertIn('untrusted', description)
            self.assertEqual(required, ['project_id'])


def clip_tools():
    return base.clip_studio.TOOLS


if __name__ == '__main__':
    unittest.main()
