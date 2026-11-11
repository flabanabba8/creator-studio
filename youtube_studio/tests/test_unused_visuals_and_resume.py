"""0.2.1 fixtures: the Gemini guard reserves in proportion to the text and explains a refusal; the skills state the rules.
(Unused visuals, resume status and take reuse are tested in tests/test_resume.py.)"""
import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import base64,importlib.util,io,json,shutil,sys,tempfile,unittest,wave
from pathlib import Path
from unittest import mock
from PIL import Image
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.video_fix021_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.video_fix021_fixture.media_project import MediaProject
from cs_t.common import gemini_speech as g
HAVE=shutil.which('ffmpeg')

def wavbytes(seconds=1.0):
    b=io.BytesIO()
    with wave.open(b,'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\x10\x00'*int(24000*seconds))
    return b.getvalue()
def ok_body():
    return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(wavbytes()).decode()}}]}}],'usageMetadata':{'promptTokenCount':40,'candidatesTokenCount':300}}).encode()

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir()
        storage=_t.ModuleType('plugins.plugin_storage');storage.plugin_data_dir=lambda name:self.data
        p=mock.patch.dict(sys.modules,{'plugins':_t.ModuleType('plugins'),'plugins.plugin_storage':storage});p.start();self.addCleanup(p.stop);self.addCleanup(self.tmp.cleanup)
    def visual(self,title,kind='flowchart'):
        data={'nodes':[{'id':'a','label':'Sunlight'},{'id':'b','label':'Scattering'}],'edges':[['a','b']]}if kind=='flowchart'else None
        out=json.loads(module.invoke('youtube_make_visual',{'kind':kind,'title':title,'data':data,'provenance':{'kind':'sourced','note':'fixture'}}))
        return out
    def lesson(self,titles=('Why the sky is blue','Sunsets turn red')):
        app=MediaProject(self.data,'video');pid=app.create('Sky',factual=False)['project_id']
        app.script(pid,[{'title':t,'turns':[{'speaker':'N','text':'Short line number %d.'%i}]}for i,t in enumerate(titles)])
        return app,pid
    def wav(self):
        path=self.root/'speech.wav';path.write_bytes(wavbytes(2));return path

class SkillRules(unittest.TestCase):
    def test_skills_state_the_visual_rule_and_the_resume_path(self):
        t=(ROOT/'skills/create-youtube-video/SKILL.md').read_text();self.assertIn('visuals_used',t);self.assertIn('every attached picture',t)
        for part,name in(('youtube_studio','create-youtube-video'),('podcast_studio','create-podcast'),('tutorial_creator','create-tutorial')):
            self.assertIn('arry on',(ROOT.parent/part/'skills'/name/'SKILL.md').read_text(),part)

class Speech(Base):
    def setUp(self):
        super().setUp();self.calls=[]
        def fake(url,headers,body):self.calls.append(body);return 200,ok_body()
        for p in(mock.patch.object(g,'project',lambda:'proj-x'),mock.patch.object(g,'access_token',lambda:'t'),mock.patch.object(g,'transport',fake)):p.start();self.addCleanup(p.stop)
    def test_short_line_passes_a_small_guard(self):
        self.assertLess(g.estimate_usd('Hello there, this is a short line.'),0.03)
        self.assertLess(g.estimate_usd('word '*100),0.1)
        led=self.root/'l.json';g.synthesize('Hello there.','Kore',led,max_usd=0.05);self.assertEqual(len(self.calls),1)
        self.assertLess(json.loads(led.read_text())[0]['reserved_or_actual_usd'],0.01)
    def test_estimate_grows_with_the_text_and_has_a_small_minimum(self):
        self.assertGreaterEqual(g.estimate_usd('Hi'),g.MIN_ESTIMATE_USD);self.assertGreater(g.estimate_usd('word '*80),g.estimate_usd('word '*10))
    def test_guard_stays_strict_and_the_refusal_explains(self):
        led=self.root/'l.json';est=g.estimate_usd('Hello there.')
        with self.assertRaises(g.GeminiSpeechError)as c:g.synthesize('Hello there.','Kore',led,max_usd=est/2)
        m=str(c.exception);self.assertEqual(self.calls,[]);self.assertIn('estimated %.4f'%est,m);self.assertIn('%.4f USD cap'%(est/2),m);self.assertIn('0 earlier cues were recorded',m);self.assertIn('this cue was refused without being sent',m)
        with self.assertRaises(g.GeminiSpeechError):g.synthesize('Hello there.','Kore',led,max_usd=est*0.999)
        self.assertEqual(self.calls,[])
        # the earlier spend counts: a second request that would pass the guard is refused
        g.synthesize('Hello there.','Kore',led,max_usd=est*1.5+0.02);self.assertEqual(len(self.calls),1)
        with self.assertRaises(g.GeminiSpeechError):g.synthesize('Hello there.','Kore',led,max_usd=1e-9+0.0001)
if __name__=='__main__':unittest.main()
