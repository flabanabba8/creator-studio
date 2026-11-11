"""Mechanical dialogue checks distilled from a daily production show's script linter.

These catch spoken-word tells. They cannot judge accuracy, clarity or humor; the editorial review still must.
"""
import re

TAG = re.compile(r'<\|([a-z_]+)(?::([a-z_]+))?\|>')
HIGGS = {
    'emotion': {'affection', 'amusement', 'anger', 'arousal', 'awe', 'bitterness', 'confusion', 'contemplation', 'contentment', 'determination', 'disgust',
                'elation', 'enthusiasm', 'fear', 'helplessness', 'longing', 'pride', 'relief', 'sadness', 'shame', 'surprise'},
    'style': {'singing', 'shouting', 'whispering'},
    'sfx': {'cough', 'laughter', 'crying', 'screaming', 'burping', 'humming', 'sigh', 'sniff', 'sneeze'},
    'prosody': {'speed_very_slow', 'speed_slow', 'speed_fast', 'speed_very_fast', 'pitch_low', 'pitch_high', 'expressive_high', 'expressive_low', 'pause', 'long_pause'},
}
RULES = [  # (id, severity, regex, case-sensitive)
    ('director-voice', 'error', r"(?:^|[.!?]\s+)(?:(?:so|then|okay|now)[, ]+)*(?:let'?s\s+|I'?d\s+)?start\s+(?:with|there|here)\b", False),
    ('director-voice', 'error', r"\b(?:walk|talk) (?:me|us) through\b|\btake the romance out\b|\bgive (?:me|us) the (?:mechanism|setup|stakes)\b", False),
    ('director-voice', 'error', r"\b(set the scene|give (people|them|us|me) the picture|paint the picture|close the loop|strip the story off|steel-?man (it|that))\b", False),
    ('think-piece-opener', 'error', r"I'?ve been (staring|thinking|looking) at|I have a theory about", False),
    ('process-meta', 'error', r"sat with the feed|read the day'?s papers|looking for the thread|no theme today", False),
    ('enumeration', 'error', r"[Ll]et me name (the|what)", True),
    ('author-tell', 'error', r"organized around a single|the shape of (today|the day)|listen for it\b|[Ww]e'?ll come back to (it|that)\b", False),
    ('author-tell', 'error', r"\bthe whole (paper|thing|study|result|argument) in one\b|\bif you remember (one thing|nothing else)\b|\bin one (line|sentence)\b", False),
    ('running-order', 'error', r"\b(theme song|jingle)\b|then we get into it", False),
    ('introducer', 'error', r"I want to (flag|surface|pull out|push on)|Important (refinement|detail), though|Here'?s the thing|Honest correction", False),
    ('introducer', 'error', r"\bHere'?s what (I|we) (find|love|like)\b|\bWhat I find (genuinely|really|so)\b|\bHere'?s (why|where) (this|that|it)\b", False),
    ('fair-framing', 'error', r"fair (framing|refinement|application)", False),
    ('sycophancy', 'error', r"Great question|Absolutely!|^(Exactly|Correct)\.?\s*$", True),
    ('audience-ref', 'error', r"\b(a|the|our|any|some) listeners?\b|\bpeople listening\b", False),
]
NUMBER_RULES = [
    ('spoken-number', r"\d+(\.\d+)?\s*(%|percent)"),
    ('spoken-number', r"\b\d+\.\d+\s*(points?|score)\b|\bF1\b|\bIoU\b|\bBLEU\b|\bR\^?2\b"),
]
CAPS = [('antithesis-tic', 'error', 1, r"\b(That'?s|It'?s|This is|That is) not (a |an |the )?[\w\- ]{2,28}\.\s*(That'?s|It'?s|This is|That is)\b"),
        ('intensifier-tic', 'warn', 3, r"\b(genuinely|honestly|really quite|actually quite)\b"),
        ('opener-tic', 'warn', 5, r"^(Okay|Right|Yeah)\s*[,.-]")]
