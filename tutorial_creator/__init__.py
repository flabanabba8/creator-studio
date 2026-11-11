"""Hermes tools for controlled local demonstration recording."""
STORAGE_NAMESPACE = 'creator-studio-tutorial'  # separate plugin-data folder for this part
import json
import os
import threading
from pathlib import Path
from .core import Director, sources, window_pid, is_spreadsheet_grid, set_clipboard
from .narration import narrate
from . import gemini_speech


_step_lock = threading.Lock()

TOOLS = {
    'capture_sources': ('List local X11 windows and application audio streams. Native Wayland windows are not supported.', {
        'display': {'type': 'string', 'description': 'Optional local X11 display, such as :0.'}}, []),
    'capture_start': ('Start recording one selected visible X11 window. Optionally route ONE explicitly selected audio stream into a temporary recording sink; playback is muted until recording stops. Recording stops automatically at max_seconds.', {
        'window_id': {'type': 'string', 'description': 'Hex window ID returned by capture_sources.'},
        'display': {'type': 'string'}, 'max_seconds': {'type': 'number', 'minimum': 1, 'maximum': 1800},
        'capture_mode': {'type': 'string', 'enum': ['window', 'window_region'], 'description': 'window records the selected drawable. Explicit window_region records its fixed on-screen rectangle, including dialogs/overlapping pixels inside it. Use a private display; keep unrelated windows/notifications away, and do not move/resize the selected window.'},
        'show_cursor': {'type': 'boolean', 'description': 'Show the real pointer in the recording; useful for guided tutorials. Default false.'},
        'audio_stream': {'type': 'integer', 'minimum': 0, 'description': 'Optional exact audio stream ID returned by capture_sources; omitted means silent video.'}}, ['window_id']),
    'capture_status': ('Read recording state, media duration and step markers. With no job_id it lists the newest recordings with what each still needs (the resume path for "carry on"): export, narrate or nothing; already spoken cues are cached and never paid for twice.', {'job_id': {'type': 'string'}}, []),
    'capture_mark': ('Mark a demonstration step on the current media timeline, approximately half-second precision.', {
        'job_id': {'type': 'string'}, 'label': {'type': 'string', 'maxLength': 160}}, ['job_id', 'label']),
    'capture_stop': ('Stop this plugin-owned recording and restore its selected audio route.', {'job_id': {'type': 'string'}}, ['job_id']),
    'capture_export': ('Cut ordered segments from a completed recording into a checked H.264 MP4, at most 89 seconds. Original recording is preserved.', {
        'job_id': {'type': 'string'}, 'segments': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': {
            'type': 'object', 'properties': {'start': {'type': 'number', 'minimum': 0}, 'duration': {'type': 'number', 'minimum': .1}},
            'required': ['start', 'duration'], 'additionalProperties': False}}}, ['job_id', 'segments']),
    'tutorial_timeline': ('Read source-video or exported-video timestamps, including the mapping of recorded step markers through the chosen cuts.', {
        'job_id': {'type': 'string'}, 'export_name': {'type': 'string'}}, ['job_id']),
    'tutorial_frame': ('Decode a frame at a requested export timestamp so the agent can inspect what actually appears before writing narration. Returns a local PNG path; no image model is called.', {
        'job_id': {'type': 'string'}, 'export_name': {'type': 'string'}, 'seconds': {'type': 'number', 'minimum': 0}}, ['job_id', 'export_name', 'seconds']),
    'tutorial_narrate': ('Generate timestamped narration and mix it into a completed export. Default route: Gemini 3.8 Flash TTS with a Google sign-in held by Hermes, one request per cue, a named voice (see capture_sources, speech section) and a spend guard; other routes are a configured local speech service or a host speech tool. Measures every clip, refuses overruns without speeding/cutting speech, caches unchanged cues, and writes segment captions plus the speech credit and usage. Does not start or install a model.', {
        'job_id': {'type': 'string'}, 'export_name': {'type': 'string'}, 'import_from_project': {'type': 'boolean', 'description': 'Explicitly copy a configured voice reference from another project and record its origin.'}, 'cues': {'type': 'array', 'minItems': 1, 'maxItems': 20,
            'items': {'type': 'object', 'properties': {'start': {'type': 'number'}, 'end': {'type': 'number'}, 'text': {'type': 'string', 'maxLength': 300}},
                      'required': ['start', 'end', 'text'], 'additionalProperties': False}}}, ['job_id', 'export_name', 'cues']),
    'tutorial_step': ('Perform ONE computer-use action through Hermes\'s native tool, with its approvals unchanged, while a take is recording. Mark the attempt on the media timeline and return a fresh capture for verification. A tool acknowledgment is not proof the intended UI result occurred. Use only for the user-authorized tutorial task and the selected app.', {
        'job_id': {'type': 'string'}, 'label': {'type': 'string', 'maxLength': 160},
        'action': {'type': 'object', 'description': 'Arguments for the existing computer_use tool; use its current schema and a freshly observed target.'},
        'observe': {'type': 'object', 'description': 'Explicit app and window_id matching the recording; optional pid and capture mode.'}}, ['job_id', 'label', 'action', 'observe']),
}


