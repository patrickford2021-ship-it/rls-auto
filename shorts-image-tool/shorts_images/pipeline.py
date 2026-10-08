"""Runs one search term end to end: search -> download -> dedupe -> crop -> CSV."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import requests

from . import sources as src
from .config import get_key
from .crop import crop_for_shorts
from .dedupe import DuplicateIndex
from .download import DownloadError, fetch_image, reported_too_small
from .models import ImageCandidate, Job
from .parsing import slugify

CSV_COLUMNS = ["file", "cropped_file", "source", "source_site", "page_url", "image_url", "width", "height", "title", "credit"]


@dataclass
class Settings:
    output_dir: Path
    count: int = 8
    min_width: int = 800
    crop: bool = True
    crop_size: tuple = (1080, 960)
    use_faces: bool = True
    timeout: int = 25


@dataclass
class TermResult:
    term: str
    saved: int
    skipped: int
    folder: Path
    errors: List[str]


class MissingKeyTracker:
    """Warn once per missing key instead of once per term."""

    def __init__(self) -> None:
        self._warned: set[str] = set()

    def warn(self, source: str) -> None:
        if source in self._warned:
            return
        self._warned.add(source)
        key_name = src.SOURCE_KEY[source]
        from .config import KEY_NAMES

        print(f"  !! {src.PRETTY[source]} skipped: {KEY_NAMES[key_name]} is not set in .env")


def gather_candidates(job: Job, settings: Settings, session: requests.Session, tracker: MissingKeyTracker) -> List[ImageCandidate]:
    """Query every source the job's tag expands to, interleaving their results."""
    per_source: Dict[str, List[ImageCandidate]] = {}
    for name in src.TAG_TO_SOURCES[job.tag]:
        key = get_key(src.SOURCE_KEY[name])
        if not key:
            tracker.warn(name)
            continue
        try:
            results = src.SOURCES[name].search(job.term, settings.count, key, session)
            print(f"  {src.PRETTY[name]}: {len(results)} results")
            per_source[name] = results
        except Exception as exc:  # one source failing must not stop the run
            print(f"  !! {src.PRETTY[name]} failed: {exc}")
    return _interleave(per_source)


def _interleave(per_source: Dict[str, List[ImageCandidate]]) -> List[ImageCandidate]:
    """Round-robin merge so a term gets a mix of sources rather than all from one."""
    merged: List[ImageCandidate] = []
    lists = [list(v) for v in per_source.values() if v]
    while lists:
        for lst in list(lists):
            merged.append(lst.pop(0))
            if not lst:
                lists.remove(lst)
    return merged


def process_term(job: Job, settings: Settings, session: requests.Session, tracker: MissingKeyTracker) -> TermResult:
    slug = slugify(job.term)
    folder = settings.output_dir / slug
    cropped_dir = folder / "cropped"

    index = DuplicateIndex()
    existing: List[Path] = []
    if folder.is_dir():
        existing = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    already_have = index.load_existing(existing)
    _load_existing_urls(folder / "sources.csv", index)
    if already_have:
        print(f"  Folder already has {already_have} image(s); only adding new ones")

    needed = max(0, settings.count - already_have)
    if needed == 0:
        print(f"  Already have {already_have} images (target {settings.count}); nothing to do")
        return TermResult(job.term, 0, 0, folder, [])

    candidates = gather_candidates(job, settings, session, tracker)
    if not candidates:
        print("  No candidates found for this term.")
        return TermResult(job.term, 0, 0, folder, ["no results"])

    # Only create folders once we actually have something to put in them.
    folder.mkdir(parents=True, exist_ok=True)
    if settings.crop:
        cropped_dir.mkdir(exist_ok=True)

    rows: List[dict] = []
    saved = skipped = 0
    next_number = _next_number(existing, slug)
    errors: List[str] = []

    for cand in candidates:
        if saved >= needed:
            break
        if index.seen_url(cand.image_url):
            skipped += 1
            continue
        index.add_url(cand.image_url)
        if reported_too_small(cand.width, settings.min_width):
            skipped += 1
            continue

        label = f"{cand.source:<9}"
        try:
            data, image, ext = fetch_image(cand.image_url, session, timeout=settings.timeout)
        except DownloadError as exc:
            skipped += 1
            print(f"    - skip [{label}] {exc}")
            continue

        if image.width < settings.min_width:
            skipped += 1
            print(f"    - skip [{label}] only {image.width}px wide (min {settings.min_width})")
            continue

        reason = index.is_duplicate(data, image)
        if reason:
            skipped += 1
            print(f"    - skip [{label}] {reason}")
            continue

        filename = f"{slug}_{next_number:02d}.{ext}"
        (folder / filename).write_bytes(data)
        index.add(data, image)

        cropped_name = ""
        method = ""
        if settings.crop:
            cropped_name = f"{slug}_{next_number:02d}.jpg"
            try:
                cropped, method = crop_for_shorts(image, settings.crop_size, settings.use_faces)
                cropped.save(cropped_dir / cropped_name, "JPEG", quality=90, optimize=True)
            except Exception as exc:
                cropped_name = ""
                errors.append(f"crop failed for {filename}: {exc}")
                print(f"    ! crop failed for {filename}: {exc}")

        if cand.source == "unsplash":
            src.unsplash.register_download(cand, get_key("unsplash") or "", session)

        rows.append(
            {
                "file": filename,
                "cropped_file": f"cropped/{cropped_name}" if cropped_name else "",
                "source": cand.source,
                "source_site": _site_name(cand),
                "page_url": cand.page_url,
                "image_url": cand.image_url,
                "width": image.width,
                "height": image.height,
                "title": cand.title,
                "credit": cand.credit,
            }
        )
        saved += 1
        next_number += 1
        crop_note = f", crop: {method}" if method else ""
        print(f"    + {saved}/{needed} [{label}] {filename} ({image.width}x{image.height}{crop_note})")
        time.sleep(0.1)  # be polite to the image hosts

    if rows:
        _append_csv(folder / "sources.csv", rows)
    if saved < needed:
        print(f"  Only found {saved} usable image(s) out of {needed} wanted ({skipped} skipped)")
    return TermResult(job.term, saved, skipped, folder, errors)


# --------------------------------------------------------------------------- helpers


def _site_name(cand: ImageCandidate) -> str:
    if cand.source == "google":
        host = cand.page_url.split("//", 1)[-1].split("/", 1)[0]
        return host.removeprefix("www.") or "google images"
    return src.PRETTY.get(cand.source, cand.source)


def _next_number(existing: List[Path], slug: str) -> int:
    highest = 0
    prefix = f"{slug}_"
    for path in existing:
        stem = path.stem
        if stem.startswith(prefix) and stem[len(prefix):].isdigit():
            highest = max(highest, int(stem[len(prefix):]))
    return highest + 1


def _load_existing_urls(csv_path: Path, index: DuplicateIndex) -> None:
    if not csv_path.is_file():
        return
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("image_url"):
                    index.add_url(row["image_url"])
    except Exception:
        pass


def _append_csv(csv_path: Path, rows: List[dict]) -> None:
    new_file = not csv_path.is_file() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)
