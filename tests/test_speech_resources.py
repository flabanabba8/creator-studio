import importlib.util, json, tempfile, unittest, wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sr_under_test', ROOT / 'common' / 'speech_resources.py')
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)
NO = lambda n: None
ANSWERS = {'needs': 'lesson voice-overs in English', 'quality': 'plain-ok', 'allow_cloud': False, 'allow_paid': False, 'budget_usd': 0, 'has': [], 'voice_notes': ''}


def found(tools, **kw):
    return sr.discover(kw.pop('settings', {}), secret_present=kw.pop('keys', lambda n: False), which=lambda n: '/bin/' + n if n in tools else None, platform=kw.pop('platform', 'linux'), probe=False)


class Discovery(unittest.TestCase):
    def test_nothing_found_gives_plain_advice(self):
        r = found([])
        self.assertEqual(r['backends'], [])
        self.assertIn('espeak-ng', r['advice'])

    def test_nothing_is_ranked_recommended_or_picked(self):
        r = found(['flite', 'espeak-ng'], keys=lambda n: n == 'GEMINI_API_KEY')
        self.assertNotIn('recommended', r)
        self.assertEqual(sr.chosen(r, None), None)          # no profile -> no route
        self.assertEqual(sr.chosen(r, {'route': None}), None)
        with self.assertRaisesRegex(ValueError, 'No speech route has been chosen'):
            sr.resolve({}, 'auto', r)
        with self.assertRaises(ValueError):
            sr.resolve({}, 'chosen', r)

    def test_options_describe_where_text_goes_and_cost(self):
        r = found(['flite'], keys=lambda n: n == 'GEMINI_API_KEY')
        by = {o['id']: o for o in sr.ready_options(r)}
        self.assertEqual(by['system:flite']['where_text_goes'], 'stays on this computer'); self.assertEqual(by['system:flite']['cost'], 'free')
        self.assertIn('online', by['gemini:developer']['where_text_goes']); self.assertEqual(by['gemini:developer']['cost'], 'may cost money')

    def test_only_the_route_the_user_chose_is_returned(self):
        r = found(['flite', 'espeak-ng'])
        self.assertEqual(sr.chosen(r, {'route': 'system:flite'})['id'], 'system:flite')
        self.assertIsNone(sr.chosen(r, {'route': 'system:say'}))     # chosen route no longer available -> ask again

    def test_platform_tools_respected(self):
        self.assertNotIn('system:say', [b['id'] for b in found(['say'], platform='linux')['backends']])
        self.assertIn('system:say', [b['id'] for b in found(['say'], platform='darwin')['backends']])
        self.assertIn('system:sapi', [b['id'] for b in found(['powershell'], platform='win32')['backends']])

    def test_piper_needs_a_model_file(self):
        self.assertFalse([b for b in found(['piper'])['backends'] if b['ready']])
        with tempfile.NamedTemporaryFile(suffix='.onnx') as f:
            self.assertIn('system:piper', [b['id'] for b in found(['piper'], settings={'piper_model': f.name})['backends'] if b['ready']])

    def test_unsupported_hosted_providers_are_never_reported(self):
        r = sr.discover({}, secret_present=lambda n: True, which=NO, probe=False, hosted=('gemini',))
        self.assertEqual([b['id'] for b in r['backends']], ['gemini:developer'])

    def test_no_secret_value_appears_in_a_report(self):
        r = sr.discover({'gemini_project': 'secret-project-x'}, secret_present=lambda n: True, which=NO, probe=False)
        self.assertNotIn('secret-project-x', json.dumps(r))

    def test_explicit_unavailable_route_is_refused_with_advice(self):
        with self.assertRaisesRegex(ValueError, 'not available'):
            sr.resolve({}, 'elevenlabs', found([]))

    def test_no_cloud_setting_removes_online_routes(self):
        r = found([], keys=lambda n: n == 'GEMINI_API_KEY', settings={'speech_allow_cloud': 'false'})
        self.assertEqual(r['backends'], [])


