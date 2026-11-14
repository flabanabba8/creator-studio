"""Clip Studio: transcript parsing, cut-point snapping, project flow. No network: YouTube is replaced by a fake; FFmpeg makes tiny real media."""
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
spec = importlib.util.spec_from_file_location('creator_studio_clip_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_clip_test import clip_studio  # noqa: E402
from creator_studio_clip_test.clip_studio import project as P, source as S, transcript as T  # noqa: E402

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')
SENTENCES = ['This is the first idea.', 'Here comes a second thought, and it runs on.', 'Why does it matter?', 'Because the answer is short.', 'That is all for today.']


def word_track(gap_after=(2,)):
    """json3 the way YouTube's speech recognition writes it: one event per line, words with offsets. A pause of over 3 s follows sentence index 2."""
    events, at = [{'tStartMs': 0, 'dDurationMs': 99999, 'id': 1}], 1000
    for n, sentence in enumerate(SENTENCES):
        segs, offset = [], 0
        for k, word in enumerate(sentence.split()):
            segs.append({'utf8': (' ' if k else '') + word, **({'tOffsetMs': offset} if k else {})})
            offset += 400
        events.append({'tStartMs': at, 'dDurationMs': offset + 2000, 'segs': segs})
        events.append({'tStartMs': at + offset - 10, 'dDurationMs': 100, 'aAppend': 1, 'segs': [{'utf8': '\n'}]})
        at += offset + (4000 if n in gap_after else 100)
    return json.dumps({'events': events})


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.kind, self.units = T.parse(word_track(), '.json3')
        self.segs = T.segments(self.kind, self.units)

    def test_word_track_gives_word_times_and_sentences(self):
        self.assertEqual(self.kind, 'words')
        self.assertEqual([s['t'] for s in self.segs], SENTENCES)
        self.assertEqual(self.units[0], {'s': 1000, 'e': 1400, 't': 'This'})
        self.assertTrue(all(a['e'] <= b['s'] for a, b in zip(self.units, self.units[1:])))

    def test_uploader_track_is_cues(self):
        kind, units = T.parse(json.dumps({'events': [{'tStartMs': 1200, 'dDurationMs': 2000, 'segs': [{'utf8': 'Hello\nthere &amp; welcome'}]}, {'tStartMs': 4000, 'dDurationMs': 0, 'segs': [{'utf8': 'x'}]}]}), '.json3')
        self.assertEqual((kind, units), ('cues', [{'s': 1200, 'e': 3200, 't': 'Hello there & welcome'}]))

    def test_rolling_vtt_is_read_once_per_word(self):
        vtt = ('WEBVTT\nKind: captions\n\n00:00:01.000 --> 00:00:03.000 align:start position:0%\n \nhello<00:00:01.400><c> big</c><00:00:01.900><c> world</c>\n\n'
               '00:00:03.000 --> 00:00:03.010 align:start position:0%\nhello big world\n \n\n00:00:03.010 --> 00:00:05.000 align:start position:0%\nhello big world\nagain<00:00:03.500><c> now</c>\n')
        kind, units = T.parse(vtt, '.vtt')
        self.assertEqual(kind, 'words')
        self.assertEqual([(u['s'], u['t']) for u in units], [(1000, 'hello'), (1400, 'big'), (1900, 'world'), (3010, 'again'), (3500, 'now')])

    def test_srt_cues_and_sentence_merge(self):
        kind, units = T.parse('1\n00:00:01,000 --> 00:00:02,000\nOne half\n\n2\n00:00:02,000 --> 00:00:03,000\n<i>and the rest.</i>\n\n3\n00:00:03,100 --> 00:00:04,000\nNext.\n', '.srt')
        self.assertEqual(kind, 'cues')
        self.assertEqual([s['t'] for s in T.segments(kind, units)], ['One half and the rest.', 'Next.'])

    def test_empty_or_wrong_input_is_refused(self):
        for bad in ('WEBVTT\n\n', '{"events": []}', 'just words'):
            with self.assertRaises(ValueError):
                T.parse(bad)

    def test_clock_times_are_accepted(self):
        self.assertEqual([T.seconds(x) for x in (90, '1:30', '0:01:30.5', '12.25')], [90.0, 90.0, 90.5, 12.25])
        for bad in ('soon', True, -1, '1:2:3:4', None):
            with self.assertRaises(ValueError):
                T.seconds(bad)

    def test_snap_moves_to_sentence_edges_and_never_into_a_word(self):
        second, third = self.segs[1], self.segs[2]
        s, e = T.snap(self.kind, self.units, self.segs, second['s'] + 650, third['e'] - 950)
        self.assertLessEqual(s, second['s'])
        self.assertGreaterEqual(s, self.segs[0]['e'])  # padding stops before the previous word
        self.assertGreaterEqual(e, third['e'])
        self.assertLessEqual(e, third['e'] + 250)
        self.assertEqual(T.text_between(self.units, s, e), SENTENCES[1] + ' ' + SENTENCES[2])
        s, e = T.snap(self.kind, self.units, self.segs, second['s'] + 800, third['e'])  # a start given exactly on a word edge is kept
        self.assertEqual(T.text_between(self.units, s, e).split()[0], 'a')

    def test_search_page_and_outline(self):
        self.assertEqual([h['text'] for h in T.search(self.segs, 'the ANSWER is')], [SENTENCES[3]])
        self.assertEqual(T.search(self.segs, 'matter because')[0]['text'], SENTENCES[2] + ' ' + SENTENCES[3])  # across two sentences
        self.assertEqual(T.search(self.segs, 'zebra'), [])
        page = T.page(self.segs, start=0, end=None, max_chars=60)
        self.assertEqual(len(page['sentences']), 1)
        self.assertEqual(page['continue_from'], round(self.segs[1]['s'] / 1000, 2))
        out = T.outline(self.segs, 30000, [{'start_time': 0, 'end_time': 30, 'title': 'Only'}], [{'start_time': 0, 'end_time': 3, 'value': 1.0}, {'start_time': 9, 'end_time': 12, 'value': 0.8}])
        self.assertEqual(out['rows'][0]['chapter'], 'Only')
        self.assertEqual(out['rows'][0]['questions'], 1)
        self.assertEqual([p['start'] for p in out['signals']['most_replayed']], [9])  # the opening seconds are ignored
        self.assertEqual(len(out['signals']['longest_pauses']), 1)

    def test_clip_captions_start_at_zero(self):
        seg = self.segs[1]
        srt = T.clip_srt(self.kind, self.units, seg['s'] - 100, seg['e'], 22)
        self.assertTrue(srt.startswith('1\n00:00:00,100 --> '))
        self.assertEqual(' '.join(l for l in srt.splitlines() if l and '-->' not in l and not l.isdigit()), SENTENCES[1])


class LinkTests(unittest.TestCase):
    def test_video_links(self):
        for link in ('https://www.youtube.com/watch?v=aaaaaaaaaaa&list=PLx&t=30s', 'youtu.be/aaaaaaaaaaa?si=x', 'https://youtube.com/shorts/aaaaaaaaaaa',
                     'https://www.youtube.com/live/aaaaaaaaaaa', 'https://m.youtube.com/watch?v=aaaaaaaaaaa', 'aaaaaaaaaaa'):
            self.assertEqual(S.video_id(link), 'aaaaaaaaaaa', link)

    def test_other_links_are_refused(self):
        for link in ('https://www.youtube.com/playlist?list=PL123', 'https://www.youtube.com/@channel', 'https://example.com/watch?v=aaaaaaaaaaa', 'https://youtube.com.evil.example/watch?v=aaaaaaaaaaa',
                     'file:///etc/passwd', 'https://youtu.be/--exec=whoami', '--config-location=/tmp/x', 'https://www.youtube.com/watch?v=short', 7):
            with self.assertRaises(ValueError, msg=str(link)):
                S.video_id(link)

    def test_track_choice(self):
        auto = {'en': [1], 'en-orig': [1], 'de': [1]}
        self.assertEqual(P.pick_track({'subtitles': {'en': [1], 'live_chat': [1]}, 'automatic_captions': auto})[:2], ('en', False))
        self.assertEqual(P.pick_track({'subtitles': {'live_chat': [1]}, 'automatic_captions': auto})[:2], ('en-orig', True))
        self.assertEqual(P.pick_track({'subtitles': {'fr': [1]}, 'automatic_captions': auto, 'language': 'en-US'})[:2], ('en-orig', True))
        self.assertEqual(P.pick_track({'automatic_captions': auto}, 'de')[2], 'YouTube machine translation of its speech recognition')
        self.assertEqual(P.pick_track({'subtitles': {}, 'automatic_captions': {}}), (None, False, None))

    def test_private_and_profile_files_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder in ('.ssh', '.hermes'):
                (Path(tmp) / folder).mkdir()
                (Path(tmp) / folder / 'a.srt').write_text('x')
                with self.assertRaises(ValueError):
                    S.local_media(Path(tmp) / folder / 'a.srt')
            (Path(tmp) / 'link.srt').symlink_to(Path(tmp) / '.ssh' / 'a.srt')
            with self.assertRaises(ValueError):
                S.local_media(Path(tmp) / 'link.srt')


def make_media(path, seconds, picture=True):
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%s' % seconds]
    if picture:
        args += ['-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25:duration=%s' % seconds, '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']
    subprocess.run(args + ['-c:a', 'aac', '-y', str(path)], check=True)


class FakeYouTube:
    calls = []
    status = 'not_live'
    subtitles = True

    def __init__(self, settings=None):
        pass

    def info(self, vid):
        self.calls.append(('info', vid))
        return {'id': vid, 'title': 'A talk', 'channel': 'Someone', 'duration': 30, 'live_status': self.status, 'language': 'en',
                'chapters': [{'start_time': 0, 'end_time': 30, 'title': 'All of it'}], 'heatmap': [{'start_time': 9, 'end_time': 12, 'value': 0.9}],
                'subtitles': {'live_chat': [1]}, 'automatic_captions': {'en-orig': [1], 'en': [1]} if self.subtitles else {}, 'formats': [{'url': 'https://signed.example/secret'}]}

    def captions(self, vid, track, automatic, folder):
        self.calls.append(('captions', track, automatic))
        path = Path(folder) / 'captions.json3'
        path.write_text(word_track())
        return path

    def audio(self, vid, folder):
        self.calls.append(('audio', vid))
        path = Path(folder) / 'audio.m4a'
        path.write_bytes(b'sound')
        return path

    def section(self, vid, start, end, max_height, target):
        self.calls.append(('section', round(start, 2), round(end, 2), max_height))
        make_media(target, end - start)
        return Path(target)


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
        FakeYouTube.calls, FakeYouTube.status, FakeYouTube.subtitles = [], 'not_live', True
        for patcher in (mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage}), mock.patch.object(S, 'YouTube', FakeYouTube)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def call(self, name, **args):
        return json.loads(clip_studio.invoke(name, args))


