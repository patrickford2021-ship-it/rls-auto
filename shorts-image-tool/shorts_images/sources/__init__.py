"""Image sources. Each module exposes `search(term, limit, key, session)`."""

from . import pexels, pixabay, serpapi, tmdb, unsplash

# Map source name -> module. Order matters for the default "stock" tag.
SOURCES = {
    "tmdb": tmdb,
    "google": serpapi,
    "unsplash": unsplash,
    "pexels": pexels,
    "pixabay": pixabay,
}

# Which sources a tag expands to.
TAG_TO_SOURCES = {
    "tmdb": ["tmdb"],
    "google": ["google"],
    "unsplash": ["unsplash"],
    "pexels": ["pexels"],
    "pixabay": ["pixabay"],
    "stock": ["unsplash", "pexels", "pixabay"],
}

# Which env key each source needs (see config.KEY_NAMES).
SOURCE_KEY = {
    "tmdb": "tmdb",
    "google": "serpapi",
    "unsplash": "unsplash",
    "pexels": "pexels",
    "pixabay": "pixabay",
}

PRETTY = {
    "tmdb": "TMDB",
    "google": "Google Images (SerpAPI)",
    "unsplash": "Unsplash",
    "pexels": "Pexels",
    "pixabay": "Pixabay",
}
