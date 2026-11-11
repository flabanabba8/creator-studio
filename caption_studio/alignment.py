"""Model-independent word-timing normalization and conservative caption comparison."""
from bisect import bisect_left
from collections import Counter
from difflib import SequenceMatcher
import math
import re

MAX_WORDS = 100000
MAX_GAP = 1500
TIMING_TOLERANCE_MS = 120

# Conservative rule for corrections proposed without a human (see propose()).
CLEAR_MIN_COVERAGE = .75     # share of a cue's words matched to heard words
CLEAR_MIN_MATCHED = 3        # matched words that surround a one-word edit
CLEAR_MIN_CONFIDENCE = .8    # supplied confidence of the heard word
CLEAR_MIN_SIMILARITY = .6    # spelling similarity that corroborates without confidence
CLEAR_MAX_SHIFT_MS = 10000   # larger displacements may be a repeated phrase
CLEAR_MAX_SPREAD_MS = 600    # start and end displacement must agree this closely
START_ONLY_MIN_SHIFT_MS = 300  # a cue whose start alone is this far off (its end already agrees) is a late/early start
END_AGREES_MS = 150
# English function words: a one-word swap between two of these, with every other word of the cue matched on
# both sides, is clear even without recognizer confidence or similar spelling (never names, numbers or content words).
COMMON_WORDS = frozenset('a an and or but nor so the of in on at to for with from by as into onto up out off over than then if is are was were be been am it its this that these those not no'.split())

def tokens(text):
    text = re.sub(r'<[^>]*>', '', text).casefold().replace('’', "'")
    return re.findall(r'[\u3400-\u9fff\u3040-\u30ff]|[^\W_]+(?:\x27[^\W_]+)*', text)

def normalize_transcript(data, duration_ms):
    """Accept common recognizer JSON shapes; never invent missing word timestamps."""
    if not isinstance(data, dict): raise ValueError('Recognizer must return a JSON object')
    if data.get('error') or data.get('success') is False or data.get('status') in ('denied','blocked','cancelled','refused','error'): raise ValueError('Selected recognizer failed or refused the request; approvals are not bypassed')
    rows = data.get('words')
    if rows is None and isinstance(data.get('segments'), list):
        rows = []
        for segment in data['segments']:
            if not isinstance(segment, dict) or not isinstance(segment.get('words'), list):
                raise ValueError('Word timestamps are required; this recognizer returned segment-only timing')
            rows.extend(segment['words'])
    if rows is None and isinstance(data.get('chunks'), list): rows = data['chunks']
    if rows is None and isinstance(data.get('transcription'), list):
        # whisper.cpp full JSON: merge its subword tokens before word matching.
        rows = []
        for segment in data['transcription']:
            current = None
            for item in segment.get('tokens', []):
                text = item.get('text', '')
                if not text or text.startswith('[_'): continue
                offset = item.get('offsets', {})
                if text[:1].isspace() or current is None:
                    if current: rows.append(current)
                    current = {'text':text.strip(), 'start_ms':offset.get('from'), 'end_ms':offset.get('to')}
                else:
                    current['text'] += text; current['end_ms'] = offset.get('to')
            if current: rows.append(current)
    if not isinstance(rows, list): raise ValueError('Recognizer returned no timestamped words; enable word-level JSON output')
    if len(rows) > MAX_WORDS: raise ValueError('Recognizer output exceeds the 100,000-word bound')
    words = []
    for row in rows:
        if not isinstance(row, dict): raise ValueError('Invalid word record')
        if row.get('type', 'word') not in ('word', 'text'): continue
        text = row.get('word', row.get('text', ''))
        if not isinstance(text, str) or len(text)>1000: raise ValueError('Invalid recognized word text')
        lexical = tokens(text)
        if not lexical: continue
        if len(lexical)>1 and not all(re.fullmatch(r'[\u3400-\u9fff\u3040-\u30ff]', x) for x in lexical):
            raise ValueError('Recognizer returned multi-word segments; request word timestamps, not segment timestamps')
        if 'start_ms' in row:
            start, end = row.get('start_ms'), row.get('end_ms')
        else:
            pair = row.get('timestamp', [row.get('start'), row.get('end')])
            if not isinstance(pair, (list,tuple)) or len(pair)!=2: raise ValueError('Missing word timestamp pair')
            start, end = pair
            if all(type(v) in (int,float) and math.isfinite(v) for v in pair): start,end=round(start*1000),round(end*1000)
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0 <= start < end <= duration_ms+250:
            raise ValueError('Recognizer word times are missing, invalid or outside the selected audio')
        start,end=round(start),min(round(end),duration_ms)
        if words and start < words[-1]['start_ms']: raise ValueError('Recognizer words must be ordered in audio time')
        confidence = row.get('probability', row.get('confidence'))
        if confidence is not None and (type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1):
            raise ValueError('Word confidence must be between zero and one when supplied')
        for token in lexical:
            words.append({'text':token if len(lexical)>1 else text.strip(),'token':token,'start_ms':start,'end_ms':end,'confidence':confidence})
    return words

