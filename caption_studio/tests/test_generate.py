import hashlib
import json
from pathlib import Path
import time
import unittest
import test_audio as fixture


class GenerateTests(unittest.TestCase):
    setUp=fixture.AudioJobTests.setUp
    tearDown=fixture.AudioJobTests.tearDown

    def ready(self,job):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=self.app.status(job['job_id'])
            if state['state'] not in ('preparing','running'):break
            time.sleep(.01)
        self.assertEqual(state['state'],'ready',state)
        return state

    def test_generate_without_source_srt_and_export_draft_then_review(self):
        self.assertEqual(fixture.package.TOOLS['captions_audio_export'][1]['decisions']['minItems'],0)
        self.srt.unlink()
        original=hashlib.sha256(self.media.read_bytes()).hexdigest()
        job=self.app.generate(str(self.media),{'kind':'import','transcript_path':str(self.transcript)})
        state=self.ready(job);self.assertEqual(state['mode'],'create');self.assertGreater(state['total_cues'],0)
        review=self.app.review(job['job_id']);self.assertIn('generated_caption_needs_review',review['cues'][0]['flags'])
        exported=self.app.export(job['job_id'],[]);self.assertTrue(exported['draft']);self.assertEqual(exported['reviewed_cues'],0)
        content=Path(exported['output_path']).read_text();self.assertIn('green coat',content);self.assertNotIn('green boat',content)
        self.assertIn('00:00:01,000',content)
        self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(),original)
        decisions=[{'cue_id':c['cue_id'],'text':c['original']['text'],'use_timing':True}for c in review['cues']]
        reviewed=self.app.export(job['job_id'],decisions);self.assertFalse(reviewed['draft']);self.assertEqual(reviewed['reviewed_cues'],state['total_cues'])

    def test_silence_does_not_invent_a_caption(self):
        self.transcript.write_text(json.dumps({'words':[]}))
        job=self.app.generate(str(self.media),{'kind':'import','transcript_path':str(self.transcript)})
        state=self.ready(job);self.assertEqual(state['total_cues'],0)
        exported=self.app.export(job['job_id'],[]);self.assertEqual(exported['cues'],0);self.assertEqual(Path(exported['output_path']).read_text(),'\n')

    def test_caption_layout_uses_measured_boundaries_and_rejects_bad_options(self):
        words=fixture.alignment.normalize_transcript({'words':fixture.words('One original sentence. Another sentence.',1000)},10000)
        cues=fixture.audio.caption_draft(words,{'line_chars':12,'max_lines':2})
        self.assertGreaterEqual(len(cues),2)
        measured={w['start_ms']for w in words};ends={w['end_ms']for w in words}
        self.assertTrue(all(c['start_ms']in measured and c['end_ms']in ends for c in cues))
        for options in ([],{'line_chars':True},{'max_lines':0},{'unknown':2}):
            with self.assertRaises(ValueError):fixture.audio.caption_draft(words,options)


if __name__=='__main__':unittest.main()
