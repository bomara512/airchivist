import pytest
from webapp.filters import format_view_count, format_date, format_duration


class TestFormatViewCount:
    def test_none_returns_dash(self):
        assert format_view_count(None) == "—"

    def test_zero(self):
        assert format_view_count(0) == "0"

    def test_below_thousand(self):
        assert format_view_count(999) == "999"

    def test_one_thousand(self):
        assert format_view_count(1000) == "1,000"

    def test_thousands_with_commas(self):
        assert format_view_count(12345) == "12,345"

    def test_one_million(self):
        assert format_view_count(1_000_000) == "1.0M"

    def test_millions_one_decimal(self):
        assert format_view_count(2_500_000) == "2.5M"


class TestFormatDate:
    def test_none_returns_dash(self):
        assert format_date(None) == "—"

    def test_iso_date_string(self):
        assert format_date("2024-01-15") == "Jan 15, 2024"

    def test_iso_datetime_string(self):
        assert format_date("2024-06-01T12:00:00") == "Jun 01, 2024"

    def test_invalid_string_returns_original(self):
        assert format_date("not-a-date") == "not-a-date"


class TestFormatDuration:
    def test_none_returns_dash(self):
        assert format_duration(None) == "—"

    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(185) == "3:05"

    def test_hours_minutes_seconds(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"
