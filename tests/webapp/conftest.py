import pytest
import sqlite3
from webapp.app import create_app, _regexp
from webapp.db import init_webapp_tables
from crawler.datastore import _SCHEMA as _CRAWLER_SCHEMA


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

UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0;
"""


def _setup_db(db_path: str) -> None:
    """Initialize the full schema the same way the production stack does."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_CRAWLER_SCHEMA)  # base tables: videos, tags, video_tags, index
    conn.close()
    init_webapp_tables(db_path)  # webapp extension tables + column migrations


@pytest.fixture
def db_conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    _setup_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.create_function("regexp", 2, _regexp)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SEED_SQL)
    yield conn
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    _setup_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(SEED_SQL)
    conn.close()
    app = create_app(db_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c