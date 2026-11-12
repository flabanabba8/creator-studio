import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util,json,sys,tempfile,unittest,wave
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.video_project_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.video_project_fixture.media_project import MediaProject
from cs_t.video_project_fixture.visuals import make_visual

class ResearchProjectTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def wav(self):
        path=self.root/'speech.wav'
        with wave.open(str(path),'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\0\0'*48000)
        return path
    def test_status_without_id_lists_projects(self):
        app=MediaProject(self.root/'data','video');p=app.create('Topic')['project_id']
        self.assertEqual([r['project_id']for r in app.status()['projects']],[p])
    def test_same_file_attached_twice_is_reused(self):
        app=MediaProject(self.root/'data','video');p=app.create('Topic')['project_id'];src=app.add_source(p,'S','https://example.org/s','Body text.');app.source_read(p,src['source_id'])
        app.script(p,[{'title':'A','source_ids':[src['source_id']],'turns':[{'speaker':'N','text':'Hi.'}]}])
        first=app.add_asset(p,str(self.wav()),'audio',0);second=app.add_asset(p,str(self.wav()),'audio',0)
        self.assertTrue(second['already_attached']);self.assertEqual(first['asset_id'],second['asset_id'])
        self.assertEqual(app.load(p)[1]['sections'][0]['audio_ids'],[first['asset_id']])
    def test_wrong_project_id_lists_existing_ids(self):
        app=MediaProject(self.root/'data','video');p=app.create('Topic')['project_id']
        with self.assertRaisesRegex(ValueError,'Existing project IDs: '+p):app.load(p[:-1])
        with self.assertRaisesRegex(ValueError,'Existing project IDs: '+p):app.load('0'*32)
    def test_complete_source_read_script_real_assets_and_assembly(self):
        app=MediaProject(self.root/'data','video');p=app.create('An original demonstration')['project_id'];s=app.add_source(p,'Fixture','https://example.org/source','Original fixture information for this demonstration.')
        sections=[{'title':'Example','source_ids':[s['source_id']],'turns':[{'speaker':'Narrator','text':'An original demonstration.'}]}]
        with self.assertRaisesRegex(ValueError,'Read complete'):app.script(p,sections)
        app.source_read(p,s['source_id']);script=app.script(p,sections);self.assertTrue(Path(script['episode_dir']).is_dir())
        with self.assertRaisesRegex(ValueError,'speech WAV'):app.assemble(p)
        image=self.root/'image.png';Image.new('RGB',(400,300),'#2595a4').save(image)
        app.add_asset(p,str(image),'image',0,'Synthetic fixture geometry checked; no real artwork quality claim')
        app.add_asset(p,str(self.wav()),'audio',0)
        result=app.assemble(p);self.assertEqual(result['seconds'],2);self.assertTrue(Path(result['video']['output_path']).is_file());self.assertEqual(app.status(p)['phase'],'assembled')
    def test_assembly_writes_measured_captions_chapters_and_moves_the_pictures(self):
        app=MediaProject(self.root/'data','video');p=app.create('Captions topic')['project_id'];s=app.add_source(p,'Fixture','https://example.org/source','Original fixture information.');app.source_read(p,s['source_id'])
        app.script(p,[{'title':'First part','source_ids':[s['source_id']],'turns':[{'speaker':'N','text':'One short idea. And a second idea.'}]}])
        image=self.root/'img.png';Image.new('RGB',(400,300),'#2595a4').save(image)
        app.add_asset(p,str(self.wav()),'audio',0);app.add_asset(p,str(image),'image',0,'checked')
        result=app.assemble(p)
        srt=Path(result['captions_srt_path']).read_text();self.assertIn('One short idea.',srt);self.assertIn('And a second idea.',srt)
        self.assertTrue(Path(result['captions_vtt_path']).read_text().startswith('WEBVTT'));self.assertTrue(result['captions_burned'])
        self.assertEqual(result['caption_count'],2);self.assertEqual(result['chapters'],[])
    def test_caption_cues_follow_turn_times_and_chapters_need_two_sections_of_five_seconds(self):
        from cs_t.video_project_fixture.media_project import caption_cues,chapter_list
        cues=caption_cues([('First sentence here. Second one follows.',0,10),('Another turn.',10,12)],12)
        self.assertEqual([c['text'] for c in cues],['First sentence here.','Second one follows.','Another turn.'])
        self.assertAlmostEqual(cues[0]['end'],cues[1]['start']);self.assertEqual(cues[-1]['end'],12)
        timeline=[{'title':'A','start':0.0},{'title':'B','start':12.7},{'title':'C','start':30.2}]
        self.assertEqual([c['start'] for c in chapter_list(timeline,45)],[0,12,30])
        self.assertEqual([c['start'] for c in chapter_list(timeline[:2],45)],[0,12]);self.assertEqual(chapter_list(timeline[:1],45),[]);self.assertEqual(chapter_list(timeline,33),[])  # last span 2.8 s
    def test_unknown_source_id_error_lists_the_real_ids_and_a_unique_prefix_is_accepted(self):
        app=MediaProject(self.root/'data','video');p=app.create('Topic')['project_id']
        with self.assertRaisesRegex(ValueError,'none saved yet'):app.script(p,[{'title':'A','source_ids':['0'*32],'turns':[{'speaker':'N','text':'Hi.'}]}])
        a=app.add_source(p,'First source','https://example.org/a','Alpha text.');b=app.add_source(p,'Second source','https://example.org/b','Beta text.')
        app.source_read(p,a['source_id']);app.source_read(p,b['source_id'])
        with self.assertRaises(ValueError)as caught:app.script(p,[{'title':'A','source_ids':['f'*32],'turns':[{'speaker':'N','text':'Hi.'}]}])
        message=str(caught.exception);self.assertIn(a['source_id'],message);self.assertIn(b['source_id'],message);self.assertIn('First source',message);self.assertIn("is not in this project",message)
        app.script(p,[{'title':'A','source_ids':[a['source_id'][:12]],'turns':[{'speaker':'N','text':'Hi.'}]}])  # an unambiguous prefix is taken as the intended ID
        self.assertEqual(app.load(p)[1]['sections'][0]['source_ids'],[a['source_id']])
    def test_a_drawn_visual_can_be_the_picture_of_its_section_and_the_tool_offers_it(self):
        import json as j
        from cs_t.video_project_fixture.visuals import make_visual
        app=MediaProject(self.root/'data','video');p=app.create('Topic',factual=False)['project_id']
        app.script(p,[{'title':'A','turns':[{'speaker':'N','text':'Hi.'}]},{'title':'B','turns':[{'speaker':'N','text':'Cycle.'}]}])
        v=make_visual(self.root/'data','table','Phases',{'columns':['Phase','What we see'],'rows':[['New','Dark'],['Full','All lit']]},{'kind':'sourced','note':'NASA'})
        row=app.add_asset(p,v['output_path'],'image',1,'Drawn from supplied data')
        self.assertEqual(app.load(p)[1]['sections'][1]['image_id'],row['asset_id'])
        src=(ROOT/'__init__.py').read_text();self.assertIn("'section_index'",src);self.assertIn('attached_to_section',src)
    def test_slides_tool_offers_project_attachment_and_skill_forbids_stopping_for_missing_image_tool(self):
        src=(ROOT/'__init__.py').read_text();self.assertIn("'section_indexes'",src);self.assertIn("'attached'",src)
        skill=(ROOT/'skills/create-youtube-video/SKILL.md').read_text();self.assertIn('never stop because',skill)
    def test_slide_images_attach_to_sections_through_the_project(self):
        from cs_t.video_project_fixture.deck import make_slides
        app=MediaProject(self.root/'data','video');p=app.create('Topic',factual=False)['project_id']
        app.script(p,[{'title':'A','turns':[{'speaker':'N','text':'Hi.'}]},{'title':'B','turns':[{'speaker':'N','text':'There.'}]}])
        made=make_slides(self.root/'data',[{'title':'One','bullets':['a']},{'title':'Two','bullets':['b']}],theme='light')
        for i,x in enumerate(made['slides']):app.add_asset(p,x['path'],'image',i,'drawn')
        self.assertTrue(all(s['image_id']for s in app.load(p)[1]['sections']))
    def test_research_runtime_comes_only_from_the_owners_settings_and_never_from_a_search_or_a_tool_argument(self):
        from cs_t.video_project_fixture import discovery
        from unittest import mock
        home=self.root/'home';(home/'.cache/camoufox').mkdir(parents=True);b=home/'.cache/camoufox/camoufox-bin';b.write_text('x');b.chmod(0o755)
        env=home/'work/camoufox/bin';env.mkdir(parents=True);(env.parent/'pyvenv.cfg').write_text('x');py=env/'python';py.write_text('#!/bin/sh\necho True\n');py.chmod(0o755)
        with mock.patch.object(discovery.Path,'home',return_value=home),mock.patch.dict('os.environ',{'PATH':'/nonexistent'},clear=True):
            self.assertIsNone(discovery.camoufox_runtime())                                    # a venv in the home folder is NOT found and NOT run
            self.assertIsNone(discovery.camoufox_runtime({}))
            found=discovery.camoufox_runtime({'camoufox_python':str(py)})
        self.assertEqual((found['python_executable'],found['browser_executable']),(str(py),str(b)))
        app=MediaProject(self.root/'data','video');p=app.create('Topic')['project_id']
        with self.assertRaises(TypeError):app.fetch(p,'https://example.org/',python_executable=str(py))       # no longer a tool argument
        with self.assertRaises(TypeError):app.fetch(p,'https://example.org/',browser_executable=str(b))
        with mock.patch.object(discovery.Path,'home',return_value=self.root/'empty'),mock.patch.dict('os.environ',{'PATH':'/nonexistent'},clear=True):
            (self.root/'empty').mkdir()
            app.settings={}
            self.assertIsNone(app.create('Another')['research_tools']['camoufox'])
            with self.assertRaisesRegex(ValueError,'No Camoufox runtime is configured'):app.fetch(p,'https://example.org/')
    def test_the_probe_of_the_configured_python_runs_with_a_clean_environment(self):
        from cs_t.video_project_fixture import discovery
        from unittest import mock
        seen={}
        def fake(argv,**kw):
            seen['env']=kw.get('env');return mock.Mock(returncode=0,stdout='True\n')
        py=self.root/'py';py.write_text('x');py.chmod(0o755)
        with mock.patch.dict('os.environ',{'OPENAI_API_KEY':'sk-x','PATH':'/usr/bin'}),mock.patch('subprocess.run',fake):
            self.assertEqual(discovery.camoufox_pythons(str(py)),[str(py)])
        self.assertNotIn('OPENAI_API_KEY',seen['env'])
    def test_speech_server_discovery_reports_a_request_shape_only_for_a_speech_route(self):
        import threading,http.server
        from cs_t.video_project_fixture import discovery
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body=json.dumps({'paths':{'/v1/audio/speech':{}}} if self.path=='/openapi.json' else {'data':[{'id':'/x/.cache/huggingface/hub/models--org--tts-model/snapshots/abc'}]}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
            def log_message(self,*a):pass
        server=http.server.HTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            found=discovery.speech_servers(ports=(server.server_port,))
            self.assertEqual(found[0]['models'],['org/tts-model']);self.assertEqual(found[0]['request_example']['response_format'],'wav')
        finally:server.shutdown()
        self.assertEqual(discovery.speech_servers(ports=(1,)),[])
    def test_podcast_assembly_and_source_change_boundaries(self):
        app=MediaProject(self.root/'pod','podcast');p=app.create('Original fiction',factual=False)['project_id'];app.script(p,[{'title':'Story','turns':[{'speaker':'Host','text':'Original fiction.'}]}]);a=app.add_asset(p,str(self.wav()),'audio',0);result=app.assemble(p);self.assertEqual(result['seconds'],2)
        folder=app.folder(p);(folder/a['file']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):app.assemble(p)
    def test_data_graphs_table_flow_and_bad_data(self):
        provenance={'kind':'illustrative','note':'Explicit fixture values, not a real-world benchmark'}
        for kind,data in [('bar',{'labels':['One','Two'],'values':[1,2]}),('line',{'x':[0,2,9],'values':[1,2,3]}),('table',{'columns':['Step','Action'],'rows':[['One','Research'],['Two','Review']]}),('flowchart',{'nodes':[{'id':'a','label':'Research'},{'id':'b','label':'Write'}],'edges':[{'from':'a','to':'b'}]})]:
            result=make_visual(self.root,kind,'Original visual',data,provenance)
            with Image.open(result['output_path'])as img:self.assertEqual(img.size,(1920,1080))
            self.assertEqual(result['data'],data)
        with self.assertRaises(ValueError):make_visual(self.root,'bar','Bad',{'labels':['A'],'values':[float('nan')]},provenance)
        with self.assertRaises(ValueError):make_visual(self.root,'flowchart','Cycle',{'nodes':[{'id':'a','label':'A'}],'edges':[{'from':'a','to':'a'}]},provenance)
    def test_native_image_refusal_and_context_are_preserved(self):
        calls=[];refusal={'error':'denied','status':'blocked'}
        class Host:
            def get_config(self,key):return 'selected_native_image'
            def dispatch_tool(self,name,args,**kw):calls.append((name,args,kw));return refusal
        result=module.invoke('youtube_generate_image',{'arguments':{'prompt':'An original asset'}},Host(),session_id='actual-session',private='not-forwarded')
        self.assertIs(result,refusal);self.assertEqual(calls[0][2],{'session_id':'actual-session'})
        host=Host();host.get_config=lambda key:'youtube_generate_image'
        self.assertIn('recursive',json.loads(module.invoke('youtube_generate_image',{'arguments':{}},host))['error'])
        self.assertIn('No selected native image tool',json.loads(module.invoke('youtube_generate_image',{'arguments':{}}))['error'])

if __name__=='__main__':unittest.main()
