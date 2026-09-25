import pytest

from webapp.pagination import pagination_context, requested_page


class TestRequestedPage:
    """Review Focus #1: junk page params must never 500."""

    @pytest.mark.parametrize("raw,expected", [
        ("3", 3),
        ("1", 1),
        ("abc", 1),
        ("-5", 1),
        ("0", 1),
        ("", 1),
        (None, 1),
    ])
    def test_coerces_to_a_sane_page_number(self, raw, expected):
        args = {} if raw is None else {"page": raw}
        assert requested_page(args) == expected


class TestPaginationContext:
    def test_clamps_page_beyond_the_last(self, app):
        with app.test_request_context("/?page=99999"):
            ctx = pagination_context("main.index", requested_page=99999, total=10, page_size=100)
        assert ctx["page"] == 1
        assert ctx["total_pages"] == 1
        assert ctx["next_url"] is None
        assert ctx["prev_url"] is None

    def test_builds_next_and_prev_when_multiple_pages(self, app):
        with app.test_request_context("/?page=2"):
            ctx = pagination_context("main.index", requested_page=2, total=300, page_size=100)
        assert ctx["page"] == 2
        assert ctx["total_pages"] == 3
        assert "page=1" in ctx["prev_url"]
        assert "page=3" in ctx["next_url"]

    def test_carries_other_query_params_into_the_urls(self, app):
        with app.test_request_context("/?channel=SomeChannel&page=1"):
            ctx = pagination_context("main.index", requested_page=1, total=300, page_size=100)
        assert "channel=SomeChannel" in ctx["next_url"]

    def test_drops_the_append_param(self, app):
        """The bug this helper exists to make unrepeatable."""
        with app.test_request_context("/?append=1&page=1"):
            ctx = pagination_context("main.index", requested_page=1, total=300, page_size=100)
        assert "append" not in ctx["next_url"]

    def test_zero_total_still_yields_one_page(self, app):
        with app.test_request_context("/"):
            ctx = pagination_context("main.index", requested_page=1, total=0, page_size=100)
        assert ctx["page"] == 1
        assert ctx["total_pages"] == 1
