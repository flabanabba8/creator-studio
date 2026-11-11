from pathlib import Path
import json
import unittest
from unittest.mock import patch
import test_tutorial as fixture

narration=__import__('tutorial_test.narration',fromlist=['narrate'])

class HostNarrationTests(unittest.TestCase):
    setUp=fixture.Media.setUp
    tearDown=fixture.Media.tearDown
    def config(self):return {'narration_backend':'host','host_tts_tool':'selected_speech','host_tts_backend_id':'chosen/runtime/model@1','host_tts_arguments':{'text':'{text}','voice':'{voice}'},'host_tts_voice':'chosen-voice'}
    def test_host_selection_cache_timing_and_credit(self):
        exported=self.director.export(self.job_id,[{'start':0,'duration':2.5}]);voice=Path(self.temp.name)/'host.wav';voice.write_bytes(fixture.voice_fixture());calls=[]
        def dispatch(name,args):calls.append((name,args));return {'path':str(voice),'credit':'Fixture provider credit'}
        cue=[{'start':.1,'end':.8,'text':'Literal {voice} sentence.'}]
        with patch.object(narration,'synthesize',side_effect=AssertionError('No legacy-provider fallback')):
            result=narration.narrate(self.temp.name,self.job_id,Path(exported['path']).name,cue,self.config(),dispatch)
            again=narration.narrate(self.temp.name,self.job_id,Path(exported['path']).name,cue,self.config(),dispatch)
        self.assertEqual(result['state'],'complete');self.assertEqual(result['credit'],'Fixture provider credit');self.assertTrue(again['cues'][0]['cache_reused']);self.assertEqual(len(calls),1);self.assertEqual(calls[0][1]['text'],'Literal {voice} sentence.')
    def test_uncertain_attempt_requires_explicit_retry_without_invalidating_cache(self):
        exported=self.director.export(self.job_id,[{'start':0,'duration':2.5}]);calls=[]
        def fail(*_):calls.append(1);raise RuntimeError('sensitive fixture error')
        args=(self.temp.name,self.job_id,Path(exported['path']).name,[{'start':.1,'end':.8,'text':'Fixture sentence.'}])
        with self.assertRaises(RuntimeError):narration.narrate(*args,self.config(),fail)
        with self.assertRaisesRegex(RuntimeError,'retry_nonce'):narration.narrate(*args,self.config(),fail)
        self.assertEqual(len(calls),1)
    def test_local_http_selection_does_not_force_higgs_model_or_controls(self):
        exported=self.director.export(self.job_id,[{'start':0,'duration':2.5}]);cfg={'narration_backend':'local_http','speech_http_url':'http://localhost:8000','speech_http_model':'selected-model','speech_http_credit':'Selected model credit'}
        with patch.object(narration,'synthesize',return_value=fixture.voice_fixture()) as synth:
            result=narration.narrate(self.temp.name,self.job_id,Path(exported['path']).name,[{'start':.1,'end':.8,'text':'Fixture sentence.'}],cfg)
        self.assertEqual(synth.call_args.args[1],'selected-model');self.assertFalse(synth.call_args.kwargs['higgs_defaults']);self.assertEqual(result['credit'],'Selected model credit')

if __name__=='__main__':unittest.main()
