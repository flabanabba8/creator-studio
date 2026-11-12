import sys as _s,types as _t,pathlib as _p
_cs=_t.ModuleType('cs_t');_cs.__path__=[str(_p.Path(__file__).resolve().parents[2])];_s.modules.setdefault('cs_t',_cs)
import importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('cs_t.pod_own_fixture',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from cs_t.pod_own_fixture import episode

def write(folder):
    folder.mkdir(parents=True)
    (folder/'01-intro.txt').write_text('# title: Intro\n# source: Supplied note\n\nANA: Hello there.\nBEN: Hi.\n')

class OwnEpisodeFolder(unittest.TestCase):
    def tearDown(self): episode.OWN_ROOT=None
    def test_an_episode_inside_the_plugins_own_data_folder_under_a_private_looking_home_is_readable(self):
        """Found through Hermes: the plugin's own data folder sits under .hermes, so its lint and preflight refused the episode it had just written."""
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            own=Path(tmp)/'.hermes'/'profiles'/'p'/'plugin-data'/'creator-studio-podcast'
            mine=own/'projects'/'x'/'episode-1';write(mine)
            with self.assertRaises(ValueError): episode.episode_files(str(mine))             # not the plugin's own folder: refused
            episode.OWN_ROOT=own
            self.assertEqual(len(episode.episode_files(str(mine))[1]),1)                    # its own folder: allowed
    def test_a_private_folder_inside_the_own_data_folder_or_a_sibling_stays_refused(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            own=Path(tmp)/'.hermes'/'plugin-data'/'creator-studio-podcast';own.mkdir(parents=True)
            sibling=Path(tmp)/'.hermes'/'other'/'ep';write(sibling)
            inner=own/'.ssh'/'ep';write(inner)
            episode.OWN_ROOT=own
            for bad in (sibling,inner):
                with self.assertRaises(ValueError): episode.episode_files(str(bad))

if __name__=='__main__': unittest.main()
