"""Unsplash source."""

from __future__ import annotations

from typing import List

import requests

from ..models import ImageCandidate

API = "https://api.unsplash.com/search/photos"


def search(term: str, limit: int, key: str, session: requests.Session) -> List[ImageCandidate]:
    headers = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}
    params = {"query": term, "per_page": min(30, max(10, limit * 3)), "content_filter": "high"}
    resp = session.get(API, params=params, headers=headers, timeout=20)
    if resp.status_code in (401, 403):
        raise RuntimeError("Unsplash rejected the key. Check UNSPLASH_ACCESS_KEY in .env")
    if resp.status_code == 429:
        raise RuntimeError("Unsplash rate limit hit (demo apps: 50 requests/hour). Try again later")
    resp.raise_for_status()

    results: List[ImageCandidate] = []
    for photo in resp.json().get("results", []):
        urls = photo.get("urls", {})
        # "raw" lets us ask for a sensible size instead of 6000px originals.
        base = urls.get("raw") or urls.get("full")
        if not base:
            continue
        sep = "&" if "?" in base else "?"
        image_url = f"{base}{sep}w=1920&q=85&fm=jpg"
        user = photo.get("user", {}) or {}
        results.append(
            ImageCandidate(
                image_url=image_url,
                source="unsplash",
                page_url=(photo.get("links", {}) or {}).get("html", ""),
                width=photo.get("width"),
                height=photo.get("height"),
                title=photo.get("alt_description") or photo.get("description") or "",
                credit=user.get("name", ""),
                extra={"download_location": (photo.get("links", {}) or {}).get("download_location", "")},
            )
        )
    return results


def register_download(candidate: ImageCandidate, key: str, session: requests.Session) -> None:
    """Unsplash API guidelines ask apps to ping this endpoint when a photo is used."""
    loc = candidate.extra.get("download_location")
    if not loc:
        return
    try:
        session.get(loc, headers={"Authorization": f"Client-ID {key}"}, timeout=10)
    except requests.RequestException:
        pass  # best effort only
