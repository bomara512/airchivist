from datetime import date, datetime, timedelta, timezone

from webapp.filters import (
    format_date,
    format_duration,
    format_view_count,
    last_viewed_reason,
    shelf_expires_label,
    shelf_reason,
)

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


class TestShelfExpiresLabel:
    def test_none_is_an_em_dash(self):
        assert shelf_expires_label(None) == "—"

    def test_unparseable_is_an_em_dash(self):
        assert shelf_expires_label("not-a-date") == "—"

    def test_a_naive_timestamp_is_read_as_utc_not_a_crash(self):
        naive = (datetime.now(timezone.utc) + timedelta(days=3, seconds=1)).replace(tzinfo=None).isoformat()
        assert shelf_expires_label(naive) == "3 days"

    def test_past_is_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert shelf_expires_label(past) == "expired"

    def test_days_are_pluralized(self):
        # The `+ 1s` is load-bearing: the label truncates (see the next test), so
        # an expiry exactly 3 days out already reads "2 days" by the time the
        # subtraction runs a few microseconds later.
        soon = datetime.now(timezone.utc)
        assert shelf_expires_label((soon + timedelta(days=3, seconds=1)).isoformat()) == "3 days"
        assert shelf_expires_label((soon + timedelta(days=1, hours=1)).isoformat()) == "1 day"

    def test_truncates_rather_than_rounding(self):
        """Pre-existing behavior, preserved: a freshly generated 7-day shelf reads
        "6 days" for its whole first day. Cosmetic; filed in TODO.md."""
        exactly_three = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        assert shelf_expires_label(exactly_three) == "2 days"

    def test_under_a_day_falls_back_to_hours(self):
        soon = (datetime.now(timezone.utc) + timedelta(hours=5, seconds=1)).isoformat()
        assert shelf_expires_label(soon) == "5 hours"


class TestLastViewedReason:
    NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    def test_never_opened(self):
        assert last_viewed_reason(0, None, now=self.NOW) == "Never opened"

    def test_no_date_but_viewed(self):
        assert last_viewed_reason(3, None, now=self.NOW) == "Not recently viewed"

    def test_today(self):
        same_day = datetime(2026, 9, 24, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, same_day, now=self.NOW) == "Last viewed today"

    def test_one_day_is_singular(self):
        yesterday = datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, yesterday, now=self.NOW) == "Last viewed 1 day ago"

    def test_many_days(self):
        older = datetime(2026, 9, 14, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, older, now=self.NOW) == "Last viewed 10 days ago"

    def test_a_naive_timestamp_is_read_as_utc_not_a_crash(self):
        """A row written with SQLite's `datetime('now')` has no offset. Subtracting
        it from an aware `now` raises TypeError, which surfaced as a 500 on the
        whole index page rather than a bad label on one card."""
        naive = "2026-09-14T01:00:00"
        assert last_viewed_reason(1, naive, now=self.NOW) == "Last viewed 10 days ago"

    def test_an_unparseable_timestamp_degrades_instead_of_raising(self):
        assert last_viewed_reason(1, "not-a-date", now=self.NOW) == "Not recently viewed"


class TestShelfReason:
    """The Jinja-facing one-argument wrapper: a template can't pass two args."""

    def test_reads_the_two_fields_off_the_row(self):
        assert shelf_reason({"personal_view_count": 0, "date_last_viewed": None}) == "Never opened"

    def test_missing_keys_do_not_raise(self):
        assert shelf_reason({}) == "Never opened"

    def test_null_view_count_is_treated_as_never_opened(self):
        assert shelf_reason({"personal_view_count": None, "date_last_viewed": None}) == "Never opened"