class ProjectTests(Fixture):
    def test_bad_requests_return_plain_errors_without_network(self):
        self.assertIn('Only YouTube video links', self.call('clips_open', url='https://vimeo.com/1')['error'])
        self.assertIn('either', self.call('clips_open')['error'])
        self.assertIn('Unknown project_id', self.call('clips_outline', project_id='../../etc')['error'])
        self.assertEqual(FakeYouTube.calls, [])

    def test_open_reads_page_and_recognized_captions_only(self):
        out = self.call('clips_open', url='https://youtu.be/aaaaaaaaaaa')
        self.assertEqual(out['transcript']['from'], 'YouTube speech recognition')
        self.assertEqual(out['transcript']['timing'], 'each word')
        self.assertEqual(FakeYouTube.calls, [('info', 'aaaaaaaaaaa'), ('captions', 'en-orig', True)])
        saved = (self.base / 'profile/plugin-data/creator-studio-clips/projects' / out['project_id'] / 'project.json').read_text()
        self.assertNotIn('signed.example', saved)  # stream addresses are never stored
        again = self.call('clips_open', url='https://www.youtube.com/watch?v=aaaaaaaaaaa')
        self.assertTrue(again['reopened'])
        self.assertEqual(again['project_id'], out['project_id'])
        self.assertEqual(len(FakeYouTube.calls), 2)

    def test_outline_read_and_search(self):
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        outline = self.call('clips_outline', project_id=pid)
        self.assertEqual(outline['signals']['most_replayed'][0]['start'], 9)
        self.assertEqual(self.call('clips_transcript', project_id=pid, start=0, end='0:03')['sentences'][0]['text'], SENTENCES[0])
        self.assertEqual(self.call('clips_transcript', project_id=pid, query='second thought')['matches'][0]['text'], SENTENCES[1])

    def test_propose_snaps_edits_and_validates(self):
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        segs = T.segments(*T.parse(word_track(), '.json3'))
        first = self.call('clips_propose', project_id=pid, clips=[{'start': segs[1]['s'] / 1000 + 0.6, 'end': segs[2]['e'] / 1000 - 0.5, 'title': 'The question', 'reason': 'It asks and sets up.'}])
        clip = first['clips'][0]
        self.assertEqual((clip['clip_id'], clip['opens_with'].split()[0], clip['ends_with'].split()[-1]), ('c1', 'Here', 'matter?'))
        self.assertTrue(clip['moved_to_speech_boundaries'])
        self.assertIn('watch?v=aaaaaaaaaaa&t=', clip['preview'])
        exact = self.call('clips_propose', project_id=pid, clips=[{'clip_id': 'c1', 'start': 2, 'end': '0:07', 'title': 'Exact', 'exact': True}])['clips'][0]
        self.assertEqual((exact['clip_id'], exact['start'], exact['end']), ('c1', 2.0, 7.0))
        self.assertEqual(len(self.call('clips_status', project_id=pid)['clips']), 1)
        for bad in ([{'start': 5, 'end': 5.5, 'title': 'too short', 'exact': True}], [{'start': 9, 'end': 3, 'title': 'backwards'}], [{'start': 100, 'end': 120, 'title': 'past the end'}],
                    [{'start': 1, 'end': 9, 'title': ''}], [{'clip_id': 'c9', 'start': 1, 'end': 9, 'title': 'unknown'}], []):
            self.assertIn('error', self.call('clips_propose', project_id=pid, clips=bad), bad)
        self.assertFalse(any(c[0] == 'section' for c in FakeYouTube.calls))  # proposing downloads nothing

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_cut_vertical_with_burned_captions(self):
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 7, 'title': 'Opening: "idea"!'}])
        out = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='burned', max_height=720)
        self.assertNotIn('error', out, out)
        clip = out['clips'][0]
        self.assertEqual((clip['width'], clip['height'], clip['captions']), (1080, 1920, 'burned'))
        video = Path(clip['video_path'])
        self.assertEqual(video.name, 'c1-opening-idea-vertical.mp4')
        self.assertAlmostEqual(S.probe(video)['duration'], clip['seconds'], delta=0.1)
        self.assertIn('This is the first idea.', ' '.join(l for l in Path(clip['captions_path']).read_text().splitlines() if l and '-->' not in l and not l.isdigit()))
        self.assertEqual([c for c in FakeYouTube.calls if c[0] == 'section'][0][3], 720)
        self.assertEqual(list(video.parent.parent.glob('work-*')), [])
        status = self.call('clips_status', project_id=pid)['clips'][0]['cut']
        self.assertTrue(status['file_present'])
        self.call('clips_propose', project_id=pid, clips=[{'clip_id': 'c1', 'start': 1, 'end': 9, 'title': 'Longer'}])
        self.assertNotIn('cut', self.call('clips_status', project_id=pid)['clips'][0])  # new times: the old file no longer counts

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_short_download_is_refused(self):
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 12, 'title': 'Long', 'exact': True}])
        with mock.patch.object(FakeYouTube, 'section', lambda self, vid, start, end, h, target: (make_media(target, 3), Path(target))[1]):
            out = self.call('clips_cut', project_id=pid, clip_ids=['c1'])
        self.assertIn('instead of 11.0', out['error'])
        self.assertEqual(list((self.base / 'profile/plugin-data/creator-studio-clips/projects' / pid / 'clips').glob('*')), [])

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_dead_air_and_skipped_stretch_are_removed_and_captions_follow(self):
        # 14 s recording: tone 0-3, silence 3-6, tone 6-14; captions say three things
        media, srt = self.base / 'talk.mp4', self.base / 'talk.srt'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', "sine=frequency=440:duration=14,volume='if(between(t,3,6),0,1)':eval=frame",
                        '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25:duration=14', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(media)], check=True)
        srt.write_text('1\n00:00:00,500 --> 00:00:02,800\nFirst the setup.\n\n2\n00:00:06,200 --> 00:00:09,000\nThen a long tangent.\n\n3\n00:00:09,200 --> 00:00:13,000\nAnd the payoff.\n')
        pid = self.call('clips_open', media_path=str(media))['project_id']
        self.call('clips_use_transcript', project_id=pid, transcript_path=str(srt))
        plain = self.call('clips_propose', project_id=pid, clips=[{'start': 0.3, 'end': 13.2, 'title': 'Whole', 'exact': True}])['clips'][0]
        tight = self.call('clips_cut', project_id=pid, clip_ids=['c1'], remove_pauses=True)['clips'][0]
        self.assertEqual(tight['trimmed']['pauses_removed'], 1)
        self.assertAlmostEqual(tight['seconds'], plain['duration'] - 2.7, delta=0.4)  # 3 s of silence shortened to a 0.3 s breath
        cues = Path(tight['captions_path']).read_text()
        self.assertIn('00:00:00,200 --> 00:00:02,500', cues)   # before the pause: only the clip start is subtracted
        self.assertIn('\n00:00:03,2', cues)                    # after it: 2.7 s earlier than 5.9 s
        edited = self.call('clips_propose', project_id=pid, clips=[{'clip_id': 'c1', 'start': 0.3, 'end': 13.2, 'title': 'No tangent', 'exact': True, 'skip': [{'start': 6.0, 'end': '0:09'}]}])['clips'][0]
        self.assertEqual(edited['skip'][0]['drops'], 'Then a long tangent.')
        out = self.call('clips_cut', project_id=pid, clip_ids=['c1'], remove_pauses=True, captions='burned')['clips'][0]
        self.assertEqual(out['trimmed']['stretches_skipped'], 1)
        self.assertAlmostEqual(out['seconds'], edited['duration'] - 2.7, delta=0.5)
        text = Path(out['captions_path']).read_text()
        self.assertNotIn('tangent', text)
        self.assertIn('And the payoff.', text)
        facts = S.probe(out['video_path'])
        self.assertTrue(facts['video'] and facts['audio'])
        for bad in ([{'start': 0.1, 'end': 5}], [{'start': 7, 'end': 20}], [{'start': 6, 'end': 9}, {'start': 8, 'end': 12.5}]):
            self.assertIn('error', self.call('clips_propose', project_id=pid, clips=[{'clip_id': 'c1', 'start': 0.3, 'end': 13.2, 'title': 'Bad', 'exact': True, 'skip': bad}]), bad)
        self.assertIn('error', self.call('clips_cut', project_id=pid, clip_ids=['c1'], remove_pauses=True, max_pause=0.1))

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_frame_grid_and_face_layouts(self):
        media = self.base / 'vt.mp4'
        # blue picture with a red "avatar" in the bottom-right corner (x 75-100 %, y 60-100 %)
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=6', '-f', 'lavfi', '-i', 'color=c=blue:size=640x360:rate=25:duration=6',
                        '-vf', 'drawbox=x=480:y=216:w=160:h=144:color=red:t=fill', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(media)], check=True)
        pid = self.call('clips_open', media_path=str(media))['project_id']
        shot = self.call('clips_frame', project_id=pid, at=2)
        self.assertEqual((shot['width'], shot['height']), (640, 360))
        self.assertTrue(Path(shot['grid_path']).is_file() and Path(shot['frame_path']).is_file())
        for bad in ({'left': 80, 'top': 60, 'width': 30, 'height': 40}, {'left': 0, 'top': 0, 'width': 2, 'height': 50}, {'left': '10', 'top': 0, 'width': 20, 'height': 20}):
            self.assertIn('error', self.call('clips_face', project_id=pid, **bad), bad)
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 5, 'title': 'Corner', 'exact': True}])

        def colour(path, x, y):
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '1', '-i', path, '-frames:v', '1', '-vf', 'crop=4:4:%d:%d,scale=1:1' % (x, y), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
            return 'red' if raw[0] > 150 and raw[2] < 100 else 'blue' if raw[2] > 150 and raw[0] < 100 else 'other'
        plain = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', framing='crop', captions='none')['clips'][0]
        self.assertIn('no face box', plain['face_layout'])
        self.assertEqual(colour(plain['video_path'], 540, 300), 'blue')        # a centre crop loses the corner avatar
        self.assertEqual(self.call('clips_face', project_id=pid, left=75, top=60, width=25, height=40)['face']['left'], 75.0)
        stacked = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none')['clips'][0]
        self.assertIn('panel on top', stacked['face_layout'])
        self.assertEqual((stacked['width'], stacked['height']), (1080, 1920))
        self.assertEqual(colour(stacked['video_path'], 540, 300), 'red')       # the avatar fills the top panel
        self.assertEqual(colour(stacked['video_path'], 200, 1300), 'blue')     # the picture is below it
        big = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none', face={'left': 60, 'top': 20, 'width': 40, 'height': 80})['clips'][0]
        self.assertIn('one panel', big['face_layout'])
        self.assertEqual(colour(big['video_path'], 900, 1700), 'red')          # cropped around the right side, where the avatar is
        self.assertEqual(self.call('clips_status', project_id=pid)['face']['width'], 40.0)

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_dead_air_is_found_under_background_music(self):
        # a steady quiet "music" tone all the way through, a loud "voice" tone at 0-3 s and 6-10 s: never silent, but 3 s without voice
        media = self.base / 'music.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=10', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=10',
                        '-filter_complex', "[0]volume=0.05[m];[1]volume='if(between(t,3,6),0,0.8)':eval=frame[v];[m][v]amix=inputs=2:normalize=0", '-c:a', 'aac', '-y', str(media)], check=True)
        found, why = S.quiet_spans(media, 0.7, [(0.2, 2.9), (6.1, 9.8)])
        self.assertIsNone(why)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0][0], 3.0, delta=0.2)
        self.assertAlmostEqual(found[0][1], 6.0, delta=0.2)
        inside_word, _ = S.quiet_spans(media, 0.7, [(0.2, 4.5), (6.1, 9.8)])  # the transcript says a word runs to 4.5 s: it is not cut into
        self.assertGreaterEqual(inside_word[0][0], 4.5)
        flat = self.base / 'flat.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=6', '-c:a', 'aac', '-y', str(flat)], check=True)
        self.assertEqual(S.quiet_spans(flat, 0.7)[0], [])
        self.assertIn('not clearly louder', S.quiet_spans(flat, 0.7)[1])

    def test_stream_on_air_and_missing_captions(self):
        FakeYouTube.status, FakeYouTube.subtitles = 'is_live', False
        out = self.call('clips_open', url='aaaaaaaaaaa')
        self.assertIn('no captions', out['no_captions'])
        self.assertIn('still on air', out['live_note'])
        self.assertIn('no transcript yet', self.call('clips_outline', project_id=out['project_id'])['error'])
        self.assertIn('still on air', self.call('clips_transcribe', project_id=out['project_id'])['error'])
        FakeYouTube.status, FakeYouTube.subtitles = 'was_live', True
        later = self.call('clips_open', url='aaaaaaaaaaa', refresh=True)
        self.assertEqual((later['project_id'], later['live']), (out['project_id'], 'recorded live stream'))
        self.assertIn('transcript', later)

    def test_transcribe_returns_the_interview_before_fetching_any_audio(self):
        FakeYouTube.subtitles = False
        pid = self.call('clips_open', url='aaaaaaaaaaa')['project_id']
        seen = []

        def fake(name, args, ctx=None, **context):
            seen.append((name, args))
            return json.dumps({'state': 'interview_needed', 'questions': ['which recognizer?']})
        with mock.patch.object(suite.caption_studio, 'invoke', fake):
            first = self.call('clips_transcribe', project_id=pid)
        self.assertIn('recognizer_interview', first)
        self.assertIn('Do not guess', first['next'])
        self.assertEqual([c[0] for c in seen], ['captions_recognizer_setup'])
        self.assertEqual([c[0] for c in FakeYouTube.calls].count('audio'), 0)  # nothing is fetched before the user has chosen

    @unittest.skipUnless(FFMPEG, 'needs ffmpeg')
    def test_local_recording_with_own_captions(self):
        media, srt = self.base / 'stream.mp4', self.base / 'stream.srt'
        make_media(media, 12)
        srt.write_text('1\n00:00:01,000 --> 00:00:03,000\nWelcome back to the stream.\n\n2\n00:00:04,000 --> 00:00:07,500\nToday we fix the bug.\n')
        opened = self.call('clips_open', media_path=str(media))
        pid = opened['project_id']
        self.assertEqual((opened['kind'], opened['duration']), ('file', 12.0))
        self.assertIn('error', self.call('clips_use_transcript', project_id=pid, transcript_path=str(media)))
        self.assertEqual(self.call('clips_use_transcript', project_id=pid, transcript_path=str(srt))['transcript']['sentences'], 2)
        self.call('clips_propose', project_id=pid, clips=[{'start': 3.8, 'end': 7.4, 'title': 'The fix'}])
        out = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='square', framing='fit', captions='file')
        self.assertNotIn('error', out, out)
        clip = out['clips'][0]
        self.assertEqual((clip['width'], clip['height']), (1080, 1080))
        self.assertAlmostEqual(clip['seconds'], 3.9, delta=0.3)
        self.assertIn('Today we fix the bug.', Path(clip['captions_path']).read_text())
        self.assertEqual(FakeYouTube.calls, [])
        fixed = self.base / 'fixed.srt'
        fixed.write_text('1\n00:00:00,300 --> 00:00:03,500\nToday we fix THE bug.\n')
        burned = self.call('clips_burn', project_id=pid, clip_id='c1', captions_path=str(fixed))
        self.assertNotIn('error', burned, burned)
        self.assertTrue(burned['video_path'].endswith('-captioned.mp4') and Path(burned['video_path']).is_file() and Path(burned['clean_copy']).is_file())
        late = self.base / 'late.srt'
        late.write_text('1\n00:01:00,000 --> 00:01:02,000\nNot this clip.\n')
        self.assertIn('past the end', self.call('clips_burn', project_id=pid, clip_id='c1', captions_path=str(late))['error'])
        media.write_bytes(media.read_bytes() + b'changed')
        self.assertIn('changed since', self.call('clips_cut', project_id=pid, clip_ids=['c1'])['error'])


if __name__ == '__main__':
    unittest.main()
