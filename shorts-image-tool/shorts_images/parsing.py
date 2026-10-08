"""Parses keywords.txt into a list of jobs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from .models import Job

# Tags the user may put at the start of a line, and what they map to.
TAG_ALIASES = {
    "tmdb": "tmdb",
    "movie": "tmdb",
    "tv": "tmdb",
    "google": "google",
    "serp": "google",
    "serpapi": "google",
    "unsplash": "unsplash",
    "pexels": "pexels",
    "pixabay": "pixabay",
    "stock": "stock",
}

_TAG_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+?)\s*$")


def parse_line(line: str) -> Job | None:
    """Turn one line into a Job, or None for blank/comment lines."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    match = _TAG_RE.match(stripped)
    if match and match.group(1).lower() in TAG_ALIASES:
        tag = TAG_ALIASES[match.group(1).lower()]
        term = match.group(2)
    else:
        tag = "stock"
        term = stripped
    # Collapse internal whitespace so folder names stay tidy.
    term = re.sub(r"\s+", " ", term).strip()
    if not term:
        return None
    return Job(term=term, tag=tag, raw=stripped)


def parse_keywords_file(path: Path) -> List[Job]:
    jobs: List[Job] = []
    seen = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            job = parse_line(line)
            if job is None:
                continue
            key = (job.tag, job.term.lower())
            if key in seen:
                continue
            seen.add(key)
            jobs.append(job)
    return jobs


def slugify(text: str) -> str:
    """'Breaking Bad: Walter White!' -> 'breaking-bad-walter-white'."""
    text = text.lower()
    text = re.sub(r"['’]", "", text)          # drop apostrophes
    text = re.sub(r"[^a-z0-9]+", "-", text)        # everything else -> dash
    text = text.strip("-")
    return text[:80] or "term"
