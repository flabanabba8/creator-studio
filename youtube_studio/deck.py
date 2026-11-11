"""Make 1920x1080 slide images from a text outline (title, bullets, optional picture). CPU-only, local, no design tools."""
import os
from pathlib import Path
import uuid
from .render import media

THEMES = {
    'light': {'bg': (248, 248, 244), 'fg': (28, 30, 36), 'accent': (30, 100, 200), 'title_size': 84, 'body_size': 56},
    'dark': {'bg': (18, 20, 26), 'fg': (240, 242, 246), 'accent': (80, 200, 140), 'title_size': 84, 'body_size': 56},
    'terminal': {'bg': (14, 17, 23), 'fg': (214, 226, 214), 'accent': (80, 220, 140), 'title_size': 64, 'body_size': 44},
    'kids': {'bg': (255, 244, 200), 'fg': (40, 36, 70), 'accent': (240, 90, 60), 'title_size': 108, 'body_size': 76},
}
FONTS = ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
         '/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf')
MONO = ('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', '/usr/share/fonts/dejavu/DejaVuSansMono.ttf', '/usr/share/fonts/TTF/DejaVuSansMono.ttf', '/System/Library/Fonts/Menlo.ttc', 'C:/Windows/Fonts/consola.ttf')
REGULAR = tuple(f.replace('-Bold', '').replace('Bold', '').replace('arialbd', 'arial') for f in FONTS)
W, H, MARGIN = 1920, 1080, 110


def clean(value, name, limit):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c != '\n' for c in value): raise ValueError(f'{name} must be printable text of at most {limit} characters')
    return value.strip()


def wrap(draw, text, font, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=font) <= width or not line: line = trial
        else: lines.append(line); line = word
    return lines + ([line] if line else [])


