import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cs_t.podcast_episode_fixture', root / '__init__.py', submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
import sys
sys.modules['cs_t.podcast_episode_fixture'] = package
spec.loader.exec_module(package)

STORY = ("# title: A tool launches\n# paper: https://example.com/launch\n\n"
         "ALEX: A company launched a tool that turns notes into short audio summaries. It runs in the browser.\n\n"
         "SAM: It sends the notes to a server, so the company says private notes should not be pasted into it.\n")
CLOSE = "# title: Wrap-up\n\nALEX: That covers the launch and its privacy caveat today.\n\nSAM: Follow the show if you want more explanations like this.\n"


def make(base, story=STORY, close=CLOSE, review=True):
    (base / '01-launch.txt').write_text(story)
    (base / '98-wrapup.txt').write_text(close)
    (base / 'meta.json').write_text(json.dumps({'title': 'Test episode'}))
    if review:
        records = {}
        for name in ('01-launch.txt', '98-wrapup.txt'):
            records[name] = {'sha256': hashlib.sha256((base / name).read_bytes()).hexdigest(), 'purpose': 'x', 'opening_check': 'y', 'source_check': 'z', 'edits': 'none needed'}
        (base / 'editorial-review.json').write_text(json.dumps({'status': 'passed', 'reviewer': 'tester', 'segments': records}))


class EpisodeTests(unittest.TestCase):
    def run_tool(self, name, **args): return json.loads(package.invoke(name, args))

    def test_load_parses_headers_turns_and_closing_without_sources(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            make(Path(tmp))
            result = self.run_tool('podcast_load_episode', episode_dir=tmp)
            self.assertEqual(result['files'], ['01-launch.txt', '98-wrapup.txt'])
            self.assertEqual(result['segments'][0]['title'], 'A tool launches')
            self.assertEqual(result['segments'][0]['sources'], ['https://example.com/launch'])
            self.assertIn('closing', result['segments'][1]['sources'][0])
            self.assertEqual(result['speakers'], ['ALEX', 'SAM'])
            self.assertEqual(result['meta'], {'title': 'Test episode'})

    def test_missing_sources_rejected_unless_format_allows_it(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            make(Path(tmp), story="# title: Fiction\n\nALEX: Once upon a time there was a small robot.\n")
            self.assertIn('error', self.run_tool('podcast_load_episode', episode_dir=tmp))
            ok = self.run_tool('podcast_load_episode', episode_dir=tmp, require_sources=False)
            self.assertNotIn('error', ok)

    def test_lint_catches_director_voice_numbers_cutoffs_and_tags(self):
        bad = ("# title: Bad\n# paper: https://example.com/x\n\nALEX: Let's start with the setup. It scored 91 percent on the test.\n\n"
               "SAM: Great question. <|emotion:surprise|>Wait, that cuts off --\n\nALEX: Mm.\n")
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            make(Path(tmp), story=bad)
            result = self.run_tool('podcast_lint_episode', episode_dir=tmp)
            rules = {f['rule'] for f in result['findings']}
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue({'director-voice', 'spoken-number', 'sycophancy', 'tag', 'cutoff', 'bare-interjection'} <= rules)

    def test_style_profile_opens_the_rules_for_other_formats(self):
        loose = ("# title: Story\n\nALEX: <|emotion:surprise|>It was 91 percent finished when the lights went out.\n\n"
                 "SAM: <|style:whispering|>Quiet now, someone is coming up the stairs.\n")
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            make(Path(tmp), story=loose)
            style = {'tags': 'higgs', 'spoken_numbers': 'off', 'banned_tags': ['style:whispering'], 'banned_phrases': ['someone is coming']}
            result = self.run_tool('podcast_lint_episode', episode_dir=tmp, style=style, require_sources=False)
            rules = [f['rule'] for f in result['findings']]
            self.assertNotIn('spoken-number', rules)
            self.assertEqual(sorted(set(rules)), ['custom-phrase', 'tag'])
            self.assertEqual(self.run_tool('podcast_lint_episode', episode_dir=tmp, style={'disabled_rules': ['nope']}, require_sources=False)['error'][:12], 'style.disabl')

    def test_kids_preset_checks_readability_sensitive_words_and_contact_details(self):
        kids = ("# title: Benny the Bear\n\nNARRATOR: Benny the bear woke up. He was very hungry. He looked for honey.\n\n"
                "BENNY: Where is my honey? Oh no, the jar fell and hurt the little bee.\n\n"
                "NARRATOR: Remember to follow us and send a message to bennybear@example.com. Then everybody in the whole big forest can be informed about the extraordinarily complicated situation with the missing honey jar.\n")
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            make(Path(tmp), story=kids)
            result = self.run_tool('podcast_lint_episode', episode_dir=tmp, style={'preset': 'kids'}, require_sources=False)
            rules = {f['rule'] for f in result['findings']}
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue({'contact-details', 'sensitive-word', 'long-sentence'} <= rules)
            self.assertNotIn('spoken-number', rules)
            simple = "# title: Benny\n\nNARRATOR: Benny the bear woke up. He was hungry. He found a jar of honey.\n\nBENNY: Yum! This is the best honey.\n"
            make(Path(tmp), story=simple)
            clean = self.run_tool('podcast_lint_episode', episode_dir=tmp, style={'preset': 'kids'}, require_sources=False)
            self.assertEqual(clean['status'], 'clean', clean['findings'])
            self.assertIn('style.preset', self.run_tool('podcast_lint_episode', episode_dir=tmp, style={'preset': 'nope'}, require_sources=False)['error'])

    def test_preflight_passes_then_blocks_after_an_edit(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); make(base)
            self.assertEqual(self.run_tool('podcast_preflight', episode_dir=tmp)['status'], 'passed')
            (base / '01-launch.txt').write_text(STORY + "\nALEX: One more fact was added after the review was written.\n")
            blocked = self.run_tool('podcast_preflight', episode_dir=tmp)
            self.assertIn('Stale or missing review', blocked['error'])

    def test_preflight_requires_a_review_and_reads_the_source_check_summary(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); make(base, review=False)
            self.assertIn('Missing editorial-review.json', self.run_tool('podcast_preflight', episode_dir=tmp)['error'])
            make(base)
            self.assertEqual(self.run_tool('podcast_preflight', episode_dir=tmp, require_source_check=True)['status'], 'blocked')
            (base / 'source-check.md').write_text('## 01\nPROBLEM x\n\nSUMMARY: 2 problems in 1 segments\n')
            result = self.run_tool('podcast_preflight', episode_dir=tmp, require_source_check=True)
            self.assertEqual(result['status'], 'passed_with_open_source_problems')
            self.assertEqual(result['source_check']['problems_reported'], 2)

    def test_unsafe_folders_and_links_are_refused(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            base = Path(tmp); make(base)
            (base / 'extra.txt').symlink_to(base / '01-launch.txt')
            self.assertIn('regular files', self.run_tool('podcast_load_episode', episode_dir=tmp)['error'])
        self.assertIn('absolute', self.run_tool('podcast_load_episode', episode_dir='relative/path')['error'])
        self.assertIn('Private configuration', self.run_tool('podcast_load_episode', episode_dir='/home/someone/.ssh/episode')['error'])


if __name__ == '__main__': unittest.main()
