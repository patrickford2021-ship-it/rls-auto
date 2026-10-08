"""Loads API keys from a .env file (or real environment variables)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Human-readable names and the env var each source needs.
KEY_NAMES = {
    "tmdb": "TMDB_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "unsplash": "UNSPLASH_ACCESS_KEY",
    "pexels": "PEXELS_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
}

PLACEHOLDERS = {"", "your_key_here", "changeme", "xxx", "paste-your-key-here"}


def load_env(script_dir: Path) -> Optional[Path]:
    """Load .env from the tool's folder (preferred) or the current directory.

    Returns the path that was loaded, or None if no .env file was found.
    Real environment variables always win over the file.
    """
    for candidate in (script_dir / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


def get_key(source: str) -> Optional[str]:
    """Return the API key for a source, or None if it is missing/placeholder."""
    var = KEY_NAMES[source]
    value = (os.environ.get(var) or "").strip().strip('"').strip("'")
    if value.lower() in PLACEHOLDERS:
        return None
    return value
