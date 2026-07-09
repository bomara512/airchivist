import sqlite3


def init_webapp_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS watch_later (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            position   INTEGER NOT NULL,
            added_at   TEXT NOT NULL,
            UNIQUE(video_id_fk)
        );
        CREATE TABLE IF NOT EXISTS rediscover_shelf (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            pool         TEXT NOT NULL,
            video_ids    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tag_keywords (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            UNIQUE(tag_id, keyword)
        );
        CREATE TABLE IF NOT EXISTS video_tags (
            video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
            PRIMARY KEY (video_id_fk, tag_id_fk)
        );
        CREATE TABLE IF NOT EXISTS tag_aliases (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern          TEXT    NOT NULL,
            match_type       TEXT    NOT NULL DEFAULT 'exact',
            canonical_tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            UNIQUE(pattern, match_type)
        );
        CREATE TABLE IF NOT EXISTS llm_suggestions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical  TEXT    NOT NULL,
            members    TEXT    NOT NULL,
            confidence TEXT,
            is_noise   BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL,
            pool_hash  TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS llm_suggestion_rejections (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_tag TEXT    NOT NULL,
            canonical  TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(member_tag, canonical)
        );
        CREATE TABLE IF NOT EXISTS tag_groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tag_group_members (
            group_id         INTEGER NOT NULL REFERENCES tag_groups(id) ON DELETE CASCADE,
            canonical_tag_id INTEGER NOT NULL REFERENCES tags(id)       ON DELETE CASCADE,
            PRIMARY KEY (group_id, canonical_tag_id)
        );
        CREATE TABLE IF NOT EXISTS channels (
            channel_id       TEXT PRIMARY KEY,
            channel_name     TEXT NOT NULL,
            channel_url      TEXT NOT NULL,
            description      TEXT,
            subscriber_count INTEGER,
            thumbnail_url    TEXT,
            fetch_error      TEXT,
            fetch_status     TEXT NOT NULL DEFAULT 'ok',
            date_added       TEXT NOT NULL DEFAULT (date('now'))
        );
    """)
    for col, ddl in [
        ("is_canonical", "ALTER TABLE tags    ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0"),
        ("is_noise",     "ALTER TABLE tags    ADD COLUMN is_noise     BOOLEAN NOT NULL DEFAULT 0"),
        ("is_hidden",    "ALTER TABLE videos  ADD COLUMN is_hidden    BOOLEAN NOT NULL DEFAULT 0"),
        ("date_hidden",   "ALTER TABLE videos  ADD COLUMN date_hidden   TEXT"),
        ("is_favourite",  "ALTER TABLE videos  ADD COLUMN is_favourite  BOOLEAN NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()
