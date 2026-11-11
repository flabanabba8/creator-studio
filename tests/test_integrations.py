"""Cross-part features: caption what the suite just made; podcast from a finished lesson's saved research. No network, no speech."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('creator_studio_integration_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_integration_test import caption_studio, podcast_studio  # noqa: E402
from creator_studio_integration_test.podcast_studio.media_project import MediaProject  # noqa: E402

BODY = 'Rayleigh scattering sends blue light in every direction. ' * 40
TIMELINE = [{'title': 'Why', 'start': 0, 'end': 4, 'source_ids': [], 'turns': [
    {'speaker': 'A', 'text': 'The sky is blue.', 'start': 0, 'end': 2.0}, {'speaker': 'B', 'text': 'Because of scattering.', 'start': 2.0, 'end': 4.0}]}]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.dirs = {n: self.base / n for n in ('creator-studio-youtube', 'creator-studio-podcast', 'creator-studio-tutorial')}
        for d in self.dirs.values():
            d.mkdir()
        storage = types.ModuleType('plugins.plugin_storage')
        storage.plugin_data_dir = lambda name: self.dirs[name]
        patcher = mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def project(self, ns, kind, pid, topic, media_name, assembled=True, sources=None, age=0):
        folder = self.dirs[ns] / 'projects' / pid
        folder.mkdir(parents=True)
        media = folder / media_name
        media.write_bytes(b'media')
        result = {'timeline': TIMELINE, 'audio_path': str(media)}
        if kind == 'video':
            result['video'] = {'output_path': str(media)}
        rows = {}
        for sid, url in (sources or {}).items():
            (folder / ('source-' + sid + '.txt')).write_text(BODY)
            rows[sid] = {'source_id': sid, 'title': 'T ' + sid[:4], 'url': url, 'sha256': hashlib.sha256(BODY.encode()).hexdigest(), 'characters': len(BODY), 'complete_claimed': True, 'read_to': len(BODY), 'verification': 'x'}
        data = {'project_id': pid, 'kind': kind, 'topic': topic, 'audience': 'Teens', 'resources': {}, 'factual': True, 'sources': rows,
                'sections': [{'title': 'Why', 'turns': [{'speaker': 'Narrator', 'text': 'Blue light scatters most.'}], 'source_ids': list(rows)}] if rows else [],
                'assets': {}, 'phase': 'assembled' if assembled else 'materials', 'result': result if assembled else None}
        (folder / 'project.json').write_text(json.dumps(data))
        import os
        t = 1_700_000_000 + age
        os.utime(folder / 'project.json', (t, t))
        return folder


class CaptionLatest(Fixture):
    def call(self, **args):
        return json.loads(caption_studio.invoke('captions_for_latest', args, None))

    def test_nothing_made_gives_a_plain_error(self):
        self.assertIn('Nothing finished', self.call()['error'])

    def test_video_gets_script_captions_from_its_timeline_and_no_recognition(self):
        self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4')
        out = self.call(kind='video')
        self.assertEqual(out['found']['kind'], 'video')
        self.assertTrue(out['found']['media_path'].endswith('out.mp4'))
        self.assertEqual(out['captions']['cues'], 2)
        self.assertEqual(Path(out['captions']['srt_path']), Path(out['found']['media_path']).with_suffix('.srt'))
        self.assertIn('not run', out['recognition'])
        self.assertIn('00:00:02,000 --> 00:00:04,000', Path(out['captions']['srt_path']).read_text())

    def test_video_uses_real_assembly_captions_without_timeline_turns(self):
        folder = self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4')
        meta = folder / 'project.json'
        data = json.loads(meta.read_text())
        data['result']['timeline'] = [{'title': 'Why', 'start': 0, 'end': 4, 'source_ids': []}]
        meta.write_text(json.dumps(data))
        (folder / 'captions.srt').write_text('1\n00:00:00,000 --> 00:00:04,000\nThe sky is blue.\n')
        out = self.call(kind='video')
        self.assertEqual(out['captions']['made_by'], 'video assembly')
        self.assertIn('The sky is blue.', Path(out['captions']['srt_path']).read_text())
        self.assertIn('not run', out['recognition'])

    def test_caption_sidecar_does_not_overwrite_a_different_file(self):
        folder = self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4')
        existing = folder / 'out.srt'
        existing.write_text('keep me')
        out = self.call(kind='video')
        self.assertEqual(existing.read_text(), 'keep me')
        self.assertEqual(Path(out['captions']['srt_path']).name, 'out-captions-1.srt')

    def test_podcast_prefers_its_own_episode_captions(self):
        folder = self.project('creator-studio-podcast', 'podcast', 'b' * 32, 'cats', 'ep.wav')
        (folder / 'captions.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nHi\n')
        out = self.call(kind='podcast')
        self.assertEqual(out['captions']['made_by'], 'podcast_episode_files')
        self.assertEqual(out['captions']['cues'], 1)

    def test_tutorial_narrated_export_and_latest_wins_for_any(self):
        self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4', age=0)
        job = self.dirs['creator-studio-tutorial'] / ('c' * 32)
        job.mkdir()
        (job / 'narrated-x.mp4').write_bytes(b'v')
        (job / 'narrated-x.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nStep one\n')
        import os
        os.utime(job / 'narrated-x.mp4', (1_800_000_000, 1_800_000_000))
        out = self.call()
        self.assertEqual(out['found']['kind'], 'tutorial')
        self.assertEqual(out['captions']['cues'], 1)

    def test_unfinished_projects_are_ignored(self):
        self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4', assembled=False)
        self.assertIn('Nothing finished', self.call(kind='video')['error'])

    def test_media_without_script_needs_a_recognizer_then_starts_the_normal_job(self):
        job = self.dirs['creator-studio-tutorial'] / ('d' * 32)
        job.mkdir()
        (job / 'export-x.mp4').write_bytes(b'v')
        self.assertIn('captions_recognizer_options', self.call(kind='tutorial')['error'])
        seen = {}

        def fake(name, args, ctx=None, **kw):
            seen.update(name=name, args=args)
            return json.dumps({'job_id': 'j1', 'phase': 'recognizing'})
        with mock.patch.object(caption_studio, 'invoke', fake):
            out = caption_studio.latest_captions({'kind': 'tutorial', 'recognizer': {'kind': 'import', 'transcript_path': 'x'}}, None)
        self.assertEqual(seen['name'], 'captions_generate')
        self.assertTrue(seen['args']['media_path'].endswith('export-x.mp4'))
        self.assertTrue(seen['args']['allow_profile_media'])
        self.assertEqual(out['recognition_job']['job_id'], 'j1')

    def test_recognize_true_runs_recognition_even_with_script_captions(self):
        self.project('creator-studio-youtube', 'video', 'a' * 32, 'sky', 'out.mp4')
        with mock.patch.object(caption_studio, 'invoke', lambda *a, **k: json.dumps({'job_id': 'j2'})):
            out = caption_studio.latest_captions({'kind': 'video', 'recognize': True, 'recognizer': {'kind': 'import', 'transcript_path': 'x'}}, None)
        self.assertEqual(out['recognition_job']['job_id'], 'j2')


class PodcastFromLesson(Fixture):
    VID = 'a' * 32
    SRC = {'1' * 32: 'https://example.org/sky', '2' * 32: 'https://example.org/light'}

    def start(self, **args):
        return json.loads(podcast_studio.invoke('podcast_start_from_video', {'video_project_id': self.VID, **args}))

    def test_copies_sources_with_ids_urls_and_origin_and_fetches_nothing(self):
        self.project('creator-studio-youtube', 'video', self.VID, 'Why the sky is blue', 'out.mp4', sources=self.SRC)
        with mock.patch('socket.socket', side_effect=AssertionError('network used')), mock.patch('subprocess.Popen', side_effect=AssertionError('process used')):
            out = self.start()
        self.assertNotIn('error', out)
        self.assertTrue(out['no_web_fetch'])
        self.assertEqual({s['source_id'] for s in out['sources']}, set(self.SRC))
        self.assertEqual({s['url'] for s in out['sources']}, set(self.SRC.values()))
        p = MediaProject(self.dirs['creator-studio-podcast'], 'podcast')
        _, data = p.load(out['project_id'])
        self.assertEqual(data['origin']['project_id'], self.VID)
        row = data['sources']['1' * 32]
        self.assertEqual(row['copied_from'], {'kind': 'video', 'project_id': self.VID, 'source_id': '1' * 32})
        self.assertEqual(row['read_to'], 0)
        self.assertIn('Rayleigh', p.source_read(out['project_id'], '1' * 32, 0, 300)['text'])
        self.assertEqual(data['topic'], 'Why the sky is blue')
        self.assertIn('Blue light scatters most.', Path(out['lesson_notes_file']).read_text())

    def test_script_writing_can_use_the_copied_ids_after_a_local_read(self):
        self.project('creator-studio-youtube', 'video', self.VID, 'sky', 'out.mp4', sources=self.SRC)
        out = self.start()
        p = MediaProject(self.dirs['creator-studio-podcast'], 'podcast')
        for sid in self.SRC:
            p.source_read(out['project_id'], sid, 0, len(BODY) + 10)
        res = p.script(out['project_id'], [{'title': 'Hook', 'source_ids': list(self.SRC), 'turns': [{'speaker': 'Ana', 'text': 'Why is the sky blue?'}, {'speaker': 'Ben', 'text': 'Scattering.'}]}])
        self.assertEqual(res['sections'], 1)

    def test_refuses_bad_ids_unknown_projects_and_changed_sources(self):
        self.assertIn('error', json.loads(podcast_studio.invoke('podcast_start_from_video', {'video_project_id': 'nope'})))
        self.assertIn('not found', self.start()['error'])
        folder = self.project('creator-studio-youtube', 'video', self.VID, 'sky', 'out.mp4', sources=self.SRC)
        (folder / ('source-' + '1' * 32 + '.txt')).write_text('tampered')
        self.assertIn('changed', self.start()['error'])

    def test_video_without_sources_is_refused_and_podcast_projects_are_not_accepted(self):
        self.project('creator-studio-youtube', 'video', self.VID, 'sky', 'out.mp4')
        self.assertIn('no saved sources', self.start()['error'])


if __name__ == '__main__':
    unittest.main()
