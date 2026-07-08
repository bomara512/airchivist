# Creator Pages Support — Schema & Crawler (Phase 1) Design

**Date:** 2026-07-07
**Status:** Approved
**Scope:** Phase 1 of creator pages support. Covers the `channels` table, `ChannelMetadata` model, `fetch_channel_metadata`, crawler pipeline changes, and webapp DB read functions. Extension popup and UI (channels page, filtering by channel entity) are out of scope for this phase.

---

## Summary

ViewTube currently stores `channel_name` and `channel_id` per video but has no first-class channel entity. This phase adds one.

Channels are populated from two sources:
1. **Firefox bookmarks of channel pages** (`/@handle`, `/c/name`, `/channel/UCxxx`, `/user/name`) — the crawler picks these up as a new bookmark category and fetches full metadata via yt-dlp.
2. **Side effects of video processing** — every video bookmark that is processed creates a lightweight channel stub from data yt-dlp already returns for free (channel_id, channel_name, constructed channel_url). No extra network call.

A `--backfill-channels` CLI flag fetches full metadata (description, subscriber count, thumbnail) for all stub-only channel records, covering the existing video library.

---

## Section 1: Schema

### New `channels` table

Added to both `crawler/datastore.py` (`_SCHEMA`) and `webapp/db/schema.py` (`init_webapp_tables`). Both use `CREATE TABLE IF NOT EXISTS` so whichever runs first wins without conflict.

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

`channel_id` is always the `UCxxxxxxxx` format that yt-dlp normalises to, regardless of the input URL form. It is the natural join key against the existing `videos.channel_id` column.

### No change to `videos`

The existing `channel_id` TEXT column on `videos` becomes the implicit join key. No migration, no new column, no FK constraint — the hybrid coupling approach.

### Two tiers of channel record

| Tier | Source | Fields populated |
|---|---|---|
| **Stub** | Video processing side effect | `channel_id`, `channel_name`, `channel_url`, `fetch_status='ok'` |
| **Full** | Channel bookmark or `--backfill-channels` | All fields including `description`, `subscriber_count`, `thumbnail_url` |

The upsert logic never overwrites `description`/`subscriber_count`/`thumbnail_url` with NULL — a full record cannot be downgraded to a stub by a later video processing run.

---

## Section 2: Models & URL Detection

### New `_YT_CHANNEL_RE` in `crawler/models.py`

```python
_YT_CHANNEL_RE = re.compile(
    r'youtube\.com/(?:channel/(UC[A-Za-z0-9_-]+)|(?:c|user)/([^/?#]+)|@([^/?#]+))'
)
```

Matches all four YouTube channel URL forms. Only `/channel/UCxxx` yields the channel_id directly from the URL; the other three require yt-dlp to resolve the canonical ID.

### New `Bookmark.youtube_channel_url` property

```python
@property
def youtube_channel_url(self) -> Optional[str]:
    return self.url if _YT_CHANNEL_RE.search(self.url) else None
```

Returns the raw URL (not the resolved ID) so the fetcher can pass it straight to yt-dlp.

### New `ChannelMetadata` dataclass in `crawler/models.py`

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

Mirrors `VideoMetadata` in structure and reuses the existing `FetchStatus` enum.

---

## Section 3: `fetch_channel_metadata`

New function in `crawler/metadata_fetcher.py`, parallel to `fetch_metadata`:

```python
def fetch_channel_metadata(channel_url: str, delay: float = 1.5) -> ChannelMetadata:
```

Uses yt-dlp with `extract_flat: "discard_in_playlist"` to read channel-level info without iterating videos.

| yt-dlp field | `ChannelMetadata` field |
|---|---|
| `channel_id` | `channel_id` |
| `uploader` or `channel` | `channel_name` |
| `channel_url` (or constructed) | `channel_url` |
| `description` | `description` |
| `channel_follower_count` | `subscriber_count` |
| `thumbnail` | `thumbnail_url` |

Error handling mirrors `fetch_metadata`: catches `yt_dlp.utils.DownloadError`, returns a `ChannelMetadata` with `fetch_status = FetchStatus.ERROR` and `fetch_error` set. The same `_classify_error` helper can be reused for `PRIVATE` / `DELETED` / `ERROR` classification.

The `delay` parameter is honoured via `time.sleep` in the `finally` block, matching the existing pattern.

---

## Section 4: DB Functions

### `crawler/datastore.py`

The `_SCHEMA` constant gains the `channels` table DDL (see Section 1).

Three new methods on `Datastore`:

**`upsert_channel(meta: ChannelMetadata) -> None`**
Full upsert — all fields updated on conflict:
```sql
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
```

