"""Clip Studio: clipping the suite's own finished work. A fake plugin-data tree shaped the way the podcast, lesson and tutorial parts write their results; FFmpeg makes the media."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('creator_studio_suite_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite_pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite_pkg
spec.loader.exec_module(suite_pkg)
from creator_studio_suite_test import clip_studio  # noqa: E402
from creator_studio_suite_test.clip_studio import source as S, suite as X  # noqa: E402

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')
PODCAST, LESSON, JOB, NARRATED = 'a' * 32, 'b' * 32, 'c' * 32, 'd' * 32
SECONDS = 14


def srt(lines):
    return '\n'.join('%d\n00:00:%02d,000 --> 00:00:%02d,800\n%s\n' % (n, 1 + n * 3, 3 + n * 3, text) for n, text in enumerate(lines))


def make_audio(path):
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=%d' % SECONDS, '-ar', '24000', '-ac', '1', '-y', str(path)], check=True)


def make_video(path):
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%d' % SECONDS, '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25:duration=%d' % SECONDS,
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(path)], check=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.data = self.base / 'profile' / 'plugin-data'
        storage = types.ModuleType('plugins.plugin_storage')

        def plugin_data_dir(name):
            folder = self.data / name
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        storage.plugin_data_dir = plugin_data_dir
        for patcher in (mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage}),
                        mock.patch.dict(clip_studio._HANDLERS, {'clips_from_studio': X.handle}),  # the module is not in EXTENSIONS yet: load it explicitly
                        mock.patch.dict(clip_studio.TOOLS, dict(X.TOOLS))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def call(self, name, **args):
        return json.loads(clip_studio.invoke(name, args))

    def project(self, part, ident, data):
        folder = self.data / X.FOLDERS[part] / 'projects' / ident
        folder.mkdir(parents=True)
        (folder / 'project.json').write_text(json.dumps({'project_id': ident, **data}))
        return folder

    def podcast(self, captions=True, phase='assembled'):
        folder = self.project('podcast', PODCAST, {'kind': 'podcast', 'topic': 'Why bread rises', 'phase': phase, 'sections': [], 'sources': {}, 'assets': {}, 'created': 1.0,
                                                  'result': {'audio_path': str(self.data / X.FOLDERS['podcast'] / 'projects' / PODCAST / ('assembled-%s.wav' % ('e' * 32))), 'seconds': SECONDS, 'timeline': []}})
        make_audio(folder / ('assembled-%s.wav' % ('e' * 32)))
        if captions:   # what podcast_episode_files writes: one cue per sentence with the host name
            (folder / 'captions.srt').write_text(srt(['MAYA: Bread rises because yeast eats sugar.', 'SAM: And it breathes out carbon dioxide.', 'MAYA: Which puffs up the dough.', 'SAM: That is the whole trick.']))
        return folder

    def lesson(self):
        root = self.data / X.FOLDERS['lesson']
        folder = self.project('lesson', LESSON, {'kind': 'video', 'topic': 'Why the Moon has phases', 'phase': 'assembled', 'sections': [], 'sources': {}, 'assets': {}, 'created': 2.0,
                                                'result': {'audio_path': str(root / 'projects' / LESSON / 'assembled-x.wav'), 'seconds': SECONDS, 'captions_srt_path': str(root / 'projects' / LESSON / 'captions.srt'),
                                                           'captions_burned': True, 'caption_count': 4, 'video': {'output_path': str(root / ('%s.mp4' % ('f' * 32))), 'segment_id': 'f' * 32, 'duration_seconds': SECONDS}}})
        make_video(root / ('%s.mp4' % ('f' * 32)))
        (folder / 'captions.srt').write_text(srt(['The Moon looks different each night.', 'Sunlight always lights half of it.', 'We see more or less of that half.', 'That is a phase.']))
        return folder

    def tutorial(self):
        folder = self.data / X.FOLDERS['tutorial'] / JOB
        folder.mkdir(parents=True)
        (folder / 'state.json').write_text(json.dumps({'state': 'complete'}))
        make_video(folder / ('narrated-%s.mp4' % NARRATED))
        (folder / ('narrated-%s.srt' % NARRATED)).write_text(srt(['Open the settings panel.', 'Choose the display tab.', 'Pick a larger size.', 'Done.']))
        (folder / ('narrated-%s.json' % NARRATED)).write_text(json.dumps({'state': 'complete', 'path': str(folder / ('narrated-%s.mp4' % NARRATED)), 'captions': str(folder / ('narrated-%s.srt' % NARRATED)),
                                                                          'seconds': float(SECONDS), 'cues': [{'cue': 0, 'start': 1, 'end': 3, 'text': 'Open the settings panel.'}]}))
        return folder

    def everything(self):
        self.podcast(), self.lesson(), self.tutorial()


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class ListTests(Fixture):
    def test_lists_finished_items_of_all_three_parts(self):
        self.everything()
        out = self.call('clips_from_studio')
        self.assertEqual(out['count'], 3)
        by = {i['part']: i for i in out['items']}
        self.assertEqual(set(by), {'podcast', 'lesson', 'tutorial'})
        self.assertEqual(by['podcast']['id'], 'podcast:' + PODCAST)
        self.assertEqual(by['podcast']['title'], 'Why bread rises')
        self.assertEqual(by['podcast']['media'], 'audio only')
        self.assertTrue(by['podcast']['captions_path'].endswith('captions.srt'))
        self.assertEqual(by['lesson']['media'], 'video')
        self.assertEqual(by['lesson']['length'], '0:14')
        self.assertIn('already drawn', by['lesson']['note'])
        self.assertEqual(by['tutorial']['id'], 'tutorial:%s:%s' % (JOB, NARRATED))
        self.assertEqual(by['tutorial']['title'], 'Tutorial: Open the settings panel.')
        self.assertTrue(all(i['date'] and i['media_path'] and Path(i['media_path']).is_file() for i in out['items']))
        self.assertEqual([i['part'] for i in self.call('clips_from_studio', part='lesson')['items']], ['lesson'])
        self.assertIn('error', self.call('clips_from_studio', part='music'))

    def test_empty_profile_says_so(self):
        out = self.call('clips_from_studio')
        self.assertEqual((out['items'], out['count']), ([], 0))
        self.assertIn('Nothing finished', out['next'])

    def test_only_assembled_results_with_their_media_are_listed(self):
        self.podcast(phase='materials')                       # still being made: nothing recorded as finished
        self.assertEqual(self.call('clips_from_studio')['count'], 0)
        shutil.rmtree(self.data / X.FOLDERS['podcast'])
        folder = self.podcast()
        next(folder.glob('assembled-*.wav')).unlink()           # the recorded file is gone
        self.assertEqual(self.call('clips_from_studio')['count'], 0)
        job = self.tutorial()
        (job / ('narrated-%s.json' % NARRATED)).write_text(json.dumps({'state': 'needs_timing_revision'}))   # narration did not finish
        self.assertEqual(self.call('clips_from_studio')['count'], 0)

    def test_paths_that_are_not_the_parts_own_files_are_not_listed(self):
        folder = self.podcast()
        meta = folder / 'project.json'
        data = json.loads(meta.read_text())
        outside = self.base / 'secret.wav'
        make_audio(outside)
        data['result']['audio_path'] = str(outside)             # recorded path outside the part's folder
        meta.write_text(json.dumps(data))
        self.assertEqual(self.call('clips_from_studio')['count'], 0)
        data['result']['audio_path'] = str(folder / ('assembled-%s.wav' % ('e' * 32)))
        meta.write_text(json.dumps(data))
        self.assertEqual(self.call('clips_from_studio')['count'], 1)
        wav = folder / ('assembled-%s.wav' % ('e' * 32))
        wav.unlink()
        os.symlink(outside, wav)                                # a link to a file elsewhere
        self.assertEqual(self.call('clips_from_studio')['count'], 0)
        lesson = self.lesson()
        data = json.loads((lesson / 'project.json').read_text())
        data['result']['video']['output_path'] = str(outside.with_suffix('.mp4'))
        (lesson / 'project.json').write_text(json.dumps(data))
        self.assertEqual(self.call('clips_from_studio', part='lesson')['count'], 0)

    def test_an_item_that_was_not_recorded_cannot_be_opened(self):
        self.everything()
        stray = self.data / X.FOLDERS['lesson'] / ('%s.mp4' % ('9' * 32))   # a finished-looking file nobody recorded
        make_video(stray)
        for bad in ('lesson:' + '9' * 32, 'podcast:' + 'b' * 32, 'podcast:../../etc/passwd', '/etc/passwd', 'tutorial:%s:%s' % (JOB, 'e' * 32), 'podcast:' + PODCAST + '/..', 5):
            self.assertIn('error', self.call('clips_from_studio', item_id=bad), bad)
        # the ordinary route still refuses private places for files of your own
        self.assertEqual(self.call('clips_status')['projects'], [])


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class OpenTests(Fixture):
    def facts(self, path):
        return S.probe(path)

    def test_podcast_episode_opens_with_its_captions_and_is_clipped_as_video(self):
        self.podcast()
        opened = self.call('clips_from_studio', item_id='podcast:' + PODCAST)
        self.assertNotIn('error', opened, opened)
        self.assertEqual(opened['title'], 'Why bread rises')
        self.assertIn('audio only', opened['audio_only'])
        self.assertIn('waveform', opened['audio_only'])
        self.assertEqual(opened['transcript']['timing'], 'each caption line')
        self.assertIn('captions.srt', opened['transcript']['from'])
        self.assertIn('not word-aligned', opened['transcript_note'])
        pid = opened['project_id']
        self.assertFalse(self.call('clips_status', project_id=pid).get('error'))
        self.assertIn('MAYA', json.dumps(self.call('clips_transcript', project_id=pid)))
        self.call('clips_propose', project_id=pid, clips=[{'start': 3, 'end': 11, 'title': 'The yeast trick', 'exact': True}])
        for shape, size in (('vertical', (1080, 1920)), ('square', (1080, 1080)), ('source', (1280, 720))):
            cut = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape=shape, captions='file')
            self.assertNotIn('error', cut, cut)
            clip = cut['clips'][0]
            facts = self.facts(clip['video_path'])
            self.assertTrue(facts['video'] and facts['audio'], (shape, facts))
            self.assertEqual((facts['width'], facts['height']), size, shape)
            self.assertAlmostEqual(facts['duration'], 8, delta=0.6)
            self.assertTrue(clip['video_path'].endswith('.mp4'))
            self.assertEqual(clip.get('face_layout'), None if shape == 'source' else 'audio with a generated picture (title and waveform)')
            self.assertTrue(Path(clip['captions_path']).is_file())

    def test_the_generated_picture_shows_the_title_and_a_waveform(self):
        self.podcast()
        pid = self.call('clips_from_studio', item_id='podcast:' + PODCAST)['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 3, 'end': 9, 'title': 'The yeast trick', 'exact': True}])
        path = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none')['clips'][0]['video_path']

        def pixels(x, y, w, h, at):
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', path, '-frames:v', '1', '-vf', 'crop=%d:%d:%d:%d,format=gray' % (w, h, x, y), '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
            return raw
        self.assertEqual(pixels(5, 1900, 4, 4, 2)[0] < 60, True)                   # dark plain picture at the bottom edge
        title = pixels(80, 190, 920, 120, 2)                                      # light text pixels in the title area
        self.assertGreater(max(title), 180)
        wave = pixels(0, 1200, 1080, 480, 2)                                       # the waveform draws bright pixels in its band
        self.assertGreater(sum(1 for v in wave if v > 120), 300)

    def test_podcast_without_captions_takes_the_no_transcript_route(self):
        self.podcast(captions=False)
        item = self.call('clips_from_studio')['items'][0]
        self.assertIsNone(item['captions_path'])
        self.assertIn('podcast_episode_files', item['note'])
        opened = self.call('clips_from_studio', item_id=item['id'])
        self.assertNotIn('transcript', opened)
        self.assertIn('clips_transcribe', opened['next'])
        self.assertIn('podcast_episode_files', opened['item_note'])
        pid = opened['project_id']
        self.assertIn('error', self.call('clips_outline', project_id=pid))
        self.call('clips_propose', project_id=pid, clips=[{'start': 2, 'end': 8, 'title': 'By the clock', 'exact': True}])   # times the user gave need no transcript
        cut = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none')['clips'][0]
        self.assertEqual((cut['width'], cut['height']), (1080, 1920))
        self.assertIn('error', self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='burned'))

    def test_opening_twice_gives_the_same_project_and_keeps_its_transcript(self):
        self.podcast()
        first = self.call('clips_from_studio', item_id='podcast:' + PODCAST)
        second = self.call('clips_from_studio', item_id='podcast:' + PODCAST)
        self.assertEqual(first['project_id'], second['project_id'])
        self.assertTrue(second.get('reopened'))
        self.assertEqual(second['transcript']['sentences'], first['transcript']['sentences'])

    def test_lesson_video_opens_and_cuts_with_its_picture(self):
        self.lesson()
        opened = self.call('clips_from_studio', item_id='lesson:' + LESSON)
        self.assertNotIn('error', opened, opened)
        self.assertNotIn('audio_only', opened)
        self.assertIn('already drawn', opened['item_note'])
        self.assertEqual(opened['title'], 'Why the Moon has phases')
        pid = opened['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 9, 'title': 'Half lit', 'exact': True}])
        clip = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none')['clips'][0]
        self.assertEqual((clip['width'], clip['height']), (1080, 1920))
        self.assertIn('no face box', clip['face_layout'])           # a real picture: the ordinary layouts apply
        self.assertTrue(self.call('clips_frame', project_id=pid, at=3)['frame_path'])

    def test_tutorial_opens_with_its_narration_captions(self):
        self.tutorial()
        opened = self.call('clips_from_studio', item_id='tutorial:%s:%s' % (JOB, NARRATED))
        self.assertNotIn('error', opened, opened)
        self.assertEqual(opened['transcript']['sentences'], 4)
        self.assertIn('narrated-%s.srt' % NARRATED, opened['transcript']['from'])
        self.assertTrue(opened['title'].startswith('Tutorial: Open the settings panel'))

    def test_a_file_of_your_own_still_opens_through_clips_open_and_audio_still_needs_no_picture_there(self):
        wav = self.base / 'mine.wav'
        make_audio(wav)
        pid = self.call('clips_open', media_path=str(wav))['project_id']
        self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 6, 'title': 'Mine', 'exact': True}])
        self.assertIn('error', self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='vertical', captions='none'))     # unchanged: no picture, no vertical
        cut = self.call('clips_cut', project_id=pid, clip_ids=['c1'], shape='source', captions='none')['clips'][0]
        self.assertTrue(cut['audio_path'].endswith('.m4a'))


class RegistrationTests(unittest.TestCase):
    def test_tool_table_matches_the_extension_hook_and_the_parts_folders(self):
        self.assertEqual(set(X.TOOLS), {'clips_from_studio'})
        name, (description, properties, required) = next(iter(X.TOOLS.items()))
        self.assertEqual(required, [])
        self.assertEqual(set(properties), {'item_id', 'part'})
        self.assertTrue(description.isascii())
        from creator_studio_suite_test import podcast_studio, tutorial_creator, youtube_studio
        self.assertEqual(X.FOLDERS, {'podcast': podcast_studio.STORAGE_NAMESPACE, 'lesson': youtube_studio.STORAGE_NAMESPACE, 'tutorial': tutorial_creator.STORAGE_NAMESPACE})


if __name__ == '__main__':
    unittest.main()
