"""Pexels source."""

from __future__ import annotations

from typing import List

import requests

from ..models import ImageCandidate

API = "https://api.pexels.com/v1/search"


def search(term: str, limit: int, key: str, session: requests.Session) -> List[ImageCandidate]:
    headers = {"Authorization": key}
    params = {"query": term, "per_page": min(80, max(15, limit * 3)), "size": "large"}
    resp = session.get(API, params=params, headers=headers, timeout=20)
    if resp.status_code in (401, 403):
        raise RuntimeError("Pexels rejected the key. Check PEXELS_API_KEY in .env")
    if resp.status_code == 429:
        raise RuntimeError("Pexels rate limit hit (200 requests/hour). Try again later")
    resp.raise_for_status()

    results: List[ImageCandidate] = []
    for photo in resp.json().get("photos", []):
        src = photo.get("src", {}) or {}
        # large2x is 1880px wide: plenty for a 1080px crop and much smaller than "original".
        image_url = src.get("large2x") or src.get("original")
        if not image_url:
            continue
        results.append(
            ImageCandidate(
                image_url=image_url,
                source="pexels",
                page_url=photo.get("url", ""),
                width=photo.get("width"),
                height=photo.get("height"),
                title=photo.get("alt", ""),
                credit=photo.get("photographer", ""),
            )
        )
    return results
