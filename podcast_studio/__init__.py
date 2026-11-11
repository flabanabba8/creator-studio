"""Local source-aware podcast script and editorial-receipt checks."""
STORAGE_NAMESPACE = 'creator-studio-podcast'  # separate plugin-data folder for this part
import hashlib
import json
import math
import re
from pathlib import Path


def check_script(segments):
    if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
        raise ValueError('Provide 1 to 100 ordered segments')
    output = []
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {'title', 'sources', 'turns'}:
            raise ValueError('Each segment needs title, sources and turns')
        title, sources, turns = segment['title'], segment['sources'], segment['turns']
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('Invalid segment title')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 30 or any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in sources):
            raise ValueError('Provide source references for every segment')
        if not isinstance(turns, list) or not 1 <= len(turns) <= 500:
            raise ValueError('Provide dialogue turns for each segment')
        words = 0
        for turn in turns:
            if not isinstance(turn, dict) or set(turn) != {'speaker', 'text'} or any(not isinstance(turn[x], str) or not turn[x].strip() for x in ('speaker', 'text')) or len(turn['text']) > 10000:
                raise ValueError('Each turn needs a speaker and text')
            words += len(turn['text'].split())
        digest = hashlib.sha256(json.dumps(segment, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        output.append({'title': title, 'sha256': digest, 'turns': len(turns), 'words': words})
    return {'segments': output, 'notice': 'Sources and dialogue are unverified; a full source and editorial review is still required.'}


def check_review(segments, review):
    script = check_script(segments)
    if not isinstance(review, dict) or set(review) != {'reviewer', 'segments'} or not isinstance(review['reviewer'], str) or not review['reviewer'].strip() or not isinstance(review['segments'], list):
        raise ValueError('Provide a reviewer and ordered segment review records')
    records = review['segments']
    if len(records) != len(script['segments']):
        raise ValueError('Review must cover every segment')
    for expected, record in zip(script['segments'], records):
        if not isinstance(record, dict) or record.get('sha256') != expected['sha256']:
            raise ValueError('Script changed or review coverage is incomplete')
        if any(not isinstance(record.get(k), str) or not record[k].strip() for k in ('purpose', 'opening_check', 'source_check', 'edits')):
            raise ValueError('Each review needs purpose, opening_check, source_check and edits')
    return {'status': 'review_record_matches_script', 'segments': len(records), 'notice': 'Review is self-attested; matching hashes do not verify source claims or editorial quality.'}


def pagecast_plan(segments, review):
    check_review(segments, review)
    lines, assignments = [], []
    for segment_index, segment in enumerate(segments):
        for turn in segment['turns']:
            text, speaker = turn['text'].strip(), turn['speaker'].strip()
            if text.splitlines() != [text] or not any(c.isalnum() for c in text):
                raise ValueError('Each PageCast turn must be one speakable line')
            if len(speaker) > 80 or any(ord(c) < 32 for c in speaker):
                raise ValueError('PageCast speakers must be at most 80 printable characters')
            assignments.append({'paragraph': len(lines), 'speaker': speaker, 'segment_index': segment_index})
            lines.append(text)
    if len(lines) > 1000 or sum(len(line) + 1 for line in lines) > 1_000_000:
        raise ValueError('PageCast draft exceeds the turn or character limit')
    text = '\n'.join(lines)
    return {'text': text, 'source_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'assignments': assignments,
            'notice': 'Import text into PageCast, inspect every resulting paragraph and assign all of its passage IDs to the listed speaker. PageCast may split turns. Review is self-attested; no speech was generated.'}


def show_notes(segments, starts):
    check_script(segments)
    if not isinstance(starts, list) or len(starts) != len(segments) or any(type(x) is not int or not 0 <= x <= 86400 for x in starts):
        raise ValueError('Provide one whole-second chapter start for each segment')
    if starts[0] != 0 or any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError('Chapter starts must begin at zero and increase')
    def timestamp(value):
        h, rem = divmod(value, 3600)
        m, sec = divmod(rem, 60)
        return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'
    chapters, references = [], []
    for segment, start in zip(segments, starts):
        title = segment['title'].strip()
        if title.splitlines() != [title] or any(ord(c) < 32 for c in title): raise ValueError('Chapter titles must be single-line printable text')
        chapters.append(f'{timestamp(start)} {title}')
        for source in segment['sources']:
            if source.splitlines() != [source] or any(ord(c) < 32 for c in source): raise ValueError('Source references must be single-line printable text')
            if source not in references: references.append(source)
    return {'chapters': chapters, 'sources': references,
            'notice': 'Times and source references are supplied by the caller, not verified against audio or source content.'}


def check_pagecast_cast(assignments, passages, total, expected_source_sha256, actual_source_sha256, source_text_status):
    if any(not isinstance(x, str) or not re.fullmatch(r'[0-9a-f]{64}', x) for x in (expected_source_sha256, actual_source_sha256)):
        raise ValueError('Source fingerprints must be lowercase SHA-256')
    if expected_source_sha256 != actual_source_sha256: raise ValueError('Book came from a different original source')
    if source_text_status != 'unchanged': raise ValueError('PageCast text changed or its import baseline is unavailable; review the current script')
    if not isinstance(assignments, list) or not 1 <= len(assignments) <= 1000:
        raise ValueError('Provide the complete PageCast assignment map')
    expected = {}
    for row in assignments:
        if not isinstance(row, dict) or type(row.get('paragraph')) is not int or row['paragraph'] < 0 or not isinstance(row.get('speaker'), str) or not row['speaker'].strip() or len(row['speaker']) > 80 or any(ord(c) < 32 for c in row['speaker']):
            raise ValueError('Each assignment needs a paragraph and speaker')
        if row['paragraph'] in expected: raise ValueError('Duplicate assignment paragraph')
        expected[row['paragraph']] = row['speaker']
    if list(expected) != list(range(len(expected))): raise ValueError('Assignment paragraphs must be complete and ordered from zero')
    if type(total) is not int or not 1 <= total <= 10000 or not isinstance(passages, list) or len(passages) != total:
        raise ValueError('Provide every PageCast passage from all pages')
    seen, paragraphs, mismatches = set(), set(), []
    for row in passages:
        if not isinstance(row, dict) or type(row.get('id')) is not int or type(row.get('paragraph')) is not int or not isinstance(row.get('speaker'), str) or not row['speaker'].strip() or len(row['speaker']) > 80 or any(ord(c) < 32 for c in row['speaker']):
            raise ValueError('Each passage needs its ID, paragraph and speaker')
        ident, paragraph = row['id'], row['paragraph']
        if ident in seen or paragraph not in expected: raise ValueError('Duplicate passage or unknown paragraph')
        seen.add(ident); paragraphs.add(paragraph)
        if row['speaker'] != expected[paragraph]:
            mismatches.append({'passage_id': ident, 'paragraph': paragraph, 'expected_speaker': expected[paragraph], 'actual_speaker': row['speaker']})
    if seen != set(range(total)) or paragraphs != set(expected): raise ValueError('PageCast passage or paragraph coverage is incomplete')
    return {'status': 'matched' if not mismatches else 'mismatched', 'passages_checked': total,
            'mismatch_count': len(mismatches), 'mismatches': mismatches[:100], 'mismatches_omitted': max(0, len(mismatches)-100),
            'notice': 'All data and fingerprints are caller-supplied and not authenticated. This checks point-in-time assignments, not voice quality, source claims or changes after the check.'}


def caption_cues(passages, strip_higgs_tags=False, expected_source_sha256=None, actual_source_sha256=None, source_text_status=None):
    if type(strip_higgs_tags) is not bool: raise ValueError('strip_higgs_tags must be boolean')
    if (expected_source_sha256 is None) != (actual_source_sha256 is None): raise ValueError('Provide both source fingerprints or neither')
    if expected_source_sha256 is not None:
        if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in (expected_source_sha256, actual_source_sha256)):
            raise ValueError('Source fingerprints must be lowercase SHA-256')
        if expected_source_sha256 != actual_source_sha256: raise ValueError('Timeline came from a different original source')
    if source_text_status is not None:
        if source_text_status not in ('unchanged', 'changed', 'unavailable'): raise ValueError('Invalid PageCast source text status')
        if expected_source_sha256 is None: raise ValueError('Source text status requires both source fingerprints')
        if source_text_status != 'unchanged': raise ValueError('PageCast text changed or its import baseline is unavailable; review the current script')
    if not isinstance(passages, list) or not 1 <= len(passages) <= 100:
        raise ValueError('Provide 1 to 100 timed passages with text')
    cues, last = [], 0
    for item in passages:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str): raise ValueError('Each passage needs text and timing')
        start, end = item.get('start_seconds'), item.get('end_seconds')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)) or start < last or end <= start or end > 86400 or round(start*1000) >= round(end*1000):
            raise ValueError('Passage times must be ordered and non-overlapping')
        text = item['text']
        if strip_higgs_tags:
            text = re.sub(r'<\|(?:emotion|style|prosody|sfx):[A-Za-z0-9_]+\|>', '', text)
        text = text.strip()
        if not text or len(text) > 4000 or any(c in text for c in ('\r', '\u0085', '\u2028', '\u2029')) or '-->' in text or re.search(r'\n[ \t]*\n', text) or any(ord(c) < 32 and c != '\n' for c in text):
            raise ValueError('Passage text cannot form a valid caption cue')
        speaker = item.get('speaker')
        if speaker is not None and (not isinstance(speaker, str) or not speaker.strip() or len(speaker) > 80 or any(ord(c) < 32 for c in speaker)): raise ValueError('A passage speaker must be a printable name of at most 80 characters')
        cue = {'start': start, 'end': end, 'text': text}
        if speaker is not None: cue.update(speaker=speaker.strip(), label=speaker.strip() + ': ' + text)
        cues.append(cue)
        last = end
    binding = 'matched_original_import_and_unchanged_text' if source_text_status == 'unchanged' else 'matched_original_import' if expected_source_sha256 is not None else 'not_checked'
    return {'cues': cues, 'source_binding': binding, 'notice': 'Caller-supplied fingerprints and text status are not independently authenticated; without a text status, an import-hash match does not detect later edits. Text status does not cover speaker assignments. Caption text is supplied script, not a speech transcript; passage-level timing is approximate. Listen, check final media timing and review all captions.'}


