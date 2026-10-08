#!/usr/bin/env python3
"""Fetch images for YouTube Shorts from a keywords file.

Usage:
    python fetch_images.py keywords.txt
    python fetch_images.py keywords.txt --count 12
    python fetch_images.py keywords.txt --output my_folder --no-crop

Each line of the keywords file is one search term. Start a line with a tag
to choose where it is searched:

    tmdb: Breaking Bad Walter White     -> TMDB (movies, TV, actors)
    google: Jim Lahey drunk             -> Google Images (via SerpAPI)
    sunset over the ocean               -> Unsplash + Pexels + Pixabay
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from shorts_images import __version__
    from shorts_images.config import KEY_NAMES, get_key, load_env
    from shorts_images.crop import HAVE_OPENCV
    from shorts_images.download import make_session
    from shorts_images.parsing import parse_keywords_file
    from shorts_images.pipeline import MissingKeyTracker, Settings, process_term
except ImportError as exc:  # friendlier than a traceback for non-developers
    print(f"Missing dependency: {exc}")
    print("Install everything with:  pip install -r requirements.txt")
    sys.exit(1)


def parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("size must look like 1080x960")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download images for YouTube Shorts from TMDB, Google Images, Unsplash, Pexels and Pixabay.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:", 1)[-1],
    )
    parser.add_argument("keywords", help="text file with one search term per line")
    parser.add_argument("-n", "--count", type=int, default=8, help="images to save per term (default: 8)")
    parser.add_argument("-o", "--output", default=str(HERE / "output"), help="output folder (default: ./output)")
    parser.add_argument("--min-width", type=int, default=800, help="skip images narrower than this (default: 800)")
    parser.add_argument("--no-crop", action="store_true", help="don't write the cropped copies")
    parser.add_argument("--crop-size", type=parse_size, default=(1080, 960), help="crop size WxH (default: 1080x960)")
    parser.add_argument("--no-faces", action="store_true", help="disable face detection when cropping")
    parser.add_argument("--timeout", type=int, default=25, help="seconds to wait for each download (default: 25)")
    parser.add_argument("--version", action="version", version=f"fetch_images {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    keywords_path = Path(args.keywords)
    if not keywords_path.is_file():
        print(f"Keywords file not found: {keywords_path}")
        return 1

    env_path = load_env(HERE)
    configured = [name for name in KEY_NAMES if get_key(name)]
    if env_path is None and not configured:
        print("No .env file found. Copy .env.example to .env and paste your API keys into it.")
        print("Continuing anyway; every source will be skipped until keys are added.\n")

    jobs = parse_keywords_file(keywords_path)
    if not jobs:
        print(f"{keywords_path} has no search terms in it.")
        return 1

    settings = Settings(
        output_dir=Path(args.output),
        count=max(1, args.count),
        min_width=max(1, args.min_width),
        crop=not args.no_crop,
        crop_size=args.crop_size,
        use_faces=not args.no_faces,
        timeout=args.timeout,
    )
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"fetch_images {__version__}")
    print(f"Keys found for: {', '.join(configured) if configured else 'none'}")
    if settings.crop:
        print(f"Cropping to {settings.crop_size[0]}x{settings.crop_size[1]} "
              f"({'face detection on' if settings.use_faces and HAVE_OPENCV else 'face detection off'})")
    print(f"{len(jobs)} term(s), {settings.count} image(s) each, min width {settings.min_width}px")
    print(f"Output: {settings.output_dir.resolve()}\n")

    session = make_session()
    tracker = MissingKeyTracker()
    started = time.time()
    total_saved = 0
    summary = []

    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {job.term}  (source: {job.tag})")
        try:
            result = process_term(job, settings, session, tracker)
        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception as exc:  # never let one bad term kill the whole run
            print(f"  !! Unexpected error, moving on: {exc}")
            summary.append((job.term, 0, "error"))
            continue
        total_saved += result.saved
        summary.append((job.term, result.saved, str(result.folder)))
        print()

    elapsed = time.time() - started
    print("=" * 60)
    print(f"Done in {elapsed:.0f}s. Saved {total_saved} new image(s).")
    for term, saved, folder in summary:
        print(f"  {saved:>3}  {term}  ->  {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
