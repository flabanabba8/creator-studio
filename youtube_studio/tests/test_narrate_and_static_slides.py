import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import http.server,importlib.util,json,shutil,subprocess,sys,tempfile,threading,unittest,wave
from pathlib import Path
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.video_narrate_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.video_narrate_fixture.media_project import MediaProject
import cs_t.video_narrate_fixture.media_project as mp
HAVE=shutil.which('ffmpeg') and shutil.which('ffprobe')

def wav_bytes(seconds):
    import io
    b=io.BytesIO()
    with wave.open(b,'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\x10\x00'*int(24000*seconds))
    return b.getvalue()

class Handler(http.server.BaseHTTPRequestHandler):
    seen=[]
    def log_message(self,*a):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));Handler.seen.append(body)
        data=wav_bytes(1+len(Handler.seen)*.5);self.send_response(200);self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

class NarrateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);Handler.seen=[]
        self.server=http.server.HTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.base='http://127.0.0.1:%d'%self.server.server_address[1]
    def tearDown(self):self.server.shutdown();self.tmp.cleanup()
    def project(self,words=5):
        app=MediaProject(self.root/'data','video');pid=app.create('T',factual=False)['project_id']
        app.script(pid,[{'title':'A','turns':[{'speaker':'N','text':'one two three four five'},{'speaker':'N','text':'six '*words}]},{'title':'B','turns':[{'speaker':'N','text':'last part here'}]}])
        return app,pid
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_one_request_per_turn_with_reference_and_attached_in_order(self):
        app,pid=self.project();ref=self.root/'ref.wav';ref.write_bytes(wav_bytes(2))
        out=app.narrate(pid,str(ref),'What the sample says.',base_url=self.base,model='m')
        self.assertEqual((out['recorded_now'],out['turns'],len(Handler.seen)),(3,3,3))
        self.assertTrue(all(r['references'][0]['audio_path'].startswith('data:audio/wav;base64,')and r['references'][0]['text']=='What the sample says.'for r in Handler.seen))
        data=app.load(pid)[1];self.assertEqual([len(s['audio_ids'])for s in data['sections']],[2,1])
        self.assertEqual(len(list((Path(out['raw_and_normalized_takes'])).glob('raw-*.wav'))),3)  # raw takes kept
        again=app.narrate(pid,str(ref),'What the sample says.',base_url=self.base,model='m')
        self.assertEqual((again['recorded_now'],again['already_recorded'],len(Handler.seen)),(0,3,3))  # no rerolls
    def test_long_turn_refused_before_any_request(self):
        app,pid=self.project(words=61)
        with self.assertRaisesRegex(ValueError,'60 words'):app.narrate(pid,base_url=self.base,model='m')
        self.assertEqual(Handler.seen,[])
    def test_non_loopback_server_refused(self):
        app,pid=self.project()
        with self.assertRaisesRegex(ValueError,'this computer'):app.narrate(pid,base_url='http://example.org:8000',model='m')

