"""Clip Studio publishing kit: facts and candidate frames, validation, the forced credit line, thumbnails, local recordings."""
import json
import subprocess
import unittest
from pathlib import Path

import test_clips as base
from creator_studio_clip_test.clip_studio import publish as P, source as S

FFMPEG = base.FFMPEG


def black_then_picture(path, black=4, picture=8):
    """640x360: black for the first seconds, then a moving test picture; with sound."""
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%d' % (black + picture),
                    '-f', 'lavfi', '-i', 'color=c=black:size=640x360:rate=25:duration=%d' % black, '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25:duration=%d' % picture,
                    '-filter_complex', '[1:v][2:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(path)], check=True)


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class PublishTests(base.Fixture):
    def local(self, shape='source', start=0.5, end=11.5):
        media = self.base / 'rec.mp4'
        black_then_picture(media)
        pid = self.call('clips_open', media_path=str(media))['project_id']
        (self.base / 'rec.srt').write_text('1\n00:00:01,000 --> 00:00:03,000\nWelcome to the stream.\n\n2\n00:00:05,000 --> 00:00:08,000\nToday we test the thing.\n\n3\n00:00:09,000 --> 00:00:11,000\nThat was it.\n')
        self.call('clips_use_transcript', project_id=pid, transcript_path=str(self.base / 'rec.srt'))
        self.call('clips_propose', project_id=pid, clips=[{'start': start, 'end': end, 'title': 'Working title', 'reason': 'It is a test.', 'exact': True}])
        out = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape=shape, framing='fit', captions='none')
        self.assertNotIn('error', out, out)
        return pid

    def youtube(self):
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1.6, 'end': 8, 'title': 'The idea', 'exact': True}])
        self.assertNotIn('error', self.call('clips_cut', project_id=pid, clip_ids=['c1'], captions='none', max_height=360))
        return pid

    def test_facts_local_recording_and_frames_skip_black(self):
        pid = self.local()
        out = self.call('clips_post_facts', project_id=pid)
        self.assertNotIn('error', out, out)
        row = out['clips'][0]
        self.assertEqual(row['clip_id'], 'c1')
        self.assertAlmostEqual(row['seconds'], 11.0, delta=0.3)
        self.assertIn('Today we test the thing.', row['words'])
        self.assertNotIn('source_link', row)
        self.assertIn('no link and no credit line', row['source_note'])
        self.assertEqual(out['uploaded'], False)
        self.assertIn('Nothing was published', out['rights'])
        frames = row['frames']
        self.assertTrue(3 <= len(frames) <= 5, frames)
        from PIL import Image, ImageStat
        for f in frames:
            self.assertGreater(f['at_seconds'], 3.5 - 0.5)  # the clip starts at 0.5, black until 4.0 in the recording = 3.5 in the clip
            with Image.open(f['path']) as image:
                self.assertGreater(ImageStat.Stat(image.convert('L')).mean[0], 25)
            self.assertTrue(f['path'].endswith('.jpg'))
        self.assertEqual(self.call('clips_post_facts', project_id=pid, frames=3)['clips'][0]['frames'].__len__(), 3)
        self.assertIn('error', self.call('clips_post_facts', project_id=pid, frames=9))
        self.assertIn('error', self.call('clips_post_facts', project_id=pid, clip_ids=['c7']))

    def test_static_picture_yields_one_frame_and_a_note(self):
        media = self.base / 'still.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=10', '-f', 'lavfi', '-i', 'color=c=0x3060a0:size=320x180:rate=25:duration=10',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(media)], check=True)
        pid = self.call('clips_open', media_path=str(media))['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 9, 'title': 'Still', 'exact': True}])
        self.call('clips_cut', project_id=pid, clip_ids=['c1'], captions='none')
        row = self.call('clips_post_facts', project_id=pid)['clips'][0]
        self.assertEqual(len(row['frames']), 1)  # one flat picture: a single frame is kept
        self.assertIn('Only 1 usable', row['thumbnails_note'])
        self.assertIn('no transcript', row['words_note'])

    def test_youtube_facts_link_and_forced_credit_line(self):
        pid = self.youtube()
        row = self.call('clips_post_facts', project_id=pid)['clips'][0]
        self.assertEqual(row['source_title'], 'A talk')
        self.assertEqual(row['source_channel'], 'Someone')
        self.assertEqual(row['source_link'], 'https://www.youtube.com/watch?v=aaaaaaaaaaa&t=1s')
        self.assertIn('first idea', row['words'])
        saved = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'A clear title', 'description': 'What this is.\n\nMore.', 'tags': ['idea', 'Idea', 'talk'], 'thumbnail': 2}])
        self.assertNotIn('error', saved, saved)
        post = saved['posts'][0]
        line = 'Source: "A talk" by Someone - https://www.youtube.com/watch?v=aaaaaaaaaaa&t=1s'
        self.assertTrue(post['description'].endswith('\n\n' + line))
        self.assertEqual(post['tags'], ['idea', 'talk'])
        text = Path(post['post_text_path']).read_text()
        self.assertIn(line, text)
        self.assertIn('Nothing was published', text)
        record = json.loads(Path(post['post_json_path']).read_text())
        self.assertEqual((record['title'], record['uploaded']), ('A clear title', False))
        self.assertTrue(record['source_link'].endswith('&t=1s'))
        again = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'T', 'description': 'Already here.\n\n' + line}])['posts'][0]
        self.assertEqual(again['description'].count(line), 1)
        # a source title with angle brackets cannot leak them into the description
        info = Path(self.base / 'profile/plugin-data/creator-studio-clips/projects' / pid / 'project.json')
        data = json.loads(info.read_text())
        data['title'] = 'Evil <b>title</b>'
        info.write_text(json.dumps(data))
        text = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'T', 'description': 'ok'}])['posts'][0]['description']
        self.assertNotIn('<', text)
        self.assertNotIn('>', text)

    def test_validation(self):
        pid = self.youtube()
        self.call('clips_post_facts', project_id=pid)

        def save(**item):
            return self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'Fine', 'description': 'Fine', **item}])
        self.assertIn('limit is 100', save(title='x' * 101)['error'])
        self.assertIn('< or >', save(title='Use <b>')['error'])
        self.assertIn('< or >', save(description='a > b')['error'])
        self.assertIn('not be empty', save(title='  ')['error'].replace('and not empty', 'not be empty'))
        room = 5000 - len('\n\nSource: "A talk" by Someone - https://www.youtube.com/watch?v=aaaaaaaaaaa&t=1s')
        self.assertNotIn('error', save(description='y' * room))
        self.assertIn('credit line', save(description='y' * (room + 1))['error'])
        self.assertIn('comma', save(tags=['a,b'])['error'])
        self.assertIn('at most 15', save(tags=['t%d' % n for n in range(16)])['error'])
        self.assertIn('limit is 30', save(tags=['x' * 31])['error'])
        self.assertIn('no frame number', save(thumbnail=5)['error'] if len(self.call('clips_post_facts', project_id=pid, frames=3)['clips'][0]['frames']) < 5 else 'no frame number')
        self.assertIn('not both', save(thumbnail=1, at=2)['error'])
        self.assertIn('past the end', save(at=500)['error'])
        self.assertIn('error', save(bogus=1))
        self.assertIn('not cut yet', self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c9', 'title': 'x', 'description': 'y'}])['error'].replace('Unknown clip_id c9', 'not cut yet'))
        self.assertEqual(self.call('clips_post_save', project_id=pid, posts=[])['error'][:4], 'Give')
        first = save(thumbnail=1)['posts'][0]
        self.assertNotIn('error', first)
        self.call('clips_cut', project_id=pid, clip_ids=['c1'], captions='none', max_height=360)  # cut again: the frame numbers no longer match
        self.assertIn('cut again', save(thumbnail=1)['error'])

    def test_thumbnail_sizes_and_local_post_has_no_credit(self):
        from PIL import Image
        pid = self.local()
        facts = self.call('clips_post_facts', project_id=pid)['clips'][0]
        saved = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'Local', 'description': 'My own stream.', 'thumbnail': len(facts['frames'])}])['posts'][0]
        self.assertEqual(saved['description'], 'My own stream.')
        self.assertIsNone(saved['credit_line'])
        self.assertEqual(saved['thumbnail_size'], '1280x720')
        with Image.open(saved['thumbnail_path']) as image:
            self.assertEqual(image.size, (1280, 720))
        self.assertTrue(saved['thumbnail_path'].endswith('-thumb.jpg') and saved['post_text_path'].endswith('-post.txt'))
        # a clip with no thumbnail chosen is saved without one
        plain = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'Local', 'description': 'No picture.'}])['posts'][0]
        self.assertIn('No thumbnail', plain['thumbnail_note'])
        # a vertical clip keeps its own framing and is saved at 1080x1920
        vertical = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', framing='fit', captions='none')
        self.assertNotIn('error', vertical, vertical)
        vf = self.call('clips_post_facts', project_id=pid)['clips'][0]
        with Image.open(vf['frames'][0]['path']) as image:
            self.assertLess(image.width, image.height)
        done = self.call('clips_post_save', project_id=pid, posts=[{'clip_id': 'c1', 'title': 'Vertical', 'description': 'Tall.', 'at': 6}])['posts'][0]
        self.assertEqual(done['thumbnail_size'], '1080x1920')
        with Image.open(done['thumbnail_path']) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_tool_texts(self):
        for name in ('clips_post_facts', 'clips_post_save'):
            description = base.clip_studio.TOOLS[name][0]
            self.assertIn('nothing is uploaded', description.lower())
            self.assertNotIn(chr(0x2014), description)
        self.assertIn('untrusted', base.clip_studio.TOOLS['clips_post_facts'][0])


if __name__ == '__main__':
    unittest.main()
