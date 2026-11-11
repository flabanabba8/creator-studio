import importlib.util
import io
import ipaddress
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tutorial_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from tutorial_test.core import Director, number, local_display, write_json
from tutorial_test.narration import endpoint, narrate, validate_cues
from tutorial_test import loopback


def voice_fixture():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(b''.join(struct.pack('<h', int(4000 * math.sin(i * 2 * math.pi * 440 / 24000))) for i in range(9600)))
    return out.getvalue()


class Boundaries(unittest.TestCase):
    def test_narration_reads_keyed_config(self):
        class Context:
            def __init__(self): self.keys = []
            def get_config(self, key): self.keys.append(key); return {'higgs_model': 'fixture-model'}.get(key)
        ctx = Context()
        with patch('plugins.plugin_storage.plugin_data_dir', return_value=Path('/tmp/fixture')), patch.object(package, 'narrate', return_value={}) as narrate_call:
            result = json.loads(package.invoke('tutorial_narrate', {'job_id': 'fixture'}, ctx))
        self.assertEqual(result, {})
        self.assertEqual(narrate_call.call_args.kwargs['settings'], {'higgs_model': 'fixture-model'})

    def test_unsupported_platform_reports_linux_before_capture(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp, patch.object(package.core.sys,'platform','win32'):
            with self.assertRaisesRegex(ValueError,'requires Linux'):package.core.sources()
            with self.assertRaisesRegex(ValueError,'requires Linux'):Director(Path(tmp)/'out').start(123)

    def test_invalid_numbers_and_remote_display(self):
        for value in [True, float('nan'), float('inf'), -1, '3']:
            with self.assertRaises(ValueError): number(value, 0, 89, 'duration')
        for display in ['remote:0', ':0;true', '']:
            with self.assertRaises(ValueError): local_display(display)
        self.assertEqual(local_display(':0.0'), ':0.0')

    def test_cue_validation_before_generation(self):
        bad = [[{'start': 1, 'end': .5, 'text': 'hello'}],
               [{'start': 0, 'end': 1, 'text': 'x'}, {'start': .9, 'end': 2, 'text': 'y'}],
               [{'start': 0, 'end': 1, 'text': '<|reset|>Hello'}]]
        for cues in bad:
            with self.assertRaises(ValueError): validate_cues(cues, 3)
        with self.assertRaises(ValueError): endpoint('https://example.com/')
        with self.assertRaises(ValueError): endpoint('http://localhost:8000/?key=private')

    def test_higgs_reference_rejects_private_configuration_before_network(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            private = root/'.codex'
            private.mkdir()
            reference = private/'fixture.wav'
            reference.write_bytes(b'fixture')
            director = Mock()
            director.timeline.return_value = {'seconds': 5}
            director.job.return_value = root
            with patch('tutorial_test.narration.Director', return_value=director), patch('tutorial_test.narration.synthesize') as synthesis:
                with self.assertRaisesRegex(ValueError, 'Private configuration'):
                    narrate(root/'plugin-data'/'automatic-tutorial-creator', 'id', 'demo.mp4',
                            [{'start':0, 'end':2, 'text':'Hello'}], {'narration_backend':'higgs','higgs_reference_audio':str(reference)})
                synthesis.assert_not_called()

    def test_resolved_remote_address_is_never_connected(self):
        remote = str(ipaddress.IPv4Address(0x08080808))
        resolved = [(loopback.socket.AF_INET, loopback.socket.SOCK_STREAM, 6, '', (remote, 80))]
        with patch.object(loopback.socket, 'getaddrinfo', return_value=resolved), patch.object(loopback.socket, 'socket') as create:
            with self.assertRaisesRegex(OSError, 'loopback'):
                loopback.LoopbackConnection('localhost', 80, timeout=1).connect()
        create.assert_not_called()

    def test_overlapping_tutorial_steps_do_not_capture_or_act(self):
        ctx, director = Mock(), Mock()
        with package._step_lock:
            with self.assertRaisesRegex(RuntimeError, 'step is in progress'):
                package.step(ctx, director, 'id', 'Click', {'action': 'click'}, {'app': 'Demo', 'window_id': 123}, session_id='fixture-session')
        ctx.dispatch_tool.assert_not_called()
        director.job.assert_not_called()

    def test_raise_window_is_best_effort(self):
        from tutorial_test import core
        with patch.object(core.shutil, 'which', return_value=None):
            self.assertFalse(core.raise_window(':7', 123))
        with patch.object(core.shutil, 'which', return_value='/usr/bin/xdotool'), patch.object(core, 'run', return_value='') as run:
            self.assertTrue(core.raise_window(':7', 123))
        self.assertEqual(run.call_args.args[0], ['/usr/bin/xdotool', 'windowraise', '123'])
        with patch.object(core.shutil, 'which', return_value='/usr/bin/xdotool'), patch.object(core, 'run', side_effect=RuntimeError('x')):
            self.assertFalse(core.raise_window(':7', 123))

    def test_step_targets_window_with_its_own_pid_and_refuses_empty_capture(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp, patch.dict('os.environ', {'DISPLAY': ':7'}):
            Path(tmp, 'request.json').write_text(json.dumps({'display': ':7', 'window_id': 123}))
            director = Mock()
            director.job.return_value = Path(tmp)
            director.status.return_value = {'state': 'recording'}
            ctx = Mock()
            action, target = {'action': 'key', 'key': 'ctrl+a'}, {'app': 'Demo', 'window_id': 123}
            with patch.object(package, 'window_pid', return_value=4242):
                ctx.dispatch_tool.side_effect = [json.dumps({'mode': 'ax', 'width': 10, 'height': 10}), json.dumps({'status': 'blocked'})]
                package.step(ctx, director, 'id', 'Select all', action, target, session_id='fixture-session')
                self.assertEqual(ctx.dispatch_tool.call_args_list[0].args[1]['pid'], 4242)
                ctx.reset_mock(); director.reset_mock()
                ctx.dispatch_tool.side_effect = [json.dumps({'mode': 'ax', 'width': 0, 'height': 0})]
                with self.assertRaisesRegex(RuntimeError, 'could not target'):
                    package.step(ctx, director, 'id', 'Select all', action, target, session_id='fixture-session')
                self.assertEqual(ctx.dispatch_tool.call_count, 1)
                director.mark.assert_not_called()
                ctx.reset_mock()
                ctx.dispatch_tool.side_effect = [json.dumps({'mode': 'ax', 'width': 10, 'height': 10}), json.dumps({'status': 'blocked'})]
                package.step(ctx, director, 'id', 'Select all', action, {**target, 'pid': 77}, session_id='fixture-session')
                self.assertEqual(ctx.dispatch_tool.call_args_list[0].args[1]['pid'], 77)

    def test_type_into_spreadsheet_grid_is_pasted_instead(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp, patch.dict('os.environ', {'DISPLAY': ':7'}):
            Path(tmp, 'request.json').write_text(json.dumps({'display': ':7', 'window_id': 123}))
            director = Mock(); director.job.return_value = Path(tmp); director.mark.return_value = {'seconds': 1, 'label': 'x'}
            director.status.return_value = {'state': 'recording'}
            ctx = Mock()
            ctx.dispatch_tool.side_effect = [json.dumps({'mode': 'ax', 'width': 10, 'height': 10}), json.dumps({'ok': True}), json.dumps({'tree': 'ok'})]
            with patch.object(package, 'is_spreadsheet_grid', return_value=True), patch.object(package, 'set_clipboard') as clip, patch.object(package, 'window_pid', return_value=5):
                result = json.loads(package.step(ctx, director, 'id', 'Paste rows', {'action': 'type', 'text': 'a\tb\n'}, {'app': 'Calc', 'window_id': 123}, session_id='fixture-session'))
            clip.assert_called_once_with(':7', 'a\tb\n')
            sent = ctx.dispatch_tool.call_args_list[1].args[1]
            self.assertEqual((sent['action'], sent['keys']), ('key', 'ctrl+v'))
            self.assertNotIn('text', sent)
            self.assertIn('pasted_instead_of_typed', result['tutorial_step'])
            ctx.reset_mock()
            ctx.dispatch_tool.side_effect = [json.dumps({'mode': 'ax', 'width': 10, 'height': 10}), json.dumps({'status': 'blocked'})]
            with patch.object(package, 'is_spreadsheet_grid', return_value=False), patch.object(package, 'set_clipboard') as clip, patch.object(package, 'window_pid', return_value=5):
                package.step(ctx, director, 'id', 'Type', {'action': 'type', 'text': 'hello'}, {'app': 'Editor', 'window_id': 123}, session_id='fixture-session')
            clip.assert_not_called()
            self.assertEqual(ctx.dispatch_tool.call_args_list[1].args[1]['text'], 'hello')

    def test_teaching_step_refuses_chained_or_long_typed_lines(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp, patch.dict('os.environ', {'DISPLAY': ':7'}):
            Path(tmp, 'request.json').write_text(json.dumps({'display': ':7', 'window_id': 123}))
            director = Mock(); director.job.return_value = Path(tmp); director.status.return_value = {'state': 'recording'}
            ctx = Mock()
            for text in ('a && b && c', 'a ; b ; c', 'one\ntwo', 'x' * 111):
                with self.assertRaisesRegex(ValueError, 'ONE short command'):
                    package.step(ctx, director, 'id', 'Chain', {'action': 'type', 'text': text}, {'app': 'XTerm', 'window_id': 123}, session_id='fixture-session')
            ctx.dispatch_tool.assert_not_called()
            director.mark.assert_not_called()

    def test_export_name_accepts_path_or_name_without_extension(self):
        from tutorial_test.core import clean_export_name
        good = 'export-' + 'a' * 32
        for given in (good + '.mp4', good, '/tmp/x/job/' + good + '.mp4', '/tmp/x/job/' + good):
            self.assertEqual(clean_export_name(given), good + '.mp4')
        self.assertEqual(clean_export_name(None), None)

    def test_native_computer_use_keeps_denial_and_context(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp, patch.dict('os.environ', {'DISPLAY': ':7'}):
            Path(tmp, 'request.json').write_text(json.dumps({'display': ':7', 'window_id': 123}))
            director = Mock()
            director.job.return_value = Path(tmp)
            director.status.return_value = {'state': 'recording'}
            director.mark.return_value = {'seconds': 2, 'label': 'Click save'}
            ctx = Mock()
            target = {'app': 'Demo', 'window_id': 123}
            action = {'action': 'click', 'coordinate': [20, 30]}
            preflight = json.dumps({'mode': 'ax', 'app': 'Demo'})
            ctx.dispatch_tool.side_effect = [preflight, json.dumps({'status': 'blocked'})]
            result = package.step(ctx, director, 'id', 'Click save', action, target, parent_agent='context', session_id='fixture-session')
            self.assertEqual(json.loads(result)['status'], 'blocked')
            self.assertEqual(ctx.dispatch_tool.call_count, 2)
            self.assertEqual(ctx.dispatch_tool.call_args.kwargs['parent_agent'], 'context')
            self.assertEqual(ctx.dispatch_tool.call_args.kwargs['session_id'], 'fixture-session')
            ctx.reset_mock()
            ctx.dispatch_tool.side_effect = [preflight, json.dumps({'ok': False, 'message': 'Action failed'})]
            result = package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session')
            self.assertFalse(json.loads(result)['ok'])
            self.assertEqual(ctx.dispatch_tool.call_count, 2)
            ctx.reset_mock()
            ctx.dispatch_tool.side_effect = [preflight, json.dumps({'action': 'click'})]
            package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session')
            self.assertEqual(ctx.dispatch_tool.call_count, 2)
            ctx.reset_mock()
            ctx.dispatch_tool.side_effect = [preflight, json.dumps({'ok': True}), json.dumps({'tree': 'Saved'})]
            result = json.loads(package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session'))
            self.assertEqual(result['tree'], 'Saved')
            self.assertIn('Review', result['tutorial_step']['verification'])
            self.assertEqual(ctx.dispatch_tool.call_args.args[1]['action'], 'capture')
            ctx.reset_mock()
            image_block = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA=='}}
            envelope = {'_multimodal': True, 'content': [{'type': 'text', 'text': 'Captured'}, image_block], 'text_summary': 'Captured'}
            ctx.dispatch_tool.side_effect = [preflight, json.dumps({'ok': True}), envelope]
            result = package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session')
            self.assertIsInstance(result, dict)
            self.assertTrue(result['_multimodal'])
            self.assertEqual(result['content'][1], image_block)
            self.assertIn('tutorial_step', result['content'][-1]['text'])
            ctx.reset_mock()
            action_envelope = {**envelope, 'action_result': {'ok': True, 'action': 'click'}}
            ctx.dispatch_tool.side_effect = [preflight, action_envelope]
            result = package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session')
            self.assertTrue(result['_multimodal'])
            self.assertEqual(result['content'][1], image_block)
            self.assertEqual(ctx.dispatch_tool.call_count, 2)
            ctx.reset_mock()
            with self.assertRaisesRegex(ValueError, 'window ID'):
                package.step(ctx, director, 'id', 'Click save', action, {'app': 'Demo', 'window_id': 999}, session_id='fixture-session')
            with self.assertRaisesRegex(ValueError, 'Element-index'):
                package.step(ctx, director, 'id', 'Click save', {'action':'click', 'element':2}, target, session_id='fixture-session')
            ctx.dispatch_tool.assert_not_called()
            director.status.return_value = {'state': 'complete'}
            with self.assertRaisesRegex(ValueError, 'recording must be active'):
                package.step(ctx, director, 'id', 'Click save', action, target, session_id='fixture-session')
            ctx.dispatch_tool.assert_not_called()



@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class Media(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.director = Director(self.temp.name)
        self.job_id = uuid.uuid4().hex
        self.folder = Path(self.temp.name) / self.job_id
        self.folder.mkdir()
        write_json(self.folder / 'state.json', {'state': 'complete'})
        (self.folder / 'marks.jsonl').write_text(json.dumps({'seconds': 1.2, 'label': 'Observed change'}) + '\n')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
                        '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000', '-t', '3',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'pcm_s16le', str(self.folder / 'raw.mkv')], check=True, timeout=20)

    def tearDown(self): self.temp.cleanup()

    def test_cut_timeline_and_bounds(self):
        result = self.director.export(self.job_id, [{'start': 1, 'duration': 1}, {'start': 0, 'duration': .5}])
        self.assertTrue(result['decoded'])
        self.assertLess(result['seconds'], 2)
        timeline = self.director.timeline(self.job_id, Path(result['path']).name)
        self.assertAlmostEqual(timeline['steps'][0]['seconds'], .2)
        self.assertEqual(timeline['clips'][1]['output_start'], 1)
        frame = self.director.frame(self.job_id, Path(result['path']).name, .2)
        self.assertTrue(Path(frame['path']).read_bytes().startswith(b'\x89PNG'))
        for parts in [[{'start': 2, 'duration': 2}], [{'start': 0, 'duration': float('nan')}]]:
            with self.assertRaises(ValueError): self.director.export(self.job_id, parts)
        with self.assertRaises(ValueError): self.director.timeline(self.job_id, '../../other.mp4')

    def test_timestamped_tts_mix_cache_and_overrun(self):
        result = self.director.export(self.job_id, [{'start': 0, 'duration': 2.5}])
        requests = []
        class Server(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                data = voice_fixture()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(('localhost', 0), Server)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        settings = {'narration_backend':'higgs','higgs_url': f'http://localhost:{server.server_port}'}
        cues = [{'start': .1, 'end': .8, 'text': 'First step.'}, {'start': 1.2, 'end': 2, 'text': 'Second step.'}]
        try:
            output = narrate(self.temp.name, self.job_id, Path(result['path']).name, cues, settings)
            self.assertEqual(output['state'], 'complete')
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(r['model'] == 'bosonai/higgs-tts-3-4b' for r in requests))
            srt = Path(output['captions']).read_text()
            self.assertIn('00:00:01,200 --> 00:00:01,600', srt)
            self.assertTrue(Path(output['path']).with_suffix('.credit.txt').exists())
            too_short = [{'start': 0, 'end': .1, 'text': 'First step.'}]
            blocked = narrate(self.temp.name, self.job_id, Path(result['path']).name, too_short, settings)
            self.assertEqual(blocked['state'], 'needs_timing_revision')
            self.assertEqual(len(requests), 2, 'Unchanged speech should reuse the cached WAV')
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': unittest.main()
