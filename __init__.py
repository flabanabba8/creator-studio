"""Creator Studio: YouTube Studio, Podcast Studio, Caption Studio, Tutorial Creator and Clip Studio in one plugin."""
from . import youtube_studio, podcast_studio, caption_studio, tutorial_creator, clip_studio

PARTS = (youtube_studio, podcast_studio, caption_studio, tutorial_creator, clip_studio)


def register(ctx):
    from .common import google_signin
    google_signin.configure(getattr(ctx, 'get_config', None))
    for part in PARTS:
        part.register(ctx)