def make_slides(root, slides, theme='light', allow_profile_media=False):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ValueError('Pillow is required to make slides; install the plugin dependency') from None
    if theme not in THEMES: raise ValueError('theme must be one of: ' + ', '.join(THEMES))
    if type(allow_profile_media) is not bool: raise ValueError('allow_profile_media must be boolean')
    if not isinstance(slides, list) or not 1 <= len(slides) <= 40: raise ValueError('Provide 1 to 40 slides')
    bold = next((f for f in FONTS if os.path.isfile(f)), None); regular = next((f for f in REGULAR if os.path.isfile(f)), bold)
    if not bold: raise ValueError('No supported font was found for slide text')
    style = THEMES[theme]
    root = Path(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    out, notes, made = [], [], []
    try:
        for index, slide in enumerate(slides, 1):
            if not isinstance(slide, dict) or not {'title'} <= set(slide) or not set(slide) <= {'title', 'bullets', 'image_path', 'notes', 'code'}: raise ValueError('Each slide needs a title (bullets, image_path and notes optional)')
            title = clean(slide['title'], 'title', 100); bullets = slide.get('bullets', [])
            if not title: raise ValueError('A slide title cannot be empty')
            if not isinstance(bullets, list) or len(bullets) > 6: raise ValueError('Use at most 6 bullets per slide')
            bullets = [clean(b, 'bullet', 140) for b in bullets]
            code = slide.get('code', '')
            if not isinstance(code, str) or len(code) > 3000 or code.count('\n') > 30 or any(len(x) > 120 for x in code.splitlines()) or any(ord(c) < 32 and c not in '\n\t' for c in code): raise ValueError('code must be text of at most 3,000 characters, 31 lines and 120 characters per line')
            code = code.replace('\t', '    ').rstrip()
            picture = Image.open(media(slide['image_path'], {'.png', '.jpg', '.jpeg'}, root, allow_profile_media)).convert('RGB') if slide.get('image_path') else None
            canvas = Image.new('RGB', (W, H), style['bg']); draw = ImageDraw.Draw(canvas)
            text_width = (W - 2 * MARGIN) if picture is None else (W // 2 - MARGIN - 20)
            draw.rectangle((0, 0, 24, H), fill=style['accent'])
            tsize = style['title_size']
            while True:
                tfont = ImageFont.truetype(bold, tsize); tlines = wrap(draw, title, tfont, text_width)
                if len(tlines) <= (2 if (bullets or code) else 3) or tsize <= 44: break
                tsize -= 6
            y = MARGIN if (bullets or picture or code) else (H - len(tlines) * int(tsize * 1.25)) // 2
            for line in tlines:
                draw.text((MARGIN, y), line, font=tfont, fill=style['fg']); y += int(tsize * 1.25)
            if bullets:
                y += 30; bsize = max(style['body_size'], 100)  # start large and shrink to fit, so short slides fill the frame
                while True:
                    bfont = ImageFont.truetype(regular, bsize); wrapped = [wrap(draw, b, bfont, text_width - 70) for b in bullets]
                    total = sum(len(w) for w in wrapped) * int(bsize * 1.3) + len(bullets) * 22
                    if y + total <= H - MARGIN or bsize <= 30: break
                    bsize -= 4
                if y + total > H - MARGIN: raise ValueError(f'Slide {index} has too much text to fit; shorten the title or bullets')
                for lines in wrapped:
                    draw.ellipse((MARGIN, y + bsize * 0.4, MARGIN + 22, y + bsize * 0.4 + 22), fill=style['accent'])
                    for line in lines:
                        draw.text((MARGIN + 60, y), line, font=bfont, fill=style['fg']); y += int(bsize * 1.3)
                    y += 22
            if code:
                mono = next((f for f in MONO if os.path.isfile(f)), None)
                if not mono: raise ValueError('No monospace font was found for code blocks')
                lines_in = code.splitlines(); top = y + 24; room = H - MARGIN - top
                csize = 40
                while csize > 14:
                    cfont = ImageFont.truetype(mono, csize); widest = max(draw.textlength(l, font=cfont) for l in lines_in)
                    if widest <= W - 2 * MARGIN - 56 and len(lines_in) * int(csize * 1.3) + 40 <= room: break
                    csize -= 2
                if len(lines_in) * int(csize * 1.3) + 40 > room or max(draw.textlength(l, font=cfont) for l in lines_in) > W - 2 * MARGIN - 56: raise ValueError(f'Slide {index} code block does not fit; shorten it')
                draw.rounded_rectangle((MARGIN - 20, top, W - MARGIN + 20, top + len(lines_in) * int(csize * 1.3) + 40), 18, fill=(4, 6, 10) if theme == 'terminal' else (30, 32, 40))
                cy = top + 20
                for line in lines_in:
                    draw.text((MARGIN + 8, cy), line, font=cfont, fill=(220, 235, 220)); cy += int(csize * 1.3)
            if picture is not None:
                box = (W // 2 - 20, MARGIN, W - MARGIN, H - MARGIN); bw, bh = box[2] - box[0], box[3] - box[1]
                scale = min(bw / picture.width, bh / picture.height); picture = picture.resize((max(1, int(picture.width * scale)), max(1, int(picture.height * scale)))); canvas.paste(picture, (box[0] + (bw - picture.width) // 2, box[1] + (bh - picture.height) // 2))
            path = root / f'{uuid.uuid4().hex}.slide.png'; made.append(path)
            canvas.save(path, 'PNG')
            out.append({'path': str(path), 'title': title, 'alt_text': title + (': ' + '; '.join(bullets) if bullets else '')})
            notes.append(clean(slide.get('notes', ''), 'notes', 4000))
        made.clear()
    finally:
        for path in made: path.unlink(missing_ok=True)
    return {'slides': out, 'notes': notes, 'theme': theme, 'size': f'{W}x{H}',
            'notice': 'Plain generated slides in plugin storage. Pass these paths to youtube_render_slides with allow_profile_media true. Check legibility, fit and the rights of any picture yourself.'}
