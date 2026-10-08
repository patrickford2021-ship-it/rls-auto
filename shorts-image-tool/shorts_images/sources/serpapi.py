"""Google Images via SerpAPI."""

from __future__ import annotations

from typing import List

import requests

from ..models import ImageCandidate

API = "https://serpapi.com/search.json"


def search(term: str, limit: int, key: str, session: requests.Session) -> List[ImageCandidate]:
    params = {
        "engine": "google_images",
        "q": term,
        "api_key": key,
        "safe": "active",
        "hl": "en",
        "gl": "us",
        # Ask Google for large images only; we still verify the real size later.
        "imgsz": "l",
    }
    resp = session.get(API, params=params, timeout=30)
    if resp.status_code in (401, 403):
        raise RuntimeError("SerpAPI rejected the key. Check SERPAPI_API_KEY in .env")
    if resp.status_code == 429:
        raise RuntimeError("SerpAPI monthly search limit reached (free plan: 250 searches/month)")
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"SerpAPI error: {data['error']}")

    results: List[ImageCandidate] = []
    for item in data.get("images_results", []):
        url = item.get("original")
        if not url or not url.lower().startswith("http"):
            continue
        results.append(
            ImageCandidate(
                image_url=url,
                source="google",
                page_url=item.get("link", ""),
                width=item.get("original_width"),
                height=item.get("original_height"),
                title=item.get("title", ""),
                credit=item.get("source", ""),
            )
        )
    return results[: limit * 4]
