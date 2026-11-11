"""Creator Studio: YouTube Studio, Podcast Studio, Caption Studio and Tutorial Creator in one plugin."""
from . import youtube_studio, podcast_studio, caption_studio, tutorial_creator

PARTS = (youtube_studio, podcast_studio, caption_studio, tutorial_creator)


def register(ctx):
    for part in PARTS:
        part.register(ctx)
