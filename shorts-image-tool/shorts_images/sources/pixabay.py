"""Pixabay source."""

from __future__ import annotations

from typing import List

import requests

from ..models import ImageCandidate

API = "https://pixabay.com/api/"


def search(term: str, limit: int, key: str, session: requests.Session) -> List[ImageCandidate]:
    params = {
        "key": key,
        "q": term,
        "image_type": "photo",
        "safesearch": "true",
        "per_page": min(200, max(20, limit * 3)),
        "min_width": 800,
    }
    resp = session.get(API, params=params, timeout=20)
    if resp.status_code in (400, 401, 403) and "key" in resp.text.lower():
        raise RuntimeError("Pixabay rejected the key. Check PIXABAY_API_KEY in .env")
    if resp.status_code == 429:
        raise RuntimeError("Pixabay rate limit hit (100 requests/minute). Try again later")
    resp.raise_for_status()

    results: List[ImageCandidate] = []
    for hit in resp.json().get("hits", []):
        # fullHDURL/imageURL need special approval; largeImageURL (1280px) is always available.
        image_url = hit.get("fullHDURL") or hit.get("largeImageURL")
        if not image_url:
            continue
        # largeImageURL is scaled to 1280 on the long edge; report that rather than the original size.
        width, height = hit.get("imageWidth"), hit.get("imageHeight")
        if not hit.get("fullHDURL") and width and height:
            scale = 1280 / max(width, height)
            if scale < 1:
                width, height = round(width * scale), round(height * scale)
        results.append(
            ImageCandidate(
                image_url=image_url,
                source="pixabay",
                page_url=hit.get("pageURL", ""),
                width=width,
                height=height,
                title=hit.get("tags", ""),
                credit=hit.get("user", ""),
            )
        )
    return results