class Hardware(unittest.TestCase):
    CATALOG = {'verified': '2026-11-12', 'remote': [
        {'id': 'elevenlabs', 'name': 'ElevenLabs', 'free_tier': 'F3', 'source': 'u3', 'verified': '2026-11-12'},
        {'id': 'gemini', 'name': 'Gemini 3.8 Flash TTS', 'free_tier': 'F1', 'source': 'u1', 'verified': '2026-11-12'},
        {'id': 'inworld', 'name': 'Inworld', 'free_tier': 'F2', 'source': 'u2', 'verified': '2026-11-12'}],
        'local': [
        {'id': 'big', 'name': 'Big', 'tier': 1, 'min_vram_gb': 16, 'min_ram_gb': 16, 'cpu_ok': False},
        {'id': 'mid', 'name': 'Mid', 'tier': 2, 'min_vram_gb': 6, 'min_ram_gb': 8, 'cpu_ok': False},
        {'id': 'small', 'name': 'Small', 'tier': 3, 'min_vram_gb': None, 'min_ram_gb': 1, 'cpu_ok': True},
        {'id': 'tiny', 'name': 'Tiny', 'tier': 4, 'min_vram_gb': None, 'min_ram_gb': 0.2, 'cpu_ok': True}]}

    def hw(self, ram, gpus=(), apple=False):
        return {'os': 'linux', 'cpu_threads': 8, 'ram_gb': ram, 'gpus': [{'vendor': 'nvidia', 'name': 'x', 'vram_gb': g} for g in gpus], 'apple_silicon': apple}

    def test_remote_services_are_suggested_in_the_stated_order_with_their_sources(self):
        r = sr.recommend(self.hw(16), self.CATALOG)['remote_in_suggested_order']
        self.assertEqual([x['id'] for x in r], ['gemini', 'inworld', 'elevenlabs'])
        self.assertEqual([x['rank'] for x in r], [1, 2, 3]); self.assertEqual(r[0]['source'], 'u1')

    def test_no_online_answer_hides_remote_suggestions(self):
        self.assertEqual(sr.recommend(self.hw(16), self.CATALOG, allow_cloud=False)['remote_in_suggested_order'], [])

    def test_local_models_follow_the_hardware(self):
        ids = lambda hw: [m['id'] for m in sr.recommend(hw, self.CATALOG)['local_that_fit_this_computer']]
        self.assertEqual(ids(self.hw(32, [24])), ['big', 'mid', 'small', 'tiny'])
        self.assertEqual(ids(self.hw(32, [8])), ['mid', 'small', 'tiny'])
        self.assertEqual(ids(self.hw(4)), ['small', 'tiny'])
        self.assertEqual(ids(self.hw(0.5)), ['tiny'])

    def test_apple_silicon_counts_unified_memory(self):
        self.assertEqual(sr.usable_gpu_memory(self.hw(32, apple=True)), 22.4)
        self.assertIn('mid', [m['id'] for m in sr.recommend(self.hw(16, apple=True), self.CATALOG)['local_that_fit_this_computer']])

    def test_hardware_reader_reads_compute_capability_when_the_driver_reports_it(self):
        run = lambda argv, **k: mock.Mock(returncode=0, stdout='NVIDIA GeForce RTX 4090, 24564, 8.9\n')
        hw = sr.hardware(run=run, platform='linux', which=lambda n: '/bin/nvidia-smi' if n == 'nvidia-smi' else None, read_text=lambda p: 'MemTotal: 1048576 kB\n')
        self.assertEqual(hw['gpus'], [{'vendor': 'nvidia', 'name': 'NVIDIA GeForce RTX 4090', 'vram_gb': 24.0, 'compute_capability': 8.9}])

    def test_hardware_reader_parses_nvidia_and_meminfo_and_leaks_no_identity(self):
        def run(argv, **k):
            return mock.Mock(returncode=0, stdout='NVIDIA GeForce RTX 4090, 24564\nNVIDIA Tesla T4, 15360\n')
        hw = sr.hardware(run=run, platform='linux', which=lambda n: '/bin/' + n if n == 'nvidia-smi' else None, read_text=lambda p: 'MemTotal:       29571020 kB\n')
        self.assertEqual(hw['ram_gb'], 28.2); self.assertEqual([g['vram_gb'] for g in hw['gpus']], [24.0, 15.0])
        self.assertEqual(set(hw), {'os', 'cpu_threads', 'ram_gb', 'gpus', 'apple_silicon'})

    def test_missing_tools_give_a_cpu_only_report_not_an_error(self):
        hw = sr.hardware(run=lambda *a, **k: (_ for _ in ()).throw(OSError()), platform='linux', which=lambda n: None, read_text=lambda p: (_ for _ in ()).throw(OSError()))
        self.assertEqual((hw['gpus'], hw['ram_gb']), ([], None))

    def test_real_hardware_report_runs(self):
        hw = sr.hardware()
        self.assertGreaterEqual(hw['cpu_threads'], 1)

    def test_interview_carries_the_recommendations_but_still_asks(self):
        with tempfile.TemporaryDirectory() as d:
            out = sr.interview({}, Path(d) / 'ns', found(['flite']))
            self.assertIn('recommendations', out); self.assertEqual(out['state'], 'interview_needed')
            self.assertIn('Gemini 3.8 Flash TTS for the best quality, then Inworld, then ElevenLabs', out['instructions_for_agent'])


