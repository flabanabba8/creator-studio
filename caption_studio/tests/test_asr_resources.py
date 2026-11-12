import datetime
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asr_under_test', ROOT / 'asr_resources.py')
A = importlib.util.module_from_spec(spec); sys.modules[spec.name] = A; spec.loader.exec_module(A)
NO = lambda n: None
ANSWERS = {'languages': 'English', 'minutes': 60, 'allow_upload': False, 'priority': 'accurate timing', 'speakers': False, 'subscriptions': ['none'], 'has': ''}


def found(keys=(), commands=(), **kw):
    return A.discover(kw.pop('settings', {}), secret_present=lambda n: n in keys, which=lambda n: '/bin/' + n if n in commands else None, probe=False, local_commands=kw.pop('local_commands', ()))


class Discovery(unittest.TestCase):
    def test_import_is_always_there_and_nothing_else_is_assumed(self):
        r = found()
        self.assertEqual([x['id'] for x in r['routes']], ['import']); self.assertIn('import route', r['advice'] + 'import route')

    def test_a_key_makes_the_service_visible_and_only_callable_ones_ready(self):
        r = {x['id']: x for x in found(keys=('GROQ_API_KEY', 'DEEPGRAM_API_KEY'))['routes']}
        self.assertTrue(r['remote:groq']['ready']); self.assertFalse(r['remote:deepgram']['ready'])
        self.assertIn('cannot call it directly', r['remote:deepgram']['detail'])

    def test_installed_programs_need_a_wrapper_and_are_not_offered_as_ready(self):
        r = {x['id']: x for x in found(commands=('whisper-cli',))['routes']}
        self.assertFalse(r['program:whisper-cli']['ready']); self.assertIn('wrapper', r['program:whisper-cli']['detail'])

    def test_no_secret_value_ever_appears(self):
        self.assertNotIn('hunter2', json.dumps(found(keys=('GROQ_API_KEY',), settings={'asr_server_url': 'http://127.0.0.1:1', 'x': 'hunter2'})))

    def test_nothing_is_chosen_without_the_users_route(self):
        r = found(keys=('GROQ_API_KEY',))
        self.assertIsNone(A.chosen(r, None)); self.assertIsNone(A.chosen(r, {'route': None})); self.assertIsNone(A.chosen(r, {'route': 'remote:deepgram'}))
        self.assertEqual(A.chosen(r, {'route': 'remote:groq'})['id'], 'remote:groq')

    def test_no_upload_answer_hides_online_routes(self):
        r = A.filter_routes(found(keys=('GROQ_API_KEY',)), {'asr_allow_upload': 'false'})
        self.assertEqual([x['id'] for x in r['routes']], ['import'])


class Recognizer(unittest.TestCase):
    def test_a_chosen_server_becomes_a_word_timestamp_http_recognizer(self):
        rec = A.recognizer_for({'id': 'server:http://127.0.0.1:8000', 'kind': 'server', 'models': ['Systran/faster-whisper-small']})
        self.assertEqual(rec['endpoint'], 'http://127.0.0.1:8000/v1/audio/transcriptions'); self.assertEqual(rec['fields']['timestamp_granularities[]'], 'word')

    def test_groq_needs_consent_and_the_stored_key_and_never_carries_a_key(self):
        rec = A.recognizer_for({'id': 'remote:groq', 'kind': 'remote', 'service': 'groq'})
        self.assertTrue(rec['allow_upload']); self.assertTrue(rec['use_api_key']); self.assertNotIn('Authorization', json.dumps(rec))

    def test_a_route_that_cannot_be_run_is_refused_with_the_import_route_as_the_way_out(self):
        with self.assertRaisesRegex(ValueError, 'import route'):
            A.recognizer_for({'id': 'remote:deepgram', 'kind': 'remote', 'service': 'deepgram'})