def invoke(name, args, ctx=None, **kwargs):
    from plugins.plugin_storage import plugin_data_dir
    try:
        if name == 'capture_sources':
            result = sources(**args)
            result['speech'] = {'selected_route': (lambda v: v if isinstance(v, str) and v else 'gemini')(ctx.get_config('narration_backend')), 'gemini': gemini_speech.availability(),
                                'note': 'Choose a voice by name to fit the content (settings gemini_voice). One request per narration line; spend guard gemini_max_usd; no project value is shown.'}
        elif name == 'tutorial_narrate':
            keys = ('higgs_url', 'higgs_model', 'higgs_voice', 'higgs_revision', 'higgs_reference_audio', 'higgs_reference_text','narration_backend','host_tts_tool','host_tts_backend_id','host_tts_arguments','host_tts_model','host_tts_voice','host_tts_audio_field','host_tts_credit','host_tts_retry_nonce','speech_http_url','speech_http_model','speech_http_voice','speech_http_revision','speech_http_reference_audio','speech_http_reference_text','speech_http_credit','speech_http_fields','gemini_voice','gemini_model','gemini_max_usd','gemini_project')
            settings = {key: value for key in keys if (value := ctx.get_config(key)) is not None}
            forwarded={k:kwargs[k] for k in ('parent_agent','session_id','task_id') if k in kwargs}
            result = narrate(plugin_data_dir(STORAGE_NAMESPACE), **args, settings=settings,dispatch=lambda tool,arguments:ctx.dispatch_tool(tool,arguments,**forwarded))
        elif name == 'tutorial_step':
            return step(ctx, Director(plugin_data_dir(STORAGE_NAMESPACE)), **args, **kwargs)
        else:
            director = Director(plugin_data_dir(STORAGE_NAMESPACE))
            method = {'tutorial_timeline': 'timeline', 'tutorial_frame': 'frame'}.get(name, name.removeprefix('capture_'))
            result = getattr(director, method)(**args)
        if name == 'capture_start' and isinstance(result, dict):
            result['next'] = 'While this take records, perform every demonstrated action with tutorial_step (not computer_use directly) so each step is marked on the timeline and verified with a fresh capture.'
        return json.dumps(result)
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        return json.dumps({'error': str(exc)})


def step(ctx, director, job_id, label, action, observe, **kwargs):
    if not _step_lock.acquire(blocking=False):
        raise RuntimeError('Another tutorial step is in progress; wait for it to finish')
    try:
        return _step(ctx, director, job_id, label, action, observe, **kwargs)
    finally:
        _step_lock.release()