class Catalog(unittest.TestCase):
    def setUp(self):
        self.cat = sr.load_catalog()
        self.wiki = (ROOT / 'llmwiki' / 'speech-models.md').read_text()

    def test_catalog_is_dated_and_every_claim_has_a_source(self):
        self.assertRegex(self.cat['verified'], r'^\d{4}-\d\d-\d\d$')
        for row in self.cat['remote'] + self.cat['local']:
            self.assertTrue(row['source'].startswith('https://'), row['id'])
            self.assertRegex(row['verified'], r'^\d{4}-\d\d-\d\d$')

    def test_remote_order_is_gemini_inworld_elevenlabs_and_free_tiers_are_stated(self):
        self.assertEqual(sr.REMOTE_ORDER, ('gemini', 'inworld', 'elevenlabs'))
        by = {r['id']: r for r in self.cat['remote']}
        for key in sr.REMOTE_ORDER:
            self.assertTrue(by[key]['free_tier'] and by[key]['paid'], key)
        self.assertIn('UNVERIFIED', by['elevenlabs']['free_tier'])      # honest about what could not be confirmed
        self.assertIn('no credit card', by['gemini']['free_tier'])

    def test_local_models_that_need_vram_say_where_the_number_came_from(self):
        for m in self.cat['local']:
            if m['min_vram_gb'] is not None:
                self.assertTrue(m['vram_basis'], m['id'])

    def test_retired_and_archived_models_are_never_recommended(self):
        ids = {m['id'] for m in sr.recommend({'os': 'linux', 'cpu_threads': 8, 'ram_gb': 64, 'gpus': [{'vendor': 'nvidia', 'name': 'x', 'vram_gb': 48}], 'apple_silicon': False}, self.cat)['local_that_fit_this_computer']}
        self.assertFalse(ids & {'chatterbox', 'supertonic-3', 'melotts'})

    def test_recommendations_name_licence_and_whether_this_plugin_can_use_the_model(self):
        r = sr.recommend({'os': 'linux', 'cpu_threads': 8, 'ram_gb': 32, 'gpus': [{'vendor': 'nvidia', 'name': 'x', 'vram_gb': 24}], 'apple_silicon': False}, self.cat)['local_that_fit_this_computer']
        higgs = [m for m in r if m['id'] == 'higgs-tts-3'][0]
        self.assertEqual(higgs['commercial'], 'restricted'); self.assertTrue(higgs['works_with_this_plugin'].startswith('yes'))
        orpheus = [m for m in r if m['id'] == 'orpheus-3b'][0]
        self.assertTrue(orpheus['works_with_this_plugin'].startswith('not directly'))

    def test_a_weak_computer_gets_cpu_models_only(self):
        r = sr.recommend({'os': 'linux', 'cpu_threads': 4, 'ram_gb': 8, 'gpus': [], 'apple_silicon': False}, self.cat)['local_that_fit_this_computer']
        self.assertTrue(r and all(m['fit'].startswith('runs on CPU') for m in r))

    def test_wiki_lists_every_model_and_service_with_its_source(self):
        for row in self.cat['remote'] + self.cat['local']:
            self.assertIn(row['name'], self.wiki, row['id'])
            self.assertIn(row['source'], self.wiki, row['id'])
        for other in self.cat['other_remote_with_free_tiers']:
            self.assertIn(other['name'], self.wiki)

    def test_wiki_tells_the_agent_to_recheck_and_never_pick(self):
        self.assertIn('never picks an engine', self.wiki)
        self.assertIn('open the source link again', self.wiki)
        self.assertIn('UNVERIFIED', self.wiki)

    def test_servers_only_name_models_that_exist_and_each_has_a_source(self):
        ids = {m['id'] for m in self.cat['local']}
        for sv in self.cat['servers']:
            self.assertTrue(sv['source'].startswith('https://'), sv['id'])
            for mid in sv['models']:
                self.assertIn(mid, ids, '%s lists unknown model %s' % (sv['id'], mid))

    def test_wiki_lists_every_server_and_its_source(self):
        for sv in self.cat['servers']:
            self.assertIn(sv['name'], self.wiki); self.assertIn(sv['source'], self.wiki)

    def test_the_catalog_is_broad_and_marks_unverified_hardware_instead_of_guessing(self):
        self.assertGreaterEqual(len(self.cat['local']), 45)
        self.assertGreaterEqual(len(self.cat['servers']), 10)
        for m in self.cat['local']:
            if m.get('hardware_unverified'):
                self.assertFalse(m['recommend'], m['id'])      # never recommended on a guess

    def test_llama_cpp_and_ollama_are_listed_as_openai_style_servers_with_their_limits(self):
        by = {sv['id']: sv for sv in self.cat['servers']}
        self.assertIn('wav or pcm only', by['llama-cpp']['openai_style']); self.assertIn('speaker_ref_b64', by['llama-cpp']['openai_style'])
        self.assertIn('wav or pcm only', by['ollama']['openai_style'])
        self.assertIn('phonon', by['ollama']['models'])

    def test_a_model_runnable_behind_a_server_says_so_and_who(self):
        hw = {'os': 'linux', 'cpu_threads': 8, 'ram_gb': 32, 'gpus': [{'vendor': 'nvidia', 'name': 'x', 'vram_gb': 24, 'compute_capability': 8.9}], 'apple_silicon': False}
        r = {m['id']: m for m in sr.recommend(hw, self.cat)['local_that_fit_this_computer']}
        q = r['qwen3-tts-1.7b']
        self.assertTrue(q['works_with_this_plugin'].startswith('yes, once run behind'))
        self.assertIn('vLLM-Omni', [s['name'] for s in q['servers_that_can_run_it']])

    def test_an_old_gpu_gets_a_warning_for_a_model_that_documents_a_newer_one(self):
        hw = {'os': 'linux', 'cpu_threads': 8, 'ram_gb': 32, 'gpus': [{'vendor': 'nvidia', 'name': 'GTX 1080', 'vram_gb': 8.0, 'compute_capability': 6.1}], 'apple_silicon': False}
        r = {m['id']: m for m in sr.recommend(hw, self.cat)['local_that_fit_this_computer']}
        self.assertIn('older', r['qwen3-tts-1.7b']['gpu_note'])
        self.assertIsNone(r['voxcpm2']['gpu_note'])

    def test_vram_figures_say_whether_stated_user_reported_or_estimated(self):
        for m in self.cat['local']:
            if m['min_vram_gb'] is not None:
                self.assertRegex(m['vram_basis'].lower(), r'stated|user-reported|estimate|conservative', m['id'])

    def test_pagecast_copy_of_the_wiki_and_catalog_match_when_present(self):
        other = ROOT.parent / 'pagecast-director'
        if (other / 'speech_catalog.json').exists():
            self.assertEqual((other / 'speech_catalog.json').read_text(), (ROOT / 'common' / 'speech_catalog.json').read_text())
            self.assertEqual((other / 'llmwiki' / 'speech-models.md').read_text(), self.wiki)


