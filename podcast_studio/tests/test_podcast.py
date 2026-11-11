import importlib.util
import sys
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('podcast', Path(__file__).resolve().parents[1] / '__init__.py')
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)

class PodcastTest(unittest.TestCase):
 def test_pagecast_cast_requires_complete_pages_and_correct_speakers(self):
  assignments=[{'paragraph':0,'speaker':'A','segment_index':0},{'paragraph':1,'speaker':'B','segment_index':0}]
  passages=[{'id':0,'paragraph':0,'speaker':'A'},{'id':1,'paragraph':0,'speaker':'A'},{'id':2,'paragraph':1,'speaker':'B'}]
  args={'assignments':assignments,'passages':passages,'total':3,'expected_source_sha256':'a'*64,'actual_source_sha256':'a'*64,'source_text_status':'unchanged'}
  self.assertEqual(p.check_pagecast_cast(**args)['status'],'matched')
  passages[1]['speaker']='B';result=p.check_pagecast_cast(**args)
  self.assertEqual(result['status'],'mismatched');self.assertEqual(result['mismatches'][0]['passage_id'],1)
  with self.assertRaisesRegex(ValueError,'every PageCast passage'):p.check_pagecast_cast(**{**args,'passages':passages[:-1]})
  with self.assertRaisesRegex(ValueError,'Duplicate passage'):p.check_pagecast_cast(**{**args,'passages':[passages[0],passages[0],passages[2]]})
  with self.assertRaisesRegex(ValueError,'coverage is incomplete'):p.check_pagecast_cast(**{**args,'passages':[passages[0],passages[1],{**passages[2],'paragraph':0}]})
  with self.assertRaisesRegex(ValueError,'unknown paragraph'):p.check_pagecast_cast(**{**args,'passages':[passages[0],passages[1],{**passages[2],'paragraph':99}]})
  with self.assertRaisesRegex(ValueError,'different original'):p.check_pagecast_cast(**{**args,'actual_source_sha256':'b'*64})
  for status in ('changed','unavailable'):
   with self.assertRaisesRegex(ValueError,'changed or its import baseline'):p.check_pagecast_cast(**{**args,'source_text_status':status})
  many=[{'id':i,'paragraph':0,'speaker':'B'} for i in range(101)]
  result=p.check_pagecast_cast(**{**args,'assignments':assignments[:1],'passages':many,'total':101})
  self.assertEqual((result['mismatch_count'],len(result['mismatches']),result['mismatches_omitted']),(101,100,1))

 def test_review_detects_any_script_or_source_change(self):
  segments = [{'title': 'A discovery', 'sources': ['Primary paper'], 'turns': [{'speaker': 'A', 'text': 'Here is the finding.'}]}]
  digest = p.check_script(segments)['segments'][0]['sha256']
  review = {'reviewer': 'editor', 'segments': [{'sha256': digest, 'purpose': 'Explain finding', 'opening_check': 'Names the result', 'source_check': 'Compared with paper', 'edits': 'Clarified the setup'}]}
  self.assertEqual(p.check_review(segments, review)['status'], 'review_record_matches_script')
  self.assertEqual(p.pagecast_plan(segments, review)['assignments'], [{'paragraph': 0, 'speaker': 'A', 'segment_index': 0}])
  segments[0]['turns'][0]['text'] += ' Changed.'
  with self.assertRaisesRegex(ValueError, 'changed'): p.check_review(segments, review)
  with self.assertRaisesRegex(ValueError, 'changed'): p.pagecast_plan(segments, review)
  segments[0]['turns'][0]['text'] = 'Here is the finding.'
  segments[0]['sources'][0] = 'Different source'
  with self.assertRaisesRegex(ValueError, 'changed'): p.check_review(segments, review)
 def test_pagecast_rejects_hidden_line_separators(self):
  segments = [{'title': 'Test', 'sources': ['Fixture'], 'turns': [{'speaker': 'A', 'text': 'One\u2028Two'}]}]
  digest = p.check_script(segments)['segments'][0]['sha256']
  review = {'reviewer': 'Fixture', 'segments': [{'sha256': digest, 'purpose': 'Fixture', 'opening_check': 'Fixture', 'source_check': 'Fixture', 'edits': 'None'}]}
  with self.assertRaisesRegex(ValueError, 'one speakable line'): p.pagecast_plan(segments, review)
 def test_caption_cues_are_passage_timed_and_tags_are_optional(self):
  passages = [{'start_seconds': 0.0, 'end_seconds': 1.5, 'text': '<|emotion:joy|>Hello.'}, {'start_seconds': 1.5, 'end_seconds': 3.0, 'text': 'Next sentence.'}]
  result = p.caption_cues(passages, strip_higgs_tags=True)
  self.assertEqual(result['cues'][0], {'start': 0.0, 'end': 1.5, 'text': 'Hello.'})
  self.assertEqual(result['source_binding'], 'not_checked')
  self.assertEqual(p.caption_cues(passages, expected_source_sha256='a'*64, actual_source_sha256='a'*64)['source_binding'], 'matched_original_import')
  self.assertEqual(p.caption_cues(passages, expected_source_sha256='a'*64, actual_source_sha256='a'*64, source_text_status='unchanged')['source_binding'], 'matched_original_import_and_unchanged_text')
  for status in ('changed', 'unavailable'):
   with self.assertRaisesRegex(ValueError, 'changed or its import baseline'): p.caption_cues(passages, expected_source_sha256='a'*64, actual_source_sha256='a'*64, source_text_status=status)
  with self.assertRaisesRegex(ValueError, 'requires both'): p.caption_cues(passages, source_text_status='unchanged')
  with self.assertRaisesRegex(ValueError, 'different original'): p.caption_cues(passages, expected_source_sha256='a'*64, actual_source_sha256='b'*64)
  with self.assertRaises(ValueError): p.caption_cues(passages, expected_source_sha256='a'*64)
  self.assertIn('<|emotion:joy|>', p.caption_cues(passages)['cues'][0]['text'])
  expressive = [{'start_seconds': 0, 'end_seconds': 2, 'text': '<|sfx:laughter|>Haha, <|prosody:pause|>that is useful.'}]
  self.assertEqual(p.caption_cues(expressive, strip_higgs_tags=True)['cues'][0]['text'], 'Haha, that is useful.')
  passages[1]['start_seconds'] = 1.0
  with self.assertRaises(ValueError): p.caption_cues(passages)

 def test_show_notes_use_measured_order_and_deduplicate_sources(self):
  segments = [{'title': 'First', 'sources': ['Paper'], 'turns': [{'speaker': 'A', 'text': 'Hello.'}]}, {'title': 'Second', 'sources': ['Paper', 'Other'], 'turns': [{'speaker': 'B', 'text': 'World.'}]}]
  result = p.show_notes(segments, [0, 62])
  self.assertEqual(result['chapters'], ['0:00 First', '1:02 Second'])
  self.assertEqual(result['sources'], ['Paper', 'Other'])
  with self.assertRaises(ValueError): p.show_notes(segments, [0, 0])
  with self.assertRaises(ValueError): p.show_notes(segments, [0, True])
  segments[1]['title'] = 'Second\u2028hidden'
  with self.assertRaises(ValueError): p.show_notes(segments, [0, 62])

 def test_missing_sources_and_incomplete_review_fail(self):
  segments = [{'title': 'A', 'sources': [], 'turns': [{'speaker': 'A', 'text': 'Hello.'}]}]
  with self.assertRaises(ValueError): p.check_script(segments)
  segments[0]['sources'] = ['Paper']
  with self.assertRaises(ValueError): p.check_review(segments, {'reviewer': 'editor', 'segments': []})

 def test_registered_skill_and_handler(self):
  class Context:
   def __init__(self): self.skills = []; self.tools = {}
   def register_skill(self, name, path, **kwargs): self.skills.append((name, path))
   def register_tool(self, **kwargs): self.tools[kwargs['name']] = kwargs
  ctx = Context(); p.register(ctx)
  self.assertEqual(len(ctx.skills), 1)
  self.assertTrue(ctx.skills[0][1].is_file())
  result = json.loads(ctx.tools['podcast_check_script']['handler']({'segments': [{'title': 'Test', 'sources': ['Paper'], 'turns': [{'speaker': 'Host', 'text': 'A finding.'}]}]}))
  self.assertNotIn('error', result)

if __name__ == '__main__': unittest.main()
