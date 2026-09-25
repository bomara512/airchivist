import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class FetchStatus(StrEnum):
    PENDING = 'pending'
    OK = 'ok'
    ERROR = 'error'
    PRIVATE = 'private'
    DELETED = 'deleted'


class MatchType(StrEnum):
    EXACT = 'exact'
    PREFIX = 'prefix'
    CONTAINS = 'contains'

YT_ID_RE = re.compile(
    r'(?:youtube\.com/watch\?.*?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)'
    r'([A-Za-z0-9_-]{11})'
)

# Keep in sync with extension/popup/popup.js YT_CHANNEL_RE.
YT_CHANNEL_RE = re.compile(
    r'youtube\.com/(?:channel/(UC[A-Za-z0-9_-]+)|(?:c|user)/([^/?#]+)|@([^/?#]+))'
)


def extract_video_id(url: str | None) -> str | None:
    """Return the 11-character YouTube video ID in `url`, or None if there isn't one.

    Anything that is not a string — None, or a JSON body sending `{"url": 123}` —
    yields None rather than raising, so a malformed request reaches the caller's
    400 instead of a 500.
    """
    if not isinstance(url, str):
        return None
    m = YT_ID_RE.search(url)
    return m.group(1) if m else None


@dataclass
class Bookmark:
    url: str
    title: str
    date_added: datetime | None = None

    @property
    def youtube_video_id(self) -> str | None:
        m = YT_ID_RE.search(self.url)
        return m.group(1) if m else None

    @property
    def youtube_channel_url(self) -> str | None:
        return self.url if YT_CHANNEL_RE.search(self.url) else None


@dataclass
class VideoMetadata:
    video_id: str
    url: str
    title: str | None = None
    description: str | None = None
    channel_name: str | None = None
    channel_id: str | None = None
    yt_view_count: int | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    date_published: datetime | None = None
    yt_categories: list[str] = field(default_factory=list)
    yt_tags: list[str] = field(default_factory=list)
    fetch_status: FetchStatus = FetchStatus.PENDING
    fetch_error: str | None = None

    def __post_init__(self) -> None:
        if self.yt_view_count is not None and self.yt_view_count < 0:
            raise ValueError("yt_view_count must be non-negative")


@dataclass
class ChannelMetadata:
    channel_id: str
    channel_name: str
    channel_url: str
    description: str | None = None
    subscriber_count: int | None = None
    thumbnail_url: str | None = None
    fetch_status: FetchStatus = FetchStatus.OK
    fetch_error: str | None = None
