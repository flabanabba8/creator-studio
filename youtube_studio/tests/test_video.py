import importlib.util
import sys
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('video', Path(__file__).resolve().parents[1] / '__init__.py')
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)

class VideoTest(unittest.TestCase):
 def test_chapters_and_captions(self):
  chapters = [{'start': 0, 'title': 'Opening'}, {'start': 15, 'title': 'Method'}, {'start': 30, 'title': 'Result'}]
  captions = [{'start': 0.5, 'end': 3, 'text': 'Opening.'}, {'start': 3, 'end': 5, 'text': 'Next.'}]
  result = p.check_timeline(45, chapters, captions)
  self.assertEqual(result['chapters_description'], '00:00 Opening\n00:15 Method\n00:30 Result')
  self.assertEqual(result['caption_count'], 2)
  self.assertIn('00:00:00.500 --> 00:00:03.000', result['captions_webvtt'])
  self.assertIn('1\n00:00:00,500 --> 00:00:03,000', result['captions_srt'])
  self.assertIn('2\n00:00:03,000 --> 00:00:05,000', result['captions_srt'])
  captions[1]['start'] = 2
  with self.assertRaises(ValueError): p.check_timeline(45, chapters, captions)
 def test_chapter_free_short_video(self):
  result = p.check_timeline(5, [], [{'start': 0, 'end': 1, 'text': 'Short.'}])
  self.assertEqual(result['chapters_description'], '')
  with self.assertRaises(ValueError): p.check_timeline(5, [{'start': 0, 'title': 'Only'}], [])
 def test_caption_text_is_literal_in_webvtt_and_srt_markup_is_flagged(self):
  result=p.check_timeline(5, [], [{'start':0,'end':2,'text':'A < B & C > D'}])
  self.assertIn('A &lt; B &amp; C &gt; D',result['captions_webvtt'])
  self.assertTrue(result['srt_markup_warning'])
  self.assertIn('A < B & C > D',result['captions_srt'])
 def test_reject_bad_bounds_and_injection(self):
  chapters = [{'start': 0, 'title': 'A'}, {'start': 10, 'title': 'B'}, {'start': 20, 'title': 'C'}]
  with self.assertRaises(ValueError): p.check_timeline(float('nan'), chapters, [])
  with self.assertRaises(ValueError): p.check_timeline(24, chapters, [])  # last chapter only 4 seconds
  chapters[1]['title'] = 'Title\n0:12 injected'
  with self.assertRaises(ValueError): p.check_timeline(40, chapters, [])
  chapters[1]['title'] = 'Title\u2028hidden'
  with self.assertRaises(ValueError): p.check_timeline(40, chapters, [])
  chapters[1]['title'] = 'B'
  with self.assertRaises(ValueError): p.check_timeline(40, chapters, [{'start': 0, 'end': 2, 'text': 'first\n  \nsecond'}])

 def test_registered_skill_and_handler(self):
  class Context:
   def __init__(self): self.skills = []; self.tools = {}
   def register_skill(self, name, path, **kwargs): self.skills.append((name, path))
   def register_tool(self, **kwargs): self.tools[kwargs['name']] = kwargs
  ctx = Context(); p.register(ctx)
  self.assertEqual(len(ctx.skills), 1)
  self.assertTrue(ctx.skills[0][1].is_file())
  result = json.loads(ctx.tools['youtube_check_timeline']['handler']({'duration': 40, 'chapters': [{'start': 0, 'title': 'A'}, {'start': 10, 'title': 'B'}, {'start': 20, 'title': 'C'}], 'captions': []}))
  self.assertNotIn('error', result)

if __name__ == '__main__': unittest.main()
