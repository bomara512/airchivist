import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from crawler.models import Bookmark, ChannelMetadata, FetchStatus, MatchType, VideoMetadata

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
    last_fetched_at     TEXT,
    is_hidden           BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tags (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    is_canonical BOOLEAN NOT NULL DEFAULT 0,
    is_noise     BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (video_id_fk, tag_id_fk)
);

CREATE INDEX IF NOT EXISTS idx_videos_video_id ON videos(video_id);

CREATE TABLE IF NOT EXISTS channels (
    channel_id       TEXT PRIMARY KEY,
    channel_name     TEXT NOT NULL,
    channel_url      TEXT NOT NULL,
    description      TEXT,
    subscriber_count INTEGER,
    thumbnail_url    TEXT,
    source_url       TEXT,
    fetch_error      TEXT,
    fetch_status     TEXT NOT NULL DEFAULT 'ok',
    date_added       TEXT NOT NULL DEFAULT (date('now'))
);
"""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def apply_aliases(conn: sqlite3.Connection, video_id: str) -> None:
    """Associate a video with canonical tags whose alias rules match any of its raw tags."""
    video_row = conn.execute(
        "SELECT id FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    if not video_row:
        return

    try:
        rules = conn.execute(
            "SELECT pattern, match_type, canonical_tag_id FROM tag_aliases"
        ).fetchall()
    except sqlite3.OperationalError:
        return  # tag_aliases table not yet created

    if not rules:
        return

    tag_names = [r[0] for r in conn.execute(
        "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id_fk = t.id "
        "WHERE vt.video_id_fk = ?",
        (video_row[0],),
    ).fetchall()]

    canonical_ids = set()
    for pattern, match_type, canonical_tag_id in rules:
        p = pattern.lower()
        for name in tag_names:
            n = name.lower()
            if match_type == MatchType.EXACT and n == p:
                canonical_ids.add(canonical_tag_id)
            elif match_type == MatchType.PREFIX and n.startswith(p):
                canonical_ids.add(canonical_tag_id)
            elif match_type == MatchType.CONTAINS and p in n:
                canonical_ids.add(canonical_tag_id)

    for cid in canonical_ids:
        conn.execute(
            "INSERT OR IGNORE INTO video_tags (video_id_fk, tag_id_fk) VALUES (?, ?)",
            (video_row[0], cid),
        )
    if canonical_ids:
        conn.commit()


class Datastore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        # See webapp/db/schema.py: WAL keeps readers from blocking on this
        # writer. Persistent, so applying it in both places is harmless.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_video(self, metadata: VideoMetadata, bookmark: Bookmark) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO videos (
                video_id, url, title, description, channel_name, channel_id,
                yt_view_count, duration_seconds, thumbnail_url, date_added,
                date_published, fetch_status, fetch_error, last_fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            -- COALESCE, not a bare assignment: fetch_metadata's failure path returns
            -- every descriptive field as None, so `--force-refresh` over a bookmarks
            -- file containing a since-deleted video would otherwise NULL out the
            -- record of what that video was. A successful fetch always supplies a
            -- value, so COALESCE is a no-op on the happy path.
            ON CONFLICT(video_id) DO UPDATE SET
                url             = COALESCE(excluded.url, videos.url),
                title           = COALESCE(excluded.title, videos.title),
                description     = COALESCE(excluded.description, videos.description),
                channel_name    = COALESCE(excluded.channel_name, videos.channel_name),
                channel_id      = COALESCE(excluded.channel_id, videos.channel_id),
                yt_view_count   = COALESCE(excluded.yt_view_count, videos.yt_view_count),
                duration_seconds = COALESCE(excluded.duration_seconds, videos.duration_seconds),
                thumbnail_url   = COALESCE(excluded.thumbnail_url, videos.thumbnail_url),
                date_published  = COALESCE(excluded.date_published, videos.date_published),
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
        apply_aliases(self._conn, metadata.video_id)

    # Columns a successful fetch is allowed to overwrite. Deliberately excludes
    # date_added, personal_view_count, date_last_viewed, is_watched, is_favorite,
    # is_hidden and date_hidden — those are the user's own data, not YouTube's.
    #
    # Split by what an absent value means. For these, "absent" is never meaningful
    # information — a video always has a URL, a channel and a publish date — so a
    # None can only mean the fetch did not report it, and COALESCE keeps the stored
    # value. `fetch_status = ok` only says `extract_info` did not raise: duration is
    # None for a live stream or scheduled premiere, view count is None when the
    # uploader hides it, and channel_name comes from `info.get("uploader")`, which
    # yt-dlp has drifted on across versions and player clients.
    _COALESCED_COLUMNS = (
        "url", "channel_name", "channel_id", "yt_view_count",
        "duration_seconds", "thumbnail_url", "date_published",
    )
    # ...and for these two, "YouTube says it is empty now" is a real thing a
    # successful fetch can report, so they are assigned through.
    _CLEARABLE_COLUMNS = ("title", "description")

    def refresh_video(self, metadata: VideoMetadata) -> None:
        """Update an existing video from a re-fetch. No-op if the row is absent.

        On a successful fetch this refreshes the descriptive columns. On any other
        status it writes ONLY fetch_status, fetch_error and last_fetched_at, leaving
        title/channel/thumbnail/view count/duration at their last known values —
        because `fetch_metadata`'s failure path returns those as None, and a nightly
        job that wrote them through would erase the record of what a since-deleted
        video was. That is the whole reason this method exists rather than reusing
        `upsert_video`.

        Even on the OK branch most columns go through COALESCE, exactly as
        `upsert_video` does — see `_COALESCED_COLUMNS`. The asymmetry with
        `upsert_video` is therefore narrow: only `title` and `description` are
        assigned through here, because those are the two fields a successful fetch
        can legitimately report as now-empty, and this branch (unlike `upsert_video`)
        has already checked the fetch's overall status before believing that.

        Deliberately does NOT apply yt-tags or aliases, unlike `upsert_video`. Those
        are one-time, at-ingest operations: `INSERT OR IGNORE` into `video_tags` is
        idempotent against the database but not against the user, who can remove a
        tag link in the webapp. Re-applying them on a ~15-day timer would silently
        restore every link the user had deliberately removed. Picking up genuinely
        new upstream tags is a separate feature and needs its own design.
        """
        now = datetime.now(UTC).isoformat()
        if metadata.fetch_status != FetchStatus.OK:
            self._conn.execute(
                """
                UPDATE videos
                   SET fetch_status = ?, fetch_error = ?, last_fetched_at = ?
                 WHERE video_id = ?
                """,
                (metadata.fetch_status, metadata.fetch_error, now, metadata.video_id),
            )
            self._conn.commit()
            return

        incoming = {
            "url": metadata.url,
            "title": metadata.title,
            "description": metadata.description,
            "channel_name": metadata.channel_name,
            "channel_id": metadata.channel_id,
            "yt_view_count": metadata.yt_view_count,
            "duration_seconds": metadata.duration_seconds,
            "thumbnail_url": metadata.thumbnail_url,
            "date_published": _dt(metadata.date_published),
        }
        columns = (*self._COALESCED_COLUMNS, *self._CLEARABLE_COLUMNS)
        assignments = ", ".join(
            f"{col} = COALESCE(?, {col})" if col in self._COALESCED_COLUMNS else f"{col} = ?"
            for col in columns
        )
        values = [incoming[col] for col in columns]
        self._conn.execute(
            f"""
            UPDATE videos
               SET {assignments},
                   fetch_status = ?, fetch_error = NULL, last_fetched_at = ?
             WHERE video_id = ?
            """,
            (*values, metadata.fetch_status, now, metadata.video_id),
        )
        self._conn.commit()

    def _apply_yt_tags(self, metadata: VideoMetadata) -> None:
        all_names = [*metadata.yt_categories, *metadata.yt_tags]
        for name in all_names:
            name = name.strip()
            if not name:
                continue
            tag_id = self.add_tag(name)
            self.tag_video(metadata.video_id, tag_id)

    def get_video_by_id(self, video_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_videos(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM videos").fetchall()
        return [dict(r) for r in rows]

    def add_tag(self, name: str) -> int:
        name = name.strip().lower()
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

    def set_fetch_status(self, video_id: str, status: str, error: str | None = None) -> None:
        self._conn.execute(
            "UPDATE videos SET fetch_status = ?, fetch_error = ? WHERE video_id = ?",
            (status, error, video_id),
        )
        self._conn.commit()

    def mark_fetch_attempted(self, video_id: str) -> None:
        """Record that a fetch was tried, without recording an outcome.

        Writes `last_fetched_at` and **deliberately nothing else** — not
        `fetch_status`, not `fetch_error`. It exists for the nightly refresh's
        unexpected-exception path, where a bare network or OS error says nothing
        about the video itself, so the last status that did know must stay put.

        `last_fetched_at` doubles as the selection cursor for
        `get_stale_video_ids`, so leaving it alone would park a deterministically
        failing video at the head of the queue forever; at `limit` such videos the
        rotation stops entirely. Bumping it costs at most one missed cycle for a
        video caught by a transient outage — bounded and self-correcting, unlike a
        stalled rotation. No-op if the row is absent.
        """
        self._conn.execute(
            "UPDATE videos SET last_fetched_at = ? WHERE video_id = ?",
            (datetime.now(UTC).isoformat(), video_id),
        )
        self._conn.commit()

    def count_videos(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    def get_stale_video_ids(self, limit: int) -> list[str]:
        """The `limit` least-recently-refreshed video IDs, stalest first.

        Never-fetched rows sort first because SQLite orders NULL before any value —
        which is the priority we want and costs nothing to get.

        Includes hidden videos and videos already marked dead: an archived video that
        gets deleted upstream is exactly the case where keeping the last-known title
        matters, and a private video can become public again.

        A non-positive limit selects nothing. This is a guard, not a formality:
        SQLite reads `LIMIT -1` as *no limit*, so passing a negative straight through
        would refresh the entire library in one run.
        """
        if limit <= 0:
            return []
        rows = self._conn.execute(
            "SELECT video_id FROM videos ORDER BY last_fetched_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["video_id"] for r in rows]

    def upsert_channel(self, meta: ChannelMetadata, source_url: str | None = None) -> None:
        self._conn.execute(
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
        self._conn.commit()

    def upsert_channel_stub(self, channel_id: str, channel_name: str, channel_url: str) -> None:
        self._conn.execute(
            """
            INSERT INTO channels (channel_id, channel_name, channel_url, fetch_status)
            VALUES (?, ?, ?, 'ok')
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_name = excluded.channel_name,
                channel_url  = excluded.channel_url
            """,
            (channel_id, channel_name, channel_url),
        )
        self._conn.commit()

    def get_channel_ids_for_backfill(self) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT v.channel_id
            FROM videos v
            LEFT JOIN channels c ON c.channel_id = v.channel_id
            WHERE v.channel_id IS NOT NULL
              AND (c.channel_id IS NULL OR c.description IS NULL OR c.thumbnail_url IS NULL)
            UNION
            SELECT channel_id
            FROM channels
            WHERE channel_id IS NOT NULL
              AND (description IS NULL OR thumbnail_url IS NULL)
            """
        ).fetchall()
        return [r[0] for r in rows]

    def has_full_channel_record(self, url: str) -> bool:
        return self._conn.execute(
            """
            SELECT 1 FROM channels
            WHERE (channel_url = ? OR source_url = ?)
              AND description IS NOT NULL
            """,
            (url, url),
        ).fetchone() is not None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
