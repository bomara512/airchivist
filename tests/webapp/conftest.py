import pytest
import sqlite3
from webapp.app import create_app

SCHEMA_SQL = """
CREATE TABLE videos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id            TEXT NOT NULL UNIQUE,
    url                 TEXT NOT NULL,
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
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE video_tags (
    video_id_fk INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id_fk   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (video_id_fk, tag_id_fk)
);
CREATE TABLE tag_keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    UNIQUE(tag_id, keyword)
);
"""

SEED_SQL = """
INSERT INTO videos (video_id, url, title, description, channel_name, yt_view_count,
                    personal_view_count, date_added, fetch_status)
VALUES
    ('aaaaaaaaaa1', 'https://youtube.com/watch?v=aaaaaaaaaa1',
     'Guitar Lesson 1', 'Learn basic guitar chords and strumming patterns',
     'GuitarChannel', 100000, 0, '2024-01-01', 'ok'),
    ('aaaaaaaaaa2', 'https://youtube.com/watch?v=aaaaaaaaaa2',
     'Thai Food Recipe', 'Authentic pad thai recipe with shrimp',
     'ThaiCooking', 200000, 3, '2024-02-01', 'ok'),
    ('aaaaaaaaaa3', 'https://youtube.com/watch?v=aaaaaaaaaa3',
     'Advanced Chords', 'Advanced guitar chord progressions',
     'GuitarChannel', 50000, 1, '2024-03-01', 'ok'),
    ('aaaaaaaaaa4', 'https://youtube.com/watch?v=aaaaaaaaaa4',
     'Pad Thai Tutorial', 'Step by step thai cooking tutorial',
     'ThaiCooking', 300000, 0, '2024-04-01', 'ok'),
    ('aaaaaaaaaa5', 'https://youtube.com/watch?v=aaaaaaaaaa5',
     'Random Video', 'Just a random video about nothing in particular',
     'OtherChannel', 10000, 0, '2024-05-01', 'error');

INSERT INTO tags (id, name) VALUES (1, 'guitar'), (2, 'thai food');

INSERT INTO video_tags (video_id_fk, tag_id_fk)
VALUES (1, 1), (3, 1), (2, 2), (4, 2);

INSERT INTO tag_keywords (tag_id, keyword)
VALUES (1, 'guitar'), (1, 'chord'), (1, 'lesson'),
       (2, 'thai'), (2, 'recipe'), (2, 'pad thai');
"""


def _make_db(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL + SEED_SQL)
    return conn


@pytest.fixture
def db_conn():
    conn = _make_db()
    yield conn
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL + SEED_SQL)
    conn.close()
    app = create_app(db_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
