import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from crawler.datastore import Datastore
from crawler.metadata_fetcher import fetch_metadata
from crawler.models import VideoMetadata

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200

# Tally key for a video whose fetch raised something `fetch_metadata` does not
# convert into a FetchStatus — a bare network error, say. Not a FetchStatus member
# because no status is written to the row: the video keeps the last status that was
# actually determined. Only `last_fetched_at` moves; see `mark_fetch_attempted`.
FAILED = "failed"


def _format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


@dataclass(frozen=True)
class RefreshSummary:
    """The outcome of one refresh run, as one scannable log line."""

    attempted: int
    library_total: int
    counts: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def line(self) -> str:
        breakdown = ", ".join(f"{n} {status}" for status, n in sorted(self.counts.items()))
        suffix = f" ({breakdown})" if breakdown else ""
        return (
            f"refreshed {self.attempted} of {self.library_total}"
            f"{suffix} in {_format_elapsed(self.elapsed_seconds)}"
        )


def run_refresh(
    ds: Datastore,
    limit: int = DEFAULT_LIMIT,
    delay: float = 1.5,
    fetch: Callable[..., VideoMetadata] = fetch_metadata,
) -> RefreshSummary:
    """Re-fetch the `limit` stalest videos and record what came back.

    `fetch` is injectable so tests can drive the loop without yt-dlp or a network.

    One video's unexpected failure never aborts the run: a nightly job that gave up
    on the first transient network error would silently stop maintaining the library,
    and the failure would only be visible to someone reading the log. Such a video is
    counted under FAILED, keeps its stored status and error, and has only its
    `last_fetched_at` bumped so it goes to the back of the rotation.
    """
    started = time.monotonic()
    video_ids = ds.get_stale_video_ids(limit)
    counts: dict[str, int] = {}

    for video_id in video_ids:
        try:
            metadata = fetch(video_id, delay=delay)
        except Exception as exc:
            logger.error("Unexpected error refreshing %s: %s", video_id, exc)
            counts[FAILED] = counts.get(FAILED, 0) + 1
            # Status and error stay as they were — a bare network error says nothing
            # about the video — but last_fetched_at moves, so a repeatably failing
            # video rotates to the back instead of blocking the queue head forever.
            ds.mark_fetch_attempted(video_id)
            continue
        ds.refresh_video(metadata)
        counts[metadata.fetch_status] = counts.get(metadata.fetch_status, 0) + 1

    return RefreshSummary(
        attempted=len(video_ids),
        library_total=ds.count_videos(),
        counts=counts,
        elapsed_seconds=time.monotonic() - started,
    )