def _step(ctx, director, job_id, label, action, observe, **kwargs):
    if not isinstance(action, dict) or action.get('action') not in {'click', 'double_click', 'right_click', 'middle_click', 'drag', 'scroll', 'type', 'key', 'wait'}:
        raise ValueError('Choose one supported computer-use action')
    if any(action.get(k) is not None for k in ('element', 'from_element', 'to_element')):
        raise ValueError('Element-index actions are unsupported after target recapture; use freshly observed coordinates')
    if not isinstance(observe, dict) or not isinstance(observe.get('app'), str) or not observe['app'].strip():
        raise ValueError('Supply the explicit application name for the verification capture')
    if observe['app'].strip().lower() in ('screen', 'desktop'):
        raise ValueError('Observe the selected application, not the entire desktop')
    if action.get('app', observe['app']) != observe['app']:
        raise ValueError('The action and observation must target the same application')
    session_id = kwargs.get('session_id') or getattr(kwargs.get('parent_agent'), 'session_id', None)
    if not isinstance(session_id, str) or not session_id:
        raise ValueError('A Hermes session ID is required for isolated computer use')
    if director.status(job_id).get('state') != 'recording':
        raise ValueError('A recording must be active before a tutorial action')
    request = json.loads((director.job(job_id) / 'request.json').read_text())
    if request.get('display') != os.environ.get('DISPLAY'):
        raise ValueError('The recording and computer-use session must use the same X11 display')
    selected = request.get('window_id')
    supplied = observe.get('window_id')
    if isinstance(supplied, str):
        try: supplied = int(supplied, 0)
        except ValueError: raise ValueError('Use the recording window ID') from None
    if isinstance(supplied, bool) or not isinstance(supplied, int) or supplied != selected:
        raise ValueError('Observation window ID must match the recorded window')
    if action.get('window_id', selected) != selected:
        raise ValueError('Action window ID must match the recorded window')
    if observe.get('pid') is not None and (type(observe['pid']) is not int or observe['pid'] < 1):
        raise ValueError('PID must be a positive integer')
    converted = False
    if action.get('action') == 'type' and is_spreadsheet_grid(request.get('display'), selected):
        # Known limit: computer-use typing into a LibreOffice Calc grid makes the app grow until the
        # system kills it. Paste from the clipboard instead; the paste key still needs approval.
        set_clipboard(request.get('display'), action.get('text'))
        action = {k: v for k, v in action.items() if k not in ('text', 'action')}
        action.update(action='key', keys='ctrl+v')
        converted = True
    if action.get('action') == 'type' and not converted:
        text = action.get('text') if isinstance(action.get('text'), str) else ''
        if text.count('&&') > 1 or text.count(';') > 1 or '\n' in text.strip('\n') or len(text) > 110:
            raise ValueError('A teaching step shows ONE short command or entry (one idea). Split this into separate tutorial_step calls: no chained && or ; lists, no embedded newlines, at most 110 characters')
    target = {'app': observe['app'], 'window_id': selected}
    # Hermes computer use targets a window only with both its process ID and window ID;
    # without the pid it silently returns an empty capture. Use the window's own pid.
    pid = observe.get('pid') if observe.get('pid') is not None else window_pid(request.get('display'), selected)
    if pid is not None: target['pid'] = pid
    context = {k: kwargs[k] for k in ('parent_agent', 'task_id') if k in kwargs}
    context['session_id'] = session_id
    # Hermes input is delivered to a sticky target. Recapture the exact window
    # in the same session before dispatch; callers must avoid concurrent CUA calls.
    preflight = ctx.dispatch_tool('computer_use', {**target, 'action': 'capture', 'mode': 'ax'}, **context)
    try: captured = json.loads(preflight) if isinstance(preflight, str) else preflight
    except (TypeError, ValueError): return preflight
    if not isinstance(captured, dict) or captured.get('error') or captured.get('ok') is False or captured.get('mode') != 'ax':
        return preflight
    if captured.get('width') == 0 or captured.get('height') == 0:
        raise RuntimeError('Computer use could not target the recorded window (empty capture); no action was sent. Check that the application window is mapped, a window manager is running, and its pid matches the window')
    marker = director.mark(job_id, label)
    outcome = ctx.dispatch_tool('computer_use', {**action, 'app': observe['app']}, **context)
    try:
        result = json.loads(outcome) if isinstance(outcome, str) else outcome
    except (TypeError, ValueError):
        return outcome
    if not isinstance(result, dict): return outcome
    verdict = result.get('action_result') if isinstance(result.get('action_result'), dict) else result
    if verdict.get('error') or verdict.get('ok') is False or verdict.get('success') is False or verdict.get('status') in ('blocked', 'denied', 'cancelled', 'error'):
        return outcome
    if verdict.get('ok') is not True and verdict.get('success') is not True and verdict.get('status') not in ('success', 'completed', 'ok'):
        return outcome
    if result.get('_multimodal') is True and isinstance(result.get('content'), list):
        # The host already captured a frame after the action; preserve it without a second capture.
        note = {'marker': marker, 'action_acknowledged': True, 'verification': 'Review this fresh observation before narrating success'}
        if converted: note['pasted_instead_of_typed'] = 'Typing into a spreadsheet grid is refused; the text was pasted with ctrl+v. A multi-line paste opens the Text Import dialog: confirm it with Return.'
        summary = json.dumps({'tutorial_step': note})
        return {**result, 'content': [*result['content'], {'type': 'text', 'text': summary}],
                'text_summary': (str(result.get('text_summary') or '') + '\n' + summary).strip()}
    followup = {**target, 'action': 'capture'}
    if 'mode' in observe: followup['mode'] = observe['mode']
    capture = ctx.dispatch_tool('computer_use', followup, **context)
    try:
        observed = json.loads(capture) if isinstance(capture, str) else capture
    except (TypeError, ValueError):
        return capture
    if isinstance(observed, dict):
        note = {'marker': marker, 'action_acknowledged': True, 'verification': 'Review this fresh observation before narrating success'}
        if converted: note['pasted_instead_of_typed'] = 'Typing into a spreadsheet grid is refused; the text was pasted with ctrl+v. A multi-line paste opens the Text Import dialog: confirm it with Return.'
        if observed.get('_multimodal') is True and isinstance(observed.get('content'), list):
            # Keep native image blocks structured; never stringify image data into text.
            summary = json.dumps({'tutorial_step': note})
            return {**observed, 'content': [*observed['content'], {'type': 'text', 'text': summary}],
                    'text_summary': (str(observed.get('text_summary') or '') + '\n' + summary).strip()}
        observed['tutorial_step'] = note
        return json.dumps(observed)
    return capture


def register(ctx):
    ctx.register_skill('create-tutorial', Path(__file__).parent / 'skills/create-tutorial/SKILL.md')
    for name, (description, properties, required) in TOOLS.items():
        schema = {'name': name, 'description': description, 'parameters': {
            'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}
        ctx.register_tool(name=name, toolset='tutorial_creator', schema=schema,
                          handler=lambda args, _name=name, **kwargs: invoke(_name, args, ctx, **kwargs))