def ordered_anchors(a,b):
    def unique(seq):
        grams=[tuple(seq[i:i+3]) for i in range(max(0,len(seq)-2))]; counts=Counter(grams)
        return {g:i for i,g in enumerate(grams) if counts[g]==1}
    left,right=unique(a),unique(b)
    pairs=sorted((i,right[g]) for g,i in left.items() if g in right)
    tails=[]; last=[]; previous=[]
    for index,(_,target) in enumerate(pairs):
        pos=bisect_left(tails,target); previous.append(last[pos-1] if pos else -1)
        if pos==len(tails): tails.append(target);last.append(index)
        else: tails[pos]=target;last[pos]=index
    chain=[]; cursor=last[-1] if last else -1
    while cursor>=0: chain.append(pairs[cursor]);cursor=previous[cursor]
    chain.reverse(); result=[]
    for i,j in chain:
        if not result or (i>=result[-1][0]+3 and j>=result[-1][1]+3): result.append((i,j))
    return result

def compare(cues, words):
    source=[];owners=[]
    for i,cue in enumerate(cues):
        items=tokens(cue['text']);source.extend(items);owners.extend([i]*len(items))
    if not source or len(source)>MAX_WORDS: raise ValueError('Captions need 1–100,000 spoken words for audio comparison')
    target=[w['token'] for w in words];ops=[];ai=bi=0
    for ax,bx in ordered_anchors(source,target)+[(len(source),len(target))]:
        if ax-ai>MAX_GAP or bx-bi>MAX_GAP:
            ops.append(('unresolved',ai,ax,bi,bx))
        else:
            ops.extend((tag,ai+i,ai+j,bi+k,bi+l) for tag,i,j,k,l in SequenceMatcher(None,source[ai:ax],target[bi:bx],autojunk=False).get_opcodes())
        if ax<len(source): ops.append(('equal',ax,ax+3,bx,bx+3))
        ai,bi=ax+3,bx+3
    assigned=[set() for _ in cues];matched=[0]*len(cues);issues=[set() for _ in cues];ambiguous=set();edits=[[] for _ in cues]
    first=[owners.index(i) if i in owners else 0 for i in range(len(cues))]
    for tag,i,j,k,l in ops:
        if tag=='equal':
            for si,ti in zip(range(i,j),range(k,l)):
                assigned[owners[si]].add(ti);matched[owners[si]]+=1
            continue
        affected=set(owners[i:j])
        if not affected:
            affected={owners[x] for x in (i-1,i) if 0<=x<len(owners)}
        reason={'replace':'word_disagreement','insert':'words_missing_from_captions','delete':'caption_words_not_heard','unresolved':'insufficient_matching_context'}[tag]
        for owner in affected: issues[owner].add(reason)
        if len(affected)==1 and tag!='unresolved':
            owner=next(iter(affected));assigned[owner].update(range(k,l))
            edits[owner].append({'op':tag,'caption_index':i-first[owner],'caption':source[i:j],'heard':target[k:l],'heard_confidence':[words[x]['confidence'] for x in range(k,l)]})
        else: ambiguous.update(affected)
    counts=Counter(owners);report=[]
    for i,cue in enumerate(cues):
        indexes=sorted(assigned[i]);coverage=matched[i]/max(1,counts[i]);flags=set(issues[i])
        if i in ambiguous: flags.add('ambiguous_caption_boundary')
        if not indexes or coverage<.5: flags.add('low_alignment_evidence')
        recognizable=bool(indexes) and coverage>=.5 and i not in ambiguous
        start=words[indexes[0]]['start_ms'] if recognizable else None
        end=max(words[j]['end_ms'] for j in indexes) if recognizable else None
        if recognizable and (abs(start-cue['start_ms'])>TIMING_TOLERANCE_MS or abs(end-cue['end_ms'])>TIMING_TOLERANCE_MS): flags.add('timing_change')
        recognized=' '.join(words[j]['text'] for j in indexes)
        recognized=re.sub(r'(?<=[\u3400-\u9fff\u3040-\u30ff])\s+(?=[\u3400-\u9fff\u3040-\u30ff])','',recognized)
        low=[words[j]['confidence'] for j in indexes if words[j]['confidence'] is not None and words[j]['confidence']<.6]
        if low: flags.add('low_recognizer_confidence')
        report.append({'cue_id':i+1,'original':cue,'suggested_start_ms':start,'suggested_end_ms':end,
            'recognized_text':recognized,'suggested_text':recognized if issues[i] and i not in ambiguous and indexes else cue['text'],
            'matched_word_coverage':round(coverage,3),'matched_words':matched[i],'caption_words':counts[i],'edits':edits[i],'flags':sorted(flags),
            'timing_available':recognizable,'text_disagreement':bool(issues[i]),
            'notice':'Recognition disagreement is a review cue, not proof that either transcript is correct.'})
    return report