class Staleness(unittest.TestCase):
    import datetime as _d
    EXP = [{'date': '2026-12-31', 'what': 'promo ends'}]

    def day(self, y, m, d):
        return self._d.date(y, m, d)

    def test_fresh_knowledge_is_not_stale_and_does_not_nag(self):
        f = sr.freshness('2026-11-12', self.EXP, None, self.day(2026, 11, 20))
        self.assertFalse(f['stale']); self.assertEqual(f['reasons'], []); self.assertIsNone(f['offer'])

    def test_old_knowledge_is_stale_and_the_offer_asks_before_researching(self):
        f = sr.freshness('2026-09-01', [], None, self.day(2026, 11, 20))
        self.assertTrue(f['stale']); self.assertIn('days ago', f['reasons'][0])
        self.assertIn('ASK whether', f['offer']); self.assertIn('Do not research without their yes', f['offer'])

    def test_a_passed_deadline_makes_it_stale_even_when_recently_checked(self):
        f = sr.freshness('2026-12-30', self.EXP, None, self.day(2027, 1, 3))
        self.assertTrue(f['stale']); self.assertTrue(any('deadline has passed' in r for r in f['reasons']))
        self.assertFalse(sr.freshness('2027-01-02', self.EXP, None, self.day(2027, 1, 3))['stale'])   # checked after the deadline: already reflected

    def test_an_approaching_deadline_is_flagged_but_not_stale(self):
        f = sr.freshness('2026-12-20', self.EXP, None, self.day(2026, 12, 25))
        self.assertFalse(f['stale']); self.assertEqual(len(f['coming_up']), 1); self.assertIsNotNone(f['offer'])

    def test_approved_research_resets_the_age(self):
        self.assertTrue(sr.freshness('2026-09-01', [], None, self.day(2026, 11, 20))['stale'])
        self.assertFalse(sr.freshness('2026-09-01', [], '2026-11-19', self.day(2026, 11, 20))['stale'])

    def test_missing_date_counts_as_stale(self):
        self.assertTrue(sr.freshness(None, [], None, self.day(2026, 11, 20))['stale'])

    def test_every_catalog_deadline_has_a_source_and_the_real_catalog_reports_freshness(self):
        cat = sr.load_catalog()
        for e in cat['expiries']:
            self.assertTrue(e['source'].startswith('https://')); self.assertRegex(e['date'], r'^\d{4}-\d\d-\d\d$')
        with tempfile.TemporaryDirectory() as d:
            out = sr.interview({}, Path(d) / 'ns', found(['flite']))
            self.assertIn('knowledge_freshness', out); self.assertIn('knowledge_freshness', out['instructions_for_agent'])

    def test_research_updates_are_validated_stored_privately_and_laid_over_the_catalog(self):
        ok = {'id': 'gemini', 'field': 'free_tier', 'value': 'NEW', 'source': 'https://aistudio.google.com/docs/pricing', 'date': '2026-11-12'}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            for bad in ({**ok, 'id': 'nope'}, {**ok, 'field': 'tier'}, {**ok, 'source': 'http://x'}, {**ok, 'date': '2099-01-01'}, {**ok, 'extra': 1}, {**ok, 'value': 'x' * 2000}):
                with self.assertRaises(ValueError):
                    sr.save_updates(root, [bad], sr.known_ids(), self.day(2026, 11, 12))
            with self.assertRaises(ValueError):
                sr.save_updates(root, [], sr.known_ids())
            sr.save_updates(root, [ok], sr.known_ids(), self.day(2026, 11, 12))
            self.assertEqual(oct(sr._updates_path(root).stat().st_mode & 0o777), '0o600')
            cat = sr.load_catalog(update_root=root)
            row = [r for r in cat['remote'] if r['id'] == 'gemini'][0]
            self.assertEqual(row['free_tier'], 'NEW'); self.assertEqual(row['updated_by_research']['free_tier']['date'], '2026-11-12')
            self.assertEqual(cat['last_refresh'], '2026-11-12')
            self.assertNotEqual([r for r in sr.load_catalog()['remote'] if r['id'] == 'gemini'][0]['free_tier'], 'NEW')   # shipped catalog untouched

    def test_setup_flow_stores_updates_and_still_asks_the_questions(self):
        ok = {'id': 'elevenlabs', 'field': 'free_tier', 'value': 'checked', 'source': 'https://elevenlabs.io/pricing', 'date': sr._today().isoformat()}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            out = sr.apply_setup(root, found(['flite']), {}, None, [ok])
            self.assertEqual(out['knowledge_updates_saved'], 1); self.assertEqual(out['state'], 'interview_needed')

    def test_generic_block_is_identical_in_every_plugin_that_has_it(self):
        def block(path):
            t = Path(path).read_text()
            return t[t.index('# ---- knowledge freshness'):t.index('# ---- end knowledge freshness ----')]
        mine = block(ROOT / 'common' / 'speech_resources.py')
        other = ROOT.parent / 'pagecast-director' / 'speech_resources.py'
        if other.exists():
            self.assertEqual(block(other), mine)
        modlab = ROOT.parent / 'modlab' / 'resources.py'
        if modlab.exists():
            self.assertEqual(block(modlab), mine)


