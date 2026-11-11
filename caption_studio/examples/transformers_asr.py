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
    device=selected.get('device','cpu')
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
    kwargs={'return_timestamps':'word','chunk_length_s':30,'batch_size':1}
    if request.get('language') and getattr(pipe,'type','')=='seq2seq_whisper': kwargs['generate_kwargs']={'language':request['language'],'task':'transcribe'}
    result=pipe({'array':samples,'sampling_rate':rate},**kwargs)
    print(json.dumps({'chunks':result.get('chunks',[]),'recognizer':{'adapter':'transformers pipeline','model':request['model']}}))

if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print('Selected Transformers runtime/model did not supply word timestamps; check its local installation and compatibility.',file=sys.stderr)
        raise SystemExit(1)