class Recommend(unittest.TestCase):
    CAT = {'verified': '2026-11-12', 'local': [
        {'id': 'big', 'name': 'Big', 'tier': 1, 'min_vram_gb': 16, 'min_ram_gb': 16, 'cpu_ok': False, 'word_timestamps': 'yes', 'source': 'https://x'},
        {'id': 'cpu', 'name': 'Cpu', 'tier': 2, 'min_vram_gb': None, 'min_ram_gb': 2, 'cpu_ok': True, 'word_timestamps': 'yes', 'source': 'https://x'},
        {'id': 'dc', 'name': 'Datacentre', 'tier': 3, 'min_vram_gb': 80, 'min_ram_gb': 64, 'cpu_ok': False, 'recommend': False, 'source': 'https://x'}],
        'remote': [{'id': 'a', 'name': 'A', 'free_minutes': {'minutes': 100, 'basis': 'stated'}, 'source': 'https://a'}, {'id': 'b', 'name': 'B', 'source': 'https://b'}],
        'servers': [], 'subscriptions': [{'id': 'chatgpt-pro-business', 'name': 'ChatGPT Pro', 'finding': 'f', 'source': 'https://s'}, {'id': 'huggingface-pro', 'name': 'HF', 'finding': 'f', 'source': 'https://h'}]}

    def hw(self, ram, gpus=()): return {'os': 'linux', 'cpu_threads': 8, 'ram_gb': ram, 'gpus': [{'vendor': 'nvidia', 'name': 'x', 'vram_gb': g} for g in gpus], 'apple_silicon': False}

    def test_local_models_follow_hardware_and_datacentre_ones_are_never_suggested(self):
        ids = lambda hw: [m['id'] for m in A.recommend(hw, self.CAT)['local_that_fit_this_computer']]
        self.assertEqual(ids(self.hw(32, [24])), ['big', 'cpu']); self.assertEqual(ids(self.hw(4)), ['cpu']); self.assertEqual(ids(self.hw(32, [80])), ['big', 'cpu'])

    def test_free_allowance_is_compared_with_the_users_minutes(self):
        r = {x['id']: x for x in A.recommend(self.hw(8), self.CAT, minutes=60)['online_services']}
        self.assertTrue(r['a']['free_allowance_covers_your_audio'].startswith('yes'))
        r = {x['id']: x for x in A.recommend(self.hw(8), self.CAT, minutes=500)['online_services']}
        self.assertTrue(r['a']['free_allowance_covers_your_audio'].startswith('no'))

    def test_no_upload_hides_online_services_and_subscriptions_can_be_filtered(self):
        self.assertEqual(A.recommend(self.hw(8), self.CAT, allow_upload=False)['online_services'], [])
        self.assertEqual([s['id'] for s in A.recommend(self.hw(8), self.CAT, subscriptions=['huggingface-pro'])['subscriptions']], ['huggingface-pro'])


