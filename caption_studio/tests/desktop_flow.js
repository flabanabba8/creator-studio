import { act } from 'react'
import { createRoot } from 'react-dom/client'
import plugin from '../../desktop/plugin.js'

export async function run(assert, document) {
  const contributions = [], calls = []
  const ctx = { register: c => contributions.push(c), rest: async (_, { body }) => {
    calls.push(body)
    switch (body.operation) {
      case 'captions_inspect': return { fingerprint:'source-hash', total:1, cues:[{start_ms:1000,end_ms:2000,text:'Hello there friend'}] }
      case 'captions_suggest_alignment': return { source_fingerprint:'source-hash', method:'single-match offset', matched_phrases:1,
        suggested_anchors:[{source_ms:1000,target_ms:1250}], notice:'Verify against the video' }
      case 'captions_retime': return { output_path:'/tmp/corrected.srt' }
      default: throw Error('Unexpected operation')
    }
  } }
  plugin.register(ctx)
  const root = createRoot(document.getElementById('root'))
  const field = name => [...document.querySelectorAll('label')].find(e => e.firstChild?.textContent === name)?.querySelector('input')
  const change = async (element, value) => act(async () => {
    assert.ok(element)
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(element, value)
    element.dispatchEvent(new window.Event('input', { bubbles:true }))
  })
  const click = async text => act(async () => {
    const element = [...document.querySelectorAll('button')].find(e => e.textContent === text)
    assert.ok(element && !element.disabled, 'Missing or disabled ' + text); element.click()
  })
  try {
    await act(async () => root.render(contributions.find(c => c.area === 'routes').render()))
    await act(async () => {
      const task=document.querySelector('[aria-label="Caption task"]')
      assert.equal(task.value,'create')
      Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype,'value').set.call(task,'repair')
      task.dispatchEvent(new window.Event('change',{bubbles:true}))
    })
    await change(field('Source SRT on the Hermes host'), '/tmp/source.srt')
    await act(async () => field('Allow selected SRT files inside this profile’s plugin data').click())
    await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles:true, cancelable:true })))
    assert.equal(calls.find(c => c.operation === 'captions_inspect').arguments.allow_profile_captions, true)
    assert.equal(calls.filter(c => c.operation === 'captions_retime').length, 0)
    await change(field('Reference SRT on the Hermes host'), '/tmp/reference.srt')
    await click('Suggest alignment')
    assert.match(document.querySelector('[role=status]').textContent, /Verify against the video/)
    assert.equal(calls.filter(c => c.operation === 'captions_retime').length, 0)
    await click('Use suggested anchors')
    assert.equal(field('Source 1 (ms)').value, '1000')
    assert.equal(field('Target 1 (ms)').value, '1250')
    await click('Write corrected SRT')
    assert.deepEqual(calls.find(c => c.operation === 'captions_retime').arguments.anchors, [{source_ms:1000,target_ms:1250}])
    assert.equal(document.querySelector('details').open, false)
    await click('Inspect corrected copy')
    assert.equal(calls.filter(c => c.operation === 'captions_inspect').at(-1).arguments.source_path, '/tmp/corrected.srt')
    assert.equal(field('Source 1 (ms)').value, '')
  } finally { await act(async () => root.unmount()) }
  return {passed:true, checks:['explicit inspection', 'profile caption opt-in', 'suggestion reviewed separately', 'explicit correction', 'reinspect output', 'anchors reset', 'file path collapsed', 'timer cleanup']}
}
