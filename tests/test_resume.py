"""Unplaced visuals are noticed at assembly; a half-finished project resumes by one plain request. No network, no speech calls."""
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('creator_studio_resume_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_resume_test.youtube_studio.media_project import MediaProject as Video  # noqa: E402
from creator_studio_resume_test.podcast_studio.media_project import MediaProject as Podcast  # noqa: E402
from creator_studio_resume_test.common import gemini_speech  # noqa: E402
from creator_studio_resume_test.tutorial_creator.core import Director  # noqa: E402
from PIL import Image  # noqa: E402

SECTIONS = [{'title': 'Why the sky is blue', 'turns': [{'speaker': 'N', 'text': 'Sunlight scatters in the air.'}], 'source_ids': [], 'visual_brief': '', 'audio_ids': [], 'image_id': None},
            {'title': 'Sunsets', 'turns': [{'speaker': 'N', 'text': 'Red light travels further.'}], 'source_ids': [], 'visual_brief': '', 'audio_ids': [], 'image_id': None}]


def png(path, colour):
    Image.new('RGB', (64, 36), colour).save(path)
    return str(path)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / 'creator-studio-youtube'
        self.dir.mkdir()

    def project(self, cls=Video, kind='video', sections=SECTIONS, root=None):
        m = cls(root or self.dir, kind)
        made = m.create('Why the sky is blue', factual=False)
        pid = made['project_id']
        p, data = m.load(pid)
        data['sections'] = json.loads(json.dumps(sections))
        data['sources'] = {'1' * 32: {'source_id': '1' * 32, 'title': 't', 'url': '', 'characters': 10, 'read_to': 10, 'complete_claimed': True}}
        (p / 'project.json').write_text(json.dumps(data))
        return m, pid, p


class UnplacedVisuals(Base):
    def log(self, path, title, kind='flowchart', project_id=None):
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        f = self.dir / 'visuals.json'
        rows = json.loads(f.read_text()) if f.is_file() else []
        rows.append({'path': path, 'sha256': sha, 'title': title, 'kind': kind, 'created': 4_000_000_000, 'project_id': project_id})
        f.write_text(json.dumps(rows))

    def test_matching_loose_visual_is_placed_in_its_section(self):
        m, pid, p = self.project()
        self.log(png(self.dir / 'flow.png', 'white'), 'Why the sky is blue: scattering flowchart', project_id=pid)
        _, data = m.load(pid)
        placed, unused = m._visuals_report(p, data)
        self.assertEqual([x['section_index'] for x in placed], [0])
        self.assertEqual(unused, [])
        self.assertTrue(m.load(pid)[1]['sections'][0]['image_id'])

    def test_unmatched_visual_is_reported_not_silently_dropped(self):
        m, pid, p = self.project()
        self.log(png(self.dir / 'tbl.png', 'grey'), 'Quarterly revenue', 'table', project_id=pid)
        placed, unused = m._visuals_report(p, m.load(pid)[1])
        self.assertEqual(placed[0]['visual'], 'Quarterly revenue')
        self.assertTrue(m.load(pid)[1]['assets'])

    def test_a_visual_pushed_out_by_a_slide_is_found_again(self):
        m, pid, p = self.project()
        flow = png(self.dir / 'flow.png', 'white')
        self.log(flow, 'Sunsets flowchart', project_id=pid)
        m.add_asset(pid, flow, 'image', 1, 'Drawn by youtube_make_visual from the supplied data (sourced: x)')
        m.add_asset(pid, png(self.dir / 'slide.png', 'black'), 'image', 1, 'Drawn by youtube_make_slides from the outline; not yet inspected')
        placed, unused = m._visuals_report(p, m.load(pid)[1])
        self.assertEqual(placed[0]['visual'], 'Sunsets flowchart')
        self.assertIn('youtube_make_slides', m.load(pid)[1]['assets'][m.load(pid)[1]['sections'][1]['image_id']]['review_note'])

    def test_unassigned_visual_from_later_project_is_not_attributed_here(self):
        m, pid, p = self.project()
        self.project()
        self.log(png(self.dir / 'later.png', 'red'), 'Later project')
        self.assertEqual(m._visuals_report(p, m.load(pid)[1]), ([], []))

    def test_status_returns_usable_asset_path_for_resume(self):
        m, pid, p = self.project()
        image = png(self.dir / 'slide.png', 'white')
        m.add_asset(pid, image, 'image', 0, 'Drawn slide; not yet inspected')
        row = m.status(pid)['assets'][0]
        self.assertEqual(Path(row['path']).parent, p)
        self.assertTrue(Path(row['path']).is_file())

    def test_displaced_generated_illustration_is_reported(self):
        m, pid, p = self.project()
        illustration = png(self.dir / 'generated.png', 'red')
        m.add_asset(pid, illustration, 'image', 0, 'Generated illustration: red sky')
        m.add_asset(pid, png(self.dir / 'flow.png', 'white'), 'image', 0, 'Drawn by youtube_make_visual: flow')
        placed, unused = m._visuals_report(p, m.load(pid)[1])
        self.assertEqual(placed, [])
        self.assertTrue(any('Generated illustration: red sky' in v['visual'] for v in unused))

    def test_visuals_from_older_projects_and_already_shown_ones_are_ignored(self):
        m, pid, p = self.project()
        old = png(self.dir / 'old.png', 'red')
        sha = hashlib.sha256(Path(old).read_bytes()).hexdigest()
        (self.dir / 'visuals.json').write_text(json.dumps([{'path': old, 'sha256': sha, 'title': 'Sunsets', 'kind': 'flowchart', 'created': 1.0}]))
        self.assertEqual(m._visuals_report(p, m.load(pid)[1]), ([], []))
        shown = png(self.dir / 'shown.png', 'blue')
        self.log(shown, 'Sunsets flowchart', project_id=pid)
        m.add_asset(pid, shown, 'image', 1, 'Drawn by youtube_make_visual (x)')
        self.assertEqual(m._visuals_report(p, m.load(pid)[1]), ([], []))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg not installed')
    def test_assembly_result_says_which_visual_was_not_used(self):
        m, pid, p = self.project()
        wav = self.dir / 'tone.wav'
        with wave.open(str(wav), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\x00\x00' * 48000)
        for i, colour in enumerate(('white', 'black')):
            m.add_asset(pid, str(wav) if i == 0 else self._wav2(i), 'audio', i, 'tone')
            m.add_asset(pid, png(self.dir / ('s%d.png' % i), colour), 'image', i, 'Drawn by youtube_make_slides; I looked at it: plain slide')
        self.log(png(self.dir / 'tbl.png', 'grey'), 'Quarterly revenue', 'table', project_id=pid)
        out = m.assemble(pid)
        self.assertEqual(len(out['visuals_used']), 3)
        self.assertEqual(out['visuals_used'][0]['start'], 0)
        self.assertAlmostEqual(out['visuals_used'][-1]['end'], out['seconds'])

    def _wav2(self, i):
        path = self.dir / ('tone%d.wav' % i)
        with wave.open(str(path), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\x01\x00' * 48000)
        return str(path)


class ProjectIsolation(Base):
    def test_cross_project_asset_requires_explicit_import(self):
        for cls, kind in ((Video, 'video'), (Podcast, 'podcast')):
            m, first, first_dir = self.project(cls=cls, kind=kind, root=self.dir / kind)
            _, second, _ = self.project(cls=cls, kind=kind, root=self.dir / kind)
            image = png(first_dir / 'owned.png', 'red')
            with self.assertRaisesRegex(ValueError, first + '.*' + second):
                m.add_asset(second, image, 'image', 0, 'reviewed')
            imported = m.add_asset(second, image, 'image', 0, 'reviewed', import_from_project=True)
            self.assertEqual(imported['imported_from']['project_id'], first)
            self.assertEqual(Path(m.load(second)[0] / imported['file']).read_bytes(), Path(image).read_bytes())

    def test_existing_script_never_restarts_research(self):
        m, pid, p = self.project()
        _, data = m.load(pid); data['sources'] = {}; data['factual'] = False
        (p / 'project.json').write_text(json.dumps(data))
        resume = m.status(pid)['resume']
        self.assertIn('narrate', resume['next'])
        self.assertFalse(any('research' in step for step in resume['next_steps_to_completion']))
        self.assertFalse(any('research:' in item for item in resume['left']))

    def test_resume_lists_every_remaining_step(self):
        m, pid, p = self.project()
        steps = m.status(pid)['resume']['next_steps_to_completion']
        self.assertTrue(any('narrate' in step for step in steps))
        self.assertTrue(any('assemble' in step for step in steps))
        self.assertIn('Show the finished video', steps[-1])


class Resume(Base):
    def test_status_tells_a_new_session_the_one_next_step(self):
        m, pid, p = self.project()
        out = m.status(pid)['resume']
        self.assertIn('narrate', out['next'])
        self.assertEqual(out['speech_turns_remaining'], 2)
        self.assertIn(pid, [r['project_id'] for r in m.status()['projects']])
        self.assertIn('narrate', m.status()['projects'][0]['next'])

    def test_podcast_status_has_the_same_resume_block(self):
        pm, pid, p = self.project(Podcast, 'podcast', root=Path(self.tmp.name) / 'creator-studio-podcast')
        self.assertIn('podcast_narrate', pm.status(pid)['resume']['next'])

    def test_assembled_project_says_nothing_is_left(self):
        m, pid, p = self.project()
        _, d = m.load(pid)
        for s in d['sections']:
            s['audio_ids'] = ['a']
            s['image_id'] = 'i'
        d['phase'] = 'assembled'
        (p / 'project.json').write_text(json.dumps(d))
        self.assertTrue(m.status(pid)['resume']['next'].startswith('nothing'))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_narration_resumes_without_paying_twice(self):
        m, pid, p = self.project()
        wav = self.dir / 'tone.wav'
        with wave.open(str(wav), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\x00\x00' * 2400)
        calls = []

        def synth(text, voice, ledger, max_usd=0.5, **kw):
            calls.append(text)
            if len(calls) == 2:
                raise gemini_speech.GeminiSpeechError('prompt flagged')
            return wav.read_bytes()
        with mock.patch.object(gemini_speech, 'synthesize', synth):
            with self.assertRaises(RuntimeError):
                m.narrate(pid, engine='gemini', voice='Charon')
            self.assertEqual(m.status(pid)['resume']['speech_turns_remaining'], 1)
            out = m.narrate(pid, engine='gemini', voice='Charon')
        self.assertEqual(out['already_recorded'], 1)
        self.assertEqual(calls, ['Sunlight scatters in the air.', 'Red light travels further.', 'Red light travels further.'])  # first turn never paid again
        self.assertEqual(m.status(pid)['resume']['speech_turns_remaining'], 0)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_a_take_paid_for_before_a_crash_is_reused(self):
        m, pid, p = self.project()
        wav = self.dir / 'tone.wav'
        with wave.open(str(wav), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\x00\x00' * 2400)
        takes = p / 'takes'
        takes.mkdir()
        for si, text in ((0, SECTIONS[0]['turns'][0]['text']), (1, SECTIONS[1]['turns'][0]['text'])):
            (takes / ('raw-%02d-00-%s.wav' % (si, hashlib.sha256((text + '|Charon').encode()).hexdigest()[:10]))).write_bytes(wav.read_bytes())
        with mock.patch.object(gemini_speech, 'synthesize', side_effect=AssertionError('paid twice')):
            out = m.narrate(pid, engine='gemini', voice='Kore')
        self.assertEqual(out['recorded_now'], 2)
        self.assertTrue(all('Charon' in a['review_note'] for a in m.load(pid)[1]['assets'].values()))


class TutorialResume(unittest.TestCase):
    def test_capture_status_without_id_lists_recordings_with_next_step(self):
        with tempfile.TemporaryDirectory() as d:
            director = Director(d)
            job = Path(d) / ('e' * 32)
            job.mkdir()
            (job / 'state.json').write_text(json.dumps({'state': 'complete', 'job_id': 'e' * 32}))
            self.assertIn('capture_export', director.status()['recordings'][0]['next'])
            (job / 'export-aaaa.mp4').write_bytes(b'v')
            self.assertIn('tutorial_narrate', director.status()['recordings'][0]['next'])
            (job / 'narrated-bbbb.mp4').write_bytes(b'v')
            self.assertTrue(director.status()['recordings'][0]['next'].startswith('nothing'))
            self.assertEqual(director.status('e' * 32)['state'], 'complete')


if __name__ == '__main__':
    unittest.main()
