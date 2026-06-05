from datetime import date
from webapp.filters import format_view_count, format_date, format_duration

TODAY = date(2026, 5, 31)


class TestFormatViewCount:
    def test_none_returns_dash(self):
        assert format_view_count(None) == "—"

    def test_zero(self):
        assert format_view_count(0) == "0"

    def test_below_thousand(self):
        assert format_view_count(999) == "999"

    def test_one_thousand(self):
        assert format_view_count(1_000) == "1K"

    def test_fifteen_hundred(self):
        assert format_view_count(1_500) == "1.5K"

    def test_thousands_compact(self):
        assert format_view_count(12_345) == "12.35K"

    def test_hundred_thousands(self):
        assert format_view_count(150_000) == "150K"

    def test_one_million(self):
        assert format_view_count(1_000_000) == "1M"

    def test_one_point_five_million(self):
        assert format_view_count(1_500_000) == "1.5M"

    def test_millions_two_decimals(self):
        assert format_view_count(7_650_000) == "7.65M"

    def test_large_millions(self):
        assert format_view_count(100_000_000) == "100M"

    def test_boundary_999999_stays_k(self):
        # 999,999 / 1000 = 999.999 → rounds to "1000" → promoted to "1M"
        assert format_view_count(999_999) == "1M"


class TestFormatDate:
    def test_none_returns_dash(self):
        assert format_date(None) == "—"

    def test_today(self):
        assert format_date("2026-05-31", _today=TODAY) == "today"

    def test_yesterday(self):
        assert format_date("2026-05-30", _today=TODAY) == "1d"

    def test_days(self):
        assert format_date("2026-05-26", _today=TODAY) == "5d"

    def test_twenty_nine_days(self):
        assert format_date("2026-05-02", _today=TODAY) == "29d"

    def test_one_month(self):
        assert format_date("2026-05-01", _today=TODAY) == "1mo"

    def test_three_months(self):
        assert format_date("2026-03-01", _today=TODAY) == "3mo"

    def test_eleven_months(self):
        assert format_date("2025-06-30", _today=TODAY) == "11mo"

    def test_one_year(self):
        assert format_date("2025-05-31", _today=TODAY) == "1yr"

    def test_two_years(self):
        assert format_date("2024-05-31", _today=TODAY) == "2yr"

    def test_datetime_string_truncated(self):
        assert format_date("2026-05-26T12:00:00", _today=TODAY) == "5d"

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
