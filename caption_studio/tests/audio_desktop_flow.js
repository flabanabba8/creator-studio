import {act} from 'react'
import {createRoot} from 'react-dom/client'
import {AudioReview} from '../../desktop/audio-review.js'
import {createElement as h} from 'react'

export async function run(assert,document){
  const calls=[],running=[]
  const cue={cue_id:1,flags:['word_disagreement','timing_change'],original:{start_ms:100,end_ms:900,text:'A green boat'},recognized_text:'A green coat',suggested_text:'A green coat',suggested_start_ms:1000,suggested_end_ms:2000,matched_word_coverage:.67,timing_available:true,text_disagreement:true}
  const ctx={rest:async(_,{body})=>{calls.push(body);switch(body.operation){
    case 'captions_analyse_audio':return {job_id:'fixture',state:'preparing'}
    case 'captions_audio_status':return {job_id:'fixture',state:'ready',phase:'Ready for review',flagged_cues:1,text_disagreements:1}
    case 'captions_audio_review':return {job_id:'fixture',cues:[cue],offset:0,next_offset:null,notice:'Listen before accepting changes'}
    case 'captions_audio_preview':return {audio_url:'data:audio/mpeg;base64,AA=='}
    case 'captions_audio_export':return {output_path:'/tmp/reviewed.srt'}
    default:throw Error('Unexpected operation '+body.operation)
  }}}
  const root=createRoot(document.getElementById('root'))
  const input=name=>[...document.querySelectorAll('label')].find(x=>x.firstChild?.textContent===name)?.querySelector('input,textarea,select')
  const change=async(element,value)=>act(async()=>{
    assert.ok(element);const proto=element.tagName==='SELECT'?window.HTMLSelectElement.prototype:element.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto,'value').set.call(element,value);element.dispatchEvent(new window.Event(element.tagName==='SELECT'?'change':'input',{bubbles:true}))
  })
  const click=async text=>act(async()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent===text);assert.ok(b&&!b.disabled,text);b.click()})
  try{
    await act(async()=>root.render(h(AudioReview,{ctx,source:'/tmp/source.srt',allowProfile:false,onRunning:x=>running.push(x)})))
    assert.equal(calls.length,0,'No recognizer or provider call on mount')
    await change(input('Audio or video on the Hermes host'),'/tmp/audio.wav');await change(input('Recognition source'),'import');await change(input('Word-timestamp transcript JSON'),'/tmp/words.json')
    await click('Analyse audio and captions')
    await act(async()=>await new Promise(resolve=>setTimeout(resolve,1150)))
    assert.match(document.body.textContent,/A green coat/)
    assert.equal(calls.filter(c=>c.operation==='captions_audio_export').length,0)
    await click('Listen at suggested timing');assert.ok(document.querySelector('audio[controls]'))
    await click('Use recognizer wording for this cue')
    await act(async()=>input('Apply this cue’s suggested timing').click())
    await click('Export 1 reviewed cue change(s)')
    const decision=calls.find(c=>c.operation==='captions_audio_export').arguments.decisions[0]
    assert.equal(decision.text,'A green coat');assert.equal(decision.use_timing,true)
    assert.match(document.body.textContent,/original files unchanged/);assert.equal(running.at(-1),false)
  }finally{await act(async()=>root.unmount())}
  return {passed:true,checks:['no default provider call','model/runtime source explicitly chosen','timed review','audio excerpt','word and timing selection','explicit reviewed export','poll cleanup']}
}

export async function runCreate(assert,document){
  const calls=[]
  const ctx={rest:async(_,{body})=>{calls.push(body);switch(body.operation){
    case 'captions_generate':return {job_id:'new-draft',mode:'create',state:'preparing'}
    case 'captions_audio_status':return {job_id:'new-draft',mode:'create',state:'ready',total_cues:1,flagged_cues:1,text_disagreements:0}
    case 'captions_audio_review':return {job_id:'new-draft',offset:0,next_offset:null,notice:'Review this draft.',cues:[{cue_id:1,flags:['generated_caption_needs_review'],original:{start_ms:0,end_ms:2000,text:'An original caption'},recognized_text:'An original caption',suggested_text:'An original caption',matched_word_coverage:1,timing_available:true,suggested_start_ms:0,suggested_end_ms:2000,text_disagreement:false}]}
    case 'captions_audio_export':return {output_path:'/tmp/generated.srt',draft:true,reviewed_cues:0}
    default:throw Error('Unexpected generation operation '+body.operation)
  }}}
  const root=createRoot(document.getElementById('root'))
  const input=name=>[...document.querySelectorAll('label')].find(x=>x.firstChild?.textContent===name)?.querySelector('input,select')
  const change=async(el,value)=>act(async()=>{assert.ok(el);const proto=el.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new window.Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}))})
  const click=async name=>act(async()=>{const el=[...document.querySelectorAll('button')].find(x=>x.textContent===name);assert.ok(el&&!el.disabled,name);el.click()})
  try{
    await act(async()=>root.render(h(AudioReview,{ctx,source:'',allowProfile:false,onRunning:()=>{},mode:'create'})))
    assert.equal(calls.length,0)
    await change(input('Audio or video on the Hermes host'),'/tmp/recording.wav');await change(input('Recognition source'),'import');await change(input('Word-timestamp transcript JSON'),'/tmp/words.json')
    await click('Generate captions');await act(async()=>await new Promise(resolve=>setTimeout(resolve,1150)))
    const request=calls.find(x=>x.operation==='captions_generate').arguments
    assert.equal('source_path'in request,false,'Creation must not require a pre-existing SRT')
    assert.match(document.body.textContent,/An original caption/)
    await click('Save generated SRT draft')
    assert.deepEqual(calls.find(x=>x.operation==='captions_audio_export').arguments.decisions,[])
    assert.match(document.body.textContent,/Generated SRT draft saved/)
  }finally{await act(async()=>root.unmount())}
  return {passed:true,checks:['no source SRT','explicit recognizer','generated draft review','honest unreviewed draft export','poll cleanup']}
}
