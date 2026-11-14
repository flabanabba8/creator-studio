"""Whole-stream recognition: piece planning, time shifting, resume, partial transcript, final attach. A fake recognizer stands in for Caption Studio; FFmpeg makes real quiet-and-loud audio."""
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('creator_studio_recog_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_recog_test import clip_studio  # noqa: E402
from creator_studio_recog_test.clip_studio import recognize as R, source as S  # noqa: E402

FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')
RATE = 16000


def make_wav(path, seconds, quiet=()):
    """Mono 16 kHz WAV: a 220 Hz hum, with silence in each (start, end) of quiet."""
    import array
    import math
    samples = array.array('h')
    for i in range(int(seconds * RATE)):
        t = i / RATE
        samples.append(0 if any(a <= t < b for a, b in quiet) else int(8000 * math.sin(2 * math.pi * 220 * t)))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.tobytes())


class PlanningTests(unittest.TestCase):
    def test_silence_lines_become_video_time_spans(self):
        text = '[silencedetect @ x] silence_start: 1.5\n[silencedetect @ x] silence_end: 2.5 | silence_duration: 1\n[silencedetect @ x] silence_start: 9.0\n'
        self.assertEqual(R.parse_silences(text, 100.0, 110.0), [(101.5, 102.5), (109.0, 110.0)])
        self.assertEqual(R.parse_silences('silence_end: 0.8 | silence_duration: 0.8', 50.0, 60.0), [(50.0, 50.8)])

    def test_cut_is_the_middle_of_the_longest_quiet_stretch_inside_the_window(self):
        spans = [(5.0, 5.4), (7.0, 8.0), (9.5, 12.0)]
        self.assertEqual(R.choose_cut(spans, 4.0, 10.0), 7.5)
        self.assertEqual(R.choose_cut(spans, 4.0, 12.0), 10.75)
        self.assertIsNone(R.choose_cut(spans, 0.0, 4.0))

    def test_pieces_are_cut_at_quiet_points_and_a_short_rest_is_not_split_off(self):
        quiet = {(540.0, 600.0): 570.0, (1140.0, 1200.0): 1170.0}
        find = lambda lo, hi: quiet.get((lo, hi))
        piece = 600000
        first = R.plan_end(0, 1500000, piece, find)
        self.assertEqual(first, 570000)  # window is the last 60 s before the 10 minute mark
        second = R.plan_end(first, 1500000, piece, find)
        self.assertEqual(second, 1170000)
        third = R.plan_end(second, 1500000, piece, find)
        self.assertEqual(third, 1500000)  # 5.5 minutes left: one last piece
        self.assertEqual(R.plan_end(0, 700000, piece, find), 700000)
        self.assertEqual(R.plan_end(0, 2000000, piece, lambda lo, hi: None), 600000)  # no quiet point: cut at the target

    def test_words_are_shifted_to_video_time_in_order(self):
        words = [{'text': ' Hello ', 'start_ms': 100, 'end_ms': 400}, {'text': '', 'start_ms': 400, 'end_ms': 500},
                 {'text': 'world.', 'start_ms': 380, 'end_ms': 900}, {'text': 'again', 'start_ms': 900, 'end_ms': 900}]
        units = R.shift_words(words, 570000)
        self.assertEqual(units[0], {'s': 570100, 'e': 570400, 't': 'Hello'})
        self.assertEqual([u['t'] for u in units], ['Hello', 'world.', 'again'])
        self.assertTrue(all(a['s'] <= b['s'] and u['e'] > u['s'] for a, b, u in zip(units, units[1:], units)))
        self.assertEqual(R.minutes(90000), 1.5)


