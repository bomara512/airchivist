from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

DEFAULT_SORT_BY = "date_added"
DEFAULT_SORT_DIR = "desc"


class WatchStatus(StrEnum):
    """Values of the toolbar's single watch-status select. Empty string = all videos."""

    UNWATCHED = "unwatched"
    UNWATCHED_FIRST = "unwatched_first"


class GroupBy(StrEnum):
    CHANNEL = "channel"
    TAG = "tag"


@dataclass(frozen=True)
class VideoListFilters:
    """The main video list's filter/sort state, parsed from the query string."""

    sort_by: str = DEFAULT_SORT_BY
    sort_dir: str = DEFAULT_SORT_DIR
    channel: str | None = None
    tag: str | None = None
    search: str | None = None
    group: str | None = None
    favorites_only: bool = False
    watch_status: str = ""
    duration: str | None = None
    added_within: int | None = None

    @classmethod
    def from_args(cls, args: Mapping[str, Any]) -> "VideoListFilters":
        try:
            added_within = int(args["added_within"]) if args.get("added_within") else None
        except (TypeError, ValueError):
            added_within = None
        return cls(
            sort_by=args.get("sort_by", DEFAULT_SORT_BY),
            sort_dir=args.get("sort_dir", DEFAULT_SORT_DIR),
            channel=args.get("channel") or None,
            tag=args.get("tag") or None,
            search=args.get("search") or None,
            group=args.get("group") or None,
            favorites_only=args.get("favorites") == "1",
            watch_status=args.get("watch_status", ""),
            duration=args.get("duration") or None,
            added_within=added_within,
        )

    @property
    def unwatched_only(self) -> bool:
        return self.watch_status == WatchStatus.UNWATCHED

    @property
    def unwatched_first(self) -> bool:
        return self.watch_status == WatchStatus.UNWATCHED_FIRST

    @property
    def active_count(self) -> int:
        """How many filters differ from their default — the `Filters N` badge.

        Search deliberately does not count: it lives outside the collapsible
        filter panel the badge describes. See plan-webapp.md.
        """
        return sum((
            self.channel is not None,
            self.tag is not None,
            self.sort_by != DEFAULT_SORT_BY,
            self.sort_dir != DEFAULT_SORT_DIR,
            bool(self.group),
            self.favorites_only,
            bool(self.watch_status),
            bool(self.duration),
            self.added_within is not None,
        ))

    def db_kwargs(self) -> dict[str, Any]:
        """The subset of this state that both count_videos and get_all_videos take."""
        return {
            "channel": self.channel,
            "tag": self.tag,
            "search": self.search,
            "favorites_only": self.favorites_only,
            "unwatched_only": self.unwatched_only,
            "duration": self.duration,
            "added_within": self.added_within,
        }


def group_videos(videos: list[dict], group: str | None) -> list[dict] | None:
    """Partition a page of videos for the grouped views, or None when not grouping.

    Shape is `[{"tag": {"name": label}, "videos": [...]}, ...]`, consumed by
    `_video_container.html`. A video with several canonical tags appears in each
    matching group, so groups can overlap; channel groups cannot.
    """
    if group == GroupBy.CHANNEL:
        grouped: dict[str, list[dict]] = {}
        for video in videos:
            grouped.setdefault(video.get("channel_name") or "Unknown", []).append(video)
        return [{"tag": {"name": name}, "videos": vids} for name, vids in grouped.items()]

    if group == GroupBy.TAG:
        grouped = {}
        untagged: list[dict] = []
        for video in videos:
            names = [t.strip() for t in (video.get("tags") or "").split(",") if t.strip()]
            if not names:
                untagged.append(video)
            for name in names:
                grouped.setdefault(name, []).append(video)
        groups = [{"tag": {"name": name}, "videos": vids} for name, vids in sorted(grouped.items())]
        if untagged:
            groups.append({"tag": {"name": "Untagged"}, "videos": untagged})
        return groups

    return None
