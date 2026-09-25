from datetime import UTC, datetime


def as_utc(value: str) -> datetime:
    """Parse an ISO timestamp, treating a missing offset as UTC.

    Every writer in the app stores tz-aware UTC (`datetime.now(UTC)`), but a row
    written at the SQL level (`datetime('now')`) or by hand is naive, and comparing
    or subtracting a naive against an aware datetime raises `TypeError`. Those
    comparisons sit behind whole-page renders, so the failure is a 500 on the index
    page rather than one bad value — which is why this lives in one place used by
    both the DB layer and the Jinja filters, rather than being fixed at whichever
    site happens to crash first.

    Assuming UTC is right for this app's data (single user, everything stored UTC)
    and cannot itself raise. A genuinely unparseable value still raises ValueError:
    that means a corrupt row, not a missing offset.
    """
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
