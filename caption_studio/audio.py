"""Private audio review jobs. Selected recognizers run once; originals stay untouched."""
import base64
from contextvars import copy_context
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import threading
import textwrap
import time
import uuid
import wave

from .alignment import compare, normalize_transcript, propose
from .core import Captions, PRIVATE, read_source, format_stamp
from .recognizers import process_env, recognize, substitute

_LOCK=threading.RLock()
_RUNNING={}
_PROCESSES={}
ID=re.compile(r'^[0-9a-f]{32}$')
MAX_MEDIA=8*1024**3

def caption_draft(words, options=None):
    """Group measured words into readable draft cues; never invent word timing."""
    options={} if options is None else options
    defaults={'line_chars':42,'max_lines':2,'max_duration_ms':6000,'max_gap_ms':800}
    bounds={'line_chars':(10,80),'max_lines':(1,3),'max_duration_ms':(1000,15000),'max_gap_ms':(100,5000)}
    if not isinstance(options,dict) or set(options)-set(defaults):raise ValueError('Unknown caption layout option')
    values={**defaults,**options}
    for key,value in values.items():
        if type(value)is not int or not bounds[key][0]<=value<=bounds[key][1]:raise ValueError('Caption layout options are outside their supported bounds')
    def joined(items):
        text=''
        for word in items:
            item=word['text'].strip()
            adjacent=bool(text) and (re.match(r'^[,.;:!?\)\]\}，。！？、]',item) or (re.search(r'[\u3040-\u30ff\u3400-\u9fff]$',text) and re.match(r'^[\u3040-\u30ff\u3400-\u9fff]',item)))
            text+=(''if not text or adjacent else' ')+item
        return text
    def lines(items):return textwrap.wrap(joined(items),width=values['line_chars'],break_long_words=False,break_on_hyphens=False)
    cues=[];group=[]
    def emit():
        if len(cues)>=10000:raise ValueError('Generated captions exceed 10000 cues; choose a shorter recording')
        cues.append({'index':str(len(cues)+1),'start_ms':group[0]['start_ms'],'end_ms':max(w['end_ms']for w in group),'settings':'','text':'\n'.join(lines(group))})
    for word in words:
        if group and (word['start_ms']-group[-1]['end_ms']>values['max_gap_ms'] or word['end_ms']-group[0]['start_ms']>values['max_duration_ms'] or len(lines(group+[word]))>values['max_lines']):emit();group=[]
        group.append(word)
        if re.search(r'[.!?。！？]["\u201d\u2019\']?$',word['text'].strip()):emit();group=[]
    if group:emit()
    return cues

def write_json(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream: json.dump(value,stream,ensure_ascii=False)
    temporary.replace(path)

def identity(info): return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]

