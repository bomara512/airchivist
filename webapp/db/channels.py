import sqlite3
from typing import Optional

from crawler.models import ChannelMetadata


def get_all_channels(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, fetch_error, fetch_status, date_added "
        "FROM channels ORDER BY channel_name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_channel(conn: sqlite3.Connection, channel_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, fetch_error, fetch_status, date_added "
        "FROM channels WHERE channel_id = ?",
        (channel_id,),
    ).fetchone()
    return dict(row) if row else None


def upsert_channel(
    conn: sqlite3.Connection,
    meta: ChannelMetadata,
    source_url: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO channels
            (channel_id, channel_name, channel_url, description,
             subscriber_count, thumbnail_url, source_url, fetch_error, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name     = excluded.channel_name,
            channel_url      = excluded.channel_url,
            description      = excluded.description,
            subscriber_count = excluded.subscriber_count,
            thumbnail_url    = excluded.thumbnail_url,
            source_url       = COALESCE(excluded.source_url, channels.source_url),
            fetch_error      = excluded.fetch_error,
            fetch_status     = excluded.fetch_status
        """,
        (
            meta.channel_id, meta.channel_name, meta.channel_url,
            meta.description, meta.subscriber_count, meta.thumbnail_url,
            source_url, meta.fetch_error, meta.fetch_status,
        ),
    )
    conn.commit()


def get_channel_by_source_url(conn: sqlite3.Connection, url: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, source_url, fetch_error, fetch_status, "
        "date_added FROM channels WHERE channel_url = ? OR source_url = ?",
        (url, url),
    ).fetchone()
    return dict(row) if row else None


_CHANNEL_SORT_COLUMNS = {
    "video_count": "video_count",
    "subscriber_count": "c.subscriber_count",
    "channel_name": "c.channel_name",
    "date_added": "c.date_added",
}


def _channel_where(search):
    if search:
        return " WHERE c.channel_name LIKE '%' || ? || '%'", [search]
    return "", []


def get_channels_page(conn, *, sort_by="video_count", sort_dir="desc",
                      search=None, has_videos=False, page=1, page_size=100):
    if sort_by not in _CHANNEL_SORT_COLUMNS:
        raise ValueError(f"invalid sort_by: {sort_by}")
    if sort_dir not in ("asc", "desc"):
        raise ValueError(f"invalid sort_dir: {sort_dir}")

    where_sql, params = _channel_where(search)
    having_sql = " HAVING video_count > 0" if has_videos else ""
    col = _CHANNEL_SORT_COLUMNS[sort_by]
    # NULLs (e.g. subscriber_count) sort last regardless of direction; stable tiebreak on name.
    order_sql = f" ORDER BY {col} IS NULL, {col} {sort_dir.upper()}, c.channel_name ASC"

    sql = (
        "SELECT c.channel_id, c.channel_name, c.channel_url, c.description, "
        "c.subscriber_count, c.thumbnail_url, c.date_added, "
        "COUNT(v.video_id) AS video_count "
        "FROM channels c LEFT JOIN videos v ON v.channel_id = c.channel_id"
        + where_sql
        + " GROUP BY c.channel_id"
        + having_sql
        + order_sql
        + " LIMIT ? OFFSET ?"
    )
    params = [*params, page_size, (page - 1) * page_size]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def count_channels(conn, *, search=None, has_videos=False):
    where_sql, params = _channel_where(search)
    having_sql = " HAVING COUNT(v.video_id) > 0" if has_videos else ""
    sql = (
        "SELECT COUNT(*) FROM ("
        "SELECT c.channel_id FROM channels c "
        "LEFT JOIN videos v ON v.channel_id = c.channel_id"
        + where_sql
        + " GROUP BY c.channel_id"
        + having_sql
        + ")"
    )
    return conn.execute(sql, params).fetchone()[0]
