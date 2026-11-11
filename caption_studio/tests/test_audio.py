import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

root=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('caption_audio_fixture',root/'__init__.py',submodule_search_locations=[str(root)])
package=importlib.util.module_from_spec(spec);sys.modules[spec.name]=package;spec.loader.exec_module(package)
alignment=sys.modules['caption_audio_fixture.alignment'];audio=sys.modules['caption_audio_fixture.audio'];recognizers=sys.modules['caption_audio_fixture.recognizers']

def words(text,start=1000):
    return [{'text':w,'start_ms':start+i*400,'end_ms':start+i*400+300,'confidence':.9} for i,w in enumerate(text.split())]

class StartOnlyTimingTests(unittest.TestCase):
    def row(self,start,end,s,e):
        return {'original':{'start_ms':start,'end_ms':end},'suggested_start_ms':s,'suggested_end_ms':e,'matched_words':7,'matched_word_coverage':1.0}
    def test_a_late_start_with_an_agreeing_end_moves_only_the_start(self):
        s,e,evidence=alignment._timing(self.row(6200,7640,5580,7700))
        self.assertEqual((s,e),(5580,7640));self.assertTrue(evidence['start_only']);self.assertEqual(evidence['start_shift_ms'],-620)
    def test_small_or_inconsistent_displacements_are_not_start_only(self):
        self.assertNotIn('start_only',alignment._timing(self.row(6200,7640,6000,7640))[2])  # 200 ms: the older consistent-shift rule applies
        self.assertIsNone(alignment._timing(self.row(6200,7640,5000,8800))[0])            # both edges far and different: not clear
        self.assertEqual(alignment._timing(self.row(6200,7640,5600,7000))[0],5600)        # consistent shift of both edges still works

class AlignmentTests(unittest.TestCase):
    def test_audio_times_and_word_disagreements_are_independent(self):
        cues=[{'index':'1','start_ms':100,'end_ms':900,'text':'We saw a green boat','settings':''}, {'index':'2','start_ms':7000,'end_ms':9000,'text':'Then we went home safely','settings':''}]
        speech=words('We saw a green coat')+words('Then we went home safely',10000)
        for w in speech:w['token']=w['text'].casefold()
        report=alignment.compare(cues,speech)
        self.assertIn('word_disagreement',report[0]['flags']);self.assertEqual(report[0]['suggested_text'],'We saw a green coat')
        self.assertEqual(report[0]['suggested_start_ms'],1000);self.assertEqual(report[1]['suggested_start_ms'],10000)
        self.assertEqual(report[1]['suggested_text'],cues[1]['text']);self.assertIn('timing_change',report[1]['flags'])

    def test_missing_caption_words_low_confidence_and_uncertainty(self):
        cue={'index':'1','start_ms':0,'end_ms':5000,'text':'We crossed the river today','settings':''}
        speech=words('We safely crossed the river today');speech[2]['confidence']=.2
        speech=alignment.normalize_transcript({'words':speech},10000)
        result=alignment.compare([cue],speech)[0]
        self.assertIn('words_missing_from_captions',result['flags']);self.assertIn('low_recognizer_confidence',result['flags'])
        wrong=alignment.normalize_transcript({'words':words('A completely different sentence')},10000)
        result=alignment.compare([cue],wrong)[0];self.assertFalse(result['timing_available']);self.assertIsNone(result['suggested_start_ms'])

    def test_backend_shapes_and_missing_timestamps(self):
        one={'word':'Hello','start':1,'end':1.5}
        for data in [{'words':[one]},{'segments':[{'words':[one]}]},{'chunks':[{'text':'Hello','timestamp':[1,1.5]}]}]:
            self.assertEqual(alignment.normalize_transcript(data,5000)[0]['start_ms'],1000)
        cpp={'transcription':[{'tokens':[{'text':' Hel','offsets':{'from':1000,'to':1100}},{'text':'lo','offsets':{'from':1100,'to':1300}}]}]}
        self.assertEqual(alignment.normalize_transcript(cpp,5000)[0]['text'],'Hello')
        for data in [{'text':'No timestamps'},{'segments':[{'text':'Hello','start':1,'end':2}]},{'words':[{'text':'Hello','start':None,'end':2}]}]:
            with self.assertRaises(ValueError):alignment.normalize_transcript(data,5000)

    def test_large_unmatched_gap_is_bounded_and_not_fabricated(self):
        cue={'index':'1','start_ms':0,'end_ms':100000,'text':' '.join(['same']*2000),'settings':''}
        speech=alignment.normalize_transcript({'words':words(' '.join(['other']*2000),0)},900000)
        result=alignment.compare([cue],speech)[0];self.assertIn('insufficient_matching_context',result['flags']);self.assertFalse(result['timing_available'])

    def test_silence_and_cjk_intervals_do_not_fabricate_word_times(self):
        self.assertEqual(alignment.normalize_transcript({'words':[]},1000),[])
        cue={'index':'1','start_ms':0,'end_ms':900,'text':'Hallucinated speech here','settings':''}
        result=alignment.compare([cue],[])[0];self.assertIn('caption_words_not_heard',result['flags']);self.assertFalse(result['timing_available'])
        speech=alignment.normalize_transcript({'words':[{'text':'你好','start':.1,'end':.8}]},1000)
        cue['text']='你好';result=alignment.compare([cue],speech)[0];self.assertTrue(result['timing_available']);self.assertEqual(result['recognized_text'],'你好')

class AudioJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.app=audio.AudioReview(self.base/'output')
        self.srt=self.base/'source.srt';self.srt.write_text('1\n00:00:00,100 --> 00:00:00,900\nWe saw a green boat\n\n2\n00:00:03,000 --> 00:00:04,900\nWe came home safely\n')
        self.media=self.base/'source.wav'
        with wave.open(str(self.media),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000*6)
        self.transcript=self.base/'transcript.json';self.transcript.write_text(json.dumps({'words':words('We saw a green coat',1000)+words('We came home safely',3500)}))
    def tearDown(self):self.tmp.cleanup()
    def ready(self,recognizer=None):
        recognizer=recognizer or {'kind':'import','transcript_path':str(self.transcript)}
        result=self.app.analyse(str(self.srt),str(self.media),recognizer);job=result['job_id']
        for _ in range(200):
            status=self.app.status(job)
            if status['state'] in ('ready','failed','cancelled'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'ready',status);return job
    def test_review_listen_and_export_only_selected_changes(self):
        before=self.srt.read_bytes();job=self.ready();rows=self.app.review(job)['cues']
        self.assertTrue(rows[0]['text_disagreement']);self.assertEqual(rows[0]['suggested_text'],'We saw a green coat')
        preview=self.app.preview(job,1,include_data=True);self.assertTrue(preview['audio_url'].startswith('data:audio/wav;base64,'));self.assertGreater(Path(preview['path']).stat().st_size,0)
        exported=self.app.export(job,[{'cue_id':1,'use_timing':True,'use_text':True}]);text=Path(exported['output_path']).read_text()
        self.assertIn('We saw a green coat',text);self.assertIn('00:00:03,000 --> 00:00:04,900',text);self.assertEqual(self.srt.read_bytes(),before)
        self.assertEqual(Path(exported['output_path']).stat().st_mode&0o777,0o600)
    def test_explicit_manual_edit_stale_source_and_invalid_export(self):
        job=self.ready()
        with self.assertRaises(ValueError):self.app.export(job,[])
        with self.assertRaises(ValueError):self.app.export(job,[{'cue_id':1,'text':'bad\n\n3\n00:00:01,000 --> 00:00:02,000'}])
        self.srt.write_text(self.srt.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'changed'):self.app.export(job,[{'cue_id':1,'text':'Manually reviewed words'}])

    def test_hallucinated_cue_removal_is_explicit(self):
        job=self.ready();result=self.app.export(job,[{'cue_id':1,'drop':True}]);self.assertEqual(result['removed_cues'],1);self.assertNotIn('green boat',Path(result['output_path']).read_text());self.assertIn('We came home safely',Path(result['output_path']).read_text())
        with self.assertRaisesRegex(ValueError,'boolean'):self.app.export(job,[{'cue_id':1,'drop':'false'}])

    def test_compatible_http_transport_is_opt_in_and_returns_timed_words(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        captured=[]
        payload=self.transcript.read_bytes()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(s):
                body=s.rfile.read(int(s.headers['Content-Length']));captured.append((body,s.headers.get('X-API-Key')))
                s.send_response(200);s.send_header('Content-Type','application/json');s.end_headers();s.wfile.write(payload)
            def log_message(*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            job=self.ready({'kind':'http','endpoint':f'http://127.0.0.1:{server.server_port}/transcribe','fields':{'model':'user-selected','word_timestamps':True}})
            self.assertEqual(self.app.status(job)['state'],'ready');self.assertEqual(len(captured),1);self.assertIn(b'user-selected',captured[0][0]);self.assertIsNone(captured[0][1])
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
    def test_local_command_protocol_uses_selected_runtime_and_no_secret_env(self):
        script=self.base/'recognize.py';script.write_text('import sys,json,os\nr=json.load(sys.stdin)\nassert "test-secret" not in str(dict(os.environ))\nprint(open('+repr(str(self.transcript))+').read())\n')
        with patch.dict('os.environ',{'ELEVENLABS_API_KEY':'test-secret','CAPTION_REPAIR_ASR_KEY':'test-secret'}):
            job=self.ready({'kind':'command','argv':[sys.executable,str(script)]})
        self.assertEqual(self.app.status(job)['recognizer_kind'],'command')
    def test_no_provider_default_remote_consent_or_private_files(self):
        with self.assertRaisesRegex(ValueError,'Choose'):self.app.analyse(str(self.srt),str(self.media),{})
        with self.assertRaisesRegex(ValueError,'Confirm'):self.app.analyse(str(self.srt),str(self.media),{'kind':'http','endpoint':'https://example.com/transcribe'})
        private=self.base/'.config';private.mkdir();target=private/'audio.wav';target.write_bytes(self.media.read_bytes())
        with self.assertRaisesRegex(ValueError,'Private'):self.app.analyse(str(self.srt),str(target),{'kind':'import','transcript_path':str(self.transcript)})
    def test_host_tool_interface_and_profile_boundaries(self):
        calls=[]
        result=self.app.analyse(str(self.srt),str(self.media),{'kind':'host','tool':'selected_speech','arguments':{'file':'{audio}','model':'user-selected'}},dispatch=lambda n,a:(calls.append((n,a)) or json.loads(self.transcript.read_text())))
        for _ in range(200):
            status=self.app.status(result['job_id'])
            if status['state'] in ('ready','failed'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'ready',status);self.assertEqual(calls[0][0],'selected_speech')
        with self.assertRaises(ValueError):audio.AudioReview(self.base/'other-profile').status(result['job_id'])

    def test_profile_file_lock_and_owned_command_cancellation(self):
        script=self.base/'slow_asr.py';script.write_text('import time\ntime.sleep(60)\n')
        result=self.app.analyse(str(self.srt),str(self.media),{'kind':'command','argv':[sys.executable,str(script)]});job=result['job_id'];folder=self.app.job(job)
        for _ in range(200):
            if str(folder) in audio._PROCESSES:break
            time.sleep(.01)
        self.assertIn(str(folder),audio._PROCESSES)
        with patch.dict(audio._RUNNING,{},clear=True):
            with self.assertRaisesRegex(ValueError,'already running'):
                audio.AudioReview(self.app.root).analyse(str(self.srt),str(self.media),{'kind':'import','transcript_path':str(self.transcript)})
        self.app.cancel(job)
        for _ in range(200):
            status=self.app.status(job)
            if status['state']=='cancelled':break
            time.sleep(.01)
        self.assertEqual(status['state'],'cancelled');self.assertNotIn(str(folder),audio._PROCESSES)

class BlindProposalTests(unittest.TestCase):
    """A human supplies only a recording and its subtitles; the engine finds and applies clear fixes."""
    fixtures=Path(__file__).parent/'fixtures'
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.app=audio.AudioReview(self.base/'output')
        self.srt=self.base/'blind.srt';self.srt.write_bytes((self.fixtures/'blind.srt').read_bytes())
        self.media=self.base/'blind.wav'
        with wave.open(str(self.media),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000*45)
        job=self.app.analyse(str(self.srt),str(self.media),{'kind':'import','transcript_path':str(self.fixtures/'blind_words.json')})['job_id']
        for _ in range(300):
            status=self.app.status(job)
            if status['state'] in ('ready','failed'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'ready',status);self.job=job
    def tearDown(self):self.tmp.cleanup()
    def blocks(self,path):return Path(path).read_text().strip().split('\n\n')
    def test_clear_fixes_found_ambiguous_surfaced_rest_unchanged(self):
        plan=self.app.propose(self.job);by={c['cue_id']:c for c in plan['cues']}
        self.assertEqual((plan['clear'],plan['ambiguous'],plan['unchanged']),(2,2,4))
        self.assertEqual(by[2]['decision'],{'cue_id':2,'text':'Fishing boats leave before the sun rises'});self.assertEqual(by[2]['changes'],['text'])
        self.assertEqual(by[4]['changes'],['timing']);self.assertEqual(by[4]['evidence']['timing']['start_shift_ms'],-2000)
        self.assertIn('possible_name_or_number',by[6]['reasons']);self.assertEqual(by[8]['status'],'ambiguous')
        self.assertEqual(plan['unchanged_cue_ids'],[1,3,5,7]);self.assertNotIn('decision',by[6])
    def test_apply_proposed_changes_only_clear_cues_and_keeps_original(self):
        before=self.srt.read_bytes();result=self.app.export(self.job,[],apply_proposed=True)
        self.assertEqual(self.srt.read_bytes(),before);self.assertTrue(result['originals_preserved']);self.assertFalse(result['listened_to']);self.assertEqual(result['basis'],'alignment-backed')
        self.assertEqual(result['applied_proposed'],2);self.assertEqual(result['left_unchanged'],4);self.assertEqual([c['cue_id'] for c in result['needs_human']],[6,8]);self.assertIn('nobody listened',result['notice'])
        old,new=self.blocks(self.srt),self.blocks(result['output_path']);self.assertEqual(len(old),len(new))
        for n in (1,3,5,6,7,8):self.assertEqual(old[n-1],new[n-1])
        self.assertIn('the sun rises',new[1]);self.assertEqual(new[1].split('\n')[1],old[1].split('\n')[1])
        self.assertEqual(new[3].split('\n')[1],'00:00:16,000 --> 00:00:18,300');self.assertEqual(new[3].split('\n')[2],old[3].split('\n')[2])
    def test_explicit_decision_wins_and_decisions_are_still_required_otherwise(self):
        result=self.app.export(self.job,[{'cue_id':2,'text':'Fishing boats leave before the dawn rises'}],apply_proposed=True)
        self.assertIn('the dawn rises',Path(result['output_path']).read_text());self.assertEqual(result['applied_proposed'],1)
        with self.assertRaises(ValueError):self.app.export(self.job)
        with self.assertRaises(ValueError):self.app.export(self.job,[])
    def test_low_confidence_and_weak_context_are_not_clear(self):
        base=[{'cue_id':1,'original':{'start_ms':0,'end_ms':900,'text':'We saw a green boat'},'suggested_start_ms':0,'suggested_end_ms':900,'recognized_text':'We saw a green coat','matched_word_coverage':.8,'matched_words':4,'caption_words':5,'flags':['word_disagreement'],'edits':[{'op':'replace','caption_index':4,'caption':['boat'],'heard':['sky'],'heard_confidence':[None]}]}]
        self.assertEqual(alignment.propose(base)['cues'][0]['reasons'],['weak_corroboration'])
        short=[dict(base[0],matched_word_coverage=.67,matched_words=2,edits=[dict(base[0]['edits'][0],heard=['coat'],heard_confidence=[.95])])]
        self.assertEqual(alignment.propose(short)['cues'][0]['reasons'],['weak_context'])
        ok=[dict(base[0],edits=[dict(base[0]['edits'][0],heard=['coat'],heard_confidence=[None])])]
        self.assertEqual(alignment.propose(ok)['cues'][0]['status'],'clear')

    def test_common_word_swap_in_fully_matched_context_is_clear_but_nothing_looser(self):
        row=lambda text,old,new,idx,matched,words,conf=None:[{'cue_id':1,'original':{'start_ms':0,'end_ms':2500,'text':text},'suggested_start_ms':0,'suggested_end_ms':2500,'recognized_text':'x','matched_word_coverage':round(matched/words,3),'matched_words':matched,'caption_words':words,'flags':['word_disagreement'],'edits':[{'op':'replace','caption_index':idx,'caption':[old],'heard':[new],'heard_confidence':[conf]}]}]
        clear=alignment.propose(row('Pass the salt in pepper please','in','and',3,5,6))['cues'][0]
        self.assertEqual(clear['status'],'clear');self.assertEqual(clear['decision']['text'],'Pass the salt and pepper please');self.assertTrue(clear['evidence']['text']['common_word_context'])
        self.assertEqual(alignment.propose(row('in the salt and pepper please','in','and',0,5,6))['cues'][0]['reasons'],['weak_corroboration'])
        self.assertEqual(alignment.propose(row('Pass the salt in pepper please','in','and',3,6,8))['cues'][0]['reasons'],['weak_corroboration'])
        self.assertEqual(alignment.propose(row('Pass the salt in pepper please','in','and',3,5,6,.2))['cues'][0]['reasons'],['weak_corroboration'])
        self.assertEqual(alignment.propose(row('Pass the salt pan pepper please','pan','and',3,5,6))['cues'][0]['status'],'clear')
        self.assertEqual(alignment.propose(row('Pass the salt bread pepper please','bread','and',3,5,6))['cues'][0]['reasons'],['weak_corroboration'])
        self.assertEqual(alignment.propose(row('Pass the Salt in pepper please','salt','and',2,5,6))['cues'][0]['reasons'],['possible_name_or_number'])

if __name__=='__main__':unittest.main()