class FakeCaption:
    """Stands in for Caption Studio. Each job 'hears' one word per 2 seconds of the piece it is given, numbered by where the piece starts in the recording."""

    def __init__(self, base, fail_on_piece=None, setup='answered'):
        self.base, self.jobs, self.calls, self.fail_on_piece, self.setup, self.pieces_heard = base, {}, [], fail_on_piece, setup, []

    def call(self, name, args, ctx, context):
        self.calls.append(name)
        if name == 'captions_recognizer_setup':
            return {'state': self.setup, 'questions': ['which recognizer?']}
        if name == 'captions_generate':
            if self.setup != 'answered':
                return {'state': 'interview_needed', 'questions': ['which recognizer?']}
            with wave.open(args['media_path']) as wav:
                seconds = wav.getnframes() / wav.getframerate()
            n = len(self.pieces_heard)
            self.pieces_heard.append(seconds)
            job = '%032x' % (n + 1)
            if self.fail_on_piece == n:
                self.jobs[job] = {'state': 'failed', 'error': 'the recognizer crashed'}
            else:
                self.jobs[job] = {'state': 'ready', 'model': 'fake-model', 'recognizer_kind': 'command', 'words': [{'text': 'w%d_%d' % (n, k), 'start_ms': k * 2000, 'end_ms': k * 2000 + 500} for k in range(int(seconds // 2))]}
            return {'job_id': job, 'state': 'preparing'}
        if name == 'captions_audio_status':
            return {k: v for k, v in self.jobs[args['job_id']].items() if k != 'words'}
        raise AssertionError(name)

    def words(self, job_id):
        return self.jobs[job_id]['words']


class RecognizeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        storage = types.ModuleType('plugins.plugin_storage')

        def plugin_data_dir(name):
            folder = self.base / 'profile' / 'plugin-data' / name
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        storage.plugin_data_dir = plugin_data_dir
        self.fake = FakeCaption(self.base)
        patches = [mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage}),
                   mock.patch.object(R, '_caption', lambda name, args, ctx, context: self.fake.call(name, args, ctx, context)),
                   mock.patch.object(R, '_read_words', lambda job: self.fake.words(job)),
                   mock.patch.object(R, 'POLL', 0.01), mock.patch.object(R, 'NAP', 0.02)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def call(self, name, **args):
        return json.loads(clip_studio.invoke(name, args))

    def project(self, seconds, quiet=()):
        media = self.base / 'recording.wav'
        make_wav(media, seconds, quiet)
        return self.call('clips_open', media_path=str(media))['project_id']

    def run_to_end(self, pid, **args):
        for _ in range(200):
            out = self.call('clips_transcribe', project_id=pid, wait_seconds=5, **args)
            if 'error' in out or out.get('recognition', {}).get('state') in R.TERMINAL:
                return out
        raise AssertionError('recognition did not finish')


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class FlowTests(RecognizeFixture):
    def test_whole_recording_is_recognised_in_pieces_and_attached_by_itself(self):
        pid = self.project(80, quiet=[(24, 27), (50, 53)])
        out = self.run_to_end(pid, piece_minutes=0.5)
        self.assertEqual(out['recognition']['state'], 'done', out)
        self.assertEqual((out['recognition']['pieces_done'], out['recognition']['recognised_minutes'], out['recognition']['total_minutes']), (3, 1.3, 1.3))
        self.assertIn('clips_outline', out['next'])
        self.assertFalse(out['transcript'].get('partial'))
        self.assertEqual(self.fake.pieces_heard, [self.fake.pieces_heard[0], self.fake.pieces_heard[1], self.fake.pieces_heard[2]])
        self.assertAlmostEqual(sum(self.fake.pieces_heard), 80, delta=0.1)
        self.assertAlmostEqual(self.fake.pieces_heard[0], 25.5, delta=0.6)  # cut in the middle of the first quiet stretch
        status = self.call('clips_status', project_id=pid)
        self.assertEqual(status['transcript']['timing'], 'each word')
        words = self.call('clips_transcript', project_id=pid, start=0, end=100)
        self.assertNotIn('partial_transcript', words)
        first_second_piece = [s for s in words['sentences'] if 'w1_0' in s['text']][0]
        self.assertAlmostEqual(first_second_piece['start'], self.fake.pieces_heard[0], delta=0.1)  # the second piece's first word sits where that piece starts
        found = self.call('clips_transcript', project_id=pid, query='w2_0')['matches']
        self.assertAlmostEqual(found[0]['start'], sum(self.fake.pieces_heard[:2]), delta=0.1)
        self.assertEqual(self.fake.calls.count('captions_generate'), 3)

    def test_interruption_resumes_from_finished_pieces_and_a_partial_transcript_is_readable(self):
        pid = self.project(80, quiet=[(24, 27), (50, 53)])
        self.fake.fail_on_piece = 1
        stopped = self.run_to_end(pid, piece_minutes=0.5)
        self.assertEqual(stopped['recognition']['state'], 'failed')
        self.assertIn('the recognizer crashed', stopped['recognition']['error'])
        self.assertEqual(stopped['recognition']['pieces_done'], 1)
        self.assertIn('carry on from piece 2', stopped['next'])
        self.assertTrue(stopped['transcript']['partial'])
        outline = self.call('clips_outline', project_id=pid)
        self.assertIn('PARTIAL', outline['partial_transcript'])
        part = self.call('clips_transcript', project_id=pid, start=0, end=100)
        self.assertIn('partial_transcript', part)
        self.assertIn('PARTIAL', part['transcript_from'])
        self.assertTrue(all(s['start'] < 26 for s in part['sentences']))
        self.assertIn('partial_transcript', self.call('clips_propose', project_id=pid, clips=[{'start': 1, 'end': 9, 'title': 'early'}]))
        self.assertIn('partial', self.call('clips_open', media_path=str(self.base / 'recording.wav'))['next'].lower())
        heard_before = len(self.fake.pieces_heard)
        self.fake.fail_on_piece = None
        done = self.run_to_end(pid)
        self.assertEqual(done['recognition']['state'], 'done', done)
        self.assertEqual(done['recognition']['pieces_done'], 3)
        self.assertEqual(len(self.fake.pieces_heard) - heard_before, 2)  # only the two missing pieces were recognised again
        self.assertNotIn('partial_transcript', self.call('clips_outline', project_id=pid))

    def test_a_dead_worker_is_resumed_not_restarted(self):
        pid = self.project(80, quiet=[(24, 27), (50, 53)])
        folder = Path(self.base / 'profile/plugin-data/creator-studio-clips/projects' / pid)
        self.run_to_end(pid, piece_minutes=0.5)
        state = json.loads((folder / 'recognition/state.json').read_text())
        for gone in state['pieces'][1:]:  # as if the process was killed after piece 1: later pieces and the final state never reached disk
            (folder / 'recognition' / gone['file']).unlink()
        state.update(pieces=state['pieces'][:1], state='recognising')
        (folder / 'recognition/state.json').write_text(json.dumps(state))
        before = len(self.fake.pieces_heard)
        out = self.run_to_end(pid)
        self.assertEqual(out['recognition']['state'], 'done')
        self.assertEqual(len(self.fake.pieces_heard) - before, 2)
        self.assertEqual(out['recognition']['resumed_from_piece'], 2)

    def test_no_chosen_recognizer_returns_the_interview_and_never_invites_guessing(self):
        pid = self.project(20)
        self.fake.setup = 'interview_needed'
        out = self.call('clips_transcribe', project_id=pid)
        self.assertIn('recognizer_interview', out)
        self.assertIn('Do not guess', out['next'])
        self.assertEqual(self.fake.calls, ['captions_recognizer_setup'])
        self.assertIn('no transcript yet', self.call('clips_outline', project_id=pid)['error'])
        configured = self.run_to_end(pid, recognizer={'kind': 'configured'})
        self.assertEqual(configured['recognition']['state'], 'needs_setup')
        self.assertIn('Do not guess', configured['next'])

    def test_progress_while_running_says_there_is_no_transcript_yet(self):
        pid = self.project(20)
        gate = []
        real = self.fake.call

        def slow(name, args, ctx, context):
            while name == 'captions_audio_status' and not gate:
                time.sleep(0.02)
            return real(name, args, ctx, context)
        with mock.patch.object(R, '_caption', slow):
            out = self.call('clips_transcribe', project_id=pid, wait_seconds=0)
            self.assertIn(out['recognition']['state'], ('preparing', 'recognising'))
            self.assertIn('no transcript yet', out['next'])
            self.assertIn('do not suggest or guess', out['next'])
            self.assertEqual(self.call('clips_transcribe', project_id=pid, wait_seconds=0, restart=True).get('error', '')[:9], 'Recogniti')
            gate.append(1)
            self.assertEqual(self.run_to_end(pid)['recognition']['state'], 'done')

    def test_existing_transcript_is_kept_unless_restart(self):
        pid = self.project(20)
        srt = self.base / 't.srt'
        srt.write_text('1\n00:00:01,000 --> 00:00:03,000\nWelcome back.\n')
        self.call('clips_use_transcript', project_id=pid, transcript_path=str(srt))
        kept = self.call('clips_transcribe', project_id=pid)
        self.assertIn('already has a transcript', kept['note'])
        self.assertEqual(self.fake.calls, [])
        out = self.run_to_end(pid, restart=True)
        self.assertEqual(out['recognition']['state'], 'done', out)
        self.assertIn('Caption Studio', self.call('clips_status', project_id=pid)['transcript']['from'])

    def test_bad_arguments_and_a_transcript_attached_meanwhile(self):
        pid = self.project(20)
        for bad in ({'recognizer': {'kind': 'import'}}, {'piece_minutes': 0}, {'wait_seconds': 999}, {'restart': 'yes'}):
            self.assertIn('error', self.call('clips_transcribe', project_id=pid, **bad), bad)
        self.assertEqual(self.fake.calls, [])
