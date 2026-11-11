import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('caption_suggest_fixture',Path(__file__).parents[1]/'core.py')
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class SuggestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp')
        self.root=Path(self.tmp.name)
        self.source=self.root/'source.srt'
        self.reference=self.root/'reference.srt'
        self.plugin=core.Captions(self.root/'output')
    def tearDown(self): self.tmp.cleanup()
    def write(self,path,times,texts):
        blocks=[]
        for index,(start,text) in enumerate(zip(times,texts),1):
            blocks.append(f'{index}\n{core.format_stamp(start)} --> {core.format_stamp(start+500)}\n{text}')
        path.write_text('\n\n'.join(blocks)+'\n')

    def test_robust_drift_estimate_reports_outlier(self):
        texts=['The first bright lantern','We cross the quiet river','The silver moon rises','A small bird is singing','Morning arrives at last']
        starts=[1000,11000,21000,31000,41000]
        targets=[3010,13110,23210,38310,43410]
        self.write(self.source,starts,texts)
        self.write(self.reference,targets,texts)
        result=self.plugin.suggest_alignment(str(self.source),str(self.reference))
        self.assertEqual(result['suggested_anchors'],[{'source_ms':1000,'target_ms':3010},{'source_ms':41000,'target_ms':43410}])
        self.assertEqual(result['median_residual_ms'],0)
        self.assertEqual(result['max_residual_ms'],5000)
        json.dumps(result)  # The tool and Desktop API must be able to serialize the report.
        output=self.plugin.retime(str(self.source),result['source_fingerprint'],result['suggested_anchors'])
        self.assertTrue(Path(output['output_path']).is_file())

    def test_single_and_duplicate_matches(self):
        self.write(self.source,[1000],['A single unique phrase'])
        self.write(self.reference,[1500],['A single unique phrase'])
        result=self.plugin.suggest_alignment(str(self.source),str(self.reference))
        self.assertEqual(result['method'],'single-match offset')
        self.write(self.source,[1000,2000],['A single unique phrase']*2)
        with self.assertRaisesRegex(ValueError,'No uniquely matching'):
            self.plugin.suggest_alignment(str(self.source),str(self.reference))

    def test_profile_caption_opt_in_is_narrow(self):
        private=self.root/'.hermes'
        other=private/'plugin-data'/'tutorial'
        other.mkdir(parents=True)
        caption=other/'captions.srt'
        self.write(caption,[1000],['A single unique phrase'])
        plugin=core.Captions(private/'plugin-data'/'caption-repair')
        with self.assertRaisesRegex(ValueError,'private configuration'):
            plugin.inspect(str(caption))
        self.assertEqual(plugin.inspect(str(caption),allow_profile_captions=True)['total'],1)
        unrelated=private/'unrelated.srt'
        unrelated.write_bytes(caption.read_bytes())
        with self.assertRaisesRegex(ValueError,'private configuration'):
            plugin.inspect(str(unrelated),allow_profile_captions=True)

    def test_custom_profile_configuration_stays_blocked(self):
        profile=self.root/'custom-profile'
        profile.mkdir()
        source=profile/'unrelated.srt'
        self.write(source,[1000],['A single unique phrase'])
        plugin=core.Captions(profile/'plugin-data'/'caption-repair')
        with self.assertRaisesRegex(ValueError,'private configuration'):
            plugin.inspect(str(source),allow_profile_captions=True)

if __name__=='__main__': unittest.main()
