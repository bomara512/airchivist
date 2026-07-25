# Creator Pages — Schema & Crawler (Phase 1) Implementation Plan

> **Status: COMPLETED** — Phase 1 (schema + crawler) shipped. This plan is retained as an artifact of record; remaining creator-pages work (extension action, channels UI) is tracked in `TODO.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `channels` table to ViewTube, teach the crawler to detect channel bookmarks and create full channel records via yt-dlp, and create channel stubs as a free side effect of video processing.

**Architecture:** Six layers of change, in dependency order: (1) models — new `ChannelMetadata` dataclass + channel URL regex; (2) fetcher — `fetch_channel_metadata` wrapping yt-dlp; (3) crawler datastore — `channels` table DDL + three new `Datastore` methods; (4) webapp DB — `webapp/db/channels.py` read functions + rename `get_all_channels` → `get_video_channel_names`; (5) crawler CLI — split bookmarks, side-effect stubs, channel bookmark loop, `--backfill-channels` flag; (6) docs. The crawler never imports from `webapp/`; the webapp never imports from `crawler/` except for `_SCHEMA` and `apply_aliases` (existing).

**Tech Stack:** Python, SQLite, yt-dlp, pytest.

---

## File Map

| File | Action |
|---|---|
| `crawler/models.py` | Add `_YT_CHANNEL_RE`, `ChannelMetadata`, `Bookmark.youtube_channel_url` |
| `crawler/metadata_fetcher.py` | Add `fetch_channel_metadata` |
| `crawler/datastore.py` | Add `channels` DDL to `_SCHEMA`; add `upsert_channel`, `upsert_channel_stub`, `get_channel_ids_for_backfill` to `Datastore` |
| `webapp/db/channels.py` | **New file** — `get_all_channels` (channel entity), `get_channel` |
| `webapp/db/schema.py` | Add `channels` table to `init_webapp_tables` |
| `webapp/db/videos.py` | Rename `get_all_channels` → `get_video_channel_names` |
| `webapp/db/__init__.py` | Import + export `get_video_channel_names` from `videos`, add `get_all_channels`/`get_channel` from `channels` |
| `webapp/routes.py` | Update one call site: `get_all_channels` → `get_video_channel_names` |
| `crawler/cli.py` | Split bookmarks; channel bookmark loop; channel stub side effect; `--backfill-channels` flag |
| `tests/crawler/fixtures/sample_bookmarks.json` | Add one channel bookmark entry |
| `tests/crawler/test_models.py` | Tests for `_YT_CHANNEL_RE`, `ChannelMetadata`, `Bookmark.youtube_channel_url` |
| `tests/crawler/test_metadata_fetcher.py` | Tests for `fetch_channel_metadata` (mocked yt-dlp) |
| `tests/crawler/test_datastore.py` | Tests for `channels` table creation + three new `Datastore` methods |
| `tests/crawler/test_cli.py` | Tests for channel bookmark processing, stub side effect, `--backfill-channels` |
| `tests/webapp/test_db.py` | Rename existing `TestGetAllChannels`, add new tests for channel entity functions |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Update to reflect channel entity, new DB functions, CLI flag |

---

### Task 1: Models — `_YT_CHANNEL_RE`, `ChannelMetadata`, `Bookmark.youtube_channel_url`

**Files:**
- Modify: `crawler/models.py`
- Test: `tests/crawler/test_models.py`

- [x] **Step 1: Write failing tests**

Append to `tests/crawler/test_models.py`:

```python
import re
from crawler.models import _YT_CHANNEL_RE, Bookmark, ChannelMetadata


