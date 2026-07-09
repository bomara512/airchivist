import sqlite3
from typing import Optional


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
