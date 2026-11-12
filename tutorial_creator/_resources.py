"""Load the suite's shared speech_resources module, also when this part is imported on its own (as its tests do)."""
try:
    from ..common import speech_resources
except (ImportError, ValueError):
    import importlib.util
    import sys
    from pathlib import Path
    _name = 'creator_studio_speech_resources'
    if _name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_name, Path(__file__).resolve().parents[1] / 'common' / 'speech_resources.py')
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _module
        _spec.loader.exec_module(_module)
    speech_resources = sys.modules[_name]
