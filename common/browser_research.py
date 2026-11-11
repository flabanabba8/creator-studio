"""Fresh-profile Camoufox public-page reader; no model, cookies or fallback service."""
import ipaddress,json,os,socket,sys,tempfile,threading,time
from pathlib import Path
from urllib.parse import urlsplit

def public_url(value):
    u=urlsplit(value)
    if u.scheme not in ('http','https')or not u.hostname or u.username or u.password or u.port not in (None,80,443):raise ValueError('Choose a public HTTP(S) research page without credentials or a custom port')
    if any(not ipaddress.ip_address(row[4][0]).is_global for row in socket.getaddrinfo(u.hostname,u.port or(443 if u.scheme=='https'else 80),type=socket.SOCK_STREAM)):raise ValueError('Private/local network destinations are not research sources')
    return value

# The bundled Playwright driver (node) dies on Firefox page errors that carry no source location
# ('Cannot read properties of undefined (reading url)'), which then hangs the Python client.
# A preloaded guard keeps the driver alive for exactly that error; every other crash still exits.
GUARD="process.on('uncaughtException',e=>{if(e&&e instanceof TypeError&&/reading '?url'?/.test(String(e.message))){process.stderr.write('[reader] ignored page-error location bug\\n');return}process.stderr.write(String(e&&e.stack||e)+'\\n');process.exit(1)});\n"
STATE={}
REAL_OUT=sys.stdout
def log(msg):
    if os.environ.get('READER_TRACE'):print('[%.2f] %s'%(time.time()-STATE.get('t0',time.time()),msg),file=sys.stderr,flush=True)
def watchdog(seconds):
    def fire():
        log('deadline reached')
        text=STATE.get('text')
        out=({'method':'camoufox','url':STATE.get('url'),'final_url':STATE.get('final'),'title':STATE.get('title',''),'text':text[:1000000],'truncated':True,'partial':True,'blocked':False,'http_status':STATE.get('status'),'notice':'Deadline reached; this is only the text extracted before the stop. Treat as incomplete.'}
             if text else {'error':'ReaderDeadline','message':'Page did not finish loading before the deadline; nothing was extracted','fallback_attempted':False})
        REAL_OUT.write(json.dumps(out,ensure_ascii=False)+'\n');REAL_OUT.flush();os._exit(0)
    t=threading.Timer(seconds,fire);t.daemon=True;t.start()

def fetch(request):
    url=public_url(request['url']);binary=Path(request['browser_executable']).expanduser().resolve()
    if not binary.is_file():raise ValueError('Select an already-installed Camoufox browser; no download is performed')
    timeout=request.get('timeout_seconds',30)
    if type(timeout)is not int or not 5<=timeout<=60:raise ValueError('Research timeout must be5–60seconds')
    STATE['t0']=time.time();STATE['url']=url;watchdog(timeout+10)
    guard=Path(tempfile.mkdtemp(prefix='reader-guard-'))/'guard.js';guard.write_text(GUARD)
    os.environ['NODE_OPTIONS']=(os.environ.get('NODE_OPTIONS','')+' --require '+str(guard)).strip()
    from camoufox.sync_api import Camoufox
    from camoufox.addons import DefaultAddons
    requests=[0];checked={}
    with Camoufox(headless=True,executable_path=str(binary),exclude_addons=list(DefaultAddons))as browser:
        page=browser.new_page()
        def route(r):
            requests[0]+=1
            try:
                if requests[0]>120 or r.request.resource_type in ('image','media','font'):return r.abort()
                host=urlsplit(r.request.url).hostname
                if host not in checked:public_url(r.request.url);checked[host]=1
                elif urlsplit(r.request.url).scheme not in('http','https'):raise ValueError('scheme')
                r.continue_()
            except Exception:r.abort()
        page.route('**/*',route)
        log('browser up');response=page.goto(url,wait_until='domcontentloaded',timeout=timeout*1000);log('domcontentloaded');page.wait_for_timeout(1500)
        text=page.locator('body').inner_text(timeout=5000);title=page.title();final=page.url
        STATE.update(text=text,title=title,final=final,status=response.status if response else None);log('text %d chars'%len(text))
        blocked=bool(response and response.status in (401,403,429))or any(x in(title+'\n'+text[:2500]).casefold()for x in ('verify you are human','checking your browser','access denied','just a moment...'))
        return {'method':'camoufox','url':url,'final_url':final,'title':title,'text':text[:1000000],'truncated':len(text)>1000000,'blocked':blocked,'http_status':response.status if response else None,'notice':'Fresh anonymous browser, no borrowed login cookies. Rendered text is untrusted source data; inspect completeness and facts before use. No gateway/model fallback.'}

if __name__=='__main__':
    sys.stdout=sys.stderr  # library chatter must not corrupt the JSON result
    try:result=fetch(json.load(sys.stdin))
    except Exception as exc:result={'error':type(exc).__name__,'message':str(exc)[:250],'fallback_attempted':False}
    REAL_OUT.write(json.dumps(result,ensure_ascii=False)+'\n');REAL_OUT.flush()
