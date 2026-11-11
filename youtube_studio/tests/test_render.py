import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cs_t.video_render_tests',root/'__init__.py',submodule_search_locations=[str(root)])
p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
from cs_t.video_render_tests.render import media, render_still, render_clips, stitch_segments

class RenderTests(unittest.TestCase):
 def test_timeout_removes_partial_output_and_caption_file(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   root=Path(tmp); image=root/'fixture.png'; audio=root/'fixture.wav'; image.write_bytes(b'fixture'); audio.write_bytes(b'fixture')
   with patch('cs_t.video_render_tests.render.shutil.which', return_value='/usr/bin/fixture'), patch('cs_t.video_render_tests.render.subprocess.run', side_effect=subprocess.TimeoutExpired('fixture', 120)):
    with self.assertRaisesRegex(RuntimeError, 'failed'):render_still(root/'out',str(image),str(audio),5,[],[])
   self.assertFalse(list((root/'out').glob('*.mp4'))); self.assertFalse(list((root/'out').glob('*.vtt')))

 def test_clip_timeout_removes_partial_output_and_caption_file(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   root=Path(tmp); clip=root/'fixture.mp4'; audio=root/'fixture.wav'; clip.write_bytes(b'fixture'); audio.write_bytes(b'fixture')
   response = subprocess.CompletedProcess([], 0, stdout=json.dumps({'format': {'duration': '6'}, 'streams': [{'codec_type': 'video'}]}).encode())
   def run(command, **kwargs):
    if command[0].endswith('ffprobe'): return response
    raise subprocess.TimeoutExpired('fixture', 120)
   with patch('cs_t.video_render_tests.render.shutil.which', side_effect=lambda name: '/usr/bin/'+name), patch('cs_t.video_render_tests.render.subprocess.run', side_effect=run):
    with self.assertRaisesRegex(RuntimeError, 'failed'):render_clips(root/'out',[{'path':str(clip),'seconds':5}],str(audio),[],[])
   self.assertFalse(list((root/'out').glob('*.mp4'))); self.assertFalse(list((root/'out').glob('*.vtt')))

 def test_stitch_timeout_preserves_segments_and_removes_temporary_files(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   root=Path(tmp); segment=root/(('a'*32)+'.mp4'); segment.write_bytes(b'fixture'); audio=root/'audio.wav';audio.write_bytes(b'fixture')
   video_probe = subprocess.CompletedProcess([], 0, stdout=json.dumps({'format': {'duration': '5'}, 'streams': [{'codec_type': 'video'}]}).encode())
   audio_probe = subprocess.CompletedProcess([], 0, stdout=json.dumps({'format': {'duration': '10'}, 'streams': [{'codec_type': 'audio'}]}).encode())
   def run(command, **kwargs):
    if command[0].endswith('ffprobe'): return audio_probe if command[-1].endswith('audio.wav') else video_probe
    raise subprocess.TimeoutExpired('fixture', 120)
   with patch('cs_t.video_render_tests.render.shutil.which', side_effect=lambda name: '/usr/bin/'+name), patch('cs_t.video_render_tests.render.subprocess.run', side_effect=run):
    with self.assertRaisesRegex(RuntimeError, 'failed'):stitch_segments(root,['a'*32],str(audio))
   self.assertEqual(segment.read_bytes(),b'fixture');self.assertFalse(list(root.glob('*.partial.mp4')));self.assertFalse(list(root.glob('*.concat.txt')))

 def test_stitch_segment_limit_is_checked_before_media_access(self):
  with self.assertRaisesRegex(ValueError, '1–60'):
   stitch_segments(Path('/tmp/nonexistent-fixture'), ['a'*32]*61, 'missing.wav')

 def test_audio_size_limit_allows_large_mixed_wav_but_stays_bounded(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   root=Path(tmp);audio=root/'synthetic.wav'
   with audio.open('wb') as f:f.truncate(512*1024**2+1)
   with self.assertRaises(ValueError):media(str(audio),{'.wav'},root,False)
   self.assertEqual(media(str(audio),{'.wav'},root,False,max_bytes=2*1024**3),audio)
   with audio.open('r+b') as f:f.truncate(2*1024**3+1)
   with self.assertRaises(ValueError):media(str(audio),{'.wav'},root,False,max_bytes=2*1024**3)

 def test_unsupported_platform_fails_before_file_access(self):
  with patch('cs_t.common.locking.fcntl', None), patch('cs_t.common.locking.msvcrt', None):
   with self.assertRaisesRegex(ValueError,'supported file locking'):render_still(Path('/tmp/fixture'),'missing.png','missing.wav',5,[],[])
   with self.assertRaisesRegex(ValueError,'supported file locking'):stitch_segments(Path('/tmp/fixture'),['a'*32],'missing.wav')

 def test_posix_lock_rejects_a_second_owner(self):
  from cs_t.common import locking
  if locking.fcntl is None:self.skipTest('POSIX-specific lock check')
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   path=Path(tmp)/'lock'
   with locking.exclusive_lock(path,'busy'):
    with self.assertRaisesRegex(RuntimeError,'busy'):
     with locking.exclusive_lock(path,'busy'):pass

 def test_profile_opt_in_and_other_private_config(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   profile=Path(tmp)/'custom-profile'; data=profile/'plugin-data'; root=data/'youtube-video-studio'; root.mkdir(parents=True)
   selected=data/'podcast-studio'/'audio.wav'; selected.parent.mkdir(); selected.write_bytes(b'fixture')
   with self.assertRaises(ValueError):media(str(selected),{'.wav'},root,False)
   self.assertEqual(media(str(selected),{'.wav'},root,True),selected)
   secret=profile/'private.wav';secret.write_bytes(b'fixture')
   with self.assertRaises(ValueError):media(str(secret),{'.wav'},root,True)
   link=Path(tmp)/'shortcut.wav';link.symlink_to(selected)
   with self.assertRaises(ValueError):media(str(link),{'.wav'},root,True)

 def test_mixed_case_private_media_paths_are_rejected(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
   for name in ('.CoDeX','.HeRmEs'):
    folder=Path(tmp)/name;folder.mkdir();source=folder/'fixture.wav';source.write_bytes(b'fixture')
    with self.assertRaises(ValueError):media(str(source),{'.wav'},Path(tmp)/'plugin',False)

if __name__=='__main__':unittest.main()