class Interview(unittest.TestCase):
    def test_first_use_lists_options_and_asks_and_picks_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = A.interview({}, Path(d) / 'ns', found(keys=('GROQ_API_KEY',)), hw={'os': 'linux', 'cpu_threads': 4, 'ram_gb': 8, 'gpus': [], 'apple_silicon': False})
            self.assertEqual(out['state'], 'interview_needed'); self.assertEqual({o['id'] for o in out['options']}, {'import', 'remote:groq'})
            self.assertIn('Do not choose a speech recognizer for the user', out['instructions_for_agent']); self.assertIn('knowledge_freshness', out)
            self.assertIn('chat plans are separate from API billing', out['instructions_for_agent']); self.assertIsNone(A.load_profile(Path(d) / 'ns'))

    def test_a_refused_interview_saves_nothing_and_a_route_must_be_offered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'; r = found(keys=('GROQ_API_KEY',))
            with self.assertRaisesRegex(ValueError, 'Ask the user which'):
                A.interview({}, root, r, {**ANSWERS, 'allow_upload': True})
            self.assertIsNone(A.load_profile(root))
            with self.assertRaisesRegex(ValueError, 'not one of the available options'):
                A.interview({}, root, r, {**ANSWERS, 'allow_upload': True, 'route': 'remote:invented'})
            with self.assertRaisesRegex(ValueError, 'must not be uploaded'):
                A.interview({}, root, r, {**ANSWERS, 'route': 'remote:groq'})

    def test_saved_profile_is_private_and_used(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            out = A.interview({}, root, found(), {**ANSWERS, 'route': 'import'})
            self.assertEqual((out['state'], out['you_chose']), ('saved', 'import'))
            self.assertEqual(oct(A.profile_path(root).stat().st_mode & 0o777), '0o600')
            self.assertEqual(A.apply_profile({}, A.load_profile(root))['asr_allow_upload'], 'false')

    def test_validation(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ({}, {**ANSWERS, 'languages': ''}, {**ANSWERS, 'minutes': 0}, {**ANSWERS, 'minutes': True}, {**ANSWERS, 'priority': 'vibes'}, {**ANSWERS, 'subscriptions': ['gold']}, {**ANSWERS, 'speakers': 'yes'}):
                with self.assertRaises(ValueError):
                    A.save_profile(Path(d) / 'ns', bad)

    def test_speaker_labels_produce_an_honest_gap(self):
        self.assertTrue(any('speaker labels' in g for g in A.gaps(found(), {**ANSWERS, 'speakers': True, 'allow_upload': True})))


class Knowledge(unittest.TestCase):
    def test_catalog_is_dated_sourced_and_honest_about_unverified_facts(self):
        cat = A.load_catalog()
        self.assertGreaterEqual(len(cat['local']), 18); self.assertGreaterEqual(len(cat['remote']), 12)
        for row in cat['remote'] + cat['local'] + cat['servers'] + cat['subscriptions']:
            self.assertTrue(row['source'].startswith('https://'), row['id']); self.assertRegex(row['verified'], r'^\d{4}-\d\d-\d\d$')
        by = {r['id']: r for r in cat['servers']}
        self.assertIn('unusable for subtitles', by['ollama-stt']['openai_style'])
        subs = {s['id']: s for s in cat['subscriptions']}
        self.assertIn('do not pay for transcription', subs['claude-max-team']['finding']); self.assertIn('UNVERIFIED', subs['google-ai-pro']['finding'])

    def test_every_local_memory_figure_says_where_it_came_from(self):
        for m in A.load_catalog()['local']:
            self.assertRegex(m['vram_basis'].lower(), r'stated|estimate|user-reported|cpu|wrapper|apple', m['id'])

    def test_server_models_exist(self):
        cat = A.load_catalog(); ids = {m['id'] for m in cat['local']}
        for sv in cat['servers']:
            for mid in sv['models']:
                self.assertIn(mid, ids)

    def test_wiki_lists_every_model_service_server_and_plan_with_its_source(self):
        wiki = (ROOT / 'llmwiki' / 'recognizer-models.md').read_text(); cat = A.load_catalog()
        for row in cat['remote'] + cat['local'] + cat['servers'] + cat['subscriptions']:
            self.assertIn(row['name'], wiki); self.assertIn(row['source'], wiki)
        self.assertIn('Never research without their yes', wiki)

    def test_freshness_staleness_and_validated_updates(self):
        cat = A.load_catalog()
        self.assertTrue(A.freshness(cat['verified'], cat['expiries'], None, datetime.date(2027, 3, 1))['stale'])      # the OpenAI shutdown date has passed
        self.assertFalse(A.freshness(cat['verified'], cat['expiries'], None, datetime.date(2026, 11, 20))['stale'])
        ok = {'id': 'groq', 'field': 'free_tier', 'value': 'NEW', 'source': 'https://console.groq.com/docs/rate-limits', 'date': '2026-11-12'}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'ns'
            for bad in ({**ok, 'id': 'nope'}, {**ok, 'field': 'tier'}, {**ok, 'source': 'http://x'}, {**ok, 'date': '2099-01-01'}):
                with self.assertRaises(ValueError):
                    A.save_updates(root, [bad], A.known_ids(), datetime.date(2026, 11, 12))
            A.save_updates(root, [ok], A.known_ids(), datetime.date(2026, 11, 12))
            row = [r for r in A.load_catalog(update_root=root)['remote'] if r['id'] == 'groq'][0]
            self.assertEqual(row['free_tier'], 'NEW'); self.assertNotEqual([r for r in A.load_catalog()['remote'] if r['id'] == 'groq'][0]['free_tier'], 'NEW')

    def test_generic_block_matches_the_speech_plugins(self):
        def block(path):
            t = Path(path).read_text()
            return t[t.index('# ---- knowledge freshness'):t.index('# ---- end knowledge freshness ----')]
        other = ROOT.parent / 'common' / 'speech_resources.py'
        if other.exists():
            self.assertEqual(block(other), block(ROOT / 'asr_resources.py'))


if __name__ == '__main__':
    unittest.main()