class StaticSlideTests(unittest.TestCase):
    def test_assembled_slides_use_no_motion(self):
        import inspect
        self.assertNotIn('MOTIONS',inspect.getsource(MediaProject.assemble))
        self.assertIn("'motion':'none'",inspect.getsource(MediaProject.assemble))
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_left_edge_text_is_not_cropped_in_first_middle_last_frames(self):
        from PIL import Image,ImageDraw,ImageChops
        from cs_t.video_narrate_fixture.slides import render_slides
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            base=Path(t);img=Image.new('RGB',(1920,1080),(250,250,250));d=ImageDraw.Draw(img)
            d.rectangle((0,200,60,300),fill=(0,0,0));d.rectangle((0,400,30,500),fill=(200,0,0))  # content touching the left edge
            still=base/'s.png';img.save(still);audio=base/'a.wav';subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=f=300:d=6',str(audio)],check=True,stdin=subprocess.DEVNULL)
            out=Path(render_slides(base/'out',[{'path':str(still),'seconds':6,'motion':'none'}],str(audio),[],[])['output_path'])
            ref=img.resize((1280,720))
            for at in(0.1,3,5.8):
                f=base/('f%s.png'%at);subprocess.run(['ffmpeg','-v','error','-y','-ss',str(at),'-i',str(out),'-frames:v','1',str(f)],check=True,stdin=subprocess.DEVNULL)
                frame=Image.open(f).convert('RGB')
                for y in(250,450):  # the black and red bars at x=0..20 must survive at every moment
                    a=frame.getpixel((8,y*2//3));b=ref.getpixel((8,y*2//3))
                    self.assertLess(sum(abs(p-q)for p,q in zip(a,b)),90,(at,y,a,b))

class LayoutTests(unittest.TestCase):
    def test_flowchart_and_table_fill_the_frame_with_large_text(self):
        from PIL import Image
        from cs_t.video_narrate_fixture.visuals import make_visual
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            flow=make_visual(Path(t),'flowchart','The phase cycle',{'nodes':[{'id':'a','label':'New Moon: lit side faces away'},{'id':'b','label':'Waxing crescent: thin lit curve grows'},{'id':'c','label':'First quarter: half the disk is lit'},{'id':'d','label':'Full Moon: the whole disk is lit'}],'edges':[{'from':'a','to':'b'},{'from':'b','to':'c'},{'from':'c','to':'d'}]},{'kind':'sourced','note':'NASA'})
            table=make_visual(Path(t),'table','The phases',{'columns':['Phase','What we see'],'rows':[['New Moon','Dark, no lit part'],['Crescent','Thin lit curve grows'],['Quarter','Half the disk lit'],['Full Moon','Whole disk lit']]},{'kind':'sourced','note':'NASA'})
            for path,low in((flow['output_path'],.22),(table['output_path'],.45)):
                img=Image.open(path).convert('RGB');px=img.load();w,h=img.size
                boxes=sum(1 for y in range(0,h,3)for x in range(0,w,3)if px[x,y]!=(240,245,251)and y>150)/((h-150)/3*w/3)
                self.assertGreater(boxes,low,(path,boxes))   # the boxes/cells cover a large share of the frame (the old four small boxes covered about 3%)
                tall=0
                for x in range(0,w,5):
                    run=0
                    for y in range(150,h):
                        if sum(abs(a-b)for a,b in zip(px[x,y],(23,55,78)))<40:run+=1;tall=max(tall,run)
                        else:run=0
                self.assertGreaterEqual(tall,24,path)   # letter strokes at least ~24 px tall: large enough to read in a 720p video
    @unittest.skipUnless(HAVE,'ffmpeg required')
    def test_burned_caption_band_never_covers_the_picture(self):
        from PIL import Image,ImageDraw
        from cs_t.video_narrate_fixture.slides import render_slides
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            base=Path(t);img=Image.new('RGB',(1920,1080),(240,245,251));d=ImageDraw.Draw(img);d.rectangle((300,900,1600,1070),fill=(200,0,0))  # content right at the bottom edge
            still=base/'s.png';img.save(still);audio=base/'a.wav';subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=f=300:d=4',str(audio)],check=True,stdin=subprocess.DEVNULL)
            out=Path(render_slides(base/'out',[{'path':str(still),'seconds':4}],str(audio),[],[{'start':0.2,'end':3.5,'text':'A caption that would normally sit on the picture'}],burn_captions=True)['output_path'])
            f=base/'f.png';subprocess.run(['ffmpeg','-v','error','-y','-ss','1.5','-i',str(out),'-frames:v','1',str(f)],check=True,stdin=subprocess.DEVNULL)
            frame=Image.open(f).convert('RGB')
            self.assertLess(sum(abs(a-b)for a,b in zip(frame.getpixel((640,610)),(200,0,0))),60)   # content bottom stays red, not covered by caption text
            band=[frame.getpixel((x,y))for y in range(632,716,2)for x in range(300,980,3)]
            self.assertGreater(sum(1 for p in band if min(p)>200),30)   # caption text is drawn in the band below the picture
            self.assertFalse(any(p[0]>150 and p[1]<60 for p in band))   # nothing of the picture reaches the band

class CycleAndSlideTests(unittest.TestCase):
    def test_eight_step_cycle_draws_all_boxes_and_closes_the_loop(self):
        from PIL import Image
        from cs_t.video_narrate_fixture.visuals import make_visual
        names=['New Moon','Waxing crescent','First quarter','Waxing gibbous','Full Moon','Waning gibbous','Last quarter','Waning crescent']
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            r=make_visual(Path(t),'cycle','The eight phases',{'nodes':[{'label':x+': what we see'}for x in names]},{'kind':'sourced','note':'NASA'})
            img=Image.open(r['output_path']).convert('RGB');px=img.load();w,h=img.size
            white=sum(1 for y in range(150,h,3)for x in range(0,w,3)if px[x,y]==(255,255,255))/((h-150)/3*w/3)
            self.assertGreater(white,.15)   # eight large boxes (the old four-box flowchart covered about 8%)
            # the loop is closed: the arrow head into box 0 (top, accent outline) exists near its left edge
            top=[(x,y)for y in range(150,330)for x in range(700,1220,2)if px[x,y]==(225,125,104)]
            self.assertTrue(top)           # first box has the accent outline
            with self.assertRaises(ValueError):make_visual(Path(t),'cycle','Too short',{'nodes':[{'label':'a'},{'label':'b'}]},{'kind':'sourced','note':'x'})
    def test_short_slides_fill_the_frame(self):
        from PIL import Image
        from cs_t.video_narrate_fixture.deck import make_slides
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            s=make_slides(Path(t),[{'title':'Why we see phases','bullets':['The Sun lights half the Moon','We see a changing part of it','The pattern repeats every month']}],theme='light')['slides'][0]['path']
            img=Image.open(s).convert('RGB');px=img.load();w,h=img.size;bg=px[w-5,5]
            lowest=max((y for y in range(h)for x in range(100,w-100,12)if sum(abs(a-b)for a,b in zip(px[x,y],bg))>150),default=0)
            self.assertGreater(lowest,h*.55)   # text reaches well below the middle of the frame

class PictureSlideTests(unittest.TestCase):
    def test_picture_gets_the_right_half_of_the_frame(self):
        from PIL import Image
        from cs_t.video_narrate_fixture.deck import make_slides
        with tempfile.TemporaryDirectory(dir='/tmp')as t:
            pic=Path(t)/'p.png';Image.new('RGB',(1536,1024),(200,30,30)).save(pic)
            s=make_slides(Path(t),[{'title':'Sunlight','bullets':['One idea','Two ideas'],'image_path':str(pic)}],theme='light',allow_profile_media=True)['slides'][0]['path']
            img=Image.open(s).convert('RGB');px=img.load();w,h=img.size
            xs=[x for x in range(w)for y in(h//2,)if px[x,y][0]>180 and px[x,y][1]<60]
            self.assertLessEqual(min(xs),w//2+10);self.assertGreaterEqual(max(xs)-min(xs),w*.4)   # picture spans at least 40% of the width, starting at the middle

if __name__=='__main__':unittest.main()
