import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from crawler.models import Bookmark, VideoMetadata

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id            TEXT    NOT NULL UNIQUE,
    url                 TEXT    NOT NULL,
    title               TEXT,
    description         TEXT,
    channel_name        TEXT,
    channel_id          TEXT,
    yt_view_count       INTEGER,
    personal_view_count INTEGER NOT NULL DEFAULT 0,
    duration_seconds    INTEGER,
    thumbnail_url       TEXT,
    date_added          TEXT,
    date_last_viewed    TEXT,
    date_published      TEXT,
    fetch_status        TEXT DEFAULT 'pending',
    fetch_error         TEXT,
    last_fetched_at     TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    is_canonical BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (video_id_fk, tag_id_fk)
);

CREATE INDEX IF NOT EXISTS idx_videos_video_id ON videos(video_id);
"""


def _dt(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class Datastore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_video(self, metadata: VideoMetadata, bookmark: Bookmark) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO videos (
                video_id, url, title, description, channel_name, channel_id,
                yt_view_count, duration_seconds, thumbnail_url, date_added,
                date_published, fetch_status, fetch_error, last_fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                url             = excluded.url,
                title           = excluded.title,
                description     = excluded.description,
                channel_name    = excluded.channel_name,
                channel_id      = excluded.channel_id,
                yt_view_count   = excluded.yt_view_count,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url   = excluded.thumbnail_url,
                date_published  = excluded.date_published,
                fetch_status    = excluded.fetch_status,
                fetch_error     = excluded.fetch_error,
                last_fetched_at = excluded.last_fetched_at
            """,
            (
                metadata.video_id,
                metadata.url,
                metadata.title,
                metadata.description,
                metadata.channel_name,
                metadata.channel_id,
                metadata.yt_view_count,
                metadata.duration_seconds,
                metadata.thumbnail_url,
                _dt(bookmark.date_added),
                _dt(metadata.date_published),
                metadata.fetch_status,
                metadata.fetch_error,
                now,
            ),
        )
        self._conn.commit()
        self._apply_yt_tags(metadata)
        from webapp.db import apply_aliases
        apply_aliases(self._conn, metadata.video_id)

    def _apply_yt_tags(self, metadata: VideoMetadata) -> None:
        all_names = [*metadata.yt_categories, *metadata.yt_tags]
        for name in all_names:
            name = name.strip()
            if not name:
                continue
            tag_id = self.add_tag(name)
            self.tag_video(metadata.video_id, tag_id)

    def get_video_by_id(self, video_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_videos(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM videos").fetchall()
        return [dict(r) for r in rows]

    def add_tag(self, name: str) -> int:
        self._conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()
        return row[0]

    def tag_video(self, video_id: str, tag_id: int) -> None:
        row = self._conn.execute(
            "SELECT id FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        if not row:
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
            (row[0], tag_id),
        )
        self._conn.commit()

    def get_tags_for_video(self, video_id: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN video_tags vt ON vt.tag_id_fk = t.id
            JOIN videos v ON v.id = vt.video_id_fk
            WHERE v.video_id = ?
            """,
            (video_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def set_fetch_status(self, video_id: str, status: str, error: Optional[str] = None) -> None:
        self._conn.execute(
            "UPDATE videos SET fetch_status = ?, fetch_error = ? WHERE video_id = ?",
            (status, error, video_id),
        )
        self._conn.commit()

    def count_videos(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