class Loopback(unittest.TestCase):
    def test_only_real_loopback_http_addresses_are_ever_probed(self):
        for bad in ('http://127.0.0.1.evil.example:8000', 'https://127.0.0.1:8000', 'http://user:pw@127.0.0.1:8000', 'http://192.168.1.5:8000', 'ftp://127.0.0.1', 'http://localhost.evil.example'):
            self.assertFalse(sr._is_loopback_http(bad), bad)
            self.assertIsNone(sr._server_models(bad))
        for good in ('http://127.0.0.1:8000', 'http://localhost:8880', 'http://[::1]:5002'):
            self.assertTrue(sr._is_loopback_http(good), good)

    def test_a_probe_does_not_follow_a_redirect_off_the_computer(self):
        import http.server, threading
        hits = []
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path); self.send_response(302); self.send_header('Location', 'http://192.0.2.1/v1/models'); self.end_headers()
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            self.assertIsNone(sr._server_models('http://127.0.0.1:%d' % srv.server_address[1], timeout=2))
            self.assertEqual(hits, ['/v1/models'])
        finally:
            srv.shutdown()

    def test_a_real_answering_server_is_found(self):
        import http.server, threading
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({'data': [{'id': 'fixture-voice'}]}).encode(); self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = 'http://127.0.0.1:%d' % srv.server_address[1]
            with mock.patch.object(sr, 'LOOPBACK_PORTS', ()):   # hermetic: a speech server running on this machine must not change the result
                self.assertEqual(sr.find_servers([url]), [{'url': url, 'models': ['fixture-voice']}])
        finally:
            srv.shutdown()


