import argparse
import logging
import sys
from pathlib import Path

from crawler.bookmark_parser import parse
from crawler.datastore import Datastore
from crawler.metadata_fetcher import fetch_channel_metadata, fetch_metadata

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Airchivist Bookmark Crawler")
    parser.add_argument("-i", "--input", required=True, type=Path, metavar="FILE",
                        help="Path to Firefox bookmarks file (.json or .html)")
    parser.add_argument("-o", "--output", required=True, type=Path, metavar="FILE",
                        help="Path to output SQLite database file")
    parser.add_argument("--api-key", default=None, metavar="KEY",
                        help="YouTube Data API v3 key (enables faster batch mode)")
    parser.add_argument("--delay", type=float, default=1.5, metavar="SECONDS",
                        help="Seconds between yt-dlp requests (default: 1.5)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Only process the first N YouTube video bookmarks")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch metadata even for already-stored videos")
    parser.add_argument("--backfill-channels", action="store_true",
                        help="Fetch full metadata for channels that only have stub records")
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

    video_bookmarks = [b for b in bookmarks if b.youtube_video_id]
    channel_bookmarks = [b for b in bookmarks if b.youtube_channel_url]
    if args.limit is not None:
        video_bookmarks = video_bookmarks[: args.limit]

    try:
        with Datastore(args.output) as ds:
            total = len(video_bookmarks)
            for i, bookmark in enumerate(video_bookmarks, 1):
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
                if metadata.channel_id and metadata.channel_name:
                    channel_url = f"https://www.youtube.com/channel/{metadata.channel_id}"
                    ds.upsert_channel_stub(
                        metadata.channel_id, metadata.channel_name, channel_url
                    )

            ch_total = len(channel_bookmarks)
            for i, bookmark in enumerate(channel_bookmarks, 1):
                print(f"[channel {i}/{ch_total}] {bookmark.url}", flush=True)
                if not args.force_refresh and ds.has_full_channel_record(bookmark.url):
                    logger.info("Skipping already-fetched channel: %s", bookmark.url)
                    continue
                try:
                    ch_meta = fetch_channel_metadata(bookmark.url, delay=args.delay)
                except Exception as exc:
                    logger.error("Unexpected error fetching channel %s: %s", bookmark.url, exc)
                    continue
                ds.upsert_channel(ch_meta, source_url=bookmark.url)

            if args.backfill_channels:
                backfill_ids = ds.get_channel_ids_for_backfill()
                bf_total = len(backfill_ids)
                for i, channel_id in enumerate(backfill_ids, 1):
                    url = f"https://www.youtube.com/channel/{channel_id}"
                    print(f"[backfill {i}/{bf_total}] {channel_id}", flush=True)
                    try:
                        ch_meta = fetch_channel_metadata(url, delay=args.delay)
                    except Exception as exc:
                        logger.error("Unexpected error backfilling %s: %s", channel_id, exc)
                        continue
                    ds.upsert_channel(ch_meta)

    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved.", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:
        logger.error("Database error: %s", exc)
        sys.exit(3)


if __name__ == "__main__":
    main()
