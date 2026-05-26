import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from crawler.metadata_fetcher import fetch_metadata
from crawler.models import VideoMetadata

_GOOD_INFO = {
    "id": "dQw4w9WgXcQ",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "description": "The official video for Never Gonna Give You Up",
    "uploader": "RickAstleyVEVO",
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "view_count": 1_400_000_000,
    "duration": 213,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "upload_date": "20091025",
}


def _make_ydl_mock(info=None, error=None):
    mock_ydl = MagicMock()
    if error:
        mock_ydl.__enter__.return_value.extract_info.side_effect = error
    else:
        mock_ydl.__enter__.return_value.extract_info.return_value = info or _GOOD_INFO
    return mock_ydl


class TestFetchMetadata:
    def test_returns_videometadata_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert isinstance(result, VideoMetadata)

    def test_maps_video_id(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.video_id == "dQw4w9WgXcQ"

    def test_maps_title(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.title == "Rick Astley - Never Gonna Give You Up"

    def test_maps_yt_view_count(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.yt_view_count == 1_400_000_000

    def test_maps_channel_name(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.channel_name == "RickAstleyVEVO"

    def test_maps_channel_id(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_maps_duration_seconds(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.duration_seconds == 213

    def test_maps_thumbnail_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.thumbnail_url == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"

    def test_maps_upload_date_to_datetime(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.date_published == datetime(2009, 10, 25)

    def test_sets_fetch_status_ok_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.fetch_status == "ok"

    def test_url_is_canonical_youtube_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_handles_private_video(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("ERROR: Private video")
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(error=error)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.fetch_status == "private"
        assert result.fetch_error is not None

    def test_handles_deleted_video(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("ERROR: This video has been removed by the user")
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(error=error)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.fetch_status == "deleted"

    def test_handles_generic_network_error(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("ERROR: Unable to download webpage")
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(error=error)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.fetch_status == "error"
        assert result.title is None

    def test_handles_missing_optional_fields(self):
        sparse_info = {
            "id": "dQw4w9WgXcQ",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Some Video",
        }
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(info=sparse_info)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.fetch_status == "ok"
        assert result.yt_view_count is None
        assert result.duration_seconds is None
        assert result.date_published is None