class Synthesis(unittest.TestCase):
    def test_arguments_are_a_list_and_odd_voices_are_refused(self):
        for bad in ('-x', 'a;rm -rf /', 'x' * 200):
            with self.assertRaises(ValueError):
                sr.synthesize_system('flite', 'hello', bad, '/tmp/x.wav')
        with self.assertRaises(ValueError):
            sr.synthesize_system('flite', 'bad \x07 text', 'rms', '/tmp/x.wav')

    def test_text_starting_with_a_dash_is_not_an_option(self):
        seen = {}
        def run(argv, **kw):
            seen['argv'], seen['input'] = argv, kw.get('input')
            Path(argv[argv.index('-w') + 1]).write_bytes(b'RIFF' + b'0' * 200)
            return mock.Mock(returncode=0)
        with tempfile.TemporaryDirectory() as d:
            sr.synthesize_system('espeak-ng', '--version please', 'en-us', Path(d) / 'o.wav', which=lambda n: '/bin/' + n, run=run)
        self.assertEqual(seen['input'], '--version please')
        self.assertNotIn('--version please', seen['argv'])

    def test_failed_program_is_an_error_not_silence(self):
        with self.assertRaisesRegex(RuntimeError, 'did not produce audio'):
            sr.synthesize_system('flite', 'hi', 'rms', '/tmp/never-written.wav', which=lambda n: '/bin/flite', run=lambda *a, **k: mock.Mock(returncode=1))

    def test_real_flite_if_installed(self):
        import shutil
        if not shutil.which('flite'):
            self.skipTest('flite not installed')
        with tempfile.TemporaryDirectory() as d:
            out = sr.synthesize_system('flite', 'This is a short test.', 'rms', Path(d) / 'o.wav')
            with wave.open(out) as w:
                self.assertGreater(w.getnframes(), 1000)

    def test_speakers_get_different_voices_and_sharing_is_reported(self):
        voices, shared = sr.assign_voices('espeak-ng', ['Host', 'Guest'], which=lambda n: n)
        self.assertNotEqual(voices['Host'], voices['Guest']); self.assertFalse(shared)
        voices, shared = sr.assign_voices('sapi', ['A', 'B'], which=lambda n: n)
        self.assertTrue(shared)
        voices, _ = sr.assign_voices('espeak-ng', ['A', 'B'], {'A': 'en-gb'}, which=lambda n: n)
        self.assertEqual(voices['A'], 'en-gb')


