"""Duplicate detection: exact (SHA-256) and near-duplicate (difference hash)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List, Optional

from PIL import Image

HASH_SIZE = 8                 # 8x8 -> 64-bit hash
NEAR_DUPLICATE_DISTANCE = 6   # hamming distance at or below this counts as the same image


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dhash(image: Image.Image) -> int:
    """Difference hash. Survives resizing, re-encoding and small colour changes."""
    gray = image.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    bits = 0
    for row in range(HASH_SIZE):
        for col in range(HASH_SIZE):
            left = pixels[row * (HASH_SIZE + 1) + col]
            right = pixels[row * (HASH_SIZE + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class DuplicateIndex:
    """Remembers what we've already kept for one search term."""

    def __init__(self) -> None:
        self.urls: set[str] = set()
        self.exact: set[str] = set()
        self.perceptual: List[int] = []

    def seen_url(self, url: str) -> bool:
        return _normalise_url(url) in self.urls

    def add_url(self, url: str) -> None:
        self.urls.add(_normalise_url(url))

    def is_duplicate(self, data: bytes, image: Image.Image) -> Optional[str]:
        """Return a reason string if this image duplicates one we already have."""
        digest = sha256(data)
        if digest in self.exact:
            return "identical file"
        phash = dhash(image)
        for known in self.perceptual:
            if hamming(phash, known) <= NEAR_DUPLICATE_DISTANCE:
                return "near-duplicate"
        return None

    def add(self, data: bytes, image: Image.Image, url: str = "") -> None:
        self.exact.add(sha256(data))
        self.perceptual.append(dhash(image))
        if url:
            self.add_url(url)

    def load_existing(self, files: Iterable[Path]) -> int:
        """Index images already on disk so re-runs don't save the same picture twice."""
        count = 0
        for path in files:
            try:
                data = path.read_bytes()
                with Image.open(path) as img:
                    img.load()
                    self.add(data, img)
                count += 1
            except Exception:  # unreadable file: ignore it
                continue
        return count


def _normalise_url(url: str) -> str:
    return url.split("#", 1)[0].strip().lower()
