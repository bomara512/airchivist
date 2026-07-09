import time
from datetime import datetime
from typing import Optional

import yt_dlp

from crawler.models import ChannelMetadata, FetchStatus, VideoMetadata

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
}


def _parse_upload_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _classify_error(message: str) -> FetchStatus:
    lower = message.lower()
    if "private video" in lower:
        return FetchStatus.PRIVATE
    if "has been removed" in lower or "video unavailable" in lower:
        return FetchStatus.DELETED
    return FetchStatus.ERROR


def fetch_metadata(video_id: str, delay: float = 1.5) -> VideoMetadata:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        return VideoMetadata(
            video_id=video_id,
            url=url,
            title=info.get("title"),
            description=info.get("description"),
            channel_name=info.get("uploader"),
            channel_id=info.get("channel_id"),
            yt_view_count=info.get("view_count"),
            duration_seconds=info.get("duration"),
            thumbnail_url=info.get("thumbnail"),
            date_published=_parse_upload_date(info.get("upload_date")),
            yt_categories=info.get("categories") or [],
            yt_tags=info.get("tags") or [],
            fetch_status=FetchStatus.OK,
        )
    except yt_dlp.utils.DownloadError as exc:
        status = _classify_error(str(exc))
        return VideoMetadata(
            video_id=video_id,
            url=url,
            fetch_status=status,
            fetch_error=str(exc),
        )
    finally:
        if delay > 0:
            time.sleep(delay)


_CHANNEL_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": True,
}


def fetch_channel_metadata(channel_url: str, delay: float = 1.5) -> ChannelMetadata:
    try:
        with yt_dlp.YoutubeDL(_CHANNEL_YDL_OPTS) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        channel_id = info.get("channel_id") or info.get("id", "")
        channel_name = info.get("channel") or info.get("uploader") or info.get("title", "")
        url = info.get("channel_url") or info.get("webpage_url") or channel_url

        return ChannelMetadata(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_url=url,
            description=info.get("description"),
            subscriber_count=info.get("channel_follower_count"),
            thumbnail_url=info.get("thumbnail"),
            fetch_status=FetchStatus.OK,
        )
    except yt_dlp.utils.DownloadError as exc:
        status = _classify_error(str(exc))
        return ChannelMetadata(
            channel_id="",
            channel_name="",
            channel_url=channel_url,
            fetch_status=status,
            fetch_error=str(exc),
        )
    finally:
        if delay > 0:
            time.sleep(delay)