class Interview(unittest.TestCase):
    def test_first_use_lists_options_and_asks_which_one_and_picks_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            out = sr.interview({}, root, found(['flite', 'espeak-ng']))
            self.assertEqual(out['state'], 'interview_needed')
            self.assertEqual({o['id'] for o in out['options']}, {'system:flite', 'system:espeak-ng'})
            ask = [q for q in out['questions'] if q['key'] == 'route'][0]
            self.assertEqual(len(ask['choices']), 2)
            self.assertIn('Do not choose a speech engine for the user', out['instructions_for_agent'])
            self.assertIn('Do not ask for or accept key values', out['instructions_for_agent'])
            self.assertIsNone(sr.load_profile(root))

    def test_answers_without_a_route_are_refused_when_options_exist(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'Ask the user which'):
                sr.interview({}, Path(d) / 'ns', found(['flite']), ANSWERS)
            self.assertIsNone(sr.load_profile(Path(d) / 'ns'))      # a refused interview saves nothing

    def test_a_route_that_was_not_offered_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'not one of the available options'):
                sr.interview({}, Path(d) / 'ns', found(['flite']), {**ANSWERS, 'route': 'elevenlabs'})

    def test_no_online_answer_refuses_an_online_route(self):
        with tempfile.TemporaryDirectory() as d:
            r = found(['flite'], keys=lambda n: n == 'GEMINI_API_KEY')
            with self.assertRaisesRegex(ValueError, 'nothing should be sent online'):
                sr.interview({}, Path(d) / 'ns', r, {**ANSWERS, 'allow_cloud': False, 'route': 'gemini:developer'})

    def test_answers_are_validated_saved_private_and_the_chosen_route_is_used(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            r = found(['flite'], keys=lambda n: n == 'GEMINI_API_KEY')
            for bad in ({}, {**ANSWERS, 'quality': 'great', 'route': 'system:flite'}, {**ANSWERS, 'allow_paid': True, 'route': 'system:flite'}, {**ANSWERS, 'allow_cloud': True, 'allow_paid': True, 'budget_usd': 0, 'route': 'system:flite'}, {**ANSWERS, 'has': ['bank_login'], 'route': 'system:flite'}, {**ANSWERS, 'needs': '', 'route': 'system:flite'}):
                with self.assertRaises(ValueError):
                    sr.interview({}, root, r, bad)
            out = sr.interview({}, root, r, {**ANSWERS, 'route': 'system:flite'})
            self.assertEqual((out['state'], out['you_chose']), ('saved', 'system:flite'))
            self.assertTrue(any('nothing should be sent online' in g for g in out['gaps']))
            self.assertEqual(oct(sr.profile_path(root).stat().st_mode & 0o777), '0o600')
            self.assertEqual(sr.interview({}, root, r)['state'], 'answered')
            self.assertEqual(sr.chosen(r, sr.load_profile(root))['id'], 'system:flite')
            self.assertEqual(sr.apply_profile({}, sr.load_profile(root))['speech_allow_cloud'], 'false')

    def test_a_profile_without_a_route_asks_again_when_options_exist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            sr.save_profile(root, ANSWERS)    # older profile with no route
            self.assertEqual(sr.interview({}, root, found(['flite']))['state'], 'interview_needed')

    def test_paid_answers_set_only_a_spending_cap(self):
        profile = {**ANSWERS, 'answered': True, 'allow_cloud': True, 'allow_paid': True, 'budget_usd': 2.5}
        s = sr.apply_profile({}, profile)
        self.assertEqual(s['gemini_max_usd'], 2.5); self.assertNotIn('speech_auto_allow_paid', s)
        self.assertEqual(sr.apply_profile({'gemini_max_usd': '1'}, profile)['gemini_max_usd'], 1.0)   # a stricter user limit stays

    def test_gaps_name_what_is_missing(self):
        profile = {**ANSWERS, 'quality': 'natural', 'allow_cloud': True, 'has': ['local_server', 'gemini_key']}
        notes = ' '.join(sr.gaps(found(['flite']), profile))
        self.assertIn('robotic', notes); self.assertIn('speech server', notes); self.assertIn('gemini key', notes)

class WrongKindOfServer(unittest.TestCase):
    def test_a_recognition_server_is_not_offered_as_a_voice(self):
        from unittest import mock
        servers = lambda urls, probe=True: [{'url': 'http://127.0.0.1:8000', 'models': ['bosonai/higgs-tts-3-4b']}, {'url': 'http://127.0.0.1:8080', 'models': ['Systran/faster-whisper-small.en']}]
        with mock.patch.object(sr, 'find_servers', servers):
            ids = [b["id"] for b in sr.discover({}, secret_present=lambda n: False, which=lambda n: None, probe=True)['backends']]
        self.assertIn('server:http://127.0.0.1:8000', ids); self.assertNotIn('server:http://127.0.0.1:8080', ids)


if __name__ == '__main__':
    unittest.main()