COMPILED = [(i, s, re.compile(rx, 0 if cs else re.I)) for i, s, rx, cs in RULES]
COMPILED_NUMBERS = [(i, re.compile(rx, re.I)) for i, rx in NUMBER_RULES]
COMPILED_CAPS = [(i, s, c, re.compile(rx, re.I)) for i, s, c, rx in CAPS]
RULE_IDS = sorted({r[0] for r in RULES} | {r[0] for r in NUMBER_RULES} | {r[0] for r in CAPS} | {'separate-opener', 'bare-interjection', 'sentence-continuation', 'cutoff', 'tag', 'custom-phrase', 'readability', 'long-sentence', 'sensitive-word', 'contact-details'})
KIDS_SENSITIVE = ('kill', 'killed', 'die', 'died', 'dead', 'death', 'blood', 'gun', 'weapon', 'hate', 'stupid', 'idiot', 'shut up', 'hurt', 'fat', 'ugly')
KIDS_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\bhttps?://|\bwww\.|\b\w+\.(?:com|net|org|io)\b|\b\d{3}[- .]\d{3,4}[- .]?\d{0,4}\b|\b(?:follow|dm|message|text) (?:me|us)\b", re.I)
PRESETS = {'kids': {'spoken_numbers': 'off', 'min_words_per_turn': 1, 'disabled_rules': ['audience-ref', 'bare-interjection'], 'reading_grade_max': 4, 'max_sentence_words': 18,
                    'sensitive_words': list(KIDS_SENSITIVE), 'block_contact_details': True}}
DEFAULT_STYLE = {'preset': None, 'reading_grade_max': None, 'max_sentence_words': None, 'sensitive_words': [], 'block_contact_details': False, 'tags': 'none', 'banned_tags': [], 'spoken_numbers': 'error', 'min_words_per_turn': 3, 'forbid_cutoffs': True,
                 'disabled_rules': [], 'banned_phrases': []}


def normalize_style(style):
    value = dict(DEFAULT_STYLE)
    if style is None: return value
    if not isinstance(style, dict) or set(style) - set(DEFAULT_STYLE): raise ValueError('style may only set: ' + ', '.join(DEFAULT_STYLE))
    if style.get('preset') is not None:
        if style['preset'] not in PRESETS: raise ValueError('style.preset may only be: ' + ', '.join(PRESETS))
        value.update(PRESETS[style['preset']])
    value.update(style)
    if value['reading_grade_max'] is not None and (type(value['reading_grade_max']) is not int or not 1 <= value['reading_grade_max'] <= 12): raise ValueError('style.reading_grade_max must be 1 to 12')
    if value['max_sentence_words'] is not None and (type(value['max_sentence_words']) is not int or not 5 <= value['max_sentence_words'] <= 80): raise ValueError('style.max_sentence_words must be 5 to 80')
    if type(value['block_contact_details']) is not bool: raise ValueError('style.block_contact_details must be boolean')
    if not isinstance(value['sensitive_words'], list) or len(value['sensitive_words']) > 200 or any(not isinstance(x, str) or not 2 <= len(x) <= 40 for x in value['sensitive_words']):
        raise ValueError('style.sensitive_words is a list of up to 200 plain words or short phrases')
    if value['tags'] not in ('none', 'higgs'): raise ValueError('style.tags must be "none" (tags are errors) or "higgs"')
    if value['spoken_numbers'] not in ('error', 'warn', 'off'): raise ValueError('style.spoken_numbers must be error, warn or off')
    if type(value['min_words_per_turn']) is not int or not 0 <= value['min_words_per_turn'] <= 10: raise ValueError('style.min_words_per_turn must be 0 to 10')
    if type(value['forbid_cutoffs']) is not bool: raise ValueError('style.forbid_cutoffs must be boolean')
    off = value['disabled_rules']
    if not isinstance(off, list) or any(r not in RULE_IDS for r in off): raise ValueError('style.disabled_rules may only list: ' + ', '.join(RULE_IDS))
    phrases = value['banned_phrases']
    if not isinstance(phrases, list) or len(phrases) > 100 or any(not isinstance(x, str) or not 2 <= len(x) <= 120 for x in phrases):
        raise ValueError('style.banned_phrases is a list of up to 100 plain phrases (2 to 120 characters)')
    banned = value['banned_tags']
    if not isinstance(banned, list) or len(banned) > 50 or any(not isinstance(b, str) or not re.fullmatch(r'(?:[A-Z][A-Z0-9_ ]{0,39}:)?[a-z_]+:[a-z_]+', b) for b in banned):
        raise ValueError('style.banned_tags entries look like "style:whispering" or "ERIS:emotion:contemplation"')
    return value


def strip_tags(text):
    return re.sub(r'\s{2,}', ' ', TAG.sub(' ', text)).strip()


