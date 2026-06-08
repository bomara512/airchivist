from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional
import re


class FetchStatus(StrEnum):
    PENDING = 'pending'
    OK = 'ok'
    ERROR = 'error'
    PRIVATE = 'private'
    DELETED = 'deleted'

_YT_ID_RE = re.compile(
    r'(?:youtube\.com/watch\?.*?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)'
    r'([A-Za-z0-9_-]{11})'
)


@dataclass
class Bookmark:
    url: str
    title: str
    date_added: Optional[datetime] = None

    @property
    def youtube_video_id(self) -> Optional[str]:
        m = _YT_ID_RE.search(self.url)
        return m.group(1) if m else None


@dataclass
class VideoMetadata:
    video_id: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    yt_view_count: Optional[int] = None
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    date_published: Optional[datetime] = None
    yt_categories: list[str] = field(default_factory=list)
    yt_tags: list[str] = field(default_factory=list)
    fetch_status: str = FetchStatus.PENDING
    fetch_error: Optional[str] = None

    def __post_init__(self):
        if self.yt_view_count is not None and self.yt_view_count < 0:
            raise ValueError("yt_view_count must be non-negative")
