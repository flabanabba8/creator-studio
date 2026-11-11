"""Validate an explicitly supplied video timeline without network or publishing."""
STORAGE_NAMESPACE = 'creator-studio-youtube'  # separate plugin-data folder for this part
import json
import html
import math
import re
from pathlib import Path


def stamp(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def vtt_stamp(value):
    ms = round(value * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{sec:02d}.{ms:03d}'


def seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Times must be finite nonnegative seconds')
    return value


def check_timeline(duration, chapters, captions):
    duration = seconds(duration)
    if not 0 < duration <= 86400:
        raise ValueError('Duration must be positive and at most one day')
    if not isinstance(chapters, list) or not (len(chapters) == 0 or 2 <= len(chapters) <= 500):
        raise ValueError('Supply no chapters or at least two ordered chapters')
    clean = []
    for c in chapters:
        if not isinstance(c, dict) or set(c) != {'start', 'title'} or not isinstance(c['title'], str) or not c['title'].strip() or len(c['title']) > 200 or c['title'].splitlines() != [c['title']]:
            raise ValueError('Each chapter needs a single-line title and start')
        start = seconds(c['start'])
        if start != int(start) or start >= duration:
            raise ValueError('Chapter starts must be whole seconds within the video')
        clean.append((start, c['title'].strip()))
    if clean and (clean[0][0] != 0 or any(b[0] - a[0] < 5 for a, b in zip(clean, clean[1:])) or duration - clean[-1][0] < 5):
        raise ValueError('Chapters must begin at zero and each span at least 5 seconds')
    if not isinstance(captions, list) or len(captions) > 10000:
        raise ValueError('Provide a captions list of at most 10,000 cues')
    last = 0
    vtt, srt = ['WEBVTT', ''], []
    for cue in captions:
        if not isinstance(cue, dict) or set(cue) != {'start', 'end', 'text'} or not isinstance(cue['text'], str) or not cue['text'].strip() or len(cue['text']) > 4000:
            raise ValueError('Each caption needs start, end and text')
        start, end = seconds(cue['start']), seconds(cue['end'])
        if start < last or end <= start or end > duration:
            raise ValueError('Captions must be ordered, non-overlapping and within duration')
        if round(start * 1000) >= round(end * 1000) or re.search(r'\n[ \t]*\n', cue['text']) or any(c in cue['text'] for c in ('\r', '\u0085', '\u2028', '\u2029')) or '-->' in cue['text'] or any(ord(c) < 32 and c != '\n' for c in cue['text']):
            raise ValueError('Caption text or millisecond timing is not valid for WebVTT')
        vtt.extend([f'{vtt_stamp(start)} --> {vtt_stamp(end)}', html.escape(cue['text'].strip(), quote=False), ''])
        srt.extend([str(len(srt) // 4 + 1), f"{vtt_stamp(start).replace('.', ',')} --> {vtt_stamp(end).replace('.', ',')}", cue['text'].strip(), ''])
        last = end
    return {'captions_webvtt': '\n'.join(vtt), 'captions_srt': '\n'.join(srt), 'chapters_description': '\n'.join(f'{stamp(start)} {title}' for start, title in clean), 'caption_count': len(captions), 'srt_markup_warning': any('<' in cue['text'] or '>' in cue['text'] for cue in captions), 'notice': 'Times are supplied by the user and not checked against media; captions and chapter titles require editorial review. SRT readers may interpret angle brackets as markup; check their display. Platform eligibility and rendering are not verified.'}


def description(blurb, duration, chapters, sources, footer=''):
    for label, value, limit in (('blurb', blurb, 1500), ('footer', footer, 1000)):
        if not isinstance(value, str) or len(value) > limit or label == 'blurb' and not value.strip(): raise ValueError(f'{label} must be text of at most {limit} characters' + (' and not empty' if label == 'blurb' else ''))
    if not isinstance(sources, list) or len(sources) > 100 or any(not isinstance(x, str) or not x.strip() or x.splitlines() != [x] or len(x) > 1000 for x in sources):
        raise ValueError('sources must be up to 100 single-line references')
    block = check_timeline(duration, chapters, [])['chapters_description']
    parts = [blurb.strip()]
    if block: parts.append(block)
    if sources: parts.append('Sources:\n' + '\n'.join(dict.fromkeys(x.strip() for x in sources)))
    if footer.strip(): parts.append(footer.strip())
    text = '\n\n'.join(parts)
    if len(text) > 5000: raise ValueError('Description is longer than 5,000 characters; shorten the blurb, sources or footer')
    return {'description': text, 'characters': len(text), 'chapters_included': bool(block),
            'youtube_chapter_list_note': ('' if len(chapters) >= 3 and all(b['start'] - a['start'] >= 10 for a, b in zip(chapters, chapters[1:])) else 'YouTube itself only shows a chapter list in the player when there are at least three chapters of ten seconds or more; shorter ones stay readable in the description.'), 'notice': 'Plain text assembled from supplied values. Chapter times and sources are not verified, and platform limits and rules should be checked on the platform before posting. Nothing was posted.'}


def invoke(name, args, ctx=None, **context):
    try:
        if name=='youtube_make_visual':
            from plugins.plugin_storage import plugin_data_dir
            from .visuals import make_visual
            args=dict(args);project_id=args.pop('project_id',None);section_index=args.pop('section_index',None)
            result=make_visual(plugin_data_dir(STORAGE_NAMESPACE),**args)
            if project_id is not None or section_index is not None:
                from .media_project import MediaProject
                if project_id is None or section_index is None:raise ValueError('Give both project_id and section_index to attach the graphic to a section')
                row=MediaProject(plugin_data_dir(STORAGE_NAMESPACE),'video').add_asset(project_id,result['output_path'],'image',section_index,'Drawn by youtube_make_visual from the supplied data (%s: %s); full 1920x1080 frame with label limits enforced; it is the picture of this section.'%(result.get('provenance',{}).get('kind','data'),result.get('provenance',{}).get('note','')))
                result=dict(result,attached_to_section=section_index,asset_id=row['asset_id'])
            return json.dumps(result)
        if name=='youtube_generate_image':
            tool=ctx.get_config('native_image_tool')if ctx is not None else None
            if not tool or not callable(getattr(ctx,'dispatch_tool',None)):raise ValueError('No selected native image tool in this host. Generate directly with the main agent’s native image tool and attach its actual file, or configure a compatible registered image tool. No image was generated.')
            if tool==name:raise ValueError('Select an actual native provider tool; a recursive bridge is not a backend')
            return ctx.dispatch_tool(tool,args['arguments'],**{k:context[k]for k in ('parent_agent','session_id','task_id')if k in context})
        from .media_project import MediaProject, schemas
        project_tools=schemas('youtube')
        if name in project_tools:
            from plugins.plugin_storage import plugin_data_dir
            project=MediaProject(plugin_data_dir(STORAGE_NAMESPACE),'video')
            return json.dumps(getattr(project,project_tools[name][3])(**args))
        if name == 'youtube_render_short':
            from plugins.plugin_storage import plugin_data_dir
            from .short import render_short
            return json.dumps(render_short(plugin_data_dir(STORAGE_NAMESPACE), **args))
        if name == 'youtube_make_slides':
            from plugins.plugin_storage import plugin_data_dir
            from .deck import make_slides
            args = dict(args); project_id = args.pop('project_id', None); indexes = args.pop('section_indexes', None)
            result = make_slides(plugin_data_dir(STORAGE_NAMESPACE), **args)
            if project_id is not None:
                from .media_project import MediaProject
                indexes = list(range(len(result['slides']))) if indexes is None else indexes
                if not isinstance(indexes, list) or len(indexes) != len(result['slides']): raise ValueError('section_indexes needs one zero-based section number per slide')
                project = MediaProject(plugin_data_dir(STORAGE_NAMESPACE), 'video')
                result['attached'] = [{'slide': k, 'section_index': i, 'asset_id': project.add_asset(project_id, x['path'], 'image', i, 'Drawn by youtube_make_slides from the outline (title and bullets as given); not yet inspected, so look at it before assembling.')['asset_id']} for k, (x, i) in enumerate(zip(result['slides'], indexes))]
            elif indexes is not None: raise ValueError('section_indexes needs project_id')
            return json.dumps(result)
        if name == 'youtube_render_slides':
            from plugins.plugin_storage import plugin_data_dir
            from .slides import render_slides
            return json.dumps(render_slides(plugin_data_dir(STORAGE_NAMESPACE), **args))
        if name == 'youtube_description':
            return json.dumps(description(**args))
        if name in ('youtube_render_still', 'youtube_render_clips', 'youtube_stitch_segments'):
            from plugins.plugin_storage import plugin_data_dir
            from .render import render_still, render_clips, stitch_segments
            method = {'youtube_render_still': render_still, 'youtube_render_clips': render_clips, 'youtube_stitch_segments': stitch_segments}[name]
            return json.dumps(method(plugin_data_dir(STORAGE_NAMESPACE), **args))
        return json.dumps(check_timeline(**args))
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        return json.dumps({'error': str(exc)})


def register(ctx):
    for tool_name,description,props,required in [('youtube_make_visual','Create an actual chart, table or flowchart PNG from explicit data with labeled provenance. No model request or invented research data.',{'kind':{'type':'string','enum':['bar','line','table','flowchart','cycle']},'title':{'type':'string'},'data':{'type':'object','description':'Bar: labels and values arrays. Line: values and optional strictly increasing x arrays. Table: columns array and rows arrays. Flowchart: nodes [{id,label}] and edges [{from,to,label?}], forming an acyclic graph. Cycle: nodes [{label}] in order, 3 to 10; the last leads back to the first (use it for a repeating cycle such as the eight Moon phases).'},'provenance':{'type':'object','properties':{'kind':{'type':'string','enum':['sourced','measurement','illustrative']},'note':{'type':'string','minLength':1,'maxLength':180,'description':'Short printable source, measurement or illustrative-data explanation.'}},'required':['kind','note']},'project_id':{'type':'string','description':'Optional: the lesson project to attach this graphic to.'},'section_index':{'type':'integer','minimum':0,'description':'With project_id: the zero-based script section this graphic explains. It becomes that section\'s picture in the assembled video (full frame).'}},['kind','title','data','provenance']),('youtube_generate_image','Invoke the explicitly selected native host image tool in the current session. Host owns model/auth/approvals; images must be inspected directly in the MAIN session before attaching to the project. Missing interface is an error, never placeholder success.',{'arguments':{'type':'object'}},['arguments'])]:
        ctx.register_tool(name=tool_name,toolset='youtube_video_studio',schema={'name':tool_name,'description':description,'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}},handler=lambda args,_name=tool_name,**kw:invoke(_name,args,ctx,**kw))
    from .media_project import schemas
    for tool_name,(description,properties,required,method) in schemas('youtube').items():
        ctx.register_tool(name=tool_name,toolset='youtube_video_studio',schema={'name':tool_name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}},handler=lambda args,_name=tool_name,**kw:invoke(_name,args))
    ctx.register_tool(name='youtube_make_slides', toolset='youtube_video_studio', schema={'name': 'youtube_make_slides', 'description': 'Make 1-40 plain 1920x1080 slide images from a text outline: title, up to six bullets, an optional picture and speaker notes, in a light, dark or kids theme. CPU-only and local. With project_id the slides are attached as the pictures of the lesson sections for you (this is how every text section gets its picture; no image-generation tool is needed). Returns image paths; check fit, legibility and picture rights yourself.', 'parameters': {'type': 'object', 'properties': {'slides': {'type': 'array', 'minItems': 1, 'maxItems': 40}, 'theme': {'type': 'string', 'enum': ['light', 'dark', 'kids', 'terminal']}, 'allow_profile_media': {'type': 'boolean'}, 'project_id': {'type': 'string', 'description': 'Optional: attach each slide as the picture of a section of this lesson project.'}, 'section_indexes': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'description': 'With project_id: the zero-based script section for each slide, in order (default: sections 0, 1, 2 ...).'}}, 'required': ['slides'], 'additionalProperties': False}}, handler=lambda args, **kwargs: invoke('youtube_make_slides', args))
    ctx.register_tool(name='youtube_render_slides', toolset='youtube_video_studio', schema={'name': 'youtube_render_slides', 'description': 'Render 1-12 explicitly selected still images (each 1-120 seconds, optional slow zoom_in, zoom_out, pan_left or pan_right) with narration and captions into a 1-120 second CPU-only 1280x720 MP4. Needs no video model. Returns a segment ID that youtube_stitch_segments can join. Nothing is uploaded.', 'parameters': {'type': 'object', 'properties': {'slides': {'type': 'array', 'minItems': 1, 'maxItems': 12}, 'audio_path': {'type': 'string'}, 'chapters': {'type': 'array'}, 'captions': {'type': 'array'}, 'allow_profile_media': {'type': 'boolean'}, 'burn_captions': {'type': 'boolean'}, 'audio_start': {'type': 'number', 'minimum': 0}}, 'required': ['slides', 'audio_path', 'chapters', 'captions'], 'additionalProperties': False}}, handler=lambda args, **kwargs: invoke('youtube_render_slides', args))
    ctx.register_tool(name='youtube_render_short', toolset='youtube_video_studio', schema={'name': 'youtube_render_short', 'description': 'Cut a 1-60 second vertical 1080x1920 promo from one explicitly selected local horizontal video with an optional header, footer and burned caption cues. CPU-only, private output, nothing uploaded; check legibility and sync yourself.', 'parameters': {'type': 'object', 'properties': {'video_path': {'type': 'string'}, 'start': {'type': 'number', 'minimum': 0}, 'duration': {'type': 'number', 'minimum': 1, 'maximum': 60}, 'header': {'type': 'string', 'maxLength': 60}, 'footer': {'type': 'string', 'maxLength': 60}, 'captions': {'type': 'array', 'maxItems': 500}, 'allow_profile_media': {'type': 'boolean'}}, 'required': ['video_path', 'start', 'duration'], 'additionalProperties': False}}, handler=lambda args, **kwargs: invoke('youtube_render_short', args))
    ctx.register_tool(name='youtube_description', toolset='youtube_video_studio', schema={'name': 'youtube_description', 'description': 'Assemble a plain-text video description from a blurb, whole-second chapters, source references and an optional footer. Does not verify anything or post.', 'parameters': {'type': 'object', 'properties': {'blurb': {'type': 'string'}, 'duration': {'type': 'number'}, 'chapters': {'type': 'array'}, 'sources': {'type': 'array'}, 'footer': {'type': 'string'}}, 'required': ['blurb', 'duration', 'chapters', 'sources'], 'additionalProperties': False}}, handler=lambda args, **kwargs: invoke('youtube_description', args))
    ctx.register_skill('create-youtube-video', Path(__file__).parent / 'skills/create-youtube-video/SKILL.md', description='Plan a sourced video and prepare and review its timeline, chapters and captions.')
    ctx.register_tool(name='youtube_stitch_segments', toolset='youtube_video_studio', schema={'name': 'youtube_stitch_segments', 'description': 'Join 1–60 selected video segment IDs and encode one explicitly selected original audio track once. Segment audio, subtitles and chapters are omitted; verify final timing.', 'parameters': {'type': 'object', 'properties': {'segment_ids': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': {'type': 'string'}}, 'audio_path': {'type': 'string'}, 'audio_start': {'type': 'number', 'minimum': 0, 'maximum': 7200}, 'audio_pad_seconds': {'type': 'number', 'minimum': 0, 'maximum': 10}, 'allow_profile_media': {'type': 'boolean'}}, 'required': ['segment_ids', 'audio_path'], 'additionalProperties': False}}, handler=lambda args, **kw: invoke('youtube_stitch_segments', args))
    ctx.register_tool(name='youtube_render_clips', toolset='youtube_video_studio', schema={'name': 'youtube_render_clips', 'description': 'Render 1–6 selected local video clips into a 1–120 second sequence with narration and optional captions, using one CPU encoder thread. Source clip audio is omitted. No upload.', 'parameters': {'type': 'object', 'properties': {'clips': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'seconds': {'type': 'number', 'minimum': 1, 'maximum': 120}, 'start': {'type': 'number', 'minimum': 0, 'maximum': 7200}}, 'required': ['path', 'seconds'], 'additionalProperties': False}}, 'audio_path': {'type': 'string'}, 'audio_start': {'type': 'number', 'minimum': 0, 'maximum': 7200}, 'allow_profile_media': {'type': 'boolean'}, 'chapters': {'type': 'array'}, 'captions': {'type': 'array'}}, 'required': ['clips', 'audio_path', 'chapters', 'captions'], 'additionalProperties': False}}, handler=lambda args, **kw: invoke('youtube_render_clips', args))
    ctx.register_tool(name='youtube_render_still', toolset='youtube_video_studio', schema={'name': 'youtube_render_still', 'description': 'Render a local 1–120 second still-image video from explicitly selected trusted image and narration, with optional captions, using one CPU encoder thread. No upload.', 'parameters': {'type': 'object', 'properties': {'image_path': {'type': 'string'}, 'audio_path': {'type': 'string'}, 'audio_start': {'type': 'number', 'minimum': 0, 'maximum': 7200}, 'allow_profile_media': {'type': 'boolean', 'description': 'Allow selected media under the active profile plugin-data directory.'}, 'duration': {'type': 'number'}, 'chapters': {'type': 'array'}, 'captions': {'type': 'array'}}, 'required': ['image_path', 'audio_path', 'duration', 'chapters', 'captions'], 'additionalProperties': False}}, handler=lambda args, **kw: invoke('youtube_render_still', args))
    ctx.register_tool(name='youtube_check_timeline', toolset='youtube_video_studio', schema={'name': 'youtube_check_timeline', 'description': 'Check supplied chapter and caption times and format a contiguous chapter block and WebVTT/SRT captions; no media or platform access.', 'parameters': {'type': 'object', 'properties': {'duration': {'type': 'number'}, 'chapters': {'type': 'array'}, 'captions': {'type': 'array'}}, 'required': ['duration', 'chapters', 'captions'], 'additionalProperties': False}}, handler=lambda args, **kw: invoke('youtube_check_timeline', args))

