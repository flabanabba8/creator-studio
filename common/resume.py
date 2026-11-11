"""One plain 'carry on': work out what a half-finished video or podcast project still needs. Read-only."""


def plan(data, kind):
    """kind is 'video' or 'podcast'. Returns what is done, what is left and the single next call."""
    prefix = 'youtube' if kind == 'video' else 'podcast'
    sections = data.get('sections') or []
    turns = sum(len(s['turns']) for s in sections)
    recorded = sum(min(len(s['audio_ids']), len(s['turns'])) for s in sections)
    read = [s for s in data.get('sources', {}).values() if s.get('read_to', 0) >= s.get('characters', 0)]
    done, left = [], []
    if data.get('sources'):done.append('sources saved (%d, %d read in full)' % (len(data['sources']), len(read)))
    elif sections and not data.get('factual', True):done.append('this non-factual script does not require research')
    else:left.append('research: no sources saved yet')
    (done if sections else left).append('script written (%d sections)' % len(sections) if sections else 'script not written')
    if sections:
        (done if recorded == turns else left).append('narration %d of %d turns recorded' % (recorded, turns))
    if kind == 'video' and sections:
        missing = [i for i, s in enumerate(sections) if not s.get('image_id')]
        (left if missing else done).append('pictures missing for sections %s' % missing if missing else 'every section has a picture')
    assembled = data.get('phase') == 'assembled'
    (done if assembled else left).append('assembled' if assembled else 'not assembled')
    if not data.get('sources') and not sections:
        nxt = prefix + '_research_fetch (or ' + prefix + '_source_add)'
    elif not sections:
        nxt = prefix + '_source_read for each source you will cite, then ' + prefix + '_write_script'
    elif recorded < turns:
        nxt = prefix + '_narrate (it skips the %d turns already recorded and only pays for the rest)' % recorded
    elif kind == 'video' and any(not s.get('image_id') for s in sections):
        nxt = 'youtube_make_visual / youtube_make_slides / youtube_material_add for the sections without a picture'
    elif not assembled:
        nxt = prefix + '_assemble_project'
    else:
        nxt = prefix + '_episode_files and show the finished files' if kind == 'podcast' else 'nothing: it is assembled; show the finished video (result.video.output_path)'
    steps=[]
    if not data.get('sources') and not sections:steps.append(prefix + '_research_fetch or ' + prefix + '_source_add')
    if not sections:steps.append(prefix + '_source_read for each cited source, then ' + prefix + '_write_script')
    if kind == 'video' and any('not yet inspected' in data.get('assets',{}).get(s.get('image_id'),{}).get('review_note','') for s in sections):steps.append('Inspect each unreviewed picture at its status path, then record what you saw with youtube_material_add')
    if not sections or recorded < turns:steps.append(prefix + '_narrate: reuse existing takes and record only missing turns')
    if kind == 'video' and (not sections or any(not s.get('image_id') for s in sections)):steps.append('Create, inspect and attach pictures for sections that need them')
    if not assembled:steps.append(prefix + '_assemble_project')
    steps.append(prefix + '_episode_files and show the episode' if kind == 'podcast' else 'Show the finished video')
    return {'next_steps_to_completion':steps, 'done': done, 'left': left, 'next': nxt, 'speech_turns_remaining': turns - recorded,
            'rule': 'Run the ordered next_steps_to_completion to the end in this request without stopping to ask, unless genuinely blocked; never redo finished work or recorded turns.'}
