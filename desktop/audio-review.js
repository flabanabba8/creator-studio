import { createElement as h, useEffect, useState } from 'react'

const box={padding:16,border:'1px solid var(--ui-stroke-secondary)',borderRadius:12,display:'grid',gap:10}
const input={padding:8,border:'1px solid var(--ui-stroke-secondary)',borderRadius:6,background:'var(--ui-bg-tertiary)',color:'var(--ui-text-primary)',maxWidth:'100%',boxSizing:'border-box'}
const label=(name,child)=>h('label',null,name,child)
const flagNames={generated_caption_needs_review:'New caption — check wording and timing',word_disagreement:'Different wording',words_missing_from_captions:'Possible missing words',caption_words_not_heard:'Words may not be spoken',insufficient_matching_context:'Needs closer listening',ambiguous_caption_boundary:'Uncertain caption boundary',low_alignment_evidence:'Could not locate reliably',timing_change:'Timing suggestion',low_recognizer_confidence:'Uncertain recognition'}
const time=t=>{const seconds=Math.floor(t/1000);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}.${String(t%1000).padStart(3,'0')}`}

const button=(name,fn,disabled=false)=>h('button',{onClick:fn,disabled,style:{...input,opacity:disabled?.5:1}},name)

export function AudioReview({ctx,source,allowProfile,onRunning,mode='repair'}) {
  const [media,setMedia]=useState(''),[kind,setKind]=useState(''),[model,setModel]=useState(''),[argv,setArgv]=useState(''),[resultLocation,setResultLocation]=useState('stdout'),[transcript,setTranscript]=useState('')
  const [endpoint,setEndpoint]=useState(''),[fields,setFields]=useState('{}'),[upload,setUpload]=useState(false),[useKey,setUseKey]=useState(false),[auth,setAuth]=useState('Authorization')
  const [decoder,setDecoder]=useState(''),[profileMedia,setProfileMedia]=useState(false),[languages,setLanguages]=useState('en'),[access,setAccess]=useState(''),[offline,setOffline]=useState(true),[resources,setResources]=useState(null)
  const [job,setJob]=useState(null),[page,setPage]=useState(null),[choices,setChoices]=useState({}),[clip,setClip]=useState(null),[output,setOutput]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const call=(operation,args)=>ctx.rest('/action',{method:'POST',body:{operation,arguments:args},timeoutMs:120000})
  const task=async fn=>{setBusy(true);setError('');try{await fn()}catch(e){setError(String(e.message||e))}finally{setBusy(false)}}
  const list=s=>s.split(',').map(x=>x.trim()).filter(Boolean)
  useEffect(()=>{setJob(null);setPage(null);setChoices({});setClip(null);setOutput(null)},[source,mode])
  useEffect(()=>{
    if(!job?.job_id||!['preparing','running'].includes(job.state))return
    let active=true;onRunning(true)
    const timer=setInterval(async()=>{
      try {
        const status=await call('captions_audio_status',{job_id:job.job_id})
        if(!active)return
        if(!['preparing','running'].includes(status.state)){
          clearInterval(timer);onRunning(false)
          if(status.state==='ready'){
            const review=await call('captions_audio_review',{job_id:job.job_id})
            if(active)setPage(review)
          }
        }
        if(active)setJob(status)
      }catch(e){if(active){setError(String(e.message||e));clearInterval(timer);onRunning(false)}}
    },1000)
    return()=>{active=false;clearInterval(timer);onRunning(false)}
  },[job?.job_id])
  const running=job&&['preparing','running'].includes(job.state)
  const text=(name,value,setter,props={})=>label(name,h('input',{...props,style:{...input,display:'block',width:'100%'},value,disabled:busy||running,onChange:e=>setter(e.target.value)}))
  const area=(name,value,setter)=>label(name,h('textarea',{style:{...input,display:'block',width:'100%',minHeight:65},value,disabled:busy||running,onChange:e=>setter(e.target.value)}))
  const check=(name,value,setter)=>label(name,h('input',{type:'checkbox',checked:value,disabled:busy||running,onChange:e=>setter(e.target.checked)}))
  const update=(id,patch)=>setChoices(old=>({...old,[id]:{...old[id],cue_id:id,...patch}}))
  const decisions=Object.values(choices).filter(x=>x.drop||x.use_timing||x.use_text||'text'in x||'start_ms'in x||'end_ms'in x)
  const start=()=>task(async()=>{
    let recognizer={kind,model,language:languages.trim()}
    if(kind==='import')recognizer.transcript_path=transcript
    if(kind==='command')recognizer={...recognizer,argv:JSON.parse(argv),output:resultLocation}
    if(kind==='http')recognizer={...recognizer,endpoint,fields:JSON.parse(fields),allow_upload:upload,use_api_key:useKey,auth_header:auth}
    const args={media_path:media,recognizer,allow_profile_media:profileMedia,...(mode==='repair'?{source_path:source,allow_profile_captions:allowProfile}:{})}
    if(decoder.trim())args.decoder_argv=JSON.parse(decoder)
    const result=await call(mode==='create'?'captions_generate':'captions_analyse_audio',args);setJob(result);setPage(null);setChoices({});setOutput(null)
  })
  const listen=(cue,timing)=>task(async()=>setClip({cue_id:cue.cue_id,...await call('captions_audio_preview',{job_id:job.job_id,cue_id:cue.cue_id,timing,include_data:true})}))
  return h('section',{style:box,'aria-label':'Audio alignment and transcription review'},
    h('h2',null,mode==='create'?'Create captions from your recording':'Align to audio and check the words'),
    h('p',null,'Choose your recognizer and runtime. Compare its timed words with these captions, listen to disagreements, then save only the changes you review.'),
    error&&h('p',{role:'alert'},error),
    text('Audio or video on the Hermes host',media,setMedia),
    check('Allow selected media and transcript files inside this profile’s plugin data',profileMedia,setProfileMedia),
    h('details',null,h('summary',null,'Help me choose a setup'),
      h('div',{style:box},text('Languages (comma-separated)',languages,setLanguages),text('API access or subscriptions you already have (optional)',access,setAccess),check('Prefer free local processing; keep audio offline',offline,setOffline),
        button('Recommend recognition options',()=>task(async()=>setResources(await call('captions_recognizer_options',{languages:list(languages),subscriptions:list(access),offline}))),busy||running),
        resources&&h('div',null,h('p',null,`${resources.hardware.cpu_threads||'?'} CPU threads · ${resources.hardware.ram_gib||'?'} GiB RAM · ${resources.hardware.gpus.length} detected NVIDIA GPU(s)`),
          ...resources.choices.map(c=>h('p',{key:c.id},h('strong',null,c.id+': '),c.description+' '+c.cost)),h('p',null,resources.notice),h('p',null,'Ask Hermes to help configure the selected backend from these resources. App subscriptions do not guarantee API access or unlimited usage.')))),
    label('Recognition source',h('select',{'aria-label':'Recognition source',value:kind,style:input,disabled:busy||running,onChange:e=>setKind(e.target.value)},h('option',{value:''},'Choose a recognition source'),h('option',{value:'command'},'Local command / any compatible runtime'),h('option',{value:'import'},'Import word-timestamp JSON'),h('option',{value:'http'},'Compatible speech HTTP service'))),
    kind==='command'&&h('div',{style:box},area('Recognizer argv (JSON array)',argv,setArgv),text('Selected model ID or model path (if needed)',model,setModel),label('Recognizer result location',h('select',{style:input,value:resultLocation,onChange:e=>setResultLocation(e.target.value),disabled:busy||running},h('option',{value:'stdout'},'JSON on stdout'),h('option',{value:'file'},'JSON file at {output} / {output_base}.json'))),h('p',null,'Use {audio}, {model}, {language}, {output} or {output_base} placeholders. The command must produce word-timestamp JSON. No shell, model download or paid service is chosen automatically. Hermes can help construct the arguments for your selected tool.')),
    kind==='import'&&text('Word-timestamp transcript JSON',transcript,setTranscript),
    kind==='http'&&h('div',{style:box},text('Selected speech endpoint',endpoint,value=>{setEndpoint(value);setUpload(false);setUseKey(false)}),area('Provider form fields (JSON object)',fields,setFields),
      check('I agree to upload this audio to the selected endpoint and any applicable service charges',upload,setUpload),
      check('Use the selected speech-service key stored in Hermes settings',useKey,setUseKey),
      useKey&&text('Credential header',auth,setAuth),
      h('p',null,'No hosted provider is selected by default. Check the endpoint’s word-timestamp support, API allowance and pricing before uploading. Keys belong in Hermes plugin settings, not this form.')),
    h('details',null,h('summary',null,'Alternative media decoder'),area('Decoder argv (optional JSON array)',decoder,setDecoder),h('p',null,'Default: installed FFmpeg. An alternative command must write mono 16 kHz 16-bit WAV using {media} and {audio}.')),
    button(mode==='create'?'Generate captions':'Analyse audio and captions',start,busy||running||(mode==='repair'&&!source.trim())||!media.trim()||!kind||(kind==='command'&&!argv.trim())||(kind==='import'&&!transcript.trim())||(kind==='http'&&!endpoint.trim())),
    job&&h('div',{role:'status',style:box},h('p',null,job.phase||job.state),job.error&&h('p',null,job.error),
      running&&button('Cancel audio review',()=>task(async()=>{await call('captions_audio_cancel',{job_id:job.job_id});setJob(await call('captions_audio_status',{job_id:job.job_id}))}),busy),
      job.state==='ready'&&h('p',null,`${job.flagged_cues} flagged cues · ${job.text_disagreements} possible text discrepancies. These are suggestions, not proven corrections.`)),
    page&&h('div',{style:{display:'grid',gap:14}},h('p',null,page.notice),mode==='create'&&h('p',null,job?.total_cues===0?'No speech was recognized. Check the recording and recognizer before accepting an empty subtitle file.':job?.recognizer_notice||'These are newly generated captions. Listen and check the words and timing.'),...page.cues.map(c=>h('article',{key:c.cue_id,style:box},
      h('h3',null,`Cue ${c.cue_id} · ${c.flags.length?c.flags.map(x=>flagNames[x]||'Needs review').join(' · '):'no difference flagged'}`),
      h('p',null,`Caption: ${time(c.original.start_ms)}–${time(c.original.end_ms)} · ${c.original.text}`),
      h('p',null,`Recognizer: ${c.recognized_text||'(not reliably located)'}`),
      h('details',null,h('summary',null,'How this caption was located'),h('p',null,`Matched-word coverage: ${Math.round(c.matched_word_coverage*100)}% — helps locate the line; it does not prove the words are correct.`)),
      h('div',{style:{display:'flex',gap:8,flexWrap:'wrap'}},button('Listen at original timing',()=>listen(c,'original'),busy),button('Listen at suggested timing',()=>listen(c,'suggested'),busy||!c.timing_available)),
      clip?.cue_id===c.cue_id&&h('audio',{controls:true,src:clip.audio_url,style:{maxWidth:'100%'}}),
      label('Apply this cue’s suggested timing',h('input',{type:'checkbox',checked:!!choices[c.cue_id]?.use_timing,disabled:busy||!c.timing_available,onChange:e=>update(c.cue_id,{use_timing:e.target.checked})})),
      label('Remove this cue after listening (for hallucinated/unspoken captions)',h('input',{type:'checkbox',checked:!!choices[c.cue_id]?.drop,disabled:busy,onChange:e=>update(c.cue_id,{drop:e.target.checked})})),
      label('Reviewed wording',h('textarea',{value:choices[c.cue_id]?.text??c.original.text,style:{...input,width:'100%',display:'block'},disabled:busy,onChange:e=>update(c.cue_id,{text:e.target.value})})),
      button('Use recognizer wording for this cue',()=>update(c.cue_id,{use_text:true,text:c.suggested_text}),busy||!c.text_disagreement),
      h('details',null,h('summary',null,'Edit timing manually'),...['start_ms','end_ms'].map(k=>h('label',{key:k},k,h('input',{type:'number',min:0,step:1,value:choices[c.cue_id]?.[k]??c.original[k],disabled:busy,style:input,onChange:e=>update(c.cue_id,{[k]:Number(e.target.value),use_timing:false})})))),
      button('Keep this cue unchanged',()=>setChoices(old=>{const next={...old};delete next[c.cue_id];return next}),busy))),
      h('div',{style:{display:'flex',gap:8}},button('Previous review cues',()=>task(async()=>setPage(await call('captions_audio_review',{job_id:job.job_id,offset:Math.max(0,page.offset-20)}))),busy||page.offset===0),button('Next review cues',()=>task(async()=>setPage(await call('captions_audio_review',{job_id:job.job_id,offset:page.next_offset}))),busy||page.next_offset==null)),
      mode==='create'&&button('Save generated SRT draft',()=>task(async()=>setOutput(await call('captions_audio_export',{job_id:job.job_id,decisions:[]}))),busy),
      button(`Export ${decisions.length} reviewed cue change(s)`,()=>task(async()=>setOutput(await call('captions_audio_export',{job_id:job.job_id,decisions}))),busy||!decisions.length)),
    output&&h('div',{role:'status',style:box},h('strong',null,output.draft?'Generated SRT draft saved — review the words and timing':'Separate reviewed SRT saved; original files unchanged'),h('details',null,h('summary',null,'Show saved caption location'),h('code',{style:{overflowWrap:'anywhere'}},output.output_path))))
}
