import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import base64,importlib.util,io,json,shutil,sys,tempfile,unittest,wave
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.pod_gemini_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.common import gemini_speech as g
from cs_t.pod_gemini_fixture.media_project import MediaProject
HAVE=shutil.which('ffmpeg')
SECRET='private-project-xyz'

def wav(sec):
    b=io.BytesIO()
    with wave.open(b,'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\x10\x00'*int(24000*sec))
    return b.getvalue()

class Route(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[]
        def fake(url,headers,body):
            self.calls.append(body);return 200,json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'data':base64.b64encode(wav(1+len(self.calls)*.25)).decode()}}]}}],'usageMetadata':{'promptTokenCount':30,'candidatesTokenCount':200}}).encode()
        self.p=[mock.patch.object(g,'project',lambda:SECRET),mock.patch.object(g,'transport',fake)]
        for x in self.p:x.start()
    def tearDown(self):
        for x in self.p:x.stop()
        self.tmp.cleanup()
    def project(self):
        app=MediaProject(self.root/'data','podcast');pid=app.create('T',factual=False)['project_id']
        app.script(pid,[{'title':'A','turns':[{'speaker':'Host','text':'Welcome to the show.'},{'speaker':'Guest','text':'Glad to be here.'}]},{'title':'B','turns':[{'speaker':'Host','text':'Goodbye.'}]}])
        return app,pid
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_two_hosts_get_their_own_voices_one_request_each_and_resume_without_rerolls(self):
        app,pid=self.project();out=app.narrate(pid,voices={'Host':'Charon','Guest':'Leda'})
        self.assertEqual((out['recorded_now'],len(self.calls)),(3,3))
        self.assertEqual([c['generationConfig']['speechConfig']['voiceConfig']['voice']for c in self.calls],['Charon','Leda','Charon'])
        self.assertEqual([len(s['audio_ids'])for s in app.load(pid)[1]['sections']],[2,1]);self.assertNotIn(SECRET,json.dumps(out))
        self.assertEqual(app.narrate(pid,voices={'Host':'Charon','Guest':'Leda'})['already_recorded'],3);self.assertEqual(len(self.calls),3)
    def test_voice_choice_required_and_checked_before_any_request(self):
        app,pid=self.project()
        with self.assertRaisesRegex(ValueError,'Choose Gemini voices'):app.narrate(pid)
        with self.assertRaisesRegex(ValueError,'No voice chosen'):app.narrate(pid,voices={'Host':'Charon'})
        with self.assertRaisesRegex(ValueError,'named Gemini voices'):app.narrate(pid,voice='Nobody')
        self.assertEqual(self.calls,[])
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_start_topic_reports_the_route_and_the_episode_assembles(self):
        app=MediaProject(self.root/'data2','podcast')
        with mock.patch.object(g,'available',lambda:{'available':True,'voices':[]}):self.assertTrue(app.create('T',factual=False)['gemini_speech']['available'])
        app,pid=self.project();app.narrate(pid,voices={'Host':'Charon','Guest':'Leda'});result=app.assemble(pid)
        self.assertAlmostEqual(result["seconds"],4.5,delta=.3)
        turns=[t for sec in result['timeline'] for t in sec['turns']]
        self.assertEqual([(t['speaker'],t['voice']) for t in turns],[('Host','Charon'),('Guest','Leda'),('Host','Charon')])
        self.assertTrue(all(b['start']==a['end'] for a,b in zip(turns,turns[1:])) and turns[0]['start']==0)
        cues=module.caption_cues([{'start_seconds':t['start'],'end_seconds':t['end'],'text':t['text'],'speaker':t['speaker']} for t in turns])['cues']
        self.assertEqual(cues[1]['label'],'Guest: Glad to be here.')
    def test_spend_guard(self):
        with self.assertRaises(g.GeminiSpeechError):g.synthesize('hello','Kore',self.root/'l.json',max_usd=0.001)
        self.assertEqual(self.calls,[])
class Files(Route):
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_show_notes_and_speaker_captions_come_from_the_measured_timeline(self):
        app,pid=self.project()
        with self.assertRaisesRegex(ValueError,'Assemble'):app.episode_files(pid)
        app.narrate(pid,voices={'Host':'Charon','Guest':'Leda'});app.assemble(pid)
        out=app.episode_files(pid,str(self.root));self.assertEqual(out['speakers'],{'Host':'Charon','Guest':'Leda'})
        notes=(self.root/'show-notes.md').read_text();self.assertIn('Host (Gemini voice Charon)',notes);self.assertIn('0:00 A',notes)
        srt=(self.root/'captions.srt').read_text();self.assertIn('Guest: Glad to be here.',srt);self.assertIn('00:00:00,000 -->',srt)
        self.assertIn('<v Host>',(self.root/'captions.vtt').read_text());self.assertNotIn(SECRET,notes+srt)
class Lint(unittest.TestCase):
    def test_episode_files_written_by_the_plugin_pass_its_own_lint(self):
        with tempfile.TemporaryDirectory() as d:
            app=MediaProject(Path(d),'podcast');pid=app.create('T',factual=False)['project_id']
            out=app.script(pid,[{'title':'A','turns':[{'speaker':'Maya','text':'Welcome back to the show, everyone, we have a good one.'},{'speaker':'Dr. Leo','text':'Glad to be here, and ready to talk about purring.'}]}])
            self.assertEqual(module.lint_episode_tool(out['episode_dir'],require_sources=False)['errors'],0)
class Snippet(unittest.TestCase):
    def test_search_snippet_is_not_a_complete_source(self):
        with tempfile.TemporaryDirectory() as d:
            app=MediaProject(Path(d),'podcast');pid=app.create('T',factual=True)['project_id']
            with self.assertRaisesRegex(ValueError,'search snippet'):app.add_source(pid,'S','https://example.org/a','short snippet text')
            self.assertTrue(app.add_source(pid,'S','https://example.org/a','x'*1600)['characters']==1600)
            self.assertTrue(app.add_source(pid,'S','https://example.org/a','short excerpt',complete=False))
if __name__=='__main__':unittest.main()
