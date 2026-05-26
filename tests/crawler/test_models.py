import pytest
from crawler.models import Bookmark, VideoMetadata
from datetime import datetime


class TestBookmark:
    def test_construct_with_required_fields(self):
        b = Bookmark(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="Test")
        assert b.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert b.title == "Test"
        assert b.date_added is None

    def test_construct_with_date(self):
        dt = datetime(2024, 1, 15)
        b = Bookmark(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="Test", date_added=dt)
        assert b.date_added == dt

    def test_youtube_video_id_watch_url(self):
        b = Bookmark(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="T")
        assert b.youtube_video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_with_extra_params(self):
        b = Bookmark(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLabc", title="T")
        assert b.youtube_video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_short_url(self):
        b = Bookmark(url="https://youtu.be/dQw4w9WgXcQ", title="T")
        assert b.youtube_video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_embed_url(self):
        b = Bookmark(url="https://www.youtube.com/embed/dQw4w9WgXcQ", title="T")
        assert b.youtube_video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_shorts_url(self):
        b = Bookmark(url="https://www.youtube.com/shorts/dQw4w9WgXcQ", title="T")
        assert b.youtube_video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_non_youtube_url(self):
        b = Bookmark(url="https://www.google.com", title="T")
        assert b.youtube_video_id is None

    def test_youtube_video_id_vimeo_url(self):
        b = Bookmark(url="https://vimeo.com/123456789", title="T")
        assert b.youtube_video_id is None


class TestVideoMetadata:
    def test_construct_with_required_fields(self):
        m = VideoMetadata(video_id="dQw4w9WgXcQ", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert m.video_id == "dQw4w9WgXcQ"
        assert m.fetch_status == "pending"
        assert m.yt_view_count is None

    def test_yt_view_count_valid(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc", yt_view_count=1000000)
        assert m.yt_view_count == 1000000

    def test_yt_view_count_zero_is_valid(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc", yt_view_count=0)
        assert m.yt_view_count == 0

    def test_yt_view_count_negative_raises(self):
        with pytest.raises(ValueError, match="yt_view_count"):
            VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc", yt_view_count=-1)

    def test_fetch_status_default(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc")
        assert m.fetch_status == "pending"

    def test_all_optional_fields_none_by_default(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc")
        assert m.title is None
        assert m.description is None
        assert m.channel_name is None
        assert m.channel_id is None
        assert m.duration_seconds is None
        assert m.thumbnail_url is None
        assert m.date_published is None
        assert m.fetch_error is None

    def test_yt_categories_defaults_to_empty_list(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc")
        assert m.yt_categories == []

    def test_yt_tags_defaults_to_empty_list(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc")
        assert m.yt_tags == []

    def test_yt_categories_stores_values(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc",
                          yt_categories=["Music", "Education"])
        assert m.yt_categories == ["Music", "Education"]

    def test_yt_tags_stores_values(self):
        m = VideoMetadata(video_id="abc", url="https://youtube.com/watch?v=abc",
                          yt_tags=["guitar", "tutorial", "fingerstyle"])
        assert m.yt_tags == ["guitar", "tutorial", "fingerstyle"]

    def test_yt_categories_and_tags_are_independent_instances(self):
        # each instance must get its own list, not a shared default
        m1 = VideoMetadata(video_id="aaa", url="https://youtube.com/watch?v=aaa")
        m2 = VideoMetadata(video_id="bbb", url="https://youtube.com/watch?v=bbb")
        m1.yt_categories.append("Music")
        assert m2.yt_categories == []
