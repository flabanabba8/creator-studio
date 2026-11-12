"""Where the owner's Camoufox install is: only what the plugin settings name (camoufox_python, camoufox_browser) and the standard browser folder. No interpreter is searched for or run."""
import os
import subprocess
from pathlib import Path


def camoufox_browsers():
    """Camoufox browser binaries in the standard cache/data folders."""
    home = Path.home(); found = []
    for base in (os.environ.get('XDG_CACHE_HOME'), str(home / '.cache'), os.environ.get('XDG_DATA_HOME'), str(home / '.local/share')):
        if not base: continue
        for name in ('camoufox/camoufox-bin', 'camoufox/camoufox'):
            path = Path(base) / name
            if path.is_file() and os.access(path, os.X_OK) and str(path) not in found: found.append(str(path))
    return found


def camoufox_pythons(configured=None, limit=4):
    """The Python the OWNER named in the plugin setting camoufox_python, if it can import camoufox. No interpreter is searched for or run
    from PATH, the home folder or anywhere else. The probe runs with a clean environment."""
    if not configured: return []
    path = Path(str(configured)).expanduser()
    if not path.is_file(): return []
    try:
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR')}
        r = subprocess.run([str(path), '-I', '-c', 'import importlib.util as u;print(u.find_spec("camoufox") is not None)'], capture_output=True, text=True, timeout=8, env=env)
        if r.returncode == 0 and r.stdout.strip() == 'True': return [str(path)]
    except (OSError, subprocess.TimeoutExpired): pass
    return []


def camoufox_runtime(settings=None):
    """{'python_executable':..., 'browser_executable':...} from the owner's plugin settings (camoufox_python, camoufox_browser or the standard browser folder), or None. Nothing is launched."""
    settings = settings or {}
    pythons = camoufox_pythons(settings.get('camoufox_python'))
    browsers = [settings['camoufox_browser']] if settings.get('camoufox_browser') else camoufox_browsers()
    if pythons and browsers: return {'python_executable': pythons[0], 'browser_executable': browsers[0], 'other_pythons': []}
    return None