SENTENCE_END = re.compile(r'[.!?\u3002\uff01\uff1f]["\u201d\u2019\']?\s*$')
WORD = re.compile(r"<[^>]*>|[\u3400-\u9fff\u3040-\u30ff]|[^\W_]+(?:['\u2019][^\W_]+)*")
BLOCKING = {'caption_words_not_heard':'words_not_heard','words_missing_from_captions':'words_missing_from_captions',
    'insufficient_matching_context':'weak_alignment','ambiguous_caption_boundary':'weak_alignment','low_alignment_evidence':'weak_alignment',
    'low_recognizer_confidence':'low_recognizer_confidence'}
EXPLAIN = {'words_not_heard':'caption words were not heard in the audio','words_missing_from_captions':'the speech has words the caption lacks',
    'weak_alignment':'too little reliable alignment to this cue','low_recognizer_confidence':'the recognizer was unsure of some words',
    'multi_word_rewrite':'more than one word would change','possible_name_or_number':'the word may be a name or a number',
    'weak_context':'too few surrounding words matched','weak_corroboration':'the heard word is neither confident, similar to the caption word, nor a common-word swap inside fully matched context',
    'unsupported_text':'this wording cannot be edited safely in place','timing_not_clear':'cue displacement is not consistent or is too large',
    'would_overlap_neighbour':'the new timing would overlap a neighbouring cue'}

def _text(row, previous):
    """Return (new_text, evidence) for a clear one-word replacement, else (None, reason)."""
    edits = row['edits']
    if len(edits) != 1 or edits[0]['op'] != 'replace' or len(edits[0]['caption']) != 1 or len(edits[0]['heard']) != 1: return None, 'multi_word_rewrite'
    edit = edits[0]; old, new = edit['caption'][0], edit['heard'][0]; text = row['original']['text']
    spans = [m for m in WORD.finditer(text) if m.group()[0] != '<']
    p = edit['caption_index']
    if len(spans) != len(tokens(text)) or not 0 <= p < len(spans) or spans[p].group().casefold().replace('\u2019', "'") != old: return None, 'unsupported_text'
    raw = spans[p].group()
    if re.search(r'[\u3400-\u9fff\u3040-\u30ff]', raw + new): return None, 'unsupported_text'
    sentence_start = p == 0 and (previous is None or bool(SENTENCE_END.search(previous['original']['text'])))
    if any(c.isdigit() for c in raw + new) or (len(raw) > 1 and raw[:1].isupper() and not sentence_start): return None, 'possible_name_or_number'
    if row['matched_words'] < CLEAR_MIN_MATCHED or row['matched_word_coverage'] < CLEAR_MIN_COVERAGE: return None, 'weak_context'
    confidence = edit['heard_confidence'][0]; similarity = round(SequenceMatcher(None, old, new).ratio(), 3)
    common = (old.casefold() in COMMON_WORDS and new.casefold() in COMMON_WORDS and 0 < p < len(spans) - 1
              and row['matched_words'] == row['caption_words'] - 1 and (confidence is None or confidence >= .5))
    if not (confidence is not None and confidence >= CLEAR_MIN_CONFIDENCE or similarity >= CLEAR_MIN_SIMILARITY or common): return None, 'weak_corroboration'
    replacement = new[:1].upper() + new[1:] if raw[:1].isupper() else new
    return text[:spans[p].start()] + replacement + text[spans[p].end():], {'from': raw, 'to': replacement, 'heard_confidence': confidence, 'spelling_similarity': similarity, 'common_word_context': common}

def _timing(row):
    """Return (start, end, evidence) when the whole cue is displaced consistently, else (None, None, reason)."""
    cue = row['original']; s, e = row['suggested_start_ms'], row['suggested_end_ms']
    if s is None or row['matched_words'] < CLEAR_MIN_MATCHED or row['matched_word_coverage'] < CLEAR_MIN_COVERAGE: return None, None, 'weak_context'
    ds, de = s - cue['start_ms'], e - cue['end_ms']
    if abs(ds) >= START_ONLY_MIN_SHIFT_MS and abs(de) <= END_AGREES_MS and abs(ds) <= CLEAR_MAX_SHIFT_MS and s < cue['end_ms']:
        # fully matched cue whose end already agrees with the speech: only the start is wrong, so move only the start
        return s, cue['end_ms'], {'from_ms': [cue['start_ms'], cue['end_ms']], 'to_ms': [s, cue['end_ms']], 'start_shift_ms': ds, 'end_shift_ms': 0, 'start_only': True}
    if max(abs(ds), abs(de)) > CLEAR_MAX_SHIFT_MS or abs(ds - de) > CLEAR_MAX_SPREAD_MS or s >= e: return None, None, 'timing_not_clear'
    return s, e, {'from_ms': [cue['start_ms'], cue['end_ms']], 'to_ms': [s, e], 'start_shift_ms': ds, 'end_shift_ms': de}

