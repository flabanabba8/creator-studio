import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
"""Synthetic CPU clip-sequence export; no visual or audio quality claim."""
import importlib.util
import json
from pathlib import Path
import subprocess
import struct
import shutil
import sys
import tempfile
import unittest
import wave
root=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('cs_t.clips_fixture',root/'__init__.py',submodule_search_locations=[str(root)]);p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
from cs_t.clips_fixture.render import render_clips, stitch_segments

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
class ClipRender(unittest.TestCase):
 def test_two_clips_and_narration(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);clip=base/'fixture.mp4';audio=base/'narration.wav'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=5:d=31','-c:v','libx264','-preset','ultrafast','-threads','1','-y',str(clip)],check=True,capture_output=True,timeout=15)
   white=base/'white.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=white:s=160x90:r=5:d=16','-c:v','libx264','-preset','ultrafast','-threads','1','-y',str(white)],check=True,capture_output=True,timeout=15)
   with wave.open(str(audio),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*(8000*31))
   chapters=[{'start':0,'title':'Intro'},{'start':10,'title':'Method'},{'start':20,'title':'Result'}]
   result=render_clips(base/'out',[{'path':str(clip),'seconds':15},{'path':str(white),'seconds':15}],str(audio),chapters,[{'start':0.5,'end':3,'text':'Synthetic caption.'}])
   self.assertEqual(result['clips'],2);self.assertTrue(result['captions_included']);self.assertTrue(Path(result['output_path']).is_file());self.assertEqual(Path(result['output_path']).stat().st_mode & 0o777,0o600)
   def pixel(second):
    return subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',result['output_path'],'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','gray','-'],timeout=10)[0]
   self.assertLess(pixel(5), pixel(20))
   silent=render_clips(base/'out',[{'path':str(clip),'seconds':15},{'path':str(white),'seconds':15}],str(audio),chapters,[])
   self.assertFalse(silent['captions_included']);self.assertTrue(Path(silent['output_path']).is_file())
   with wave.open(str(audio),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*(8000*61))
   joined=stitch_segments(base/'out',[result['segment_id'],silent['segment_id']],str(audio))
   info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',joined['output_path']],timeout=10))
   self.assertEqual({x['codec_type'] for x in info['streams']},{'video','audio'})
   short=render_clips(base/'short-video',[{'path':str(clip),'seconds':5}],str(audio),[],[])
   self.assertEqual(short['clips'],1);self.assertLess(short['duration_seconds'],6)
   single=render_clips(base/'single',[{'path':str(clip),'seconds':30}],str(audio),chapters,[])
   self.assertEqual(single['clips'],1)
   with self.assertRaisesRegex(ValueError, 'shorter'):
    render_clips(base/'short',[{'path':str(clip),'seconds':32}],str(audio),chapters,[])
   self.assertFalse(list((base/'short').glob('*.mp4')))

 def test_segment_offsets_select_later_clip_and_audio(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);clip=base/'two-colors.mp4';audio=base/'two-tones.wav'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=5:d=5','-f','lavfi','-i','color=c=white:s=160x90:r=5:d=5','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0,setpts=PTS+2/TB[v]','-map','[v]','-c:v','libx264','-preset','ultrafast','-threads','1','-y',str(clip)],check=True,capture_output=True,timeout=15)
   with wave.open(str(audio),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*(8000*5)+b'\x10\x27'*(8000*5))
   output_root=base/"out'fixture"
   first=render_clips(output_root,[{'path':str(clip),'start':0,'seconds':5}],str(audio),[],[],audio_start=0)
   result=render_clips(output_root,[{'path':str(clip),'start':5,'seconds':5}],str(audio),[],[],audio_start=5)
   pixel=subprocess.check_output(['ffmpeg','-v','error','-ss','1','-i',result['output_path'],'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','gray','-'],timeout=10)[0]
   pcm=subprocess.check_output(['ffmpeg','-v','error','-i',result['output_path'],'-t','1','-map','0:a:0','-f','s16le','-'],timeout=10)
   self.assertGreater(pixel,200);self.assertTrue(any(pcm));self.assertEqual(result['audio_start_seconds'],5)
   joined=stitch_segments(output_root,[first['segment_id'],result['segment_id']],str(audio))
   self.assertEqual(joined['segments'],2);self.assertAlmostEqual(joined['duration_seconds'],10,delta=0.5)
   subprocess.run(['ffmpeg','-v','error','-xerror','-i',joined['output_path'],'-f','null','-'],check=True,capture_output=True,timeout=15)
   self.assertAlmostEqual(joined['segment_boundaries'][1]['estimated_start_seconds'],5,delta=0.2)
   def sample(second):return subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',joined['output_path'],'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','gray','-'],timeout=10)[0]
   self.assertLess(sample(2),sample(7))
   def audio_at(second):return subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',joined['output_path'],'-t','1','-map','0:a:0','-f','s16le','-'],timeout=10)
   self.assertFalse(any(audio_at(2)));self.assertTrue(any(audio_at(7)))
   raw=subprocess.check_output(['ffmpeg','-v','error','-i',joined['output_path'],'-t','6','-map','0:a:0','-ac','1','-ar','8000','-f','s16le','-'],timeout=10)
   samples=struct.unpack('<'+'h'*(len(raw)//2),raw)
   onset=next(i for i,value in enumerate(samples) if abs(value)>1000)/8000
   self.assertLess(abs(onset-5),0.15, 'synthetic onset seconds: '+str(onset))
   self.assertEqual(Path(joined['output_path']).stat().st_mode & 0o777,0o600)
   self.assertFalse(list(output_root.glob('*.concat.txt')))
   meta=base/'chapters.txt';meta.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=4000\ntitle=fixture\n')
   marked=output_root/(('c'*32)+'.mp4')
   subprocess.run(['ffmpeg','-v','error','-i',first['output_path'],'-f','ffmetadata','-i',str(meta),'-map','0','-c','copy','-map_chapters','1','-y',str(marked)],check=True,capture_output=True,timeout=10)
   original_chapters=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_chapters','-of','json',str(marked)],timeout=10))['chapters']
   self.assertTrue(original_chapters)
   cleared=stitch_segments(output_root,['c'*32],str(audio))
   self.assertEqual(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_chapters','-of','json',cleared['output_path']],timeout=10))['chapters'],[])
   incompatible=output_root/(('d'*32)+'.mp4')
   subprocess.run(['ffmpeg','-v','error','-i',first['output_path'],'-vf','scale=640:360','-c:v','libx264','-preset','ultrafast','-threads','1','-c:a','copy','-y',str(incompatible)],check=True,capture_output=True,timeout=15)
   with self.assertRaisesRegex(ValueError,'incompatible'):stitch_segments(output_root,[first['segment_id'],'d'*32],str(audio))
   with self.assertRaises(ValueError):stitch_segments(output_root,['../outside'],str(audio))
   self.assertFalse(list(output_root.glob('*.concat.txt')))

 def test_late_segment_from_large_sparse_wav(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);clip=base/'fixture.mp4';audio=base/'long.wav'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=5:d=3','-c:v','libx264','-preset','ultrafast','-threads','1','-y',str(clip)],check=True,capture_output=True,timeout=15)
   size=3000*48000*4
   header=struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',36+size,b'WAVE',b'fmt ',16,1,2,48000,192000,4,16,b'data',size)
   with audio.open('wb') as f:f.write(header);f.truncate(44+size)
   self.assertGreater(audio.stat().st_size,512*1024**2)
   if getattr(audio.stat(),'st_blocks',0)*512>4*1024**2:self.skipTest('Sparse fixture is not supported on this filesystem')
   result=render_clips(base/'out',[{'path':str(clip),'seconds':2}],str(audio),[],[],audio_start=2997)
   self.assertAlmostEqual(result['duration_seconds'],2,delta=.5);self.assertEqual(result['audio_start_seconds'],2997)

if __name__=='__main__':unittest.main()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
class SegmentsFromDifferentToolsJoin(unittest.TestCase):
 def test_still_clips_and_slides_segments_can_be_stitched_together(self):
  """Found through Hermes: the slideshow was 25 fps while still and clip segments were 10 fps, so stitching mixed segments failed."""
  from cs_t.clips_fixture.render import render_still
  from cs_t.clips_fixture.slides import render_slides
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);root=base/'store';root.mkdir(mode=0o700);audio=root/'a.wav';image=root/'i.png';clip=root/'c.mp4'
   run=lambda *a:subprocess.run(['ffmpeg','-v','error','-y',*a],check=True,capture_output=True,timeout=60)
   run('-f','lavfi','-i','sine=f=300:d=6','-ar','24000','-ac','1',str(audio))
   run('-f','lavfi','-i','color=c=blue:s=320x180','-frames:v','1',str(image))
   run('-f','lavfi','-i','color=c=red:s=320x180:r=5:d=4','-c:v','libx264','-preset','ultrafast',str(clip))
   still=render_still(root,str(image),str(audio),2,[],[])['segment_id']
   slides=render_slides(root,[{'path':str(image),'seconds':2}],str(audio),[],[])['segment_id']
   clips=render_clips(root,[{'path':str(clip),'seconds':2}],str(audio),[],[])['segment_id']
   result=stitch_segments(root,[still,slides,clips],str(audio))
   self.assertTrue(Path(result['output_path']).is_file())
