import base64
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from test_tutorial import package, voice_fixture
from tutorial_test import gemini_speech


def ok_response(audio=None, tokens=(10, 100)):
    audio = audio or voice_fixture()
    body = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {'mimeType': 'audio/wav', 'data': base64.b64encode(audio).decode()}}]}}],
            'usageMetadata': {'promptTokenCount': tokens[0], 'candidatesTokenCount': tokens[1]}}
    response = Mock(status_code=200, content=json.dumps(body).encode())
    response.json.return_value = body
    return response


class GeminiSpeech(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.ledger = Path(self.tmp.name) / 'usage.json'
        self.creds = Mock(token='fixture-token')
    def tearDown(self): self.tmp.cleanup()

    def call(self, transport, **kw):
        return gemini_speech.synthesize('Hello there.', kw.pop('voice', 'Achird'), 'gemini-3.8-flash-tts', project='fixture-project',
                                        ledger_path=self.ledger, transport=transport, credentials=self.creds, **kw)

    def test_request_shape_one_post_and_ledger(self):
        seen = []
        def transport(url, headers, body): seen.append((url, headers, body)); return ok_response()
        audio = self.call(transport)
        self.assertEqual(audio[:4], b'RIFF')
        self.assertEqual(len(seen), 1)
        url, headers, body = seen[0]
        self.assertIn('gemini-3.8-flash-tts:generateContent', url)
        self.assertEqual(body['generationConfig']['speechConfig']['voiceConfig']['voice'], 'Achird')
        self.assertEqual(headers['Authorization'], 'Bearer fixture-token')
        rows = json.loads(self.ledger.read_text())
        self.assertEqual(rows[0]['status'], 'received')
        self.assertEqual(rows[0]['input_tokens'], 10)
        self.assertLess(rows[0]['reserved_or_actual_usd'], 0.01)

    def test_http_error_is_not_retried_and_hides_project(self):
        calls = []
        def transport(url, headers, body):
            calls.append(1)
            r = Mock(status_code=403, content=b'x'); r.json.return_value = {'error': {'message': 'denied for fixture-project'}}; return r
        with self.assertRaises(gemini_speech.SpeechError) as ctx:
            self.call(transport)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('fixture-project', str(ctx.exception))
        self.assertIn('<project>', str(ctx.exception))
        self.assertEqual(json.loads(self.ledger.read_text())[0]['reserved_or_actual_usd'], 0)

    def test_transport_failure_keeps_reservation_and_is_not_retried(self):
        calls = []
        def transport(*a): calls.append(1); raise OSError('down')
        with self.assertRaisesRegex(gemini_speech.SpeechError, 'no retry'):
            self.call(transport)
        self.assertEqual(len(calls), 1)
        row = json.loads(self.ledger.read_text())[0]
        self.assertEqual(row['status'], 'unknown'); self.assertGreater(row['reserved_or_actual_usd'], 0)

    def test_spend_guard_blocks_before_any_request(self):
        transport = Mock()
        with self.assertRaisesRegex(gemini_speech.SpeechError, 'spending guard'):
            self.call(transport, max_usd=0.0001)
        transport.assert_not_called()

    def test_unknown_voice_and_model_refused(self):
        with self.assertRaises(ValueError): self.call(Mock(), voice='NotAVoice')
        with self.assertRaises(ValueError):
            gemini_speech.synthesize('x', 'Achird', 'other-model', project='p', ledger_path=self.ledger, transport=Mock(), credentials=self.creds)

    def test_invalid_audio_is_recorded(self):
        bad = ok_response(audio=b'not a wav')
        with self.assertRaisesRegex(gemini_speech.SpeechError, 'invalid audio'):
            self.call(lambda *a: bad)
        self.assertEqual(json.loads(self.ledger.read_text())[0]['status'], 'audio_invalid')

    def test_availability_lists_thirty_named_voices_without_project(self):
        with patch.object(gemini_speech, 'project_id', return_value='fixture-project'):
            info = gemini_speech.availability()
        self.assertEqual(len(info['voices']), 30)
        self.assertNotIn('fixture-project', json.dumps(info))
        self.assertTrue(info['project_configured'])

    def test_project_id_never_accepts_unsafe_text(self):
        with patch.object(gemini_speech.subprocess, 'run', return_value=Mock(stdout='bad project; rm -rf\n')):
            with self.assertRaisesRegex(ValueError, 'No Google Cloud project'):
                gemini_speech.project_id('')
        self.assertEqual(gemini_speech.project_id('my-project-1'), 'my-project-1')

    def test_narrate_uses_gemini_cache_and_reports_usage(self):
        from tutorial_test.narration import narrate
        from tutorial_test.core import Director
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            director = Mock(); folder = root / 'job'; folder.mkdir()
            video = folder / 'export.mp4'
            import subprocess
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=3', '-pix_fmt', 'yuv420p', str(video)], check=True)
            posts = []
            def transport(url, headers, body): posts.append(body); return ok_response()
            settings = {'narration_backend': 'gemini', 'gemini_voice': 'Achird', 'gemini_project': 'fixture-project'}
            with patch('tutorial_test.narration.Director') as D, patch.object(gemini_speech, 'synthesize', side_effect=lambda t, v, m, **kw: gemini_speech.__dict__['_real'](t, v, m, transport=transport, credentials=self.creds, **kw)):
                D.return_value.timeline.return_value = {'seconds': 3.0}
                D.return_value.job.return_value = folder
                result = narrate(root, 'job', 'export.mp4', [{'start': 0, 'end': 1.5, 'text': 'Hello there.'}], settings)
                self.assertEqual(result['state'], 'complete')
                self.assertEqual(result['voice'], 'Achird')
                self.assertEqual(result['usage']['requests'], 1)
                self.assertIn('Gemini', result['credit'])
                result2 = narrate(root, 'job', 'export.mp4', [{'start': 0, 'end': 1.5, 'text': 'Hello there.'}], settings)
                self.assertTrue(result2['cues'][0]['cache_reused'])
            self.assertEqual(len(posts), 1)


gemini_speech.__dict__['_real'] = gemini_speech.synthesize

if __name__ == '__main__':
    unittest.main()
