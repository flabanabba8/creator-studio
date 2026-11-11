import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { createElement as h, useState } from 'react'
import { AudioReview } from './audio-review.js'

const field = { padding: '8px 10px', border: '1px solid var(--ui-stroke-secondary)', borderRadius: 7, background: 'var(--ui-bg-tertiary)', color: 'var(--ui-text-primary)' }
const card = { padding: 16, border: '1px solid var(--ui-stroke-secondary)', borderRadius: 12, display: 'grid', gap: 10 }
const row = { display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }
const button = (text, onClick, disabled = false, props = {}) => h('button', { style: { ...field, opacity: disabled ? 0.5 : 1 }, onClick, disabled, ...props }, text)
const label = (text, input) => h('label', null, text, input)

function Captions({ ctx }) {
  const [mode,setMode]=useState('create')
  const [source, setSource] = useState(''), [reference, setReference] = useState(''), [allowProfile, setAllowProfile] = useState(false)
  const [inspection, setInspection] = useState(null), [suggestion, setSuggestion] = useState(null), [output, setOutput] = useState(null)
  const [source1, setSource1] = useState(''), [target1, setTarget1] = useState(''), [source2, setSource2] = useState(''), [target2, setTarget2] = useState('')
  const [drift, setDrift] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const call = (operation, args) => ctx.rest('/action', { method: 'POST', body: { operation, arguments: args }, timeoutMs: 60000 })
  const task = async fn => { setBusy(true); setError(''); try { await fn() } catch (e) { setError(String(e.message || e)) } finally { setBusy(false) } }
  const inspect = async path => {
    const r = await call('captions_inspect', { source_path: path, allow_profile_captions: allowProfile, limit: 20 })
    setSource(path); setInspection(r); setSuggestion(null); setOutput(null)
    setSource1(''); setTarget1(''); setSource2(''); setTarget2(''); setDrift(false)
  }
  const integer = value => value !== '' && Number.isSafeInteger(Number(value)) && Number(value) >= 0
  const valid = integer(source1) && integer(target1) && (!drift || (integer(source2) && integer(target2) && Number(source2) > Number(source1) && Number(target2) > Number(target1)))
  const applySuggestion = () => {
    const anchors = suggestion.suggested_anchors
    setSource1(String(anchors[0].source_ms)); setTarget1(String(anchors[0].target_ms)); setDrift(anchors.length === 2)
    setSource2(anchors.length === 2 ? String(anchors[1].source_ms) : ''); setTarget2(anchors.length === 2 ? String(anchors[1].target_ms) : '')
  }
  const num = (name, value, setter) => label(name, h('input', { style: { ...field, display: 'block' }, type: 'number', min: 0, step: 1, value, disabled: busy, onChange: e => setter(e.target.value) }))
  return h('main', { style: { maxWidth: 1000, padding: 28, margin: 'auto', display: 'grid', gap: 20, color: 'var(--ui-text-primary)' } },
    h('header', null, h('h1', null, 'Caption Studio'), h('p', null, 'Create captions from a recording, check the words, and keep them in time.')),
    label('What would you like to do?',h('select',{'aria-label':'Caption task',value:mode,disabled:busy,style:field,onChange:e=>setMode(e.target.value)},h('option',{value:'create'},'Create new captions'),h('option',{value:'repair'},'Review or repair existing captions'))),
    error && h('p', { role: 'alert', style: card }, error),
    mode==='repair'&&h('form', { style: card, onSubmit: e => { e.preventDefault(); task(() => inspect(source)) } },
      label('Source SRT on the Hermes host', h('input', { style: { ...field, display: 'block', width: '100%' }, value: source, disabled: busy, onChange: e => { setSource(e.target.value); setInspection(null); setSuggestion(null); setOutput(null) } })),
      label('Allow selected SRT files inside this profile’s plugin data', h('input', { type: 'checkbox', checked: allowProfile, disabled: busy, onChange: e => { setAllowProfile(e.target.checked); setInspection(null); setSuggestion(null); setOutput(null) } })),
      button('Inspect captions', undefined, busy || !source.trim(), { type: 'submit' })),
    h(AudioReview,{ctx,source,allowProfile,onRunning:setBusy,mode}),
    inspection && h('section', { style: { display: 'grid', gap: 14 }, 'aria-label': 'Caption timing' },
      h('div', { style: card }, h('h2', null, 'Source cues'), h('p', null, `${inspection.total} cues · first ${inspection.cues.length} shown`),
        h('ol', null, ...inspection.cues.map((cue, i) => h('li', { key: i }, `${cue.start_ms}–${cue.end_ms} ms · ${cue.text}`)))),
      h('div', { style: card }, h('h2', null, 'Reference suggestion'),
        label('Reference SRT on the Hermes host', h('input', { style: { ...field, display: 'block', width: '100%' }, value: reference, disabled: busy, onChange: e => { setReference(e.target.value); setSuggestion(null) } })),
        button('Suggest alignment', () => task(async () => {
          const result = await call('captions_suggest_alignment', { source_path: source, reference_path: reference, allow_profile_captions: allowProfile })
          if (result.source_fingerprint !== inspection.fingerprint) throw Error('Source changed; inspect captions again')
          setSuggestion(result)
        }), busy || !reference.trim()),
        suggestion && h('div', { role: 'status' }, h('p', null, `${suggestion.method} · ${suggestion.matched_phrases} matched phrase(s)`),
          suggestion.median_residual_ms != null && h('p', null, `Median residual ${suggestion.median_residual_ms} ms · maximum ${suggestion.max_residual_ms} ms`),
          h('p', null, suggestion.notice), button('Use suggested anchors', applySuggestion, busy))),
      h('div', { style: card }, h('h2', null, 'Timing anchors'),
        h('p', null, 'Match a source subtitle timestamp to the corresponding video/reference timestamp. Check against the video.'),
        h('div', { style: row }, num('Source 1 (ms)', source1, setSource1), num('Target 1 (ms)', target1, setTarget1)),
        label('Use a second anchor for linear drift', h('input', { type: 'checkbox', checked: drift, disabled: busy, onChange: e => setDrift(e.target.checked) })),
        drift && h('div', { style: row }, num('Source 2 (ms)', source2, setSource2), num('Target 2 (ms)', target2, setTarget2)),
        button('Write corrected SRT', () => task(async () => {
          const anchors = [{ source_ms: Number(source1), target_ms: Number(target1) }]
          if (drift) anchors.push({ source_ms: Number(source2), target_ms: Number(target2) })
          setOutput(await call('captions_retime', { source_path: source, fingerprint: inspection.fingerprint, anchors, allow_profile_captions: allowProfile }))
        }), busy || !valid)),
      output && h('div', { style: card, role: 'status' }, h('strong', null, 'Separate SRT written'),
        h('details', null, h('summary', null, 'Show saved file location'), h('code', { style: { overflowWrap: 'anywhere' } }, output.output_path)),
        button('Inspect corrected copy', () => task(() => inspect(output.output_path)), busy))))
}

export default { id: 'caption-studio', name: 'Caption Studio', register(ctx) {
  ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/caption-studio' }, render: () => h(Captions, { ctx }) })
  ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/caption-studio', label: 'Caption Studio', codicon: 'comment-discussion' } })
} }
