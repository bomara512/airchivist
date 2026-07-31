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
