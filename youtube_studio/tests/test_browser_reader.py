import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
READER=Path(__file__).parents[2]/'common'/'browser_research.py'
sys.path.insert(0,str(READER.parent))
import browser_research as br

class BrowserReaderOfflineTests(unittest.TestCase):
    def run_reader(self,request):
        done=subprocess.run([sys.executable,str(READER)],input=json.dumps(request).encode(),capture_output=True,timeout=30)
        return json.loads(done.stdout.decode().strip().splitlines()[-1])
    def test_private_and_credentialed_urls_are_refused_without_a_browser(self):
        for url in ('http://127.0.0.1/','http://localhost/x','https://user:pw@example.com/','https://example.com:8443/'):
            out=self.run_reader({'url':url,'browser_executable':'/nonexistent'})
            self.assertEqual(out['error'],'ValueError',url);self.assertFalse(out['fallback_attempted'])
    def test_missing_browser_is_an_error_not_a_fake_result(self):
        out=self.run_reader({'url':'https://example.com/','browser_executable':'/nonexistent/camoufox-bin'})
        self.assertIn('error',out);self.assertNotIn('text',out)
    @unittest.skipUnless(shutil.which('node'),'node not installed')
    def test_driver_guard_ignores_only_the_page_error_location_bug(self):
        with tempfile.TemporaryDirectory()as d:
            g=Path(d)/'g.js';g.write_text(br.GUARD)
            ok=subprocess.run(['node','--require',str(g),'-e',"setTimeout(()=>{console.log('alive')},50);setTimeout(()=>{(function(){undefined.url})()},10)"],capture_output=True,timeout=20)
            self.assertEqual(ok.returncode,0);self.assertIn(b'alive',ok.stdout)
            bad=subprocess.run(['node','--require',str(g),'-e',"setTimeout(()=>{throw new Error('other crash')},10)"],capture_output=True,timeout=20)
            self.assertNotEqual(bad.returncode,0)
if __name__=='__main__':unittest.main()