def load_episode_tool(episode_dir, require_sources=True):
    from .episode import load_episode
    return load_episode(episode_dir, require_sources)


def lint_episode_tool(episode_dir, style=None, require_sources=True):
    from .episode import load_episode
    from .lint import lint
    episode = load_episode(episode_dir, require_sources)
    findings = lint(episode['segments'], episode['files'], style)
    errors = sum(f['severity'] == 'error' for f in findings)
    return {'status': 'blocked' if errors else 'clean', 'errors': errors, 'warnings': len(findings) - errors, 'findings': findings[:200], 'findings_omitted': max(0, len(findings) - 200),
            'notice': 'Mechanical spoken-word checks only. They cannot judge accuracy, clarity or humor; the full editorial review is still required.'}


def preflight_tool(episode_dir, style=None, require_sources=True, require_source_check=False):
    """The pre-TTS gate: lint must have no errors, and a self-attested review must match the exact current files."""
    from .episode import load_episode, check_review_file
    from .lint import lint
    if type(require_source_check) is not bool: raise ValueError('require_source_check must be boolean')
    episode = load_episode(episode_dir, require_sources)
    findings = lint(episode['segments'], episode['files'], style)
    errors = [f for f in findings if f['severity'] == 'error']
    if errors:
        return {'status': 'blocked', 'reason': 'lint errors', 'errors': len(errors), 'findings': findings[:100]}
    review = check_review_file(episode_dir, episode['segment_sha256'])
    result = {'status': 'passed', 'files': len(episode['files']), 'segment_sha256': episode['segment_sha256'], 'warnings': len(findings), 'review': review}
    from .episode import episode_files, read_bytes
    check = episode_files(episode_dir)[0] / 'source-check.md'
    if check.is_file() and not check.is_symlink():
        match = re.findall(r'^SUMMARY:\s*(\d+)\s+problems?\s+in\s+(\d+)\s+segments?', read_bytes(check).decode('utf-8', 'replace'), re.M)
        result['source_check'] = {'present': True, 'problems_reported': int(match[-1][0]) if match else None}
        if match and int(match[-1][0]):
            result['status'] = 'passed_with_open_source_problems'
            result['notice_source_check'] = 'The separate fact-check report lists problems; confirm each was fixed and recorded in the review edits, then rerun the check.'
        elif not match:
            result['source_check']['note'] = 'No "SUMMARY: N problems in M segments" line found.'
    elif require_source_check:
        return {'status': 'blocked', 'reason': 'source-check.md missing; run the separate fact-check pass first'}
    result['notice'] = 'The gate checks files and self-attested records. It does not verify sources, listen to audio or judge quality. Any dialogue edit changes the hashes and needs review again.'
    return result


