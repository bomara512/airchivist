import argparse
import logging
import sys
from pathlib import Path

from crawler.bookmark_parser import parse
from crawler.datastore import Datastore
from crawler.metadata_fetcher import fetch_metadata

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="ViewTube Bookmark Crawler")
    parser.add_argument("-i", "--input", required=True, type=Path, metavar="FILE",
                        help="Path to Firefox bookmarks file (.json or .html)")
    parser.add_argument("-o", "--output", required=True, type=Path, metavar="FILE",
                        help="Path to output SQLite database file")
    parser.add_argument("--api-key", default=None, metavar="KEY",
                        help="YouTube Data API v3 key (enables faster batch mode)")
    parser.add_argument("--delay", type=float, default=1.5, metavar="SECONDS",
                        help="Seconds between yt-dlp requests (default: 1.5)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Only process the first N YouTube bookmarks")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch metadata even for already-stored videos")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        bookmarks = parse(args.input)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    yt_bookmarks = [b for b in bookmarks if b.youtube_video_id]
    if args.limit is not None:
        yt_bookmarks = yt_bookmarks[: args.limit]

    try:
        with Datastore(args.output) as ds:
            total = len(yt_bookmarks)
            for i, bookmark in enumerate(yt_bookmarks, 1):
                vid_id = bookmark.youtube_video_id
                print(f"[{i}/{total}] {vid_id}", flush=True)

                if not args.force_refresh and ds.get_video_by_id(vid_id):
                    logger.info("Skipping already-fetched: %s", vid_id)
                    continue

                try:
                    metadata = fetch_metadata(vid_id, delay=args.delay)
                except Exception as exc:
                    logger.error("Unexpected error fetching %s: %s", vid_id, exc)
                    continue

                ds.upsert_video(metadata, bookmark)

    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved.", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:
        logger.error("Database error: %s", exc)
        sys.exit(3)


if __name__ == "__main__":
    main()
