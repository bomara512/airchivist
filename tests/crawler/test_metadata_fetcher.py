import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from crawler.metadata_fetcher import fetch_metadata, fetch_channel_metadata
from crawler.models import VideoMetadata, ChannelMetadata

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
    "categories": ["Music"],
    "tags": ["rick astley", "never gonna give you up", "pop", "80s"],
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

    def test_maps_yt_categories(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.yt_categories == ["Music"]

    def test_maps_yt_tags(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock()):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert "rick astley" in result.yt_tags
        assert "80s" in result.yt_tags

    def test_yt_categories_defaults_to_empty_list_when_missing(self):
        info = {**_GOOD_INFO}
        del info["categories"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(info=info)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.yt_categories == []

    def test_yt_tags_defaults_to_empty_list_when_missing(self):
        info = {**_GOOD_INFO}
        del info["tags"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(info=info)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.yt_tags == []

    def test_yt_categories_handles_none_value(self):
        info = {**_GOOD_INFO, "categories": None}
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL", return_value=_make_ydl_mock(info=info)):
            result = fetch_metadata("dQw4w9WgXcQ", delay=0)
        assert result.yt_categories == []

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


_GOOD_CHANNEL_INFO = {
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "channel": "RickAstleyVEVO",
    "uploader": "RickAstleyVEVO",
    "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
    "description": "The official Rick Astley YouTube channel.",
    "channel_follower_count": 4_200_000,
    "thumbnail": "https://yt3.ggpht.com/rick-avatar.jpg",
}

_CHANNEL_URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"


def _make_channel_ydl_mock(info=None, error=None):
    mock_ydl = MagicMock()
    if error:
        mock_ydl.__enter__.return_value.extract_info.side_effect = error
    else:
        mock_ydl.__enter__.return_value.extract_info.return_value = (
            info if info is not None else _GOOD_CHANNEL_INFO
        )
    return mock_ydl


class TestFetchChannelMetadata:
    def test_returns_channelmetadata_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert isinstance(result, ChannelMetadata)

    def test_maps_channel_id(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_maps_channel_name_from_channel_field(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_name == "RickAstleyVEVO"

    def test_maps_channel_name_from_uploader_when_channel_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_name == "RickAstleyVEVO"

    def test_maps_channel_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_url == "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_falls_back_to_input_url_when_channel_url_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel_url"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_url == _CHANNEL_URL

    def test_maps_description(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.description == "The official Rick Astley YouTube channel."

    def test_maps_subscriber_count(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.subscriber_count == 4_200_000

    def test_maps_thumbnail_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.thumbnail_url == "https://yt3.ggpht.com/rick-avatar.jpg"

    def test_sets_fetch_status_ok_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "ok"

    def test_returns_error_status_on_download_error(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("ERROR: Unable to download webpage")
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(error=error)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "error"
        assert result.fetch_error is not None

    def test_handles_missing_optional_fields(self):
        sparse = {"channel_id": "UCabc", "channel": "Test",
                  "channel_url": "https://www.youtube.com/channel/UCabc"}
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=sparse)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "ok"
        assert result.description is None
        assert result.subscriber_count is None
        assert result.thumbnail_url is None

    def test_maps_channel_id_from_id_field_when_channel_id_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel_id"]
        info["id"] = "UCuAXFkgsw1L7xaCfnd5JJOw"
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_maps_channel_name_from_title_when_channel_and_uploader_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel"]
        del info["uploader"]
        info["title"] = "RickAstleyVEVO"
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_name == "RickAstleyVEVO"