TOOLS = {
    'podcast_start_from_video': ('Start a podcast project from a finished lesson video project: copies its saved source records (same source_ids and urls, marked as copied from the video) and its script notes. No web fetch, no model call; go straight to reading the sources locally and writing the script. For "make a podcast episode from that lesson".', {'video_project_id': {'type': 'string', 'description': 'Full 32-character video project ID (youtube_project_status with no project_id lists them).'}, 'audience': {'type': 'string'}}, ['video_project_id']),
    'podcast_load_episode': ('Read an episode folder (NN-slug.txt segments with # title: and # paper:/# source: headers, SPEAKER: lines, optional meta.json) into reviewable segments. Local files only; nothing is run or sent.', {'episode_dir': {'type': 'string'}, 'require_sources': {'type': 'boolean'}}, ['episode_dir']),
    'podcast_lint_episode': ('Mechanical spoken-word checks on an episode folder under an adjustable style profile (tags none/higgs, banned tags and phrases, spoken-number rule, disabled rules). Cannot judge accuracy or quality.', {'episode_dir': {'type': 'string'}, 'style': {'type': 'object'}, 'require_sources': {'type': 'boolean'}}, ['episode_dir']),
    'podcast_preflight': ('Pre-production gate for an episode folder: lint must have no errors and editorial-review.json must match the exact current segment files; optionally require a separate source-check.md. Self-attested; verifies no claims.', {'episode_dir': {'type': 'string'}, 'style': {'type': 'object'}, 'require_sources': {'type': 'boolean'}, 'require_source_check': {'type': 'boolean'}}, ['episode_dir']),
    'podcast_check_script': ('Fingerprint ordered sourced dialogue segments and report basic counts. Does not verify claims.', {'segments': {'type': 'array'}}, ['segments']),
    'podcast_check_pagecast_cast': ('Compare a complete PageCast passage list to the reviewed handoff speaker map. Requires matching caller-supplied source fingerprints and unchanged text status; does not change assignments or authenticate inputs.', {'assignments': {'type': 'array', 'minItems': 1, 'maxItems': 1000, 'items': {'type': 'object'}}, 'passages': {'type': 'array', 'minItems': 1, 'maxItems': 10000, 'items': {'type': 'object'}}, 'total': {'type': 'integer', 'minimum': 1, 'maximum': 10000}, 'expected_source_sha256': {'type': 'string'}, 'actual_source_sha256': {'type': 'string'}, 'source_text_status': {'type': 'string', 'enum': ['unchanged', 'changed', 'unavailable']}}, ['assignments', 'passages', 'total', 'expected_source_sha256', 'actual_source_sha256', 'source_text_status']),
    'podcast_mix_timeline': ('Mix 1–20 explicitly selected music beds over non-overlapping narration intervals into a private WAV. Times are milliseconds; optional explicit fades, no playback or automatic ducking.', {'narration_path': {'type': 'string'}, 'beds': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': {'type': 'object', 'properties': {'music_path': {'type': 'string'}, 'start_ms': {'type': 'integer', 'minimum': 0}, 'end_ms': {'type': 'integer', 'minimum': 1}, 'music_db': {'type': 'number', 'minimum': -30, 'maximum': 0}, 'fade_in_ms': {'type': 'integer', 'minimum': 0}, 'fade_out_ms': {'type': 'integer', 'minimum': 0}}, 'required': ['music_path', 'start_ms', 'end_ms', 'music_db'], 'additionalProperties': False}}, 'voice_db': {'type': 'number', 'minimum': -12, 'maximum': 0}, 'loudness_lufs': {'type': 'number', 'minimum': -30, 'maximum': -10}, 'allow_profile_media': {'type': 'boolean'}, 'import_from_project': {'type': 'boolean'}}, ['narration_path', 'beds']),
    'podcast_mix': ('Mix explicitly selected narration and music files into a private WAV without audio playback. Music loops; no automatic ducking. Check rights and listen before sharing.', {'narration_path': {'type': 'string'}, 'music_path': {'type': 'string'}, 'music_db': {'type': 'number', 'minimum': -30, 'maximum': 0}, 'voice_db': {'type': 'number', 'minimum': -12, 'maximum': 0}, 'loudness_lufs': {'type': 'number', 'minimum': -30, 'maximum': -10}, 'allow_profile_media': {'type': 'boolean'}, 'import_from_project': {'type': 'boolean'}}, ['narration_path', 'music_path']),
    'podcast_caption_cues': ('Prepare passage-timed draft caption cues from explicitly supplied PageCast timeline text. Text is script, not verified speech; no word-level timing.', {'passages': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': {'type': 'object', 'properties': {'start_seconds': {'type': 'number'}, 'end_seconds': {'type': 'number'}, 'text': {'type': 'string'}, 'speaker': {'type': 'string'}}, 'required': ['start_seconds', 'end_seconds', 'text']}}, 'strip_higgs_tags': {'type': 'boolean'}, 'expected_source_sha256': {'type': 'string'}, 'actual_source_sha256': {'type': 'string'}, 'source_text_status': {'type': 'string', 'enum': ['unchanged', 'changed', 'unavailable']}}, ['passages']),
    'podcast_show_notes': ('Prepare chapter labels and deduplicated source references from caller-supplied measured start times; does not inspect audio or verify sources.', {'segments': {'type': 'array'}, 'starts': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0}}}, ['segments', 'starts']),
    'podcast_pagecast_plan': ('Prepare reviewed dialogue for optional PageCast import with an explicit paragraph-to-speaker map. Does not render audio.', {'segments': {'type': 'array'}, 'review': {'type': 'object'}}, ['segments', 'review']),
    'podcast_check_review': ('Check a supplied full editorial review covers the current exact segments. Review is self-attested.', {'segments': {'type': 'array'}, 'review': {'type': 'object'}}, ['segments', 'review']),
}


def invoke(name, args):
    try:
        from .media_project import MediaProject, schemas
        project_tools=schemas('podcast')
        if name in project_tools:
            from plugins.plugin_storage import plugin_data_dir
            project=MediaProject(plugin_data_dir(STORAGE_NAMESPACE),'podcast')
            return json.dumps(getattr(project,project_tools[name][3])(**args))
        if name == 'podcast_start_from_video':
            from plugins.plugin_storage import plugin_data_dir
            from .media_project import MediaProject
            return json.dumps(MediaProject(plugin_data_dir(STORAGE_NAMESPACE),'podcast').start_from_video(plugin_data_dir('creator-studio-youtube'),**args))
        if name in ('podcast_mix', 'podcast_mix_timeline'):
            from plugins.plugin_storage import plugin_data_dir
            from .mix import mix, mix_timeline
            method = mix if name == 'podcast_mix' else mix_timeline
            return json.dumps(method(plugin_data_dir(STORAGE_NAMESPACE), **args))
        return json.dumps({'podcast_load_episode': load_episode_tool, 'podcast_lint_episode': lint_episode_tool, 'podcast_preflight': preflight_tool, 'podcast_check_script': check_script, 'podcast_check_review': check_review, 'podcast_pagecast_plan': pagecast_plan, 'podcast_check_pagecast_cast': check_pagecast_cast, 'podcast_show_notes': show_notes, 'podcast_caption_cues': caption_cues}[name](**args))
    except (TypeError, KeyError, ValueError, OSError, RuntimeError) as exc:
        return json.dumps({'error': str(exc)})


def register(ctx):
    from .media_project import schemas
    for tool_name,(description,properties,required,method) in schemas('podcast').items():
        ctx.register_tool(name=tool_name,toolset='podcast_studio',schema={'name':tool_name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}},handler=lambda args,_name=tool_name,**kw:invoke(_name,args))
    ctx.register_skill('create-podcast', Path(__file__).parent / 'skills/create-podcast/SKILL.md', description='Develop a source-backed podcast with an editorial review before production.')
    for name, (description, properties, required) in TOOLS.items():
        ctx.register_tool(name=name, toolset='podcast_studio', schema={'name': name, 'description': description, 'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}, handler=lambda args, _name=name, **kw: invoke(_name, args))
