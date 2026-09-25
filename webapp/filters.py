from datetime import UTC, datetime
from datetime import date as _date

from webapp.timeutil import as_utc


def format_view_count(value):
    if value is None:
        return "—"
    if value >= 1_000_000:
        s = f"{value / 1_000_000:.2f}".rstrip('0').rstrip('.')
        return s + 'M'
    if value >= 1_000:
        s = f"{value / 1_000:.2f}".rstrip('0').rstrip('.')
        return '1M' if s == '1000' else s + 'K'
    return str(value)


def format_date(value, _today=None):
    if value is None:
        return "—"
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return str(value)
    today = _today or _date.today()
    days = (today - d).days
    if days <= 0:
        return "today"
    if days < 30:
        return f"{days}d"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}yr"


def format_duration(seconds):
    if seconds is None:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def shelf_expires_label(expires_at: str | None) -> str:
    """Human label for how long the rediscover shelf has left ("3 days", "5 hours")."""
    if not expires_at:
        return "—"
    try:
        expires = as_utc(expires_at)
    except (TypeError, ValueError):
        return "—"
    diff = expires - datetime.now(UTC)
    if diff.total_seconds() <= 0:
        return "expired"
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''}"
    hours = diff.seconds // 3600
    return f"{hours} hour{'s' if hours != 1 else ''}"


def last_viewed_reason(
    personal_view_count: int,
    date_last_viewed: str | None,
    *,
    now: datetime | None = None,
) -> str:
    """Why a video is on the rediscover shelf, as shown on its card."""
    if not personal_view_count:
        return "Never opened"
    if not date_last_viewed:
        return "Not recently viewed"
    reference = now or datetime.now(UTC)
    try:
        last_viewed = as_utc(date_last_viewed)
    except (TypeError, ValueError):
        return "Not recently viewed"
    days = (reference - last_viewed).days
    if days == 0:
        return "Last viewed today"
    if days == 1:
        return "Last viewed 1 day ago"
    return f"Last viewed {days} days ago"


def shelf_reason(video: dict) -> str:
    """Jinja-friendly wrapper: reads the two fields `last_viewed_reason` needs off a row.

    A Jinja filter takes the piped value as its first argument, so a two-argument
    signature can't be applied to a video row without repeating both fields in
    every template that uses it.
    """
    return last_viewed_reason(video.get("personal_view_count") or 0, video.get("date_last_viewed"))
