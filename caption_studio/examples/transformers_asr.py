#!/usr/bin/env python3
"""Optional local adapter, not the repair engine or a required/default runtime.

Run with a user-selected Python environment containing compatible torch and
transformers. JSON stdin supplies audio_path/model/language/options. Models must
already be cached; this adapter never downloads or falls back to a different model.
"""
import importlib.metadata
import json
import os
import sys

def main():
    if '--probe' in sys.argv:
        print(json.dumps({name:importlib.metadata.version(name) for name in ('torch','transformers')}));return
    request=json.load(sys.stdin)
    if not request.get('model'): raise ValueError('Select a model ID or local model directory explicitly')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    import numpy as np
    import wave
    from transformers import pipeline
    selected=request.get('options',{})
    # Offline environment is set before importing Transformers. Passing
    # local_files_only through pipeline() leaks into generate() in some versions.
    device=selected.get('device','auto')
    if device=='auto':  # no device named (an owner-set command): the graphics card when it has room, else the CPU
        device='cpu'
        try:
            import torch
            if torch.cuda.is_available() and torch.cuda.mem_get_info()[0]>=5000*2**20: device='cuda'
        except Exception: pass
    extra={'device':device}
    if str(device).startswith('cuda'):
        import torch
        # Half precision, loaded straight onto the GPU: keeps host RAM and GPU memory to a few GiB.
        extra={'device_map':device,'dtype':torch.float16,'model_kwargs':{'low_cpu_mem_usage':True}}
    pipe=pipeline('automatic-speech-recognition',model=request['model'],trust_remote_code=False,token=False,**extra)
    with wave.open(request['audio_path']) as wav:
        if wav.getnchannels()!=1 or wav.getsampwidth()!=2: raise ValueError('Expected normalized mono PCM audio')
        samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
        rate=wav.getframerate()
    kwargs={'return_timestamps':'word','batch_size':1}
    if request.get('language') and getattr(pipe,'type','')=='seq2seq_whisper': kwargs['generate_kwargs']={'language':request['language'],'task':'transcribe'}
    # The pipeline's own long-audio merge (chunk_length_s) repeats words and returns times out of order, so audio
    # over 28 s is recognised in windows cut at the quietest point between 16 and 26 s and the times are shifted back.
    chunks=[];last=0.0
    for begin,end in windows(samples,rate,np):
        offset=begin/rate
        for chunk in pipe({'array':samples[begin:end],'sampling_rate':rate},**kwargs).get('chunks',[]):
            start,stop=chunk.get('timestamp') or (None,None)
            if start is None or not str(chunk.get('text','')).strip(): continue
            start=max(start+offset,last);stop=max((stop if stop is not None else start)+offset,start+0.02)
            chunks.append({'text':chunk['text'],'timestamp':[round(start,3),round(stop,3)]});last=start
    print(json.dumps({'chunks':chunks,'recognizer':{'adapter':'transformers pipeline','model':request['model']}}))

def windows(samples,rate,np):
    """(begin, end) sample ranges of at most about 26 s, cut where the sound is quietest."""
    total=len(samples);hop=max(1,int(rate*0.02));cuts=[0]
    usable=total-total%hop
    energy=np.mean(samples[:usable].reshape(-1,hop)**2,axis=1) if usable else np.zeros(0)
    while (total-cuts[-1])/rate>28:
        low=cuts[-1]//hop+int(16/0.02);high=cuts[-1]//hop+int(26/0.02)
        smooth=np.convolve(energy[low:high],np.ones(5)/5,mode='same')
        cuts.append((low+int(np.argmin(smooth)))*hop)
    return list(zip(cuts,cuts[1:]+[total]))

if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print('Selected Transformers runtime/model did not supply word timestamps; check its local installation and compatibility.',file=sys.stderr)
        raise SystemExit(1)
