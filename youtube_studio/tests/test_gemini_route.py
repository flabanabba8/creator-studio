import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import base64,importlib.util,io,json,shutil,sys,tempfile,unittest,wave
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.video_gemini_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.common import gemini_speech as g
from cs_t.video_gemini_fixture.media_project import MediaProject
HAVE=shutil.which('ffmpeg')
SECRET_PROJECT='my-private-project-123'

def wav(seconds=1.0):
    b=io.BytesIO()
    with wave.open(b,'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\x10\x00'*int(24000*seconds))
    return b.getvalue()

def ok_body(seconds=1.0):
    return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(wav(seconds)).decode()}}]}}],'usageMetadata':{'promptTokenCount':40,'candidatesTokenCount':300}}).encode()

class Route(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[]
        def fake(url,headers,body):
            self.calls.append((url,headers,body));return 200,ok_body(1+len(self.calls)*.25)
        self.patches=[mock.patch.object(g,'project',lambda:SECRET_PROJECT),mock.patch.object(g,'access_token',lambda:'tok'),mock.patch.object(g,'transport',fake)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def project(self,text='one two three'):
        app=MediaProject(self.root/'data','video');pid=app.create('T',factual=False)['project_id']
        app.script(pid,[{'title':'A','turns':[{'speaker':'N','text':text},{'speaker':'N','text':'second part'}]},{'title':'B','turns':[{'speaker':'N','text':'last part'}]}])
        return app,pid
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_one_request_per_part_named_voice_ledger_and_attach_in_order(self):
        app,pid=self.project();out=app.narrate(pid,engine='gemini',voice='Charon')
        self.assertEqual((out['recorded_now'],len(self.calls)),(3,3))
        self.assertTrue(all(c[2]['generationConfig']['speechConfig']['voiceConfig']['voice']=='Charon' and c[0].endswith('gemini-3.8-flash-tts:generateContent')for c in self.calls))
        self.assertEqual([len(s['audio_ids'])for s in app.load(pid)[1]['sections']],[2,1])
        self.assertEqual(out['usage']['requests'],3);self.assertEqual(out['usage']['input_tokens'],120);self.assertLess(out['usage']['estimated_usd'],0.5)
        self.assertNotIn(SECRET_PROJECT,json.dumps(out))   # the project id never appears in a result
        again=app.narrate(pid,engine='gemini',voice='Charon');self.assertEqual((again['recorded_now'],again['already_recorded'],len(self.calls)),(0,3,3))  # no rerolls
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_default_engine_is_gemini_when_available(self):
        app,pid=self.project()
        with mock.patch.object(g,'available',lambda:{'available':True}):out=app.narrate(pid,voice='Kore')
        self.assertEqual(out['engine'],'gemini')
    def test_voice_required_and_validated(self):
        app,pid=self.project()
        with self.assertRaisesRegex(ValueError,'Choose a Gemini voice'):app.narrate(pid,engine='gemini')
        with self.assertRaisesRegex(ValueError,'named Gemini voices'):app.narrate(pid,engine='gemini',voice='Nobody')
        self.assertEqual(self.calls,[])
    def test_spend_guard_blocks_before_any_request(self):
        led=self.root/'led.json'
        with self.assertRaises(g.GeminiSpeechError)as c:g.synthesize('hello','Kore',led,max_usd=0.001)
        self.assertEqual(self.calls,[]);self.assertIn('Spend guard',str(c.exception))
    def test_rejected_request_is_not_retried_and_hides_the_project(self):
        led=self.root/'led.json'
        with mock.patch.object(g,'transport',lambda u,h,b:(400,json.dumps({'error':{'message':'bad project '+SECRET_PROJECT}}).encode())):
            with self.assertRaises(g.GeminiSpeechError)as c:g.synthesize('hello','Kore',led)
        self.assertNotIn(SECRET_PROJECT,str(c.exception));self.assertIn('<project>',str(c.exception));self.assertIn('no retry',str(c.exception))
        self.assertEqual(json.loads(led.read_text())[0]['status'],'rejected')
    def test_unavailable_reports_reason_without_project(self):
        stub=mock.MagicMock()
        with mock.patch.object(g,'project',lambda:None),mock.patch.dict(sys.modules,{'google':stub,'google.auth':stub,'requests':stub}):
            r=g.available();self.assertFalse(r['available']);self.assertIn('project',r['reason'])
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_review_note_is_rewritten_when_the_picture_is_looked_at_and_assembly_requires_it(self):
        from PIL import Image
        app,pid=self.project();img=self.root/'s.png';Image.new('RGB',(64,36),'white').save(img)
        for i in(0,1):
            p2=self.root/('s%d.png'%i);Image.new('RGB',(64,36),(i*40,0,0)).save(p2)
            app.add_asset(pid,str(p2),'image',i,'Drawn by youtube_make_slides from the outline; not yet inspected, so look at it before assembling.')
        app.narrate(pid,engine='gemini',voice='Kore')
        with self.assertRaisesRegex(ValueError,'look at its picture'):
            app.assemble(pid)
        row=app.add_asset(pid,str(self.root/'s0.png'),'image',0,'Looked at it: title and two bullets fully visible.')
        self.assertTrue(row['already_attached']);self.assertIn('Looked at it',app.load(pid)[1]['assets'][row['asset_id']]['review_note'])
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_assembly_requires_generated_illustrations_when_the_host_has_an_image_tool(self):
        from PIL import Image
        app,pid=self.project();app.narrate(pid,engine='gemini',voice='Kore')
        for i in(0,1):
            p2=self.root/('g%d.png'%i);Image.new('RGB',(64,36),(i*50,9,9)).save(p2);app.add_asset(pid,str(p2),'image',i,'Inspected slide, readable.')
        with self.assertRaisesRegex(ValueError,'generated illustrations'):app.assemble(pid,image_tool_available=True)
        app.add_asset(pid,str(self.root/'g0.png'),'image',0,'Generated illustration: sun on the left lighting the Moon.')
        self.assertTrue(app.assemble(pid,image_tool_available=True)['video'])
        app2,pid2=self.project();app2.narrate(pid2,engine='gemini',voice='Kore')
        for i in(0,1):app2.add_asset(pid2,str(self.root/('g%d.png'%i)),'image',i,'Inspected slide, readable.')
        self.assertTrue(app2.assemble(pid2,image_tool_available=False)['video'])  # no image tool: slides and graphics are fine
if __name__=='__main__':unittest.main()
