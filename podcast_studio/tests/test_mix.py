import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

root=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('cs_t.podcast_mix_fixture',root/'__init__.py',submodule_search_locations=[str(root)]);p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
from cs_t.podcast_mix_fixture.mix import mix, mix_timeline, media

class MixTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
 def test_private_mix_and_loop_without_playback(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);narration=base/'narration.wav';music=base/'music.wav'
   def make(path,seconds,freq):
    with wave.open(str(path),'wb') as f:
     f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
     f.writeframes(b''.join(struct.pack('<h',round(3000*math.sin(i*2*math.pi*freq/8000))) for i in range(8000*seconds)))
   make(narration,2,0);make(music,1,220);before=[x.read_bytes() for x in (narration,music)]
   result=mix(base/'out',str(narration),str(music),music_db=-18)
   output=Path(result['output_path']);self.assertEqual(output.stat().st_mode & 0o777,0o600);self.assertAlmostEqual(result['duration_seconds'],2,delta=.25)
   with wave.open(str(output),'rb') as f:
    self.assertEqual((f.getnchannels(),f.getframerate()),(2,48000));f.setpos(72000);self.assertTrue(any(f.readframes(4000)))
   self.assertEqual(before,[x.read_bytes() for x in (narration,music)]);self.assertFalse(list((base/'out').glob('*.partial.wav')))
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
 def test_distinct_non_overlapping_music_beds(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);voice=base/'voice.wav';low=base/'low.wav';high=base/'high.wav'
   def make(path,seconds,freq):
    with wave.open(str(path),'wb') as f:
     f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
     f.writeframes(b''.join(struct.pack('<h',round(3000*math.sin(i*2*math.pi*freq/8000))) for i in range(8000*seconds)))
   make(voice,3,0);make(low,1,220);make(high,1,440)
   beds=[{'music_path':str(low),'start_ms':0,'end_ms':1000,'music_db':-12,'fade_in_ms':200,'fade_out_ms':200},{'music_path':str(high),'start_ms':1500,'end_ms':2500,'music_db':-12}]
   result=mix_timeline(base/'out',str(voice),beds);self.assertEqual(result['beds'],2)
   with wave.open(result['output_path'],'rb') as f:
    def samples(start):
     f.setpos(int(start*48000));data=f.readframes(19200);return struct.unpack('<'+'h'*(len(data)//2),data)[::2]
    first,gap,second=samples(.3),samples(1.1),samples(1.8)
    def level(start):
     f.setpos(int(start*48000));data=f.readframes(2400);values=struct.unpack('<'+'h'*(len(data)//2),data)[::2];return sum(abs(x) for x in values)/len(values)
    early,middle,late=level(.03),level(.45),level(.92)
    f.setpos(int(1.4*48000));data=f.readframes(9600);transition=struct.unpack('<'+'h'*(len(data)//2),data)[::2]
    onset=1.4+next(i for i,x in enumerate(transition) if abs(x)>100)/48000
   def crossings(values):return sum((a<0)!=(b<0) for a,b in zip(values,values[1:]))
   self.assertGreater(crossings(second),crossings(first)*1.5)
   self.assertLess(max(abs(x) for x in gap),20)
   self.assertLess(early,middle*.6);self.assertLess(late,middle*.6)
   self.assertLess(abs(onset-1.5),.002)
   beds[0]['fade_in_ms']=900;beds[0]['fade_out_ms']=200
   with self.assertRaisesRegex(ValueError,'Fades'):mix_timeline(base/'out',str(voice),beds)
   beds[0]['fade_in_ms']=200
   beds[1]['start_ms']=900
   with self.assertRaisesRegex(ValueError,'non-overlapping'):mix_timeline(base/'out',str(voice),beds)

 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
 def test_limiter_compensates_synthetic_narration_delay(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);voice=base/'voice.wav';music=base/'music.wav'
   with wave.open(str(voice),'wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000+struct.pack('<h',12000)*80+b'\0\0'*(8000-80))
   with wave.open(str(music),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000)
   result=mix(base/'out',str(voice),str(music))
   with wave.open(result['output_path'],'rb') as f:
    data=f.readframes(f.getnframes());samples=struct.unpack('<'+'h'*(len(data)//2),data)[::2]
   onset=next(i for i,value in enumerate(samples) if abs(value)>1000)/48000
   self.assertLess(abs(onset-1),.002)

 def test_private_profile_opt_in_and_gain_validation(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   data=Path(tmp)/'profile'/'plugin-data';root=data/'podcast-studio';root.mkdir(parents=True);audio=data/'pagecast'/'audio.wav';audio.parent.mkdir();audio.write_bytes(b'fixture')
   with self.assertRaises(ValueError):media(str(audio),root,False)
   self.assertEqual(media(str(audio),root,True),audio)
   with self.assertRaises(ValueError):mix(root,str(audio),str(audio),music_db=float('nan'),allow_profile_media=True)
 def test_unsupported_platform_fails_before_file_access(self):
  with patch('cs_t.common.locking.fcntl', None), patch('cs_t.common.locking.msvcrt', None):
   with self.assertRaisesRegex(ValueError,'supported file locking'):mix(Path('/tmp/fixture'),'missing.wav','missing.wav')
 def test_mixed_case_private_audio_paths_are_rejected(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   for name in ('.CoDeX','.HeRmEs'):
    folder=Path(tmp)/name;folder.mkdir();source=folder/'fixture.wav';source.write_bytes(b'fixture')
    with self.assertRaises(ValueError):media(str(source),Path(tmp)/'plugin',False)
 def test_posix_lock_rejects_a_second_owner(self):
  from cs_t.common import locking
  if locking.fcntl is None:self.skipTest('POSIX-specific lock check')
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   path=Path(tmp)/'lock'
   with locking.exclusive_lock(path,'busy'):
    with self.assertRaisesRegex(RuntimeError,'busy'):
     with locking.exclusive_lock(path,'busy'):pass

 def test_timeout_removes_partial(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);a=base/'a.wav';b=base/'b.wav';a.write_bytes(b'fixture');b.write_bytes(b'fixture')
   response=subprocess.CompletedProcess([],0,stdout=json.dumps({'format':{'duration':'2'},'streams':[{'codec_type':'audio'}]}).encode())
   def run(command,**kwargs):
    if command[0].endswith('ffprobe'):return response
    raise subprocess.TimeoutExpired('fixture',120)
   with patch('cs_t.podcast_mix_fixture.mix.shutil.which',side_effect=lambda name:'/usr/bin/'+name),patch('cs_t.podcast_mix_fixture.mix.subprocess.run',side_effect=run):
    with self.assertRaisesRegex(RuntimeError,'failed'):mix(base/'out',str(a),str(b))
   self.assertFalse(list((base/'out').glob('*.wav')))

if __name__=='__main__':unittest.main()

class LoudnessTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
 def test_loudness_target_is_applied_and_measured(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   base=Path(tmp);narration=base/'n.wav';music=base/'m.wav'
   for path,freq,amp in ((narration,220,0.03),(music,330,0.02)):
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=f={freq}:d=20:sample_rate=48000','-af',f'volume={amp}',str(path)],check=True,stdin=subprocess.DEVNULL)
   quiet=mix(base/'out',str(narration),str(music))
   target=mix(base/'out2',str(narration),str(music),loudness_lufs=-16)
   self.assertLess(quiet['integrated_lufs'],-30)
   self.assertAlmostEqual(target['integrated_lufs'],-16,delta=2.5)
   self.assertEqual(target['loudness_target_lufs'],-16)
   with self.assertRaisesRegex(ValueError,'loudness_lufs'):mix(base/'out3',str(narration),str(music),loudness_lufs=-5)