def tag_problems(text, speaker, style):
    out = []
    for match in TAG.finditer(text):
        category, value = match.group(1), match.group(2)
        label = match.group(0)
        if style['tags'] == 'none':
            out.append(f'{label} would be read aloud by a voice engine without tag support; remove it or set style.tags to "higgs"')
        elif value is None or value not in HIGGS.get(category, ()):
            out.append(f'unknown tag {label}')
        elif f'{category}:{value}' in style['banned_tags'] or f'{speaker}:{category}:{value}' in style['banned_tags']:
            out.append(f'{label} is banned by this show\'s style')
        elif category == 'sfx' and not text[match.end():match.end() + 1].isalpha():
            out.append(f'{label} must be followed directly by its sound, for example Haha, Uh, Ahem')
    leftover = TAG.sub('', text)
    if '<|' in leftover or '|>' in leftover: out.append('malformed tag (use <|category:value|>)')
    return out


def syllables(word):
    word = re.sub(r'[^a-z]', '', word.lower())
    if not word: return 0
    count = len(re.findall(r'[aeiouy]+', word))
    if word.endswith('e') and not word.endswith(('le', 'ee')) and count > 1: count -= 1
    return max(1, count)


def grade_level(text):
    sentences = [x for x in re.split(r'[.!?]+', text) if re.search(r'[A-Za-z]', x)]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words: return 0.0
    return round(0.39 * len(words) / len(sentences) + 11.8 * sum(syllables(w) for w in words) / len(words) - 15.59, 1)


def lint(segments, names, style=None, raw_headers=None):
    """segments: list of {'turns':[{'speaker','text'}]} aligned with file names. Returns findings list."""
    style = normalize_style(style)
    findings, counts = [], {}
    disabled = set(style['disabled_rules'])
    phrases = [(x, re.compile(re.escape(x), re.I)) for x in style['banned_phrases']]
    def add(severity, name, turn, rule, detail):
        if rule in disabled: return
        findings.append({'severity': severity, 'file': name, 'turn': turn, 'rule': rule, 'detail': detail[:160]})
    for name in names:
        if re.match(r'^00-(?:cold-open|opener|intro)', name): add('error', name, 0, 'separate-opener', 'Begin directly with the lead story; no separate opener file')
    sensitive = [(w, re.compile(r'\b' + re.escape(w) + r'\b', re.I)) for w in style['sensitive_words']]
    for name, segment in zip(names, segments):
        if style['reading_grade_max']:
            grade = grade_level(' '.join(strip_tags(t['text']) for t in segment['turns']))
            if grade > style['reading_grade_max']: add('warn', name, 0, 'readability', f'estimated reading grade {grade} is above the target {style["reading_grade_max"]}; use shorter sentences and simpler words')
        for index, turn in enumerate(segment['turns'], 1):
            speaker, raw = turn['speaker'], turn['text']
            for problem in tag_problems(raw, speaker, style): add('error', name, index, 'tag', problem)
            text = strip_tags(raw)
            for phrase, rx in phrases:
                if rx.search(text): add('error', name, index, 'custom-phrase', f'banned phrase {phrase!r}: {text}')
            for rule, severity, rx in COMPILED:
                if rx.search(text): add(severity, name, index, rule, text)
            if style['spoken_numbers'] != 'off':
                for rule, rx in COMPILED_NUMBERS:
                    if rx.search(text): add(style['spoken_numbers'], name, index, rule, text)
            if style['block_contact_details'] and KIDS_CONTACT.search(text): add('error', name, index, 'contact-details', 'spoken contact details, links or invitations to message the show are not allowed in this format')
            for word, rx in sensitive:
                if rx.search(text): add('warn', name, index, 'sensitive-word', f'{word!r}: confirm this is right for the audience: {text}')
            if style['max_sentence_words']:
                longest = max((len(re.findall(r"[A-Za-z0-9']+", x)) for x in re.split(r'[.!?]+', text)), default=0)
                if longest > style['max_sentence_words']: add('warn', name, index, 'long-sentence', f'{longest}-word sentence; the target is {style["max_sentence_words"]}')
            words = len(re.findall(r"[A-Za-z0-9']+", text))
            if 0 < words < style['min_words_per_turn']: add('error', name, index, 'bare-interjection', f'{text!r} has {words} word(s); use a short phrase that adds something')
            if re.match(r'^(?:--|—|\.\.\.|…)', text): add('error', name, index, 'sentence-continuation', 'turn starts by continuing another speaker')
            if style['forbid_cutoffs'] and re.search(r'(?:--|—)\s*$', text): add('error', name, index, 'cutoff', 'turn ends mid-sentence for another speaker to finish')
            for rule, severity, cap, rx in COMPILED_CAPS:
                if rx.search(text):
                    counts[rule] = counts.get(rule, 0) + 1
                    if counts[rule] > cap: add(severity, name, index, rule, f'use #{counts[rule]} of a pattern capped at {cap} per episode: {text}')
    return findings
