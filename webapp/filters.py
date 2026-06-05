from datetime import datetime, date as _date


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
