"""Downloads an image URL and validates it with Pillow."""

from __future__ import annotations

import io
from typing import Optional, Tuple

import requests
from PIL import Image, UnidentifiedImageError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_BYTES = 40 * 1024 * 1024  # refuse anything above 40 MB

FORMAT_TO_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp", "TIFF": "tif"}


class DownloadError(Exception):
    pass


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
    return session


def fetch_image(url: str, session: requests.Session, timeout: int = 25) -> Tuple[bytes, Image.Image, str]:
    """Download `url`. Returns (raw bytes, opened PIL image, file extension)."""
    try:
        resp = session.get(url, timeout=timeout, stream=True, allow_redirects=True)
    except requests.RequestException as exc:
        raise DownloadError(f"network error: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise DownloadError(f"HTTP {resp.status_code}")

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if content_type.startswith("text/html"):
        raise DownloadError("got a web page instead of an image")

    chunks, total = [], 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        total += len(chunk)
        if total > MAX_BYTES:
            raise DownloadError("file too large")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise DownloadError("empty response")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise DownloadError("not a readable image") from exc

    ext = FORMAT_TO_EXT.get(image.format or "", "jpg")
    if ext == "gif":
        # Keep only the first frame of animated GIFs and save it as JPEG.
        image = image.convert("RGB")
        ext = "jpg"
    return data, image, ext


def reported_too_small(width: Optional[int], min_width: int) -> bool:
    """True when the API already tells us the image is narrower than we want."""
    return width is not None and width > 0 and width < min_width