class TestYtChannelRe:
    def test_matches_at_handle(self):
        assert _YT_CHANNEL_RE.search("https://www.youtube.com/@rickastley")

    def test_matches_at_handle_with_path(self):
        assert _YT_CHANNEL_RE.search("https://www.youtube.com/@rickastley/videos")

    def test_matches_c_prefix(self):
        assert _YT_CHANNEL_RE.search("https://www.youtube.com/c/RickAstleyVEVO")

    def test_matches_user_prefix(self):
        assert _YT_CHANNEL_RE.search("https://www.youtube.com/user/RickAstleyVEVO")

    def test_matches_channel_id(self):
        assert _YT_CHANNEL_RE.search(
            "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
        )

    def test_does_not_match_video_url(self):
        assert not _YT_CHANNEL_RE.search(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

    def test_does_not_match_non_youtube(self):
        assert not _YT_CHANNEL_RE.search("https://vimeo.com/@rickastley")

    def test_does_not_match_shorts_url(self):
        assert not _YT_CHANNEL_RE.search(
            "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        )


class TestBookmarkYoutubeChannelUrl:
    def test_returns_url_for_at_handle(self):
        b = Bookmark(url="https://www.youtube.com/@rickastley", title="Rick")
        assert b.youtube_channel_url == "https://www.youtube.com/@rickastley"

    def test_returns_url_for_channel_id(self):
        url = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
        b = Bookmark(url=url, title="Rick")
        assert b.youtube_channel_url == url

    def test_returns_none_for_video_bookmark(self):
        b = Bookmark(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="V")
        assert b.youtube_channel_url is None

    def test_returns_none_for_non_youtube(self):
        b = Bookmark(url="https://docs.python.org/3/", title="Docs")
        assert b.youtube_channel_url is None


class TestChannelMetadata:
    def test_construct_required_fields(self):
        m = ChannelMetadata(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_name="RickAstleyVEVO",
            channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        )
        assert m.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert m.channel_name == "RickAstleyVEVO"
        assert m.fetch_status == "ok"

    def test_optional_fields_default_to_none(self):
        m = ChannelMetadata(
            channel_id="UCabc", channel_name="Test", channel_url="https://youtube.com/channel/UCabc"
        )
        assert m.description is None
        assert m.subscriber_count is None
        assert m.thumbnail_url is None
        assert m.fetch_error is None

    def test_full_construction(self):
        m = ChannelMetadata(
            channel_id="UCabc",
            channel_name="Test",
            channel_url="https://youtube.com/channel/UCabc",
            description="A channel",
            subscriber_count=42000,
            thumbnail_url="https://example.com/thumb.jpg",
            fetch_status="ok",
        )
        assert m.subscriber_count == 42000
        assert m.description == "A channel"
```

- [x] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/crawler/test_models.py::TestYtChannelRe tests/crawler/test_models.py::TestBookmarkYoutubeChannelUrl tests/crawler/test_models.py::TestChannelMetadata -v
```

Expected: FAIL — `_YT_CHANNEL_RE`, `ChannelMetadata`, and `youtube_channel_url` do not exist.

- [x] **Step 3: Add models to `crawler/models.py`**

After line 24 (the `_YT_ID_RE` block), add:

```python
_YT_CHANNEL_RE = re.compile(
    r'youtube\.com/(?:channel/(UC[A-Za-z0-9_-]+)|(?:c|user)/([^/?#]+)|@([^/?#]+))'
)
```

In the `Bookmark` dataclass, after the `youtube_video_id` property (after line 36), add:

```python
    @property
    def youtube_channel_url(self) -> Optional[str]:
        return self.url if _YT_CHANNEL_RE.search(self.url) else None
```

After the `VideoMetadata` dataclass (after line 59), add:

```python
@dataclass
class ChannelMetadata:
    channel_id: str
    channel_name: str
    channel_url: str
    description: Optional[str] = None
    subscriber_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    fetch_status: str = FetchStatus.OK
    fetch_error: Optional[str] = None
```

- [x] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/crawler/test_models.py::TestYtChannelRe tests/crawler/test_models.py::TestBookmarkYoutubeChannelUrl tests/crawler/test_models.py::TestChannelMetadata -v
```

Expected: all PASS.

- [x] **Step 5: Run full suite to check no regressions**

```bash
python -m pytest -q
```

Expected: same number of passes as before (410 + new tests).

- [x] **Step 6: Commit**

```bash
git add crawler/models.py tests/crawler/test_models.py
git commit -m "feat(crawler): add ChannelMetadata, _YT_CHANNEL_RE, Bookmark.youtube_channel_url"
```

---

### Task 2: `fetch_channel_metadata`

**Files:**
- Modify: `crawler/metadata_fetcher.py`
- Test: `tests/crawler/test_metadata_fetcher.py`

- [x] **Step 1: Write failing tests**

Append to `tests/crawler/test_metadata_fetcher.py`:

```python
from crawler.metadata_fetcher import fetch_channel_metadata
from crawler.models import ChannelMetadata

_GOOD_CHANNEL_INFO = {
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "channel": "RickAstleyVEVO",
    "uploader": "RickAstleyVEVO",
    "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
    "description": "The official Rick Astley YouTube channel.",
    "channel_follower_count": 4_200_000,
    "thumbnail": "https://yt3.ggpht.com/rick-avatar.jpg",
}

_CHANNEL_URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"


def _make_channel_ydl_mock(info=None, error=None):
    mock_ydl = MagicMock()
    if error:
        mock_ydl.__enter__.return_value.extract_info.side_effect = error
    else:
        mock_ydl.__enter__.return_value.extract_info.return_value = (
            info if info is not None else _GOOD_CHANNEL_INFO
        )
    return mock_ydl


class TestFetchChannelMetadata:
    def test_returns_channelmetadata_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert isinstance(result, ChannelMetadata)

    def test_maps_channel_id(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_maps_channel_name_from_channel_field(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_name == "RickAstleyVEVO"

    def test_maps_channel_name_from_uploader_when_channel_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_name == "RickAstleyVEVO"

    def test_maps_channel_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_url == "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"

    def test_falls_back_to_input_url_when_channel_url_missing(self):
        info = {**_GOOD_CHANNEL_INFO}
        del info["channel_url"]
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=info)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.channel_url == _CHANNEL_URL

    def test_maps_description(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.description == "The official Rick Astley YouTube channel."

    def test_maps_subscriber_count(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.subscriber_count == 4_200_000

    def test_maps_thumbnail_url(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.thumbnail_url == "https://yt3.ggpht.com/rick-avatar.jpg"

    def test_sets_fetch_status_ok_on_success(self):
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock()):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "ok"

    def test_returns_error_status_on_download_error(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("ERROR: Unable to download webpage")
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(error=error)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "error"
        assert result.fetch_error is not None

    def test_handles_missing_optional_fields(self):
        sparse = {"channel_id": "UCabc", "channel": "Test",
                  "channel_url": "https://www.youtube.com/channel/UCabc"}
        with patch("crawler.metadata_fetcher.yt_dlp.YoutubeDL",
                   return_value=_make_channel_ydl_mock(info=sparse)):
            result = fetch_channel_metadata(_CHANNEL_URL, delay=0)
        assert result.fetch_status == "ok"
        assert result.description is None
        assert result.subscriber_count is None
        assert result.thumbnail_url is None
```

- [x] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/crawler/test_metadata_fetcher.py::TestFetchChannelMetadata -v
```

Expected: FAIL — `fetch_channel_metadata` does not exist.

- [x] **Step 3: Add `fetch_channel_metadata` to `crawler/metadata_fetcher.py`**

Add to the imports at the top:
```python
from crawler.models import FetchStatus, VideoMetadata, ChannelMetadata
```

Add these constants and function after the existing `fetch_metadata` function:

```python
_CHANNEL_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": True,
}


def fetch_channel_metadata(channel_url: str, delay: float = 1.5) -> ChannelMetadata:
    try:
        with yt_dlp.YoutubeDL(_CHANNEL_YDL_OPTS) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        channel_id = info.get("channel_id") or info.get("id", "")
        channel_name = info.get("channel") or info.get("uploader") or info.get("title", "")
        url = info.get("channel_url") or info.get("webpage_url") or channel_url

        return ChannelMetadata(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_url=url,
            description=info.get("description"),
            subscriber_count=info.get("channel_follower_count"),
            thumbnail_url=info.get("thumbnail"),
            fetch_status=FetchStatus.OK,
        )
    except yt_dlp.utils.DownloadError as exc:
        status = _classify_error(str(exc))
        return ChannelMetadata(
            channel_id="",
            channel_name="",
            channel_url=channel_url,
            fetch_status=status,
            fetch_error=str(exc),
        )
    finally:
        if delay > 0:
            time.sleep(delay)
```

Note: the existing import in `metadata_fetcher.py` is `from crawler.models import FetchStatus, VideoMetadata` — update it to include `ChannelMetadata`.

- [x] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/crawler/test_metadata_fetcher.py::TestFetchChannelMetadata -v
```

Expected: all PASS.

- [x] **Step 5: Run full suite**

```bash
python -m pytest -q
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add crawler/metadata_fetcher.py tests/crawler/test_metadata_fetcher.py
git commit -m "feat(crawler): add fetch_channel_metadata"
```

---

### Task 3: `channels` table + `Datastore` channel methods

**Files:**
- Modify: `crawler/datastore.py`
- Test: `tests/crawler/test_datastore.py`

- [x] **Step 1: Write failing tests**

Append to `tests/crawler/test_datastore.py`:

```python
from crawler.models import ChannelMetadata


def _make_channel_meta(channel_id="UCtest123", **kwargs):
    defaults = dict(
        channel_name="Test Channel",
        channel_url=f"https://www.youtube.com/channel/{channel_id}",
        description="A test description",
        subscriber_count=50_000,
        thumbnail_url="https://example.com/thumb.jpg",
        fetch_status="ok",
    )
    defaults.update(kwargs)
    return ChannelMetadata(channel_id=channel_id, **defaults)


class TestChannelsTable:
    def test_creates_channels_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            tables = ds._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert "channels" in {r[0] for r in tables}


class TestUpsertChannel:
    def test_inserts_all_fields(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta())
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row is not None
        assert row["channel_name"] == "Test Channel"
        assert row["description"] == "A test description"
        assert row["subscriber_count"] == 50_000
        assert row["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_updates_subscriber_count_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(subscriber_count=100))
            ds.upsert_channel(_make_channel_meta(subscriber_count=200))
            row = ds._conn.execute(
                "SELECT subscriber_count FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row["subscriber_count"] == 200

    def test_overwrites_description_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(description="Old"))
            ds.upsert_channel(_make_channel_meta(description="New"))
            row = ds._conn.execute(
                "SELECT description FROM channels WHERE channel_id = 'UCtest123'"
            ).fetchone()
        assert row["description"] == "New"


class TestUpsertChannelStub:
    def test_inserts_stub_record(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel_stub("UCabc", "My Channel", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row is not None
        assert row["channel_name"] == "My Channel"
        assert row["description"] is None
        assert row["subscriber_count"] is None

    def test_does_not_overwrite_description_after_full_upsert(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel(_make_channel_meta(
                channel_id="UCabc", description="Rich description", subscriber_count=999
            ))
            ds.upsert_channel_stub("UCabc", "Updated Name", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT * FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row["description"] == "Rich description"
        assert row["subscriber_count"] == 999

    def test_updates_channel_name_on_conflict(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ds.upsert_channel_stub("UCabc", "Old Name", "https://youtube.com/channel/UCabc")
            ds.upsert_channel_stub("UCabc", "New Name", "https://youtube.com/channel/UCabc")
            row = ds._conn.execute(
                "SELECT channel_name FROM channels WHERE channel_id = 'UCabc'"
            ).fetchone()
        assert row["channel_name"] == "New Name"


class TestGetChannelIdsForBackfill:
    def test_returns_channel_id_not_in_channels_table(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" in ids

    def test_returns_stub_only_channel(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_channel_stub("UCabc", "Test", "https://youtube.com/channel/UCabc")
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" in ids

    def test_excludes_fully_fetched_channel(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            meta = _make_metadata(channel_id="UCabc", channel_name="Test")
            ds.upsert_video(meta, _make_bookmark())
            ds.upsert_channel(_make_channel_meta(channel_id="UCabc"))
            ids = ds.get_channel_ids_for_backfill()
        assert "UCabc" not in ids

    def test_returns_empty_list_when_no_videos(self, tmp_path):
        with Datastore(tmp_path / "test.db") as ds:
            ids = ds.get_channel_ids_for_backfill()
        assert ids == []
```

- [x] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/crawler/test_datastore.py::TestChannelsTable tests/crawler/test_datastore.py::TestUpsertChannel tests/crawler/test_datastore.py::TestUpsertChannelStub tests/crawler/test_datastore.py::TestGetChannelIdsForBackfill -v
```

Expected: FAIL.

- [x] **Step 3: Update `crawler/datastore.py`**

Add the `channels` table to `_SCHEMA` (after the `idx_videos_video_id` CREATE INDEX line):

```python
CREATE TABLE IF NOT EXISTS channels (
    channel_id       TEXT PRIMARY KEY,
    channel_name     TEXT NOT NULL,
    channel_url      TEXT NOT NULL,
    description      TEXT,
    subscriber_count INTEGER,
    thumbnail_url    TEXT,
    fetch_status     TEXT NOT NULL DEFAULT 'ok',
    date_added       TEXT NOT NULL DEFAULT (date('now'))
);
```

Add the import at the top of the file (update the existing import line):
```python
from crawler.models import Bookmark, ChannelMetadata, MatchType, VideoMetadata
```

Add three new methods to the `Datastore` class (before `close`):

```python
def upsert_channel(self, meta: ChannelMetadata) -> None:
    self._conn.execute(
        """
        INSERT INTO channels (channel_id, channel_name, channel_url, description,
                              subscriber_count, thumbnail_url, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            channel_name     = excluded.channel_name,
            channel_url      = excluded.channel_url,
            description      = excluded.description,
            subscriber_count = excluded.subscriber_count,
            thumbnail_url    = excluded.thumbnail_url,
            fetch_status     = excluded.fetch_status
        """,
        (
            meta.channel_id, meta.channel_name, meta.channel_url,
            meta.description, meta.subscriber_count, meta.thumbnail_url,
            meta.fetch_status,
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
          AND (c.channel_id IS NULL OR c.description IS NULL)
        """
    ).fetchall()
    return [r[0] for r in rows]
```

- [x] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/crawler/test_datastore.py::TestChannelsTable tests/crawler/test_datastore.py::TestUpsertChannel tests/crawler/test_datastore.py::TestUpsertChannelStub tests/crawler/test_datastore.py::TestGetChannelIdsForBackfill -v
```

Expected: all PASS.

- [x] **Step 5: Run full suite**

```bash
python -m pytest -q
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add crawler/datastore.py tests/crawler/test_datastore.py
git commit -m "feat(crawler): add channels table and Datastore channel methods"
```

---

### Task 4: Webapp DB — `channels.py`, schema, rename `get_all_channels`

**Files:**
- Create: `webapp/db/channels.py`
- Modify: `webapp/db/schema.py`
- Modify: `webapp/db/videos.py:137-141`
- Modify: `webapp/db/__init__.py`
- Modify: `webapp/routes.py:72`
- Test: `tests/webapp/test_db.py`

Context: `webapp/db/videos.py` has `get_all_channels` at line 137 returning `list[str]` (channel names for the filter dropdown). It must be renamed to `get_video_channel_names`. A new `get_all_channels` in `webapp/db/channels.py` will return `list[dict]` (full channel entity records). The existing `TestGetAllChannels` test class in `test_db.py` tests the string-returning version; it must be updated to use the new name.

- [x] **Step 1: Write failing tests**

In `tests/webapp/test_db.py`:

a) Update the import block at the top — replace `get_all_channels` with `get_video_channel_names` and add new imports:

```python
from webapp.db import (
    get_all_videos, get_video_by_id, get_video_channel_names, get_all_tags,
    get_tags_with_keywords, get_tag_keywords, get_stats, get_tags_for_video,
    record_visit, create_tag, set_tag_keywords, delete_tag,
    add_video_tag, remove_video_tag, init_webapp_tables, count_videos,
    apply_aliases, get_canonical_tags, create_canonical_tag,
    add_alias, delete_alias, retroactive_apply,
    get_unclassified_tags, confirm_suggestion,
    save_llm_suggestions, get_llm_suggestions, dismiss_llm_suggestion,
    is_llm_suggestion_cache_stale, get_videos_status_batch,
    confirm_and_dismiss_suggestion, accept_noise_and_dismiss_suggestion,
    add_alias_and_apply, edit_alias_and_apply,
    get_all_channels, get_channel,
)
```

b) Rename the existing `TestGetAllChannels` class to `TestGetVideoChannelNames` and update its method bodies to call `get_video_channel_names`:

```python
class TestGetVideoChannelNames:
    def test_returns_distinct_names(self, db_conn):
        channels = get_video_channel_names(db_conn)
        assert set(channels) == {"GuitarChannel", "ThaiCooking", "OtherChannel"}

    def test_excludes_null_channels(self, db_conn):
        db_conn.execute("INSERT INTO videos (video_id, url) VALUES ('nullchan1', 'http://x.com')")
        channels = get_video_channel_names(db_conn)
        assert None not in channels
```

c) Add new `TestGetAllChannels` and `TestGetChannel` classes:

```python
def _seed_channel(conn, channel_id="UCtest123", channel_name="Test Channel",
                  description="A test channel"):
    conn.execute(
        "INSERT INTO channels (channel_id, channel_name, channel_url, description, fetch_status) "
        "VALUES (?, ?, ?, ?, 'ok')",
        (channel_id, channel_name,
         f"https://www.youtube.com/channel/{channel_id}", description),
    )
    conn.commit()


class TestGetAllChannelsEntity:
    def test_returns_list_of_dicts(self, db_conn):
        _seed_channel(db_conn)
        channels = get_all_channels(db_conn)
        assert isinstance(channels, list)
        assert isinstance(channels[0], dict)

    def test_returns_expected_channel(self, db_conn):
        _seed_channel(db_conn, channel_id="UCabc", channel_name="My Channel")
        channels = get_all_channels(db_conn)
        names = [c["channel_name"] for c in channels]
        assert "My Channel" in names

    def test_returns_empty_list_when_no_channels(self, db_conn):
        channels = get_all_channels(db_conn)
        assert channels == []

    def test_ordered_by_channel_name(self, db_conn):
        _seed_channel(db_conn, channel_id="UCzzz", channel_name="Zebra")
        _seed_channel(db_conn, channel_id="UCaaa", channel_name="Alpha")
        channels = get_all_channels(db_conn)
        assert channels[0]["channel_name"] == "Alpha"
        assert channels[1]["channel_name"] == "Zebra"


class TestGetChannel:
    def test_returns_dict_for_existing_channel(self, db_conn):
        _seed_channel(db_conn, channel_id="UCabc")
        ch = get_channel(db_conn, "UCabc")
        assert ch is not None
        assert ch["channel_id"] == "UCabc"

    def test_returns_none_for_missing_channel(self, db_conn):
        assert get_channel(db_conn, "UCmissing") is None
```

- [x] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/webapp/test_db.py::TestGetVideoChannelNames tests/webapp/test_db.py::TestGetAllChannelsEntity tests/webapp/test_db.py::TestGetChannel -v
```

Expected: FAIL — `get_video_channel_names`, `get_all_channels` (entity), `get_channel` not importable.

- [x] **Step 3: Add `channels` table to `webapp/db/schema.py`**

Inside the `executescript("""...""")` block in `init_webapp_tables`, add after the last `CREATE TABLE` block (before the closing `"""`):

```sql
        CREATE TABLE IF NOT EXISTS channels (
            channel_id       TEXT PRIMARY KEY,
            channel_name     TEXT NOT NULL,
            channel_url      TEXT NOT NULL,
            description      TEXT,
            subscriber_count INTEGER,
            thumbnail_url    TEXT,
            fetch_status     TEXT NOT NULL DEFAULT 'ok',
            date_added       TEXT NOT NULL DEFAULT (date('now'))
        );
```

- [x] **Step 4: Create `webapp/db/channels.py`**

```python
import sqlite3
from typing import Optional


def get_all_channels(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, fetch_status, date_added "
        "FROM channels ORDER BY channel_name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_channel(conn: sqlite3.Connection, channel_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT channel_id, channel_name, channel_url, description, "
        "subscriber_count, thumbnail_url, fetch_status, date_added "
        "FROM channels WHERE channel_id = ?",
        (channel_id,),
    ).fetchone()
    return dict(row) if row else None
```

- [x] **Step 5: Rename `get_all_channels` → `get_video_channel_names` in `webapp/db/videos.py`**

Change line 137:
```python
def get_video_channel_names(conn: sqlite3.Connection) -> list[str]:
```
(Only the function name changes; body is identical.)

- [x] **Step 6: Update `webapp/db/__init__.py`**

Replace the `get_all_channels` import from `webapp.db.videos` with `get_video_channel_names`:

```python
from webapp.db.videos import (
    ALLOWED_SORT_COLUMNS,
    ALLOWED_SORT_DIRS,
    add_to_watch_later,
    add_video,
    count_hidden_videos,
    count_videos,
    delete_video,
    generate_rediscover_shelf,
    get_video_channel_names,
    get_all_videos,
    get_current_rediscover_shelf,
    get_hidden_videos,
    get_stats,
    get_video_by_id,
    set_favourite,
    get_videos_status_batch,
    get_watch_later_count,
    get_watch_later_queue,
    get_watch_later_video_ids,
    hide_video,
    is_in_watch_later,
    is_rediscover_shelf_expired,
    record_visit,
    refresh_rediscover_shelf,
    remove_from_rediscover_shelf,
    remove_from_watch_later,
    reorder_watch_later,
    unhide_video,
)
```

Add after the `from webapp.db.schema import init_webapp_tables` line:

```python
from webapp.db.channels import (
    get_all_channels,
    get_channel,
)
```

Update `__all__` in `webapp/db/__init__.py`: replace `"get_all_channels"` in the `# videos` section with `"get_video_channel_names"`, and add a new `# channels` section:

```python
    # channels
    "get_all_channels", "get_channel",
```

Add `"get_video_channel_names"` to the `# videos` section of `__all__`.

- [x] **Step 7: Update `webapp/routes.py` line 72**

Change:
```python
    channels = _db.get_all_channels(g.db)
```
to:
```python
    channels = _db.get_video_channel_names(g.db)
```

- [x] **Step 8: Run tests to verify they pass**

```bash
python -m pytest tests/webapp/test_db.py::TestGetVideoChannelNames tests/webapp/test_db.py::TestGetAllChannelsEntity tests/webapp/test_db.py::TestGetChannel -v
```

Expected: all PASS.

- [x] **Step 9: Run full suite**

```bash
python -m pytest -q
```

Expected: all pass.

- [x] **Step 10: Commit**

```bash
git add webapp/db/channels.py webapp/db/schema.py webapp/db/videos.py webapp/db/__init__.py webapp/routes.py tests/webapp/test_db.py
git commit -m "feat(webapp/db): add channels.py, add channels table to schema, rename get_all_channels"
```

---

### Task 5: Crawler CLI — channel bookmarks, stub side effect, `--backfill-channels`

**Files:**
- Modify: `crawler/cli.py`
- Modify: `tests/crawler/fixtures/sample_bookmarks.json`
- Test: `tests/crawler/test_cli.py`

Context: `crawler/cli.py` currently collects video bookmarks only (`b.youtube_video_id`), processes them in a loop, and calls `ds.upsert_video`. We need to also collect channel bookmarks, add a side-effect stub after each video upsert, process channel bookmarks via `fetch_channel_metadata`, and add `--backfill-channels`.

The fixture `tests/crawler/fixtures/sample_bookmarks.json` has only video bookmarks; we add one channel entry to enable testing.

- [x] **Step 1: Add a channel bookmark to the fixture**

In `tests/crawler/fixtures/sample_bookmarks.json`, inside the `"children"` list of the `"Videos"` folder (after the `bookmark2` entry, before `bookmark3`), add:

```json
            {
              "guid": "channelbm1_",
              "title": "Rick Astley Official",
              "id": 9,
              "dateAdded": 1635000000000000,
              "lastModified": 1700000000000000,
              "type": "text/x-moz-place",
              "typeCode": 1,
              "uri": "https://www.youtube.com/@rickastley"
            },
```

- [x] **Step 2: Write failing tests**

In `tests/crawler/test_cli.py`, update `_run_main` to also patch `fetch_channel_metadata`, add `_GOOD_CHANNEL_META`, and add new test classes:

First add imports at the top of the file:
```python
from crawler.models import ChannelMetadata
```

Add `_GOOD_CHANNEL_META` near `_GOOD_METADATA`:
```python
_GOOD_CHANNEL_META = ChannelMetadata(
    channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
    channel_name="RickAstleyVEVO",
    channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
    description="The official Rick Astley channel",
    subscriber_count=4_000_000,
    thumbnail_url="https://yt3.ggpht.com/rick.jpg",
)
```

Replace `_run_main` with:
```python
def _run_main(args: list[str], mock_fetch=None, mock_channel_fetch=None):
    if mock_fetch is None:
        mock_fetch = MagicMock(return_value=_GOOD_METADATA)
    if mock_channel_fetch is None:
        mock_channel_fetch = MagicMock(return_value=_GOOD_CHANNEL_META)
    with patch("crawler.cli.fetch_metadata", mock_fetch):
        with patch("crawler.cli.fetch_channel_metadata", mock_channel_fetch):
            with patch.object(sys, "argv", ["crawler"] + args):
                try:
                    cli.main()
                    return 0
                except SystemExit as e:
                    return e.code
```

Add new test classes:
```python
class TestCliChannelBookmarks:
    def test_channel_bookmark_stored_in_channels_table(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        row = conn.execute("SELECT * FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'").fetchone()
        conn.close()
        assert row is not None

    def test_channel_bookmark_has_full_metadata(self, tmp_path):
        out = tmp_path / "out.db"
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)])
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row[0] == "The official Rick Astley channel"

    def test_fetch_channel_metadata_called_for_channel_bookmark(self, tmp_path):
        out = tmp_path / "out.db"
        mock_ch = MagicMock(return_value=_GOOD_CHANNEL_META)
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)],
                  mock_channel_fetch=mock_ch)
        mock_ch.assert_called()
        called_url = mock_ch.call_args[0][0]
        assert "rickastley" in called_url


class TestCliChannelStubSideEffect:
    def test_video_processing_creates_channel_stub(self, tmp_path):
        out = tmp_path / "out.db"
        meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Rick Astley",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(FIXTURES / "sample_bookmarks.json"), "-o", str(out)],
                  mock_fetch=meta)
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT channel_name FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_stub_has_no_description(self, tmp_path):
        out = tmp_path / "out.db"
        # Use a bookmark file with no channel bookmarks to isolate stub creation
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=meta)
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        # Stub has no description (channel bookmark loop didn't run)
        assert row[0] is None


class TestCliBackfillChannels:
    def test_backfill_fetches_full_metadata_for_stubs(self, tmp_path):
        out = tmp_path / "out.db"
        # First run: create stub via video processing
        meta = MagicMock(return_value=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            fetch_status="ok",
        ))
        video_only_json = tmp_path / "video_only.json"
        video_only_json.write_text("""{
  "guid": "root________", "title": "", "id": 1,
  "dateAdded": 1600000000000000, "lastModified": 1700000000000000,
  "type": "text/x-moz-place-container", "root": "placesRoot",
  "children": [{"guid": "bm1", "title": "V", "id": 2,
    "dateAdded": 1620000000000000, "lastModified": 1700000000000000,
    "type": "text/x-moz-place", "typeCode": 1,
    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]
}""")
        _run_main(["-i", str(video_only_json), "-o", str(out)], mock_fetch=meta)

        # Second run with --backfill-channels
        mock_ch = MagicMock(return_value=_GOOD_CHANNEL_META)
        _run_main(["-i", str(video_only_json), "-o", str(out), "--backfill-channels"],
                  mock_fetch=MagicMock(return_value=VideoMetadata(
                      video_id="dQw4w9WgXcQ",
                      url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                      fetch_status="ok",
                  )),
                  mock_channel_fetch=mock_ch)
        mock_ch.assert_called()
        conn = sqlite3.connect(str(out))
        row = conn.execute(
            "SELECT description FROM channels WHERE channel_id = 'UCuAXFkgsw1L7xaCfnd5JJOw'"
        ).fetchone()
        conn.close()
        assert row[0] == "The official Rick Astley channel"
```

- [x] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/crawler/test_cli.py::TestCliChannelBookmarks tests/crawler/test_cli.py::TestCliChannelStubSideEffect tests/crawler/test_cli.py::TestCliBackfillChannels -v
```

Expected: FAIL.

- [x] **Step 4: Rewrite `crawler/cli.py`**

```python
import argparse
import logging
import sys
from pathlib import Path

from crawler.bookmark_parser import parse
from crawler.datastore import Datastore
from crawler.metadata_fetcher import fetch_channel_metadata, fetch_metadata

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="ViewTube Bookmark Crawler")
    parser.add_argument("-i", "--input", required=True, type=Path, metavar="FILE",
                        help="Path to Firefox bookmarks file (.json or .html)")
    parser.add_argument("-o", "--output", required=True, type=Path, metavar="FILE",
                        help="Path to output SQLite database file")
    parser.add_argument("--api-key", default=None, metavar="KEY",
                        help="YouTube Data API v3 key (enables faster batch mode)")
    parser.add_argument("--delay", type=float, default=1.5, metavar="SECONDS",
                        help="Seconds between yt-dlp requests (default: 1.5)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Only process the first N YouTube video bookmarks")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch metadata even for already-stored videos")
    parser.add_argument("--backfill-channels", action="store_true",
                        help="Fetch full metadata for channels that only have stub records")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        bookmarks = parse(args.input)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    video_bookmarks = [b for b in bookmarks if b.youtube_video_id]
    channel_bookmarks = [b for b in bookmarks if b.youtube_channel_url]
    if args.limit is not None:
        video_bookmarks = video_bookmarks[: args.limit]

    try:
        with Datastore(args.output) as ds:
            total = len(video_bookmarks)
            for i, bookmark in enumerate(video_bookmarks, 1):
                vid_id = bookmark.youtube_video_id
                print(f"[{i}/{total}] {vid_id}", flush=True)

                if not args.force_refresh and ds.get_video_by_id(vid_id):
                    logger.info("Skipping already-fetched: %s", vid_id)
                    continue

                try:
                    metadata = fetch_metadata(vid_id, delay=args.delay)
                except Exception as exc:
                    logger.error("Unexpected error fetching %s: %s", vid_id, exc)
                    continue

                ds.upsert_video(metadata, bookmark)
                if metadata.channel_id and metadata.channel_name:
                    channel_url = f"https://www.youtube.com/channel/{metadata.channel_id}"
                    ds.upsert_channel_stub(
                        metadata.channel_id, metadata.channel_name, channel_url
                    )

            ch_total = len(channel_bookmarks)
            for i, bookmark in enumerate(channel_bookmarks, 1):
                print(f"[channel {i}/{ch_total}] {bookmark.url}", flush=True)
                try:
                    ch_meta = fetch_channel_metadata(bookmark.url, delay=args.delay)
                except Exception as exc:
                    logger.error("Unexpected error fetching channel %s: %s", bookmark.url, exc)
                    continue
                ds.upsert_channel(ch_meta)

            if args.backfill_channels:
                backfill_ids = ds.get_channel_ids_for_backfill()
                bf_total = len(backfill_ids)
                for i, channel_id in enumerate(backfill_ids, 1):
                    url = f"https://www.youtube.com/channel/{channel_id}"
                    print(f"[backfill {i}/{bf_total}] {channel_id}", flush=True)
                    try:
                        ch_meta = fetch_channel_metadata(url, delay=args.delay)
                    except Exception as exc:
                        logger.error("Unexpected error backfilling %s: %s", channel_id, exc)
                        continue
                    ds.upsert_channel(ch_meta)

    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved.", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:
        logger.error("Database error: %s", exc)
        sys.exit(3)


if __name__ == "__main__":
    main()
```

- [x] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/crawler/test_cli.py::TestCliChannelBookmarks tests/crawler/test_cli.py::TestCliChannelStubSideEffect tests/crawler/test_cli.py::TestCliBackfillChannels -v
```

Expected: all PASS.

- [x] **Step 6: Run full suite**

```bash
python -m pytest -q
```

Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add crawler/cli.py tests/crawler/test_cli.py tests/crawler/fixtures/sample_bookmarks.json
git commit -m "feat(crawler): process channel bookmarks, add channel stub side effect, add --backfill-channels"
```

---

### Task 6: Docs — CHANGELOG + plan-webapp.md

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `plan-webapp.md`

- [x] **Step 1: Append to CHANGELOG.md**

Insert after the header block (before the first existing `###` entry):

```
### Creator pages — schema & crawler, phase 1 (2026-07-08)

Adds a first-class `channels` table to ViewTube, populated from two sources: Firefox bookmarks of YouTube channel pages (`/@handle`, `/c/name`, `/channel/UCxxx`, `/user/name`) and as a side effect of video processing (free — uses data yt-dlp already returns). A new `--backfill-channels` CLI flag fetches full metadata (description, subscriber count, thumbnail) for existing stub-only channel records. A new `webapp/db/channels.py` module provides read functions for the UI phase. `get_all_channels` in `webapp/db/videos.py` renamed to `get_video_channel_names` to free the name for the channel entity version.

**Implications**
- **+** The `channels` table is the foundation for the upcoming channels UI, filtering, and tagging phases.
- **+** Every future video crawl automatically keeps channel stubs current, so the channel list grows organically without a separate step.
- **+** `--backfill-channels` gives a one-time path to enrich existing video library channels with descriptions and subscriber counts.
- **−** `--backfill-channels` is expensive: one yt-dlp call per unique channel. A library with 200 distinct channels takes ~5 minutes at default delay.
- **−** Stub records (from video processing) have no description or thumbnail until either a channel bookmark or `--backfill-channels` fills them in — the channel entity is incomplete until then.
- **−** Renaming `get_all_channels` is a breaking change for any code calling the old function directly; all internal call sites are updated in this change.
```

- [x] **Step 2: Update `plan-webapp.md`**

In the **Routes** table section (around the `/api/status` row), add a note after the watch-later routes that `GET /api/channels` is planned (out of scope for this phase — do not add a route, just document it as upcoming).

In the **Bookmarklet / quick-add** section, add a paragraph noting the new channel side effect:

> When the crawler processes a video bookmark, it also upserts a channel stub (`channel_id`, `channel_name`, constructed `channel_url`) into the `channels` table using data already returned by yt-dlp — no extra network call. Channel bookmarks (`/@handle`, `/c/name`, etc.) trigger a full `fetch_channel_metadata` call and populate all fields including `description`, `subscriber_count`, and `thumbnail_url`. The `--backfill-channels` flag fetches full channel metadata for any channel_ids in `videos` that have only a stub record.

Also add the `channels` table to the DB schema documentation section (wherever `videos` and `watch_later` are described).

- [x] **Step 3: Run full test suite one final time**

```bash
python -m pytest -q
```

Expected: all pass.

- [x] **Step 4: Commit**

```bash
git add CHANGELOG.md plan-webapp.md
git commit -m "docs: update changelog and plan for creator pages phase 1"
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 1 (schema) → Task 3 (`_SCHEMA`) + Task 4 (`schema.py`)
- ✅ Section 2 (models) → Task 1
- ✅ Section 3 (`fetch_channel_metadata`) → Task 2
- ✅ Section 4 (DB functions) → Task 3 (crawler) + Task 4 (webapp)
- ✅ Section 5 (crawler changes) → Task 5
- ✅ Section 6 (testing) → tests in Tasks 1–5

**Placeholder scan:** No TBDs, no "similar to Task N" shortcuts. Every step has exact code.

**Type consistency:**
- `ChannelMetadata` defined in Task 1, used in Tasks 2, 3, 5 — consistent.
- `upsert_channel(meta: ChannelMetadata)` defined in Task 3, called in Task 5 — consistent.
- `upsert_channel_stub(channel_id, channel_name, channel_url)` defined in Task 3, called in Task 5 — consistent.
- `get_video_channel_names` rename threaded through Tasks 4 tests, `videos.py`, `__init__.py`, `routes.py` — consistent.
- `get_all_channels` in `webapp/db/channels.py` returns `list[dict]`; tests in Task 4 verify `isinstance(channels[0], dict)` — consistent.
