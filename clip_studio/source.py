"""Where the video comes from: YouTube through the user's own yt-dlp, or a recording already on this computer.

Only the video page, its caption track, and the requested sections are fetched. Nothing is uploaded or published.
The yt-dlp program and the browser whose sign-in it may read are owner settings; the model cannot supply either.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtube-nocookie.com'}
BROWSERS = {'firefox', 'chrome', 'chromium', 'brave', 'edge', 'opera', 'vivaldi', 'safari'}
PRIVATE = {'.ssh', '.gnupg', '.aws', '.azure', '.codex', '.docker', '.kube', '.pki', '.config'}
ENV = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'TEMP', 'TMP', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SYSTEMROOT', 'WINDIR', 'XDG_CACHE_HOME',
       'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
LONG = 6 * 3600  # ceiling for a download or encode; far above any real run, it only stops a hung process


def process_env():
    return {k: os.environ[k] for k in ENV if k in os.environ}


def video_id(url):
    """The 11-character id from a YouTube watch, share, Shorts, live or embed link. Playlists and channels are refused."""
    if not isinstance(url, str) or len(url) > 500:
        raise ValueError('Give one YouTube video link')
    url = url.strip()
    if VIDEO_ID.fullmatch(url):
        return url
    parts = urlsplit(url if '://' in url else 'https://' + url)
    host = (parts.hostname or '').lower()
    if parts.scheme not in ('http', 'https') or host not in HOSTS:
        raise ValueError('Only YouTube video links are supported (youtube.com or youtu.be). For another recording, download it yourself and give media_path.')
    path = [p for p in parts.path.split('/') if p]
    if host == 'youtu.be':
        found = path[0] if path else ''
    elif path[:1] == ['watch']:
        found = (parse_qs(parts.query).get('v') or [''])[0]
    elif len(path) >= 2 and path[0] in ('shorts', 'live', 'embed', 'v'):
        found = path[1]
    else:
        found = ''
    if not VIDEO_ID.fullmatch(found):
        raise ValueError('That link is not a single YouTube video (a playlist, channel or search page cannot be clipped). Open the video and copy its link.')
    return found


def watch_url(vid, at=None):
    return 'https://www.youtube.com/watch?v=' + vid + ('' if at is None else '&t=%ds' % int(at))


def local_media(path, profile_home=None, allowed=()):
    """A regular media file the user named, outside private configuration and the Hermes profile (except this suite's own data)."""
    p = Path(str(path)).expanduser()
    if p.is_symlink():
        raise ValueError('Symlinks are not accepted; give the real file')
    try:
        real = p.resolve(strict=True)
    except OSError:
        raise ValueError('File not found: %s' % p.name) from None
    inside_profile = any(x.casefold() == '.hermes' for x in real.parts) or (profile_home is not None and real.is_relative_to(Path(profile_home).resolve()))
    if not real.is_file() or any(x.casefold() in PRIVATE for x in real.parts) or inside_profile and not any(real.is_relative_to(Path(a).resolve()) for a in allowed):
        raise ValueError('Choose a file outside private configuration folders')
    return real


class YouTube:
    def __init__(self, settings=None):
        settings = settings or {}
        self.program = settings.get('clip_ytdlp') or shutil.which('yt-dlp')
        browser = str(settings.get('clip_cookies_browser') or '').strip().lower()
        if browser and browser not in BROWSERS:
            raise ValueError('The plugin setting clip_cookies_browser must be one of: ' + ', '.join(sorted(BROWSERS)))
        self.browser = browser
        self.js = not shutil.which('deno') and bool(shutil.which('node'))

    def _run(self, args, cwd=None, timeout=180):
        if not self.program or not (shutil.which(self.program) or Path(self.program).is_file()):
            raise ValueError('yt-dlp was not found on this computer. Install it (https://github.com/yt-dlp/yt-dlp#installation) or set clip_ytdlp in the plugin settings, then try again. A recording you already have can be opened with media_path instead.')
        if not shutil.which('ffmpeg'):
            raise ValueError('Install ffmpeg and ffprobe')
        base = [self.program, '--ignore-config', '--no-playlist', '--no-progress', '--no-colors', '--socket-timeout', '30']
        if self.browser:
            base += ['--cookies-from-browser', self.browser]
        for extra in ([['--js-runtimes', 'node']] if self.js else []) + [[]]:
            try:
                done = subprocess.run(base + extra + args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=process_env(), timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                raise RuntimeError('YouTube did not answer in time; nothing was saved. Try again later.') from None
            err = done.stderr.decode('utf-8', 'replace')
            if not (extra and 'no such option' in err):
                break
        if done.returncode != 0:
            raise RuntimeError(self._explain(err))
        return done.stdout

    def _explain(self, err):
        lines = [x.split('ERROR:', 1)[1].strip() for x in err.splitlines() if 'ERROR:' in x]
        reason = re.sub(r'https?://\S+', '', lines[-1])[:300].strip() if lines else 'yt-dlp stopped without a reason'
        low = reason.lower()
        if 'sign in' in low or 'not a bot' in low or 'cookies' in low:
            return 'YouTube asked for a sign-in before showing this video. The owner can set clip_cookies_browser (for example firefox) in the plugin settings so yt-dlp uses the browser where they are signed in. (%s)' % reason
        if 'private video' in low or 'members-only' in low or 'unavailable' in low or 'removed' in low:
            return 'YouTube says this video is not available to you: %s' % reason
        return 'YouTube could not be read: %s. If this keeps happening, update yt-dlp; YouTube changes often.' % reason

    def info(self, vid):
        data = json.loads(self._run(['--skip-download', '-J', '--', watch_url(vid)]))
        if not isinstance(data, dict) or data.get('id') != vid:
            raise RuntimeError('YouTube returned something other than this video')
        return data

    def captions(self, vid, track, automatic, folder):
        for old in Path(folder).glob('captions.*'):
            old.unlink()
        self._run(['--skip-download', '--write-auto-subs' if automatic else '--write-subs', '--sub-langs', track, '--sub-format', 'json3/vtt/srt',
                   '-o', 'captions.%(ext)s', '--', watch_url(vid)], cwd=str(folder))
        found = [p for p in Path(folder).glob('captions.*') if p.suffix in ('.json3', '.vtt', '.srt') and p.stat().st_size > 0]
        if not found:
            raise RuntimeError('YouTube listed a caption track but did not deliver it')
        return found[0]

    def chat(self, vid, folder):
        """The chat replay of a finished stream as a raw file (one JSON object per line), or None when YouTube has none. Written to chat-raw.live_chat.json."""
        for old in Path(folder).glob('chat-raw.*'):
            old.unlink()
        self._run(['--skip-download', '--write-subs', '--sub-langs', 'live_chat', '--sub-format', 'json', '-o', 'chat-raw.%(ext)s', '--', watch_url(vid)], cwd=str(folder), timeout=LONG)
        found = [p for p in Path(folder).glob('chat-raw.*') if p.suffix == '.json' and p.stat().st_size > 0]
        return found[0] if found else None

    def audio(self, vid, folder):
        for old in Path(folder).glob('audio.*'):
            old.unlink()
        self._run(['-f', 'ba[ext=m4a]/ba/b', '--max-filesize', '2000m', '-o', 'audio.%(ext)s', '--', watch_url(vid)], cwd=str(folder), timeout=LONG)
        found = [p for p in Path(folder).glob('audio.*') if p.suffix != '.part' and p.stat().st_size > 0]
        if not found:
            raise RuntimeError('The audio could not be saved')
        return found[0]

    def section(self, vid, start, end, max_height, target):
        """Fetch only start..end (seconds) and encode it so the cut is frame-exact. Returns the saved MP4."""
        target = Path(target)
        self._run(['-f', 'bv*[height<=%d]+ba/b[height<=%d]/b' % (max_height, max_height), '--download-sections', '*%.3f-%.3f' % (start, end),
                   '--force-keyframes-at-cuts', '--merge-output-format', 'mp4', '-o', target.with_suffix('').name + '.%(ext)s', '--', watch_url(vid)],
                  cwd=str(target.parent), timeout=LONG)
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError('The section could not be saved')
        return target


def ffmpeg(args, cwd=None, timeout=LONG):
    program = shutil.which('ffmpeg')
    if not program:
        raise ValueError('Install ffmpeg and ffprobe')
    try:
        done = subprocess.run([program, '-v', 'error', '-nostdin', *args], cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=process_env(), timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('The encoder stopped responding') from None
    if done.returncode != 0:
        raise RuntimeError('The clip could not be encoded: ' + done.stderr.decode('utf-8', 'replace').strip().splitlines()[-1][:200])


def quiet_spans(path, min_seconds, speech=()):
    """Stretches with no voice, as (start, end) seconds, measured against this file's own levels so they are found under music too.

    The sound is read as 50 ms loudness steps. The bed (music, room, game) is the quiet tenth of the steps; the voice level is the
    middle of the steps inside the spoken spans (or the loud half when no transcript is given). A step counts as quiet when it sits in
    the lower third between bed and voice. Returns [] with a reason when voice and bed are too close to tell apart.
    """
    import array, math
    program = shutil.which('ffmpeg')
    if not program:
        raise ValueError('Install ffmpeg and ffprobe')
    try:
        done = subprocess.run([program, '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=process_env(), timeout=LONG, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('The encoder stopped responding') from None
    samples = array.array('h')
    samples.frombytes(done.stdout[:len(done.stdout) // 2 * 2])
    step = 400  # 50 ms at 8 kHz
    levels = []
    for i in range(0, len(samples) - step + 1, step):
        chunk = samples[i:i + step]
        levels.append(10 * math.log10(sum(x * x for x in chunk) / step / 32768.0 ** 2 + 1e-10))
    if len(levels) < 40:
        return [], 'too short to measure'
    ordered = sorted(levels)
    bed = ordered[len(ordered) // 10]
    spoken = sorted(levels[k] for a, b in speech for k in range(max(0, int(a * 20)), min(len(levels), int(b * 20) + 1)))
    voice = spoken[len(spoken) // 2] if len(spoken) >= 20 else ordered[len(ordered) * 3 // 4]
    if voice - bed < 6:
        return [], 'the voice is not clearly louder than the background sound here, so quiet stretches cannot be told apart'
    gate = max(bed + (voice - bed) / 3, min(-35.0, voice - 15))
    words = sorted(speech)
    out, start = [], None
    for k, level in enumerate(levels + [0.0]):
        if level < gate and start is None:
            start = k
        elif level >= gate and start is not None:
            a, b = start / 20, k / 20
            start = None
            for s, e in words:  # never reach into a spoken word, whatever its loudness
                if s - 0.05 < b and e + 0.1 > a:
                    if s - 0.05 <= a: a = max(a, e + 0.1)
                    else: b = min(b, s - 0.05)
            if b - a > min_seconds:
                out.append((a, b))
    return out, None


def probe(path):
    program = shutil.which('ffprobe')
    if not program:
        raise ValueError('Install ffmpeg and ffprobe')
    try:
        done = subprocess.run([program, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=process_env(), timeout=60, check=False)
        data = json.loads(done.stdout or b'{}')
    except (subprocess.TimeoutExpired, ValueError):
        data = {}
    streams = data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    try:
        duration = float((data.get('format') or {}).get('duration'))
    except (TypeError, ValueError):
        raise ValueError('This file is not readable media') from None
    return {'duration': duration, 'video': bool(video), 'audio': any(s.get('codec_type') == 'audio' for s in streams),
            'width': (video or {}).get('width'), 'height': (video or {}).get('height')}
