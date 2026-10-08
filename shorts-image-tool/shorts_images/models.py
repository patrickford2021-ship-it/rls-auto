"""Shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageCandidate:
    """One image result returned by a source, before it is downloaded."""

    image_url: str                 # direct URL to the full-size image file
    source: str                    # e.g. "tmdb", "unsplash"
    page_url: str = ""             # human-facing page the image came from
    width: Optional[int] = None    # as reported by the API (may be None)
    height: Optional[int] = None
    title: str = ""                # caption / photo title if any
    credit: str = ""               # photographer / uploader
    extra: dict = field(default_factory=dict)


@dataclass
class Job:
    """One line of keywords.txt after parsing."""

    term: str                      # the search text, tag removed
    tag: str                       # "tmdb", "google", "unsplash", "pexels", "pixabay" or "stock"
    raw: str                       # original line, for messages
