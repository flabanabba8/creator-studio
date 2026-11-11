"""User-selected speech interfaces; no fixed model, runtime, paid service or fallback."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import uuid

MAX_RESPONSE = 24 * 1024 * 1024

def process_env():
    keep=('PATH','HOME','LANG','LC_ALL','SYSTEMROOT','WINDIR','TMPDIR','TEMP','TMP','HF_HOME','HF_HUB_CACHE','XDG_CACHE_HOME','CUDA_VISIBLE_DEVICES')
    return {**{k:os.environ[k] for k in keep if k in os.environ}, 'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'}

SPEECH_NAMES=re.compile(r'whisper|wav2vec|parakeet|canary|hubert|w2v|conformer|asr|speech',re.I)
SKIP_DIRS={'node_modules','.git','.hermes','.cache','site-packages','__pycache__','.npm','.cargo','.rustup','snap','proc'}

def cached_speech_models(limit=20):
    """Read-only scan of standard Hugging Face cache folders for speech models. Loads nothing."""
    home=Path.home();roots=[]
    for value in (os.environ.get('HF_HUB_CACHE'),os.environ.get('HF_HOME') and os.environ['HF_HOME']+'/hub',os.environ.get('XDG_CACHE_HOME') and os.environ['XDG_CACHE_HOME']+'/huggingface/hub',str(home/'.cache/huggingface/hub')):
        if value and Path(value) not in roots: roots.append(Path(value))
    found=[]
    for root in roots:
        try: entries=sorted(root.glob('models--*'))
        except OSError: continue
        for entry in entries:
            model_id=entry.name.removeprefix('models--').replace('--','/',1)
            if not SPEECH_NAMES.search(model_id): continue
            try: complete=any((snap/'config.json').is_file() for snap in (entry/'snapshots').iterdir())
            except OSError: complete=False
            if complete: found.append({'model':model_id,'cache':str(root),'transformers_whisper_adapter':'whisper' in model_id.lower()})
            if len(found)>=limit: return found
    return found

def python_runtimes(limit=12):
    """Bounded read-only search of PATH pythons and virtual environments under the home folder for speech modules."""
    candidates=[]
    def add(path):
        if os.access(path,os.X_OK) and str(path) not in [c[0] for c in candidates]: candidates.append((str(path),str(path)))
    for folder in os.environ.get('PATH','').split(os.pathsep):
        for name in ('python3','python'):
            if folder and (Path(folder)/name).is_file(): add(Path(folder)/name)
    home=Path.home();visited=0;started=time.monotonic()
    for base,dirs,files in os.walk(home):
        visited+=1
        depth=len(Path(base).relative_to(home).parts)
        dirs[:]=[d for d in dirs if d not in SKIP_DIRS and depth<4]
        if 'pyvenv.cfg' in files:
            dirs[:]=[]
            if (Path(base)/'bin/python').exists(): add(Path(base)/'bin/python')
        if visited>60000 or len(candidates)>=limit*3 or time.monotonic()-started>6: break
    runtimes=[]
    for shown,real in candidates:
        if len(runtimes)>=limit: break
        try:
            r=subprocess.run([shown,'-I','-c','import importlib.util as u,json;print(json.dumps({n:u.find_spec(n) is not None for n in ("torch","transformers","faster_whisper")}))'],capture_output=True,text=True,timeout=8,env=process_env())
            modules=json.loads(r.stdout) if r.returncode==0 else None
        except (OSError,ValueError,subprocess.TimeoutExpired): modules=None
        if modules and any(modules.values()): runtimes.append({'python':shown,'modules':modules,'runs_transformers_adapter':bool(modules.get('torch') and modules.get('transformers'))})
    return runtimes

def choose_device(versions,gpus,need_mib=5000):
    """cuda when a CUDA torch build and a GPU with enough free memory exist, else cpu (a large model on CPU can use 6+ GiB of RAM)."""
    if '+cpu' in versions.get('torch',''):return 'cpu'
    return 'cuda' if any(g.get('free_mib',0)>=need_mib for g in gpus) else 'cpu'

def local_speech_resources(gpus=()):
    models=cached_speech_models();runtimes=python_runtimes()
    adapter=Path(__file__).parent/'examples/transformers_asr.py'
    for runtime in [r for r in runtimes if r['runs_transformers_adapter']][:6]:
        try:
            r=subprocess.run([runtime['python'],'-I',str(adapter),'--probe'],capture_output=True,text=True,timeout=40,env=process_env())
            if r.returncode==0: runtime['versions']=json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError,ValueError,IndexError,subprocess.TimeoutExpired): pass
    usable=[r for r in runtimes if r.get('versions')]
    usable.sort(key=lambda r:'+cpu' in r['versions'].get('torch',''))
    ready=[]
    for model in models:
        if not model['transformers_whisper_adapter']: continue
        for runtime in usable[:3]:
            ready.append({'recognizer':{'kind':'command','argv':[runtime['python'],str(adapter)],'model':model['model'],'language':'en','output':'stdout','options':{'device':choose_device(runtime['versions'],gpus)}},'versions':runtime['versions'],'note':'Cached model plus a Python that imports torch and transformers; word timestamps via the bundled adapter. Offline only; nothing is run until you start a recognition. The first entry is the preferred environment (a CPU-only torch build is listed last). The device is cuda only when a CUDA torch build and a GPU with enough free memory were seen, otherwise cpu (a large model on CPU can need 6+ GiB of RAM). Run one recognition at a time.'})
    return {'cached_speech_models':models,'python_runtimes_with_speech_modules':runtimes,'ready_local_commands':ready,'scan_notice':'Read-only, bounded scan of standard Hugging Face cache folders, PATH pythons and virtual environments up to four folders deep under the home folder. Only module presence and library versions are checked; no model is loaded or downloaded.'}

def options(languages=None, subscriptions=None, offline=True):
    languages=languages or ['en'];subscriptions=subscriptions or []
    if not isinstance(languages,list) or not all(isinstance(x,str) and len(x)<40 for x in languages): raise ValueError('Provide a language list')
    if not isinstance(subscriptions,list) or not all(isinstance(x,str) and len(x)<80 for x in subscriptions): raise ValueError('Provide API-access/subscription labels; no secrets')
    tools={n:shutil.which(n) for n in ['ffmpeg','ffprobe','whisper-cli','whisper','faster-whisper','sherpa-onnx-offline']}
    ram=None
    try: ram=round(os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')/1024**3,1)
    except (ValueError,OSError,AttributeError): pass
    gpu=[]
    if shutil.which('nvidia-smi'):
        try:
            r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,env=process_env())
            if r.returncode==0: gpu=[{'name':f[0],'memory_mib':int(f[1]),'free_mib':int(f[2])} for f in ([x.strip() for x in s.rsplit(',',2)] for s in r.stdout.splitlines() if s.count(',')>=2)]
        except (OSError,ValueError,subprocess.TimeoutExpired): pass
    choices=[{'id':'import','cost':'No service fee','description':'Import word-timestamp JSON from a recognizer you already use; no inference or upload here.','requirements':['Word timestamps, not plain text or segment-only captions']}]
    local_modules={}
    for name in ['faster_whisper','transformers','torch']:
        try: local_modules[name]=importlib.util.find_spec(name) is not None
        except (ImportError,ValueError): local_modules[name]=False
    suggestions=[]
    if any(tools[n] for n in tools if n not in ['ffmpeg','ffprobe']) or any(local_modules.values()): suggestions.append('Reuse a compatible installed CLI/module before creating another runtime.')
    if gpu:
        suggestions.append('A detected GPU makes GPU-capable local recognition practical; compare memory needs and language support before choosing model size. Consider a non-Whisper recognizer for a second opinion on Whisper captions.')
    else:suggestions.append('Without a confirmed compatible accelerator, consider a CPU-friendly runtime such as whisper.cpp and a model sized for available RAM. Other GPUs/Apple accelerators are not ruled out by this NVIDIA-only probe; ask about the intended runtime and test a short sample.')
    choices.append({'id':'command','cost':'No service fee for genuinely local recognition; trusted external commands are not network-sandboxed','description':'Choose any trusted speech CLI/runtime that produces timed JSON.','suggestions':suggestions,'requirements':['Explicit executable/arguments and model choice','Model files/runtime installed separately; no automatic download']})
    choices.append({'id':'http','cost':'Local server compute, or selected provider pricing','description':'User-configured compatible speech endpoint; model/form fields are configurable.','requirements':['Word-timestamp JSON','Explicit consent before remote audio upload','API access verified separately from a chat/app subscription'],'recommended':not offline and bool(subscriptions)})
    choices.append({'id':'host','cost':'Depends on the selected host speech tool','description':'Use an existing registered Hermes speech tool that returns timed JSON; host owns model/provider routing.','requirements':['Agent context with that tool available','Word timestamps in its result']})
    access_notes=[]
    reported=' '.join(subscriptions).casefold()
    if 'openai' in reported or 'chatgpt' in reported: access_notes.append('Some eligible Pro/Business subscriptions include claimable API credits. Verify the linked API organization, active grant, transcription model/timestamp support and expiry; do not reuse chat cookies or assume unlimited API access.')
    if 'claude' in reported or 'anthropic' in reported: access_notes.append('Some Claude plans include Claude API credits; that is not evidence of a first-party transcription endpoint or credits at a separate speech provider. The active harness can help review text within its actual modalities.')
    return {'hardware':{'scope':'Hermes host; the chosen remote/runtime may differ','os':platform.system(),'architecture':platform.machine(),'cpu_threads':os.cpu_count(),'ram_gib':ram,'gpus':gpu,'gpu_probe_notice':'NVIDIA probe only; absence is not proof of no GPU/Apple accelerator.'},'installed_tools':tools,'local_speech_resources':local_speech_resources(gpu),'current_runtime_modules':local_modules,'languages':languages,'user_reported_access':subscriptions,'prefer_offline':bool(offline),'recommended_kind':'command' if offline or not subscriptions else 'http','access_notes':access_notes,'choices':choices,'questions':['Which languages and audio quality?','Keep audio offline, or allow upload to a selected service?','What runtimes/models or API allowances do you already have?'],'notice':'No model loaded, installed or downloaded. No account/credential stores inspected. Recommendations are options, not claims of backend availability or recognition accuracy.'}

def substitute(value, values):
    if isinstance(value,str):
        for key,item in values.items(): value=value.replace('{'+key+'}',item)
        return value
    if isinstance(value,list): return [substitute(x,values) for x in value]
    if isinstance(value,dict): return {k:substitute(v,values) for k,v in value.items()}
    return value

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def recognize(config, audio, folder, run, dispatch=None, secret=None):
    if not isinstance(config,dict): raise ValueError('Choose a recognizer first')
    kind=config.get('kind');values={'audio':str(audio),'output':str(folder/'recognizer-output.json'),'output_base':str(folder/'recognizer-output'),'model':str(config.get('model','')),'language':str(config.get('language',''))}
    if kind=='command':
        argv=substitute(config.get('argv'),values)
        if not isinstance(argv,list) or not argv or len(argv)>80 or not all(isinstance(x,str) and 0<len(x)<=4000 for x in argv): raise ValueError('Local recognizer needs an argument array, not a shell command')
        executable=Path(argv[0]).name.lower().removesuffix('.exe')
        if executable in {'codex','claude','gemini','hermes'}: raise ValueError('Choose a speech recognizer, not a new reasoning-agent session')
        request=json.dumps({'audio_path':str(audio),'model':config.get('model',''),'language':config.get('language',''),'options':config.get('options',{}),'output_path':values['output']}).encode()
        stdout=folder/'recognizer-stdout.json'
        run(argv, stdout=stdout, input_bytes=request, timeout=3600)
        output=Path(values['output']) if config.get('output','stdout')=='file' else stdout
        if not output.is_file() or output.stat().st_size>MAX_RESPONSE: raise ValueError('Recognizer returned no bounded JSON result')
        return json.loads(output.read_text())
    if kind=='import':
        return json.loads((folder/'imported-transcript.json').read_text())
    if kind=='host':
        if dispatch is None: raise ValueError('A host speech tool needs an active agent context; use the agent tool path')
        name=config.get('tool');args=substitute(config.get('arguments',{}),values)
        if not isinstance(name,str) or not name or not isinstance(args,dict): raise ValueError('Select a registered host speech tool and arguments')
        result=dispatch(name,args)
        return json.loads(result) if isinstance(result,str) else result
    if kind!='http': raise ValueError('Choose local command, imported JSON, compatible HTTP speech service or a host speech tool')
    endpoint=config.get('endpoint','');url=urlsplit(endpoint)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment: raise ValueError('Use a plain speech endpoint URL without credentials or query parameters')
    local=url.hostname in ('localhost','127.0.0.1','::1')
    if not local and (url.scheme!='https' or config.get('allow_upload') is not True): raise ValueError('Remote recognition needs HTTPS and explicit audio-upload consent')
    if audio.stat().st_size>64*1024*1024: raise ValueError('HTTP audio exceeds 64 MiB; use a local recognizer or analyse a shorter range')
    fields=config.get('fields',{})
    if not isinstance(fields,dict) or len(fields)>30 or not all(isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_\[\]-]{1,80}',k) and isinstance(v,(str,int,float,bool)) for k,v in fields.items()): raise ValueError('Invalid recognizer form fields')
    boundary='caption-'+uuid.uuid4().hex;chunks=[]
    for key,value in fields.items():chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),audio.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()])
    headers={'Content-Type':'multipart/form-data; boundary='+boundary}
    if secret:
        header=config.get('auth_header','Authorization')
        if not isinstance(header,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,79}',header) or header.casefold() in {'host','content-type','content-length','connection','transfer-encoding','cookie','set-cookie','proxy-authorization'}: raise ValueError('Choose a valid dedicated credential header')
        prefix=config.get('auth_prefix','Bearer ' if header.casefold()=='authorization' else '')
        if not isinstance(prefix,str) or len(prefix)>40 or '\r' in prefix or '\n' in prefix: raise ValueError('Invalid credential prefix')
        headers[header]=prefix+secret
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(Request(endpoint,data=b''.join(chunks),headers=headers),timeout=600) as response:
            data=response.read(MAX_RESPONSE+1)
    except Exception as exc:
        code=getattr(exc,'code',None)
        raise RuntimeError(f'Speech service request failed'+(f' (HTTP {code})' if code else '')+'; outcome may be uncertain and no retry was made') from None
    if len(data)>MAX_RESPONSE: raise ValueError('Speech response exceeds 24 MiB')
    return json.loads(data)