**`upsert_channel_stub(channel_id: str, channel_name: str, channel_url: str) -> None`**
Partial upsert — never overwrites rich fields already set by a full fetch:
```sql
INSERT INTO channels (channel_id, channel_name, channel_url, fetch_status)
VALUES (?, ?, ?, 'ok')
ON CONFLICT(channel_id) DO UPDATE SET
    channel_name = excluded.channel_name,
    channel_url  = excluded.channel_url
```

**`get_channel_ids_for_backfill() -> list[str]`**
Returns `channel_id` values present in `videos` but absent from `channels`, plus any `channels` rows where `description IS NULL` (stub-only records):
```sql
SELECT DISTINCT v.channel_id
FROM videos v
LEFT JOIN channels c ON c.channel_id = v.channel_id
WHERE v.channel_id IS NOT NULL
  AND (c.channel_id IS NULL OR c.description IS NULL)
```

### `webapp/db/channels.py` (new file)

Read-side functions for the webapp. The crawler never imports from `webapp/` — the crawler writes via `Datastore`; the webapp reads via this module.

- `get_all_channels(conn) -> list[dict]` — returns all rows from `channels` ordered by `channel_name`
- `get_channel(conn, channel_id: str) -> Optional[dict]` — single channel lookup

### `webapp/db/videos.py`

Rename existing `get_all_channels` → `get_video_channel_names` (it returns `list[str]` of distinct channel names from `videos`, used for the filter dropdown). Update the one call site in `routes.py`.

### `webapp/db/__init__.py`

Add exports from `channels.py`; update `get_all_channels` export to point at the new channel-entity version; add `get_video_channel_names` export.

---

## Section 5: Crawler Pipeline Changes

### `crawler/cli.py`

After parsing bookmarks, split into two lists:
```python
video_bookmarks = [b for b in bookmarks if b.youtube_video_id]
channel_bookmarks = [b for b in bookmarks if b.youtube_channel_url]
```

**Existing video loop** — unchanged except for one addition after each `ds.upsert_video(...)`:
```python
if metadata.channel_id and metadata.channel_name:
    channel_url = f"https://www.youtube.com/channel/{metadata.channel_id}"
    ds.upsert_channel_stub(metadata.channel_id, metadata.channel_name, channel_url)
```
No extra yt-dlp call — data is free from the video fetch.

**New channel bookmark loop** (after video loop):
```python
for bookmark in channel_bookmarks:
    meta = fetch_channel_metadata(bookmark.url, delay=args.delay)
    ds.upsert_channel(meta)
```

**New `--backfill-channels` flag** (opt-in, runs after channel bookmark loop):
```python
if args.backfill_channels:
    ids = ds.get_channel_ids_for_backfill()
    for channel_id in ids:
        url = f"https://www.youtube.com/channel/{channel_id}"
        meta = fetch_channel_metadata(url, delay=args.delay)
        ds.upsert_channel(meta)
```

The flag is expensive (one yt-dlp call per unique channel). For a library with hundreds of distinct channels, a single `--backfill-channels` run can take many minutes. Progress logging mirrors the video loop (`[i/total] channel_id`).

---

## Section 6: Testing

### `tests/crawler/test_models.py`
- `_YT_CHANNEL_RE` matches `/@handle`, `/c/name`, `/channel/UCxxx`, `/user/name`
- `_YT_CHANNEL_RE` does not match video URLs or non-YouTube URLs
- `Bookmark.youtube_channel_url` returns the URL for channel bookmarks, `None` for video bookmarks

### `tests/crawler/test_metadata_fetcher.py`
- `fetch_channel_metadata` maps yt-dlp response fields to `ChannelMetadata` correctly (mocked `yt_dlp.YoutubeDL`)
- `fetch_channel_metadata` returns `fetch_status='error'` on `DownloadError`

### `tests/crawler/test_datastore.py`
- `upsert_channel` stores all fields; re-upsert with new subscriber count updates correctly
- `upsert_channel_stub` inserts stub; subsequent stub upsert does not overwrite `description`/`thumbnail_url` from a prior full upsert
- `get_channel_ids_for_backfill` returns stubs and missing channels; excludes fully-fetched records

### `tests/crawler/test_cli.py`
- Channel bookmarks in fixture are processed and stored in `channels` table
- Video processing creates channel stub as a side effect
- `--backfill-channels` calls `fetch_channel_metadata` for stubs (mocked fetcher) and updates them

### `tests/webapp/test_db.py`
- `get_all_channels` (new channel-entity version) returns correct rows
- `get_channel` returns single channel and `None` for missing
- `get_video_channel_names` (renamed) still returns `list[str]` from `videos`

---

## Out of Scope for This Phase

- Extension popup behaviour on channel pages (separate spec)
- Channels UI page (separate spec)
- Filtering videos by channel entity (separate spec)
- Tags / search / history for channels (separate spec)
