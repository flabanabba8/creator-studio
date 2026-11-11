import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('caption_recognizers_fixture',Path(__file__).parents[1]/'recognizers.py')
rec=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp'); self.home=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def cache_model(self,name,config=True):
        snap=self.home/'.cache/huggingface/hub'/f'models--{name.replace("/","--")}'/'snapshots'/'abc'
        snap.mkdir(parents=True)
        if config: (snap/'config.json').write_text('{}')
    def fake_python(self,folder,body):
        env=self.home/folder; (env/'bin').mkdir(parents=True); (env/'pyvenv.cfg').write_text('home = x\n')
        exe=env/'bin/python'; exe.write_text('#!/bin/sh\n'+body+'\n'); exe.chmod(exe.stat().st_mode|stat.S_IXUSR)
        return exe
    def test_cached_speech_models_are_found_without_loading(self):
        self.cache_model('openai/whisper-large-v3-turbo'); self.cache_model('someone/text-model'); self.cache_model('nvidia/partial-asr',config=False)
        with mock.patch.dict(os.environ,{'HOME':str(self.home)},clear=True), mock.patch.object(rec.Path,'home',return_value=self.home):
            found=rec.cached_speech_models()
        self.assertEqual([m['model'] for m in found],['openai/whisper-large-v3-turbo'])
        self.assertTrue(found[0]['transformers_whisper_adapter'])
    def test_python_environments_with_speech_modules_are_found_and_others_ignored(self):
        good=self.fake_python('work/app/.venv','echo \'{"torch": true, "transformers": true, "faster_whisper": false}\'')
        self.fake_python('work/other/.venv','echo \'{"torch": false, "transformers": false, "faster_whisper": false}\'')
        self.fake_python('.hermes/hidden/.venv','echo \'{"torch": true, "transformers": true, "faster_whisper": true}\'')
        with mock.patch.dict(os.environ,{'PATH':'/nonexistent'},clear=True), mock.patch.object(rec.Path,'home',return_value=self.home):
            found=rec.python_runtimes()
        self.assertEqual([r['python'] for r in found],[str(good)])
        self.assertTrue(found[0]['runs_transformers_adapter'])
    def test_options_reports_a_ready_local_command_and_never_runs_recognition(self):
        self.cache_model('openai/whisper-large-v3-turbo')
        self.fake_python('app/.venv','''if [ "$3" = "--probe" ]; then echo '{"torch": "2.0.0", "transformers": "4.57.3"}'; else echo '{"torch": true, "transformers": true, "faster_whisper": false}'; fi''')
        with mock.patch.dict(os.environ,{'PATH':'/usr/bin:/bin'},clear=True), mock.patch.object(rec.Path,'home',return_value=self.home):
            result=rec.options()
        ready=result['local_speech_resources']['ready_local_commands']
        self.assertEqual(len(ready),1)
        recognizer=ready[0]['recognizer']
        self.assertEqual((recognizer['kind'],recognizer['model'],recognizer['output']),('command','openai/whisper-large-v3-turbo','stdout'))
        self.assertTrue(recognizer['argv'][1].endswith('examples/transformers_asr.py'))
        json.dumps(result)
    def test_device_is_cuda_only_with_a_cuda_build_and_enough_free_memory(self):
        gpu=[{'name':'x','memory_mib':24000,'free_mib':6000}]
        self.assertEqual(rec.choose_device({'torch':'2.12.0'},gpu),'cuda')
        self.assertEqual(rec.choose_device({'torch':'2.12.0+cpu'},gpu),'cpu')
        self.assertEqual(rec.choose_device({'torch':'2.12.0'},[{'free_mib':1000}]),'cpu')
        self.assertEqual(rec.choose_device({'torch':'2.12.0'},[]),'cpu')
    def test_no_resources_gives_empty_lists(self):
        with mock.patch.dict(os.environ,{'PATH':'/nonexistent'},clear=True), mock.patch.object(rec.Path,'home',return_value=self.home):
            resources=rec.local_speech_resources()
        self.assertEqual((resources['cached_speech_models'],resources['ready_local_commands']),([],[]))

if __name__=='__main__': unittest.main()