class AudioReview:
    def __init__(self,root): self.root=Path(root).resolve();self.captions=Captions(root)
    def job(self,job_id):
        if not isinstance(job_id,str) or not ID.fullmatch(job_id): raise ValueError('Invalid audio review ID')
        folder=self.root/'audio-reviews'/job_id
        if not folder.is_dir() or folder.is_symlink(): raise ValueError('Audio review not found in this profile')
        return folder
    def snapshot(self,source,target,limit,allow_profile=False):
        source=Path(source).expanduser()
        if source.is_symlink() or any(x.casefold() in PRIVATE-{'.hermes'} for x in source.parts): raise ValueError('Private configuration and symlink inputs are blocked')
        source=source.resolve(strict=True)
        profile=self.captions.profile_home
        protected=any(x.casefold()=='.hermes' for x in source.parts) or (profile and source.is_relative_to(profile))
        allowed=source.is_relative_to(self.root) or (allow_profile and profile and source.is_relative_to(self.root.parent))
        if any(x.casefold() in PRIVATE-{'.hermes'} for x in source.parts) or (protected and not allowed): raise ValueError('Selected file is inside private configuration; choose media outside it or opt into profile media')
        digest=hashlib.sha256();count=0
        fd=os.open(source,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
        with os.fdopen(fd,'rb') as src, os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as dst:
            before=os.fstat(src.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>limit: raise ValueError('Choose a bounded regular media/JSON file')
            while True:
                block=src.read(1024*1024)
                if not block: break
                count+=len(block)
                if count>limit: raise ValueError('Input grew beyond its size bound')
                digest.update(block);dst.write(block)
            after=os.fstat(src.fileno())
        if identity(before)!=identity(after) or identity(after)!=identity(source.lstat()): raise ValueError('Selected input changed while reading')
        return {'source':str(source),'identity':identity(after),'sha256':digest.hexdigest(),'bytes':count}
    def run(self,folder,argv,stdout=None,input_bytes=None,timeout=300):
        if (folder/'CANCEL').exists(): raise RuntimeError('Audio review cancelled')
        env=process_env();output=stdout or folder/'process-output.txt'
        with output.open('wb') as stream, output.with_suffix('.stderr.log').open('wb') as diagnostic:
            output.chmod(0o600)
            output.with_suffix('.stderr.log').chmod(0o600)
            process=subprocess.Popen(argv,stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,stdout=stream,stderr=diagnostic,env=env,start_new_session=os.name!='nt')
            with _LOCK: _PROCESSES[str(folder)]=process
            try:
                process.communicate(input_bytes,timeout=timeout)
            except subprocess.TimeoutExpired:
                self.stop_process(process);process.wait(timeout=10);raise RuntimeError('Selected media/speech command timed out; no automatic retry made') from None
            finally:
                with _LOCK: _PROCESSES.pop(str(folder),None)
        if (folder/'CANCEL').exists(): raise RuntimeError('Audio review cancelled')
        if process.returncode: raise RuntimeError('Selected media/speech command failed; private stderr is saved in the review folder for diagnosis. No retry or fallback made.')
    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            try:
                if os.name=='nt': process.terminate()
                else: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    if os.name=='nt': process.kill()
                    else: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=3)
    def analyse(self,source_path,media_path,recognizer,allow_profile_captions=False,allow_profile_media=False,decoder_argv=None,dispatch=None,secret=None):
        return self._start(False,source_path,media_path,recognizer,allow_profile_captions,allow_profile_media,decoder_argv,dispatch,secret)
    def generate(self,media_path,recognizer,allow_profile_media=False,decoder_argv=None,caption_options=None,dispatch=None,secret=None):
        caption_draft([],caption_options)  # Validate before any recognition or upload.
        return self._start(True,None,media_path,recognizer,False,allow_profile_media,decoder_argv,dispatch,secret,caption_options)
    def _start(self,creating,source_path,media_path,recognizer,allow_profile_captions=False,allow_profile_media=False,decoder_argv=None,dispatch=None,secret=None,caption_options=None):
        if not isinstance(recognizer,dict) or recognizer.get('kind') not in {'command','import','http','host'}: raise ValueError('Choose a recognizer/runtime or import a timed transcript first')
        if recognizer['kind']=='host' and dispatch is None: raise ValueError('Use the agent tool path for a host-backed recognizer')
        if recognizer['kind']=='http':
            from urllib.parse import urlsplit
            url=urlsplit(recognizer.get('endpoint',''))
            if url.hostname not in ('localhost','127.0.0.1','::1') and recognizer.get('allow_upload') is not True: raise ValueError('Confirm the selected remote audio upload before analysis')
        fingerprint,cues=(None,[]) if creating else read_source(source_path,self.root.parent if allow_profile_captions else self.root,self.captions.profile_home)
        key=str(self.root)
        with _LOCK:
            if key in _RUNNING: raise ValueError('An audio review is already running in this profile')
            self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
            lock_fd=os.open(self.root/'audio-review.lock',os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
            try:
                if os.name=='nt':
                    import msvcrt
                    os.write(lock_fd,b'1');os.lseek(lock_fd,0,0);msvcrt.locking(lock_fd,msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                job_id=uuid.uuid4().hex;folder=self.root/'audio-reviews'/job_id;folder.mkdir(parents=True,mode=0o700);_RUNNING[key]=job_id
            except OSError:
                os.close(lock_fd);raise ValueError('An audio review is already running in this profile, or its private lock is unavailable') from None
        try:
            state={'job_id':job_id,'mode':'create'if creating else'repair','state':'preparing','phase':'Copying selected media','source_path':None if creating else str(Path(source_path).resolve()),'source_fingerprint':fingerprint,'total_cues':len(cues),'recognizer_kind':recognizer['kind'],'model':str(recognizer.get('model','')),'created':time.time()}
            write_json(folder/'state.json',state);write_json(folder/'source-cues.json',cues)
            media=self.snapshot(media_path,folder/('source'+Path(media_path).suffix.lower()),MAX_MEDIA,allow_profile_media)
            state['media']=media;write_json(folder/'state.json',state)
            if recognizer['kind']=='import': self.snapshot(recognizer.get('transcript_path',''),folder/'imported-transcript.json',24*1024*1024,allow_profile_media)
            def work():
                try:
                    state.update(state='running',phase='Preparing audio');write_json(folder/'state.json',state)
                    audio=folder/'audio.wav';values={'media':str(folder/('source'+Path(media_path).suffix.lower())),'audio':str(audio)}
                    compatible=False
                    if not decoder_argv:
                        try:
                            with wave.open(values['media']) as source_wav: compatible=source_wav.getnchannels()==1 and source_wav.getframerate()==16000 and source_wav.getsampwidth()==2 and source_wav.getcomptype()=='NONE'
                        except (wave.Error,EOFError): pass
                    if compatible: shutil.copyfile(values['media'],audio)
                    else:
                        if not decoder_argv and not shutil.which('ffmpeg'): raise ValueError('This media needs decoding. Select an installed decoder with decoder_argv, install FFmpeg explicitly, or supply mono 16 kHz PCM WAV.')
                        command=decoder_argv or [shutil.which('ffmpeg'),'-v','error','-nostdin','-n','-protocol_whitelist','file,pipe','-i','{media}','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','{audio}']
                        if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command): raise ValueError('Decoder must be an argument array with {media} and {audio} placeholders')
                        self.run(folder,substitute(command,values),timeout=600)
                    audio.chmod(0o600)
                    with wave.open(str(audio)) as wav:
                        if wav.getnchannels()!=1 or wav.getframerate()!=16000 or wav.getsampwidth()!=2: raise ValueError('Decoder must produce mono 16 kHz 16-bit PCM WAV')
                        duration_ms=round(wav.getnframes()/wav.getframerate()*1000)
                    if not 100<=duration_ms<=7200*1000: raise ValueError('Audio review supports 0.1 seconds to two hours per job')
                    state.update(phase='Recognizing audio',duration_ms=duration_ms,local_audio_bytes=audio.stat().st_size);write_json(folder/'state.json',state)
                    raw=recognize(recognizer,audio,folder,lambda argv,**kw:self.run(folder,argv,**kw),dispatch,secret)
                    if (folder/'CANCEL').exists(): raise RuntimeError('Audio review cancelled')
                    words=normalize_transcript(raw,duration_ms);work_cues=cues
                    if creating:
                        work_cues=caption_draft(words,caption_options);draft=folder/'generated-draft.srt'
                        with os.fdopen(os.open(draft,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8')as stream:stream.write('\n\n'.join(f"{c['index']}\n{format_stamp(c['start_ms'])} --> {format_stamp(c['end_ms'])}\n{c['text']}"for c in work_cues)+('\n'if work_cues else''))
                        state.update(source_path=str(draft),source_fingerprint=hashlib.sha256(draft.read_bytes()).hexdigest(),total_cues=len(work_cues),draft=True)
                        write_json(folder/'source-cues.json',work_cues)
                    state['phase']='Preparing caption review'if creating else'Comparing words and timing';write_json(folder/'state.json',state)
                    report=[] if creating and not work_cues else compare(work_cues,words)
                    if creating:
                        for cue in report:cue['flags'].append('generated_caption_needs_review')
                    write_json(folder/'report.json',report);write_json(folder/'words.json',words)
                    state.update(state='ready',phase='Generated captions ready for review'if creating else'Ready for review',flagged_cues=sum(bool(r['flags']) for r in report),text_disagreements=sum(r['text_disagreement'] for r in report),timing_suggestions=sum(r['timing_available'] for r in report),recognizer_notice='New captions are an unreviewed recognizer draft; comparing the recognizer with itself cannot detect its own errors. Listen or explicitly choose an independent second recognizer. No speech means no invented captions.'if creating else'Selected recognizer output is evidence for review, not ground truth. No source text was supplied as a transcription prompt.')
                except Exception as exc:
                    state.update(state='cancelled' if (folder/'CANCEL').exists() else 'failed',phase='Stopped',error=str(exc)[:400] if isinstance(exc,(ValueError,RuntimeError)) else 'Audio review failed; check the selected decoder/runtime and word-timestamp format',retry_automatically=False)
                finally:
                    write_json(folder/'state.json',state)
                    with _LOCK: _RUNNING.pop(key,None)
                    os.close(lock_fd)
            thread=threading.Thread(target=copy_context().run,args=(work,),daemon=True);thread.start()
            return {'job_id':job_id,'state':'preparing','mode':state['mode'],'notice':'Caption generation started with the selected backend; no source SRT required. Review the draft before use.'if creating else'Background audio review started with the selected backend. Originals are preserved.'}
        except Exception:
            with _LOCK: _RUNNING.pop(key,None)
            os.close(lock_fd)
            raise
    def status(self,job_id):
        folder=self.job(job_id);state=json.loads((folder/'state.json').read_text());state.pop('media',None);state.pop('source_path',None)
        if (folder/'CANCEL').exists() and state['state'] in ('running','preparing'):state['phase']='Cancellation requested; waiting for the selected backend to stop'
        return state
    def review(self,job_id,offset=0,limit=20,flagged_only=False):
        folder=self.job(job_id);state=self.status(job_id)
        if state['state']!='ready': raise ValueError('Audio review is not ready')
        if type(offset)is not int or offset<0 or type(limit)is not int or not 1<=limit<=100: raise ValueError('Invalid review page')
        rows=json.loads((folder/'report.json').read_text())
        if flagged_only: rows=[r for r in rows if r['flags']]
        return {'job_id':job_id,'total':len(rows),'offset':offset,'cues':rows[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(rows) else None,'notice':'Review the audio before accepting word changes. Unselected cues remain original.'}
    def propose(self,job_id):
        folder=self.job(job_id);state=self.status(job_id)
        if state['state']!='ready': raise ValueError('Audio review is not ready')
        if state.get('mode')!='repair': raise ValueError('Proposals compare existing captions with the audio; a generated draft has nothing to compare')
        rows=json.loads((folder/'report.json').read_text())
        if rows and 'edits' not in rows[0]: raise ValueError('This review predates proposals; start a new audio review')
        return propose(rows)
    def cancel(self,job_id):
        folder=self.job(job_id);(folder/'CANCEL').touch(mode=0o600)
        with _LOCK: process=_PROCESSES.get(str(folder))
        if process: self.stop_process(process)
        return {'job_id':job_id,'state':'cancellation_requested','notice':'Owned local commands stop; a host/network request already sent may finish, but its result will not be applied.'}
    def preview(self,job_id,cue_id,timing='suggested',include_data=False):
        folder=self.job(job_id);rows=json.loads((folder/'report.json').read_text())
        if type(cue_id)is not int or not 1<=cue_id<=len(rows) or timing not in {'suggested','original'}: raise ValueError('Choose a review cue and timing')
        cue=rows[cue_id-1];start=cue['suggested_start_ms'] if timing=='suggested' else cue['original']['start_ms'];end=cue['suggested_end_ms'] if timing=='suggested' else cue['original']['end_ms']
        if start is None or end is None: raise ValueError('No reliable suggested timing; preview original timing or edit this cue manually')
        duration_ms=json.loads((folder/'state.json').read_text())['duration_ms']
        if start>=duration_ms: raise ValueError('This cue starts outside the media; review its timing manually')
        start=max(0,start-700);duration=min(20000,end-start+700)
        out=folder/f'preview-{cue_id}-{timing}.wav'
        if not out.exists():
            temporary=out.with_name(uuid.uuid4().hex+'.wav')
            with wave.open(str(folder/'audio.wav')) as src, wave.open(str(temporary),'wb') as dst:
                dst.setparams(src.getparams());src.setpos(round(start*16));dst.writeframes(src.readframes(round(duration*16)))
            temporary.chmod(0o600);temporary.replace(out)
        result={'path':str(out),'mime_type':'audio/wav','start_ms':start,'seconds':duration/1000}
        if include_data: result['audio_url']='data:audio/wav;base64,'+base64.b64encode(out.read_bytes()).decode()
        return result
    def export(self,job_id,decisions=None,apply_proposed=False):
        folder=self.job(job_id);state=json.loads((folder/'state.json').read_text())
        if state['state']!='ready' or (folder/'CANCEL').exists(): raise ValueError('Choose a completed, uncancelled review')
        plan=None
        if apply_proposed is not False and apply_proposed is not True: raise ValueError('apply_proposed must be a boolean')
        if apply_proposed:
            plan=self.propose(job_id);explicit={c.get('cue_id') for c in decisions or [] if isinstance(c,dict)}
            applied=[c for c in plan['cues'] if c['status']=='clear' and c['cue_id'] not in explicit]
            decisions=list(decisions or [])+[c['decision'] for c in applied]
        elif decisions is None: raise ValueError('Provide reviewed decisions, or set apply_proposed to apply the clear proposals')
        if state.get('mode')=='create'and state['total_cues']==0:
            actual=hashlib.sha256(Path(state['source_path']).read_bytes()).hexdigest();cues=[]
        else:actual,cues=read_source(state['source_path'],self.root.parent,self.captions.profile_home)
        if actual!=state['source_fingerprint']: raise ValueError('Source captions changed; start a new audio review')
        if identity(Path(state['media']['source']).stat())!=state['media']['identity']: raise ValueError('Source media changed; start a new audio review')
        rows=json.loads((folder/'report.json').read_text())
        if not isinstance(decisions,list) or not (0 if state.get('mode')=='create'or apply_proposed else 1)<=len(decisions)<=len(cues): raise ValueError('Explicitly select reviewed changes, or export a generated draft without claiming review')
        seen=set();dropped=set()
        for choice in decisions:
            if not isinstance(choice,dict) or set(choice)-{'cue_id','use_timing','use_text','text','start_ms','end_ms','drop'}: raise ValueError('Invalid reviewed change')
            i=choice.get('cue_id')
            if type(i)is not int or not 1<=i<=len(cues) or i in seen: raise ValueError('Cue choices must be unique and valid')
            seen.add(i);cue=cues[i-1];proposal=rows[i-1]
            for flag in ['use_timing','use_text','drop']:
                if flag in choice and type(choice[flag])is not bool: raise ValueError('Reviewed choices must use boolean flags')
            if choice.get('drop'):
                dropped.add(i);continue
            if choice.get('use_timing'):
                if not proposal['timing_available']: raise ValueError('This cue needs manual timing; no reliable audio alignment was found')
                cue['start_ms'],cue['end_ms']=proposal['suggested_start_ms'],proposal['suggested_end_ms']
            for key in ['start_ms','end_ms']:
                if key in choice: cue[key]=choice[key]
            if choice.get('use_text'): cue['text']=proposal['suggested_text']
            if 'text' in choice: cue['text']=choice['text']
            if any(type(cue[k])is not int for k in ['start_ms','end_ms']) or not 0<=cue['start_ms']<cue['end_ms']<=state['duration_ms']: raise ValueError('Reviewed times must be valid milliseconds within the media')
            if not isinstance(cue['text'],str) or not cue['text'].strip() or len(cue['text'])>8000 or re.search(r'\n\s*\n|[\x00-\x08\x0b\x0c\x0e-\x1f]',cue['text']): raise ValueError('Reviewed text is empty, too long or contains an SRT block separator/control')
        cues=[c for i,c in enumerate(cues,1) if i not in dropped]
        out=self.root/('audio-reviewed-'+uuid.uuid4().hex+'.srt')
        with os.fdopen(os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as stream:
            stream.write('\n\n'.join(f"{c['index']}\n{format_stamp(c['start_ms'])} --> {format_stamp(c['end_ms'])}{c.get('settings','')}\n{c['text']}" for c in cues)+'\n')
        draft=state.get('mode')=='create'and (not cues or len(seen)<state['total_cues'])
        result={'output_path':str(out),'cues':len(cues),'reviewed_cues':len(seen)-(len(applied) if plan else 0),'removed_cues':len(dropped),'originals_preserved':True,'job_id':job_id,'draft':draft,'notice':'Generated caption draft; unreviewed words and timing still need checking.'if draft else'Explicit reviewed decisions exported separately.'}
        if plan:
            human=[c for c in plan['cues'] if c['status']=='ambiguous' or c.get('also_ambiguous')]
            result.update(applied_proposed=len(applied),changed=[{k:c[k] for k in ('cue_id','changes','original_text','new_text','evidence') if k in c} for c in applied],
                left_unchanged=plan['unchanged'],needs_human=[{k:c[k] for k in ('cue_id','original_text','heard_text','reasons','also_ambiguous','explanation') if k in c} for c in human],basis='alignment-backed',listened_to=False,
                notice=f"Applied {len(applied)} clear correction(s) to a separate file; {plan['unchanged']} cue(s) left exactly as they were and {len(human)} cue(s) need a human. These changes rest on speech-recognition alignment only; nobody listened to them. The original SRT was not modified.")
        return result