def propose(rows):
    """Classify every reviewed cue as unchanged, clear (decision ready to export) or ambiguous (left to a human).

    A cue is clear only when its flags are limited to word_disagreement/timing_change and
      text: exactly one caption word replaced by one heard word, not a name/number/CJK, with at least
            CLEAR_MIN_MATCHED matched words, coverage >= CLEAR_MIN_COVERAGE, and the heard word either
            confident (>= CLEAR_MIN_CONFIDENCE) or spelled similarly (>= CLEAR_MIN_SIMILARITY), or both words are
            COMMON_WORDS in the middle of a cue whose every other word matched;
      timing: matched words cover the cue (same thresholds) and start and end move by the same amount
            (within CLEAR_MAX_SPREAD_MS, at most CLEAR_MAX_SHIFT_MS) without overlapping a neighbour.
    Everything else with a problem flag is ambiguous. Evidence is recognizer alignment, not listening."""
    plan = []; timed = {}
    for n, row in enumerate(rows):
        flags = set(row['flags']); item = {'cue_id': row['cue_id'], 'row': row, 'reasons': [], 'changes': {}}
        plan.append(item)
        if flags <= {'low_recognizer_confidence'}: item['skip'] = True; continue
        blocking = sorted({BLOCKING[f] for f in flags if f in BLOCKING})
        if blocking: item['reasons'] = blocking; continue
        if 'word_disagreement' in flags:
            new_text, evidence = _text(row, rows[n - 1] if n else None)
            if new_text is None: item['reasons'].append(evidence)
            else: item['changes']['text'] = (new_text, evidence)
        if 'timing_change' in flags:
            s, e, evidence = _timing(row)
            if s is None: item['reasons'].append(evidence)
            else: timed[n] = (s, e, evidence)
    def effective(n):
        return (timed[n][0], timed[n][1]) if n in timed else (rows[n]['original']['start_ms'], rows[n]['original']['end_ms'])
    for n in list(timed):
        for m in (n - 1, n + 1):
            if 0 <= m < len(rows) and (effective(n)[0] < effective(m)[1] and effective(m)[0] < effective(n)[1]) and not (rows[n]['original']['start_ms'] < rows[m]['original']['end_ms'] and rows[m]['original']['start_ms'] < rows[n]['original']['end_ms']):
                plan[n]['reasons'].append('would_overlap_neighbour'); del timed[n]; break
    for n, entry in timed.items(): plan[n]['changes']['timing'] = entry
    cues = []; unchanged = []
    for item in plan:
        row = item['row']
        if item.get('skip') or not (item['changes'] or item['reasons']): unchanged.append(item['cue_id']); continue
        entry = {'cue_id': item['cue_id'], 'original_text': row['original']['text']}
        if item['changes']:
            decision = {'cue_id': item['cue_id']}; evidence = {'matched_words': row['matched_words'], 'caption_words': row['caption_words'], 'coverage': row['matched_word_coverage']}
            if 'text' in item['changes']: decision['text'] = item['changes']['text'][0]; evidence['text'] = item['changes']['text'][1]; entry['new_text'] = decision['text']
            if 'timing' in item['changes']: decision['use_timing'] = True; evidence['timing'] = item['changes']['timing'][2]
            entry.update(status='clear', changes=sorted(item['changes']), decision=decision, evidence=evidence)
            if item['reasons']: entry['also_ambiguous'] = item['reasons']; entry['explanation'] = '; '.join(EXPLAIN[r] for r in item['reasons'])
        else:
            entry.update(status='ambiguous', reasons=item['reasons'], explanation='; '.join(EXPLAIN[r] for r in item['reasons']), heard_text=row['recognized_text'])
        cues.append(entry)
    clear = sum(c['status'] == 'clear' for c in cues)
    return {'total': len(rows), 'clear': clear, 'ambiguous': len(cues) - clear, 'unchanged': len(unchanged), 'cues': cues, 'unchanged_cue_ids': unchanged,
        'notice': 'Clear cues are alignment-backed by the recognizer, not listened to. Ambiguous cues are not applied and need a human.'}
