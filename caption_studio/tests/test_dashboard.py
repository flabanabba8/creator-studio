import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

root=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location('caption_dashboard_fixture',root/'dashboard'/'plugin_api.py')
dashboard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

class DashboardTests(unittest.TestCase):
    def test_inspect_suggest_retime_and_reinspect(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root=Path(tmp)
            source=root/'source.srt'
            reference=root/'reference.srt'
            source.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello there friend\n\n2\n00:00:04,000 --> 00:00:05,000\nAnother useful phrase\n')
            reference.write_text('1\n00:00:01,250 --> 00:00:02,250\nHello there friend\n\n2\n00:00:04,250 --> 00:00:05,250\nAnother useful phrase\n')
            app=FastAPI();app.include_router(dashboard.router);client=TestClient(app)
            with patch('plugins.plugin_storage.plugin_data_dir',return_value=root/'.hermes'/'plugin-data'/'creator-studio-captions'):
                inspect=client.post('/action',json={'operation':'captions_inspect','arguments':{'source_path':str(source)}})
                self.assertEqual(inspect.status_code,200)
                suggest=client.post('/action',json={'operation':'captions_suggest_alignment','arguments':{'source_path':str(source),'reference_path':str(reference)}})
                self.assertEqual(suggest.status_code,200,suggest.json())
                corrected=client.post('/action',json={'operation':'captions_retime','arguments':{'source_path':str(source),'fingerprint':inspect.json()['fingerprint'],'anchors':suggest.json()['suggested_anchors']}})
                self.assertEqual(corrected.status_code,200)
                check=client.post('/action',json={'operation':'captions_inspect','arguments':{'source_path':corrected.json()['output_path']}})
                self.assertEqual(check.status_code,200)
                self.assertEqual(check.json()['cues'][0]['start_ms'],1250)
                self.assertEqual(client.post('/action',json={'operation':'not_allowed','arguments':{}}).status_code,400)

if __name__=='__main__': unittest.main()
