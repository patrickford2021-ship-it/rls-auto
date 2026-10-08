"""TMDB (The Movie Database) source.

Works out whether the term is a movie, a TV show or a person, then pulls
backdrops/stills for titles and profile photos for people.
"""

from __future__ import annotations

from typing import List, Optional

import requests

from ..models import ImageCandidate

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/original"
SITE = "https://www.themoviedb.org"

# Backdrops come in many languages (text overlays). "null" = no text, best for Shorts.
LANGS = "null,en"


def _auth(key: str) -> tuple[dict, dict]:
    """TMDB accepts a short v3 key (query param) or a long v4 token (Bearer)."""
    if key.startswith("eyJ") or len(key) > 60:
        return {"Authorization": f"Bearer {key}"}, {}
    return {}, {"api_key": key}


def _get(session: requests.Session, path: str, key: str, **params) -> dict:
    headers, auth_params = _auth(key)
    params.update(auth_params)
    resp = session.get(f"{API}{path}", params=params, headers=headers, timeout=20)
    if resp.status_code == 401:
        raise RuntimeError("TMDB rejected the API key (401). Check TMDB_API_KEY in .env")
    resp.raise_for_status()
    return resp.json()


def _query_variants(term: str) -> List[str]:
    """Full term first, then shorter prefixes/suffixes.

    "Breaking Bad Walter White" has no exact TMDB match, but "Breaking Bad" does.
    """
    words = term.split()
    variants = [term]
    for n in range(len(words) - 1, 0, -1):
        variants.append(" ".join(words[:n]))      # leading words
    for n in range(len(words) - 1, 0, -1):
        variants.append(" ".join(words[-n:]))     # trailing words
    seen, out = set(), []
    for v in variants:
        if v.lower() not in seen and len(v) >= 2:
            seen.add(v.lower())
            out.append(v)
    return out


def _find(session: requests.Session, term: str, key: str) -> Optional[dict]:
    """Return the best /search/multi hit (movie, tv or person) for the term."""
    for query in _query_variants(term):
        data = _get(session, "/search/multi", key, query=query, include_adult="false", page=1)
        hits = [r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv", "person")]
        if hits:
            # Prefer the most popular hit among the first few results.
            hits = sorted(hits[:5], key=lambda r: r.get("popularity", 0), reverse=True)
            best = hits[0]
            best["_matched_query"] = query
            return best
    return None


def _label(hit: dict) -> str:
    if hit["media_type"] == "person":
        return hit.get("name", "")
    return hit.get("title") or hit.get("name") or ""


def search(term: str, limit: int, key: str, session: requests.Session) -> List[ImageCandidate]:
    hit = _find(session, term, key)
    if not hit:
        print(f"  TMDB: no movie, TV show or person matches '{term}'")
        return []

    kind, tmdb_id, label = hit["media_type"], hit["id"], _label(hit)
    pretty_kind = {"movie": "movie", "tv": "TV show", "person": "person"}[kind]
    note = "" if hit["_matched_query"] == term else f" (matched on '{hit['_matched_query']}')"
    print(f"  TMDB: '{term}' looks like a {pretty_kind}: {label}{note}")

    results: List[ImageCandidate] = []

    if kind == "person":
        data = _get(session, f"/person/{tmdb_id}/images", key)
        page = f"{SITE}/person/{tmdb_id}"
        for img in data.get("profiles", []):
            results.append(_candidate(img, page, label, "profile"))
    else:
        data = _get(session, f"/{kind}/{tmdb_id}/images", key, include_image_language=LANGS)
        page = f"{SITE}/{kind}/{tmdb_id}"
        for img in data.get("backdrops", []):
            results.append(_candidate(img, page, label, "backdrop"))
        # Posters are portrait and often have text, but they are a useful fallback.
        if len(results) < limit:
            for img in data.get("posters", []):
                if not img.get("iso_639_1") or img.get("iso_639_1") == "en":
                    results.append(_candidate(img, page, label, "poster"))

    # Highest-rated first, then largest.
    results.sort(key=lambda c: (c.extra.get("vote_average", 0), c.width or 0), reverse=True)
    return results[: limit * 3]


def _candidate(img: dict, page: str, label: str, kind: str) -> ImageCandidate:
    return ImageCandidate(
        image_url=f"{IMG}{img['file_path']}",
        source="tmdb",
        page_url=page,
        width=img.get("width"),
        height=img.get("height"),
        title=f"{label} ({kind})",
        credit="TMDB",
        extra={"vote_average": img.get("vote_average", 0), "kind": kind},
    )
