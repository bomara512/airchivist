import pytest
from pathlib import Path
from datetime import datetime, timezone
from crawler.bookmark_parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


class TestJsonParser:
    def test_parse_json_returns_bookmark_list(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        assert isinstance(bookmarks, list)
        assert len(bookmarks) > 0

    def test_parse_json_finds_nested_youtube_urls(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        yt = [b for b in bookmarks if b.youtube_video_id is not None]
        assert len(yt) >= 2

    def test_parse_json_includes_non_youtube_urls(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        non_yt = [b for b in bookmarks if b.youtube_video_id is None]
        assert len(non_yt) >= 1

    def test_parse_json_converts_microsecond_timestamps(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        # bookmark with dateAdded=1620000000000000 microseconds
        rick = next(b for b in bookmarks if "dQw4w9WgXcQ" in b.url)
        assert rick.date_added is not None
        expected = datetime.fromtimestamp(1620000000, tz=timezone.utc)
        assert rick.date_added.replace(tzinfo=timezone.utc) == expected

    def test_parse_json_handles_missing_dates_gracefully(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        no_date = next(b for b in bookmarks if "Ks-_Mh1QhMc" in b.url)
        assert no_date.date_added is None

    def test_parse_json_handles_shortlink_url(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        short = next(b for b in bookmarks if "youtu.be" in b.url)
        assert short.youtube_video_id == "9bZkp7q19f0"

    def test_parse_json_captures_title(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        rick = next(b for b in bookmarks if "dQw4w9WgXcQ" in b.url)
        assert rick.title == "Rick Astley - Never Gonna Give You Up"


class TestHtmlParser:
    def test_parse_html_returns_bookmark_list(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        assert isinstance(bookmarks, list)
        assert len(bookmarks) > 0

    def test_parse_html_finds_all_youtube_urls(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        yt = [b for b in bookmarks if b.youtube_video_id is not None]
        assert len(yt) == 3

    def test_parse_html_includes_non_youtube(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        non_yt = [b for b in bookmarks if b.youtube_video_id is None]
        assert len(non_yt) >= 1

    def test_parse_html_converts_second_timestamps(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        rick = next(b for b in bookmarks if "dQw4w9WgXcQ" in b.url)
        assert rick.date_added is not None
        expected = datetime.fromtimestamp(1620000000, tz=timezone.utc)
        assert rick.date_added.replace(tzinfo=timezone.utc) == expected

    def test_parse_html_handles_missing_last_visit(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        no_visit = next(b for b in bookmarks if "Ks-_Mh1QhMc" in b.url)
        # date_added should still be set
        assert no_visit.date_added is not None

    def test_parse_html_captures_title(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        rick = next(b for b in bookmarks if "dQw4w9WgXcQ" in b.url)
        assert rick.title == "Rick Astley - Never Gonna Give You Up"


class TestFormatDetection:
    def test_detect_format_json(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.json")
        assert len(bookmarks) > 0  # parsed successfully

    def test_detect_format_html(self):
        bookmarks = parse(FIXTURES / "sample_bookmarks.html")
        assert len(bookmarks) > 0

    def test_detect_format_unknown_raises(self, tmp_path):
        f = tmp_path / "bookmarks.csv"
        f.write_text("url,title\nhttps://youtube.com/watch?v=abc,test")
        with pytest.raises(ValueError, match="Unsupported"):
            parse(f)
