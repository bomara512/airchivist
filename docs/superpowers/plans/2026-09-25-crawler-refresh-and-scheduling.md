# Crawler Refresh and Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the library's YouTube metadata current on an unattended nightly schedule, and make a video that has been deleted or made private visible in the UI instead of discoverable only by clicking it.

**Architecture:** A new `Datastore.refresh_video` writes metadata columns only on a successful fetch and touches only `fetch_status`/`fetch_error`/`last_fetched_at` otherwise, so a dead video keeps the record of what it was. A new `crawler/refresh.py` owns the run loop (select the N stalest videos, fetch each, tally the outcomes); `crawler/cli.py` gains a `refresh` subcommand while a missing subcommand still dispatches to today's ingest. A launchd plist runs it at 03:00. The webapp gains a `fetch_status` filter and a card badge so the statuses a refresh discovers are visible.

**Tech Stack:** Python 3.12+, SQLite (switching to WAL), yt-dlp, Flask + Jinja2, pytest, ruff, mypy, launchd.

**Spec:** `docs/superpowers/specs/2026-09-25-crawler-refresh-and-scheduling-design.md`

## Global Constraints

- **The crawler never writes user-owned columns.** On any path, in any method: `date_added`, `personal_view_count`, `date_last_viewed`, `is_watched`, `is_favorite`, `is_hidden`, `date_hidden` are never in an `INSERT` column list or a `DO UPDATE SET`.
- **A failed fetch preserves descriptive metadata.** `title`, `description`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published` keep their last successful values when `fetch_status != 'ok'`.
- **`airchivist-crawler -i <file> -o <db>` keeps working verbatim.** A missing subcommand dispatches to ingest.
- **US English throughout** — identifiers, UI copy, comments, docs. "favorite", "color", "behavior", "catalog".
- **CSS uses design tokens** from `webapp/static/style.css` `:root` — no new hex colors or bare `rem`/`px` font sizes. Exception: a status badge's own intentionally theme-invariant background+foreground pair may stay literal, with a comment saying why.
- **Every new DB function gets a test in `tests/webapp/test_db.py` or `tests/crawler/test_datastore.py`; every new/changed route gets one in `tests/webapp/test_routes.py`** — happy path plus at least one error/edge case.
- **`ruff check .` and `mypy` must be clean, and `python -m pytest -q` must print an empty warnings summary.** A warning is a failure, not cleanup for later.
- **Every `Datastore`/`sqlite3.connect` in a test uses `with` or `closing()`** — an unclosed handle surfaces as a `ResourceWarning` attributed to an unrelated test.
- **Update `plan-crawler.md` and/or `plan-webapp.md` plus `CHANGELOG.md` in the same commit as each task**, and `docs/feature-sheet.html` for the two tasks that ship user-facing behavior (Tasks 6 and 9).
- Baseline before Task 1: **652 backend tests, 123 extension tests**, ruff clean, mypy clean, empty warnings summary.
- **Never open `airchivist.db` from a verification step.** `webapp.app.create_app`
  calls `init_webapp_tables(db_path)`, and `Datastore.__init__` runs its schema
  script — so merely constructing either against the real database **writes to it**
  (applying WAL, and running the `tag_keywords` DROP added on 2026-09-25). Every
  hand-verification step in this plan copies the database to the scratch directory
  first and works on the copy. A verified backup taken before this plan started is at
  `airchivist.db.backup-2026-09-26-pre-refresh-plan` (2,959 videos, 27,244 tags,
  `integrity_check` ok), made with SQLite's backup API rather than `cp`.

## Review Focus

Input classes the spec implies but which no task's own happy-path tests exercise, most likely to bite first. Each has a test assigned to the task that owns the code.

1. **`--limit 0` or a negative limit.** SQLite treats `LIMIT -1` as *no limit*, so a typo'd `--limit -1` would refresh all 2,958 videos in one ~75-minute run. A non-positive limit must refresh nothing. Pinned in Task 3.
2. **One video failing in a way `fetch_metadata` does not catch** (a bare network error, not a `yt_dlp.utils.DownloadError`). A single bad video must not abort the whole nightly job — the run logs it, counts it, and continues. Pinned in Task 4.
3. **A refresh finding a previously-dead video is alive again** (`deleted` → `ok`). It must restore the metadata *and* clear `fetch_error`, or the row keeps a stale error string forever. Pinned in Task 2.
4. **`?fetch_status=ok` passed explicitly.** Must behave exactly like omitting it, not add a second contradictory clause or return zero rows. Pinned in Task 7.
5. **A refresh run on an empty library, or one smaller than `--limit`.** Must produce a `0 of 0` summary and exit 0, not divide by zero or raise. Pinned in Task 4.

---

## File Structure

| File | Responsibility |
|---|---|
| `crawler/datastore.py` (modify) | `refresh_video`, `get_stale_video_ids`, the `upsert_video` failure fix, WAL pragma |
| `crawler/refresh.py` (create) | `RefreshSummary` dataclass + `run_refresh()` — the run loop and tally, no argparse, no SQL |
| `crawler/cli.py` (modify) | Subparsers, `refresh` dispatch, backward-compatible ingest |
| `scripts/com.airchivist.refresh.plist` (create) | launchd template |
| `webapp/db/schema.py` (modify) | WAL pragma on the webapp side |
| `webapp/db/videos.py` (modify) | `fetch_status` allow-list + `_build_where` override |
| `webapp/video_filters.py` (modify) | `FetchStatusFilter` enum + `fetch_status` on `VideoListFilters` |
| `webapp/routes.py` (modify) | Pass the new filter through (no new route) |
| `webapp/templates/_video_card.html` (modify) | The status badge |
| `webapp/templates/index.html` (modify) | The status `<select>` |
| `webapp/static/style.css` (modify) | `.status-badge` and its three variants |
| `tests/crawler/test_datastore.py`, `tests/crawler/test_refresh.py` (create), `tests/crawler/test_cli.py`, `tests/webapp/test_db.py`, `tests/webapp/test_video_filters.py`, `tests/webapp/test_routes.py` | Tests |

---

## Task 1: Switch both connection paths to WAL

**Files:**
- Modify: `webapp/db/schema.py` (`init_webapp_tables`)
- Modify: `crawler/datastore.py` (`Datastore.__init__`)
- Test: `tests/webapp/test_db.py`, `tests/crawler/test_datastore.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks call. Both connection paths leave the database in `journal_mode=wal`.

Applied in **both** places on purpose: the setting is persistent so whichever runs first does the work, but applying it in only one would leave a database unconverted for someone who runs the crawler and never starts the webapp — exactly the case a scheduled refresh creates.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py`, inside `class TestInitWebappTables`:

```python
    def test_switches_the_database_to_wal(self, tmp_path):
        db_path = self._bare_db(tmp_path)
        init_webapp_tables(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_wal_survives_a_second_init(self, tmp_path):
        db_path = self._bare_db(tmp_path)
        init_webapp_tables(db_path)
        init_webapp_tables(db_path)
        with closing(sqlite3.connect(db_path)) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
```

Add to `tests/crawler/test_datastore.py` (match the file's existing `with Datastore(...) as ds:` style):

```python
class TestWalMode:
    """The crawler may be the only thing that ever opens a given database — a
    scheduled refresh on a machine where the webapp was never started — so it
    cannot rely on init_webapp_tables having set the journal mode."""

    def test_datastore_switches_the_database_to_wal(self, tmp_path):
        db_path = tmp_path / "wal.db"
        with Datastore(db_path):
            pass
        with closing(sqlite3.connect(str(db_path))) as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py -k wal tests/crawler/test_datastore.py -k wal -v --no-cov`
Expected: FAIL — all three assert `'delete' == 'wal'`.

- [ ] **Step 3: Implement**

In `webapp/db/schema.py`, immediately after `conn.execute("PRAGMA foreign_keys = ON")`:

```python
    # WAL so a background crawler refresh never blocks a page load. Persistent —
    # one successful application converts the file for good. Applied here AND in
    # crawler/datastore.py because either may be the first to open a given
    # database; the second call is a no-op.
    conn.execute("PRAGMA journal_mode = WAL")
```

In `crawler/datastore.py`, in `__init__` immediately after `self._conn.execute("PRAGMA foreign_keys = ON")`:

```python
        # See webapp/db/schema.py: WAL keeps readers from blocking on this
        # writer. Persistent, so applying it in both places is harmless.
        self._conn.execute("PRAGMA journal_mode = WAL")
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py -k wal tests/crawler/test_datastore.py -k wal -v --no-cov`
Expected: PASS (3 tests).

- [ ] **Step 5: Verify the whole suite and the real database**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: ruff clean, mypy `Success`, **655 passed**, warnings summary empty.

Run, to confirm the real database converts and nothing is lost:

Use SQLite's backup API rather than `cp` — a plain copy of a database something
else has open can capture a torn page:

```bash
python3 -c "
import sqlite3, sys; sys.path.insert(0, '.')
src, dst = sqlite3.connect('airchivist.db'), sqlite3.connect('/tmp/wal-check.db')
with dst: src.backup(dst)
dst.close(); src.close()
from webapp.db import init_webapp_tables
init_webapp_tables('/tmp/wal-check.db')
c = sqlite3.connect('/tmp/wal-check.db')
print('journal_mode:', c.execute('PRAGMA journal_mode').fetchone()[0])
print('integrity:', c.execute('PRAGMA integrity_check').fetchone()[0])
print('videos:', c.execute('SELECT COUNT(*) FROM videos').fetchone()[0])
c.close()"
rm -f /tmp/wal-check.db /tmp/wal-check.db-wal /tmp/wal-check.db-shm
```

Expected: `journal_mode: wal`, `integrity: ok`, and a video count matching the live
database (about 2,959).

- [ ] **Step 6: Document and commit**

In `README.md`, in the Setup section after the database is first mentioned, add:

```markdown
The database runs in SQLite's WAL mode, so a background metadata refresh never
blocks a page load. SQLite keeps two sidecar files next to it,
`airchivist.db-wal` and `airchivist.db-shm`. A file-copy backup should include
them, or run `sqlite3 airchivist.db 'PRAGMA wal_checkpoint(TRUNCATE);'` first so
everything committed is inside the main file.
```

In `plan-crawler.md`, in the Tooling gates section, add one line: `Both connection paths set `journal_mode = WAL` (persistent; applied in `webapp/db/schema.py` and `crawler/datastore.py` so whichever opens a database first converts it).`

Add a `CHANGELOG.md` entry under today's date noting the switch, the sidecar files, and the backup implication as the con.

```bash
git add -u && git commit -m "perf: switch SQLite to WAL so a refresh never blocks page loads

Applied in both init_webapp_tables and Datastore.__init__ — the setting is
persistent, but applying it in only one would leave a database unconverted
for anyone who runs the crawler without ever starting the webapp, which is
exactly the case a scheduled refresh creates."
```

---

## Task 2: `refresh_video`, and the same fix for `upsert_video`

**Files:**
- Modify: `crawler/datastore.py`
- Test: `tests/crawler/test_datastore.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Datastore.refresh_video(metadata: VideoMetadata) -> None`. Called by `crawler/refresh.py` in Task 4.

This is the task the whole feature exists to get right. Read the spec's "The hazard this design exists to avoid" section before starting.

- [ ] **Step 1: Write the failing tests**

Add to `tests/crawler/test_datastore.py`:

```python
class TestRefreshVideo:
    """A refresh must never trade a real title for the fact that a video died."""

    def _seed_ok(self, ds):
        ds.upsert_video(
            VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                title="Original Title",
                description="Original description",
                channel_name="Original Channel",
                channel_id="UCorig",
                yt_view_count=1000,
                duration_seconds=600,
                thumbnail_url="https://example.test/thumb.jpg",
                fetch_status=FetchStatus.OK,
            ),
            Bookmark(url="https://www.youtube.com/watch?v=aaaaaaaaaa1", title="Original Title"),
        )

    def test_a_deleted_video_keeps_its_last_known_metadata(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                fetch_status=FetchStatus.DELETED,
                fetch_error="Video unavailable",
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "deleted"
        assert row["fetch_error"] == "Video unavailable"
        assert row["title"] == "Original Title"
        assert row["description"] == "Original description"
        assert row["channel_name"] == "Original Channel"
        assert row["channel_id"] == "UCorig"
        assert row["yt_view_count"] == 1000
        assert row["duration_seconds"] == 600
        assert row["thumbnail_url"] == "https://example.test/thumb.jpg"

    def test_a_private_video_keeps_its_last_known_metadata(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                fetch_status=FetchStatus.PRIVATE,
                fetch_error="Private video",
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "private"
        assert row["title"] == "Original Title"

    def test_a_successful_refresh_updates_the_metadata(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1",
                url="https://www.youtube.com/watch?v=aaaaaaaaaa1",
                title="Renamed Title",
                description="New description",
                channel_name="Renamed Channel",
                channel_id="UCnew",
                yt_view_count=5000,
                duration_seconds=601,
                thumbnail_url="https://example.test/new.jpg",
                fetch_status=FetchStatus.OK,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["title"] == "Renamed Title"
        assert row["yt_view_count"] == 5000
        assert row["channel_name"] == "Renamed Channel"

    def test_a_video_coming_back_to_life_clears_the_stale_error(self, tmp_path):
        """Review Focus #3: deleted -> ok must not leave fetch_error set forever."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ))
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                title="Back Again", yt_view_count=7,
                fetch_status=FetchStatus.OK,
            ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "ok"
        assert row["fetch_error"] is None
        assert row["title"] == "Back Again"

    def test_last_fetched_at_advances_on_both_outcomes(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds._conn.execute("UPDATE videos SET last_fetched_at = '2020-01-01T00:00:00+00:00'")
            ds._conn.commit()
            ds.refresh_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", fetch_status=FetchStatus.DELETED,
            ))
            after_fail = ds.get_video_by_id("aaaaaaaaaa1")["last_fetched_at"]
            assert after_fail > "2020-01-01T00:00:00+00:00"

    def test_never_touches_user_owned_columns(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed_ok(ds)
            ds._conn.execute("""
                UPDATE videos SET personal_view_count = 7, date_last_viewed = '2026-01-01',
                       is_hidden = 1, date_added = '2024-06-01'
            """)
            ds._conn.commit()
            for status in (FetchStatus.OK, FetchStatus.DELETED):
                ds.refresh_video(VideoMetadata(
                    video_id="aaaaaaaaaa1", url="u", title="X", fetch_status=status,
                ))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["personal_view_count"] == 7
        assert row["date_last_viewed"] == "2026-01-01"
        assert row["is_hidden"] == 1
        assert row["date_added"] == "2024-06-01"

    def test_refreshing_an_unknown_video_id_is_a_no_op(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds.refresh_video(VideoMetadata(
                video_id="zzzzzzzzzz9", url="u", fetch_status=FetchStatus.OK, title="T",
            ))
            assert ds.get_video_by_id("zzzzzzzzzz9") is None


class TestUpsertVideoPreservesOnFailure:
    """Same hazard, older path: `--force-refresh` over a bookmarks file containing a
    since-deleted video would otherwise NULL out its title."""

    def test_a_failed_upsert_keeps_the_existing_title(self, tmp_path):
        bookmark = Bookmark(url="https://www.youtube.com/watch?v=aaaaaaaaaa1", title="T")
        with Datastore(tmp_path / "t.db") as ds:
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u", title="Original Title",
                channel_name="Original Channel", yt_view_count=10,
                fetch_status=FetchStatus.OK,
            ), bookmark)
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ), bookmark)
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row["fetch_status"] == "deleted"
        assert row["title"] == "Original Title"
        assert row["channel_name"] == "Original Channel"
        assert row["yt_view_count"] == 10

    def test_a_first_time_failed_insert_still_creates_the_row(self, tmp_path):
        """A brand-new bookmark whose video is already dead has no metadata to
        preserve — the row must still exist, so the user sees they saved something."""
        with Datastore(tmp_path / "t.db") as ds:
            ds.upsert_video(VideoMetadata(
                video_id="aaaaaaaaaa1", url="u",
                fetch_status=FetchStatus.DELETED, fetch_error="Video unavailable",
            ), Bookmark(url="u", title="T"))
            row = ds.get_video_by_id("aaaaaaaaaa1")
        assert row is not None
        assert row["fetch_status"] == "deleted"
```

Ensure `FetchStatus` is imported in the test file's import block alongside the existing `Bookmark` / `VideoMetadata` imports, and `from contextlib import closing` if not already present.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/crawler/test_datastore.py -k "RefreshVideo or UpsertVideoPreserves" -v --no-cov`
Expected: FAIL — `AttributeError: 'Datastore' object has no attribute 'refresh_video'` for the first class; the two `TestUpsertVideoPreservesOnFailure` tests fail on `assert row["title"] == "Original Title"` with `None`.

- [ ] **Step 3: Implement `refresh_video`**

Add to `crawler/datastore.py`, directly after `upsert_video`:

```python
    # Columns a successful fetch is allowed to overwrite. Deliberately excludes
    # date_added, personal_view_count, date_last_viewed, is_watched, is_favorite,
    # is_hidden and date_hidden — those are the user's own data, not YouTube's.
    _REFRESHABLE_COLUMNS = (
        "url", "title", "description", "channel_name", "channel_id",
        "yt_view_count", "duration_seconds", "thumbnail_url", "date_published",
    )

    def refresh_video(self, metadata: VideoMetadata) -> None:
        """Update an existing video from a re-fetch. No-op if the row is absent.

        On a successful fetch this refreshes the descriptive columns. On any other
        status it writes ONLY fetch_status, fetch_error and last_fetched_at, leaving
        title/channel/thumbnail/view count/duration at their last known values —
        because `fetch_metadata`'s failure path returns those as None, and a nightly
        job that wrote them through would erase the record of what a since-deleted
        video was. That is the whole reason this method exists rather than reusing
        `upsert_video`.
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

        assignments = ", ".join(f"{col} = ?" for col in self._REFRESHABLE_COLUMNS)
        values = [
            metadata.url, metadata.title, metadata.description,
            metadata.channel_name, metadata.channel_id, metadata.yt_view_count,
            metadata.duration_seconds, metadata.thumbnail_url,
            _dt(metadata.date_published),
        ]
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
        self._apply_yt_tags(metadata)
        apply_aliases(self._conn, metadata.video_id)
```

`FetchStatus` must be added to `crawler/datastore.py`'s import from `crawler.models`.

- [ ] **Step 4: Fix `upsert_video`'s failure path**

In `upsert_video`, wrap each descriptive column's `DO UPDATE SET` assignment so a failed fetch keeps the stored value. Replace the eight assignments for `url`, `title`, `description`, `channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published` with `COALESCE(excluded.<col>, videos.<col>)`:

```sql
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
```

Add a comment above the clause:

```sql
            -- COALESCE, not a bare assignment: fetch_metadata's failure path returns
            -- every descriptive field as None, so `--force-refresh` over a bookmarks
            -- file containing a since-deleted video would otherwise NULL out the
            -- record of what that video was. A successful fetch always supplies a
            -- value, so COALESCE is a no-op on the happy path.
```

Note the deliberate difference from `refresh_video`: `COALESCE` also means a *successful* fetch that happens to return `None` for one field (a video with no description, say) keeps the old value rather than clearing it. That is the safer failure mode for an archive and is why the same shape is not used in `refresh_video`, where the status already tells us the whole fetch succeeded.

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest tests/crawler/test_datastore.py -v --no-cov`
Expected: all PASS, including the file's pre-existing `upsert_video` tests — those are the proof the `COALESCE` change did not alter happy-path behavior.

- [ ] **Step 6: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **664 passed**, warnings summary empty.

- [ ] **Step 7: Document and commit**

In `plan-crawler.md`, under the Datastore section, document `refresh_video` with its two branches, the `_REFRESHABLE_COLUMNS` tuple, and why it is separate from `upsert_video` (no `Bookmark`, and opposite obligations on failure). Note the `COALESCE` change to `upsert_video` as a behavior change.

Add a `CHANGELOG.md` entry. State plainly that `upsert_video`'s behavior changed, and that the con is the `COALESCE` asymmetry described in Step 4.

```bash
git add -u && git commit -m "feat: add Datastore.refresh_video, preserve metadata on failed fetch

fetch_metadata's failure path returns every descriptive field as None, and
upsert_video assigned all of them from excluded — so re-fetching a
since-deleted video erased the record of what it was. refresh_video writes
only status/error/timestamp on a failed fetch, and upsert_video now
COALESCEs, which fixes the same hazard in --force-refresh."
```

---

## Task 3: Staleness selection

**Files:**
- Modify: `crawler/datastore.py`
- Test: `tests/crawler/test_datastore.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Datastore.get_stale_video_ids(limit: int) -> list[str]` and `Datastore.count_videos() -> int`. Both called by `crawler/refresh.py` in Task 4.

- [ ] **Step 1: Write the failing tests**

```python
class TestGetStaleVideoIds:
    def _seed(self, ds, rows):
        """rows: list of (video_id, last_fetched_at or None)."""
        for video_id, fetched in rows:
            ds._conn.execute(
                "INSERT INTO videos (video_id, url, fetch_status, last_fetched_at) "
                "VALUES (?, ?, 'ok', ?)",
                (video_id, f"https://www.youtube.com/watch?v={video_id}", fetched),
            )
        ds._conn.commit()

    def test_orders_oldest_refreshed_first(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [
                ("newest00001", "2026-09-01T00:00:00+00:00"),
                ("oldest00001", "2026-01-01T00:00:00+00:00"),
                ("middle00001", "2026-05-01T00:00:00+00:00"),
            ])
            assert ds.get_stale_video_ids(10) == ["oldest00001", "middle00001", "newest00001"]

    def test_never_fetched_videos_come_first(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [
                ("fetched0001", "2026-01-01T00:00:00+00:00"),
                ("neverfetch1", None),
            ])
            assert ds.get_stale_video_ids(10)[0] == "neverfetch1"

    def test_honors_the_limit(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [(f"video00000{i}", f"2026-0{i}-01T00:00:00+00:00") for i in range(1, 6)])
            assert len(ds.get_stale_video_ids(2)) == 2

    def test_includes_hidden_and_already_dead_videos(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds._conn.execute(
                "INSERT INTO videos (video_id, url, fetch_status, is_hidden, last_fetched_at) "
                "VALUES ('hidden00001', 'u', 'deleted', 1, '2026-01-01T00:00:00+00:00')"
            )
            ds._conn.commit()
            assert ds.get_stale_video_ids(10) == ["hidden00001"]

    def test_a_non_positive_limit_selects_nothing(self, tmp_path):
        """Review Focus #1: SQLite reads LIMIT -1 as *no limit*, so a typo'd
        `--limit -1` would refresh the entire library in one run."""
        with Datastore(tmp_path / "t.db") as ds:
            self._seed(ds, [("video000001", None), ("video000002", None)])
            assert ds.get_stale_video_ids(0) == []
            assert ds.get_stale_video_ids(-1) == []

    def test_empty_library_returns_empty(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            assert ds.get_stale_video_ids(10) == []


class TestCountVideos:
    def test_counts_every_row(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            ds._conn.execute("INSERT INTO videos (video_id, url) VALUES ('a0000000001', 'u')")
            ds._conn.execute("INSERT INTO videos (video_id, url) VALUES ('a0000000002', 'u')")
            ds._conn.commit()
            assert ds.count_videos() == 2

    def test_empty_library_is_zero(self, tmp_path):
        with Datastore(tmp_path / "t.db") as ds:
            assert ds.count_videos() == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/crawler/test_datastore.py -k "GetStaleVideoIds or CountVideos" -v --no-cov`
Expected: FAIL — `AttributeError: 'Datastore' object has no attribute 'get_stale_video_ids'`.

- [ ] **Step 3: Implement**

```python
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

    def count_videos(self) -> int:
        """Total rows in `videos`, for the refresh summary's denominator."""
        return self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/crawler/test_datastore.py -k "GetStaleVideoIds or CountVideos" -v --no-cov`
Expected: PASS (8 tests).

- [ ] **Step 5: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **672 passed**, warnings summary empty.

- [ ] **Step 6: Document and commit**

Document both methods in `plan-crawler.md`'s Datastore section, including the NULLs-first ordering and the non-positive-limit guard with its `LIMIT -1` rationale. Add a `CHANGELOG.md` entry.

```bash
git add -u && git commit -m "feat: add staleness selection to Datastore

get_stale_video_ids(limit) returns the least-recently-refreshed videos,
NULL last_fetched_at first. Guards a non-positive limit, because SQLite
reads LIMIT -1 as no limit at all."
```

---

## Task 4: The refresh run loop

**Files:**
- Create: `crawler/refresh.py`
- Create: `tests/crawler/test_refresh.py`

**Interfaces:**
- Consumes: `Datastore.get_stale_video_ids(limit) -> list[str]`, `Datastore.count_videos() -> int`, `Datastore.refresh_video(metadata) -> None`, `crawler.metadata_fetcher.fetch_metadata(video_id, delay) -> VideoMetadata`.
- Produces: `crawler.refresh.RefreshSummary` (frozen dataclass with fields `attempted: int`, `library_total: int`, `counts: dict[str, int]`, `elapsed_seconds: float`, and a `line()` method returning the one-line summary) and `crawler.refresh.run_refresh(ds, limit, delay, fetch=fetch_metadata) -> RefreshSummary`.

`fetch` is a keyword parameter defaulting to the real fetcher so tests can inject a stub without patching a module global.

- [ ] **Step 1: Write the failing tests**

Create `tests/crawler/test_refresh.py`:

```python
from crawler.datastore import Datastore
from crawler.models import Bookmark, FetchStatus, VideoMetadata
from crawler.refresh import RefreshSummary, run_refresh


def _ok(video_id, title="T"):
    return VideoMetadata(video_id=video_id, url="u", title=title, fetch_status=FetchStatus.OK)


def _seed(ds, *video_ids):
    for vid in video_ids:
        ds.upsert_video(_ok(vid, f"Title {vid}"), Bookmark(url="u", title="T"))


class TestRunRefresh:
    def test_refreshes_every_selected_video(self, tmp_path):
        calls = []

        def fake_fetch(video_id, delay=0):
            calls.append(video_id)
            return _ok(video_id, "Updated")

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2")
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
            assert sorted(calls) == ["aaaaaaaaaa1", "aaaaaaaaaa2"]
            assert ds.get_video_by_id("aaaaaaaaaa1")["title"] == "Updated"
        assert summary.attempted == 2
        assert summary.counts["ok"] == 2

    def test_tallies_each_status(self, tmp_path):
        statuses = {
            "aaaaaaaaaa1": FetchStatus.OK,
            "aaaaaaaaaa2": FetchStatus.DELETED,
            "aaaaaaaaaa3": FetchStatus.PRIVATE,
        }

        def fake_fetch(video_id, delay=0):
            return VideoMetadata(video_id=video_id, url="u", title="T",
                                 fetch_status=statuses[video_id])

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, *statuses)
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
        assert summary.counts == {"ok": 1, "deleted": 1, "private": 1}

    def test_honors_the_limit(self, tmp_path):
        def fake_fetch(video_id, delay=0):
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3")
            summary = run_refresh(ds, limit=2, delay=0, fetch=fake_fetch)
        assert summary.attempted == 2

    def test_an_unexpected_exception_does_not_abort_the_run(self, tmp_path):
        """Review Focus #2: one bad video must not cost the whole nightly job. The
        row is left untouched so the next run retries it."""
        def fake_fetch(video_id, delay=0):
            if video_id == "aaaaaaaaaa2":
                raise OSError("network unreachable")
            return _ok(video_id, "Updated")

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3")
            summary = run_refresh(ds, limit=10, delay=0, fetch=fake_fetch)
            assert ds.get_video_by_id("aaaaaaaaaa1")["title"] == "Updated"
            assert ds.get_video_by_id("aaaaaaaaaa3")["title"] == "Updated"
            assert ds.get_video_by_id("aaaaaaaaaa2")["title"] == "Title aaaaaaaaaa2"
        assert summary.counts["ok"] == 2
        assert summary.counts["failed"] == 1

    def test_an_empty_library_is_a_clean_zero_run(self, tmp_path):
        """Review Focus #5."""
        def fake_fetch(video_id, delay=0):
            raise AssertionError("must not be called")

        with Datastore(tmp_path / "t.db") as ds:
            summary = run_refresh(ds, limit=200, delay=0, fetch=fake_fetch)
        assert summary.attempted == 0
        assert summary.library_total == 0
        assert summary.counts == {}
        assert "0 of 0" in summary.line()

    def test_a_library_smaller_than_the_limit_is_fine(self, tmp_path):
        def fake_fetch(video_id, delay=0):
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1")
            summary = run_refresh(ds, limit=200, delay=0, fetch=fake_fetch)
        assert summary.attempted == 1
        assert summary.library_total == 1

    def test_passes_the_delay_through_to_the_fetcher(self, tmp_path):
        seen = []

        def fake_fetch(video_id, delay=0):
            seen.append(delay)
            return _ok(video_id)

        with Datastore(tmp_path / "t.db") as ds:
            _seed(ds, "aaaaaaaaaa1")
            run_refresh(ds, limit=10, delay=2.5, fetch=fake_fetch)
        assert seen == [2.5]


class TestRefreshSummaryLine:
    def test_reads_as_one_scannable_line(self):
        summary = RefreshSummary(
            attempted=200, library_total=2958,
            counts={"ok": 196, "deleted": 3, "private": 1},
            elapsed_seconds=312.0,
        )
        line = summary.line()
        assert line.startswith("refreshed 200 of 2958")
        assert "196 ok" in line
        assert "3 deleted" in line
        assert "5m12s" in line

    def test_a_sub_minute_run_reads_in_seconds(self):
        summary = RefreshSummary(attempted=1, library_total=1, counts={"ok": 1},
                                 elapsed_seconds=4.0)
        assert "4s" in summary.line()

    def test_a_zero_run_still_produces_a_line(self):
        assert "refreshed 0 of 0" in RefreshSummary(
            attempted=0, library_total=0, counts={}, elapsed_seconds=0.0
        ).line()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/crawler/test_refresh.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.refresh'`.

- [ ] **Step 3: Implement**

Create `crawler/refresh.py`:

```python
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from crawler.datastore import Datastore
from crawler.metadata_fetcher import fetch_metadata
from crawler.models import VideoMetadata

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200

# Tally key for a video whose fetch raised something `fetch_metadata` does not
# convert into a FetchStatus — a bare network error, say. Not a FetchStatus member
# because nothing is written to the row: the video keeps its old status so the next
# run retries it.
FAILED = "failed"


def _format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


@dataclass(frozen=True)
class RefreshSummary:
    """The outcome of one refresh run, as one scannable log line."""

    attempted: int
    library_total: int
    counts: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def line(self) -> str:
        breakdown = ", ".join(f"{n} {status}" for status, n in sorted(self.counts.items()))
        suffix = f" ({breakdown})" if breakdown else ""
        return (
            f"refreshed {self.attempted} of {self.library_total}"
            f"{suffix} in {_format_elapsed(self.elapsed_seconds)}"
        )


def run_refresh(
    ds: Datastore,
    limit: int = DEFAULT_LIMIT,
    delay: float = 1.5,
    fetch: Callable[..., VideoMetadata] = fetch_metadata,
) -> RefreshSummary:
    """Re-fetch the `limit` stalest videos and record what came back.

    `fetch` is injectable so tests can drive the loop without yt-dlp or a network.

    One video's unexpected failure never aborts the run: a nightly job that gave up
    on the first transient network error would silently stop maintaining the library,
    and the failure would only be visible to someone reading the log. Such a video is
    counted under FAILED and left untouched, so the next run picks it up again.
    """
    started = time.monotonic()
    video_ids = ds.get_stale_video_ids(limit)
    counts: dict[str, int] = {}

    for video_id in video_ids:
        try:
            metadata = fetch(video_id, delay=delay)
        except Exception as exc:
            logger.error("Unexpected error refreshing %s: %s", video_id, exc)
            counts[FAILED] = counts.get(FAILED, 0) + 1
            continue
        ds.refresh_video(metadata)
        counts[metadata.fetch_status] = counts.get(metadata.fetch_status, 0) + 1

    return RefreshSummary(
        attempted=len(video_ids),
        library_total=ds.count_videos(),
        counts=counts,
        elapsed_seconds=time.monotonic() - started,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/crawler/test_refresh.py -v --no-cov`
Expected: PASS (10 tests).

- [ ] **Step 5: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **682 passed**, warnings summary empty.

- [ ] **Step 6: Document and commit**

Add a "Metadata refresh" section to `plan-crawler.md` covering the selection policy, the per-video exception containment and why it matters for an unattended job, and the summary-line format. Add a `CHANGELOG.md` entry.

```bash
git add crawler/refresh.py tests/crawler/test_refresh.py && git add -u
git commit -m "feat: add the refresh run loop

run_refresh selects the stalest videos, re-fetches each, and tallies the
outcomes into a one-line summary. A single video's unexpected failure is
counted and skipped rather than aborting the run — a nightly job that quit
on the first transient network error would stop maintaining the library
with nothing but a log line to show it."
```

---

## Task 5: `refresh` subcommand, with ingest unchanged

**Files:**
- Modify: `crawler/cli.py`
- Test: `tests/crawler/test_cli.py`

**Interfaces:**
- Consumes: `crawler.refresh.run_refresh`, `crawler.refresh.DEFAULT_LIMIT`, `Datastore`.
- Produces: nothing later tasks call.

Restructure `main()` so argument parsing and dispatch are separable from the work. Extract today's body into `_run_ingest(args)` and add `_run_refresh(args)`; `main()` parses and dispatches.

- [ ] **Step 1: Write the failing tests**

Add to `tests/crawler/test_cli.py`. The file already does `from crawler import cli`
and invokes `cli.main()` inside `patch(...)` blocks — match that, so replace every
`main()` below with `cli.main()`. `monkeypatch.setattr` is equivalent to the file's
`patch()` usage here and is fine; `Datastore` and `pytest` need adding to its imports.

```python
class TestRefreshSubcommand:
    def test_refresh_calls_run_refresh_with_the_parsed_options(self, tmp_path, monkeypatch):
        db = tmp_path / "t.db"
        with Datastore(db):
            pass
        captured = {}

        def fake_run_refresh(ds, limit, delay, **kwargs):
            captured["limit"] = limit
            captured["delay"] = delay
            from crawler.refresh import RefreshSummary
            return RefreshSummary(attempted=0, library_total=0, counts={}, elapsed_seconds=0.0)

        monkeypatch.setattr("crawler.cli.run_refresh", fake_run_refresh)
        monkeypatch.setattr(
            "sys.argv",
            ["airchivist-crawler", "refresh", "--db", str(db), "--limit", "5", "--delay", "0"],
        )
        main()
        assert captured == {"limit": 5, "delay": 0.0}

    def test_refresh_defaults_to_200(self, tmp_path, monkeypatch):
        db = tmp_path / "t.db"
        with Datastore(db):
            pass
        captured = {}

        def fake_run_refresh(ds, limit, delay, **kwargs):
            captured["limit"] = limit
            from crawler.refresh import RefreshSummary
            return RefreshSummary(attempted=0, library_total=0, counts={}, elapsed_seconds=0.0)

        monkeypatch.setattr("crawler.cli.run_refresh", fake_run_refresh)
        monkeypatch.setattr("sys.argv", ["airchivist-crawler", "refresh", "--db", str(db)])
        main()
        assert captured["limit"] == 200

    def test_refresh_prints_the_summary_line(self, tmp_path, monkeypatch, capsys):
        db = tmp_path / "t.db"
        with Datastore(db):
            pass
        monkeypatch.setattr("sys.argv", ["airchivist-crawler", "refresh", "--db", str(db)])
        main()
        assert "refreshed 0 of 0" in capsys.readouterr().out

    def test_refresh_exits_1_when_the_database_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["airchivist-crawler", "refresh", "--db", str(tmp_path / "nope.db")],
        )
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_refresh_does_not_require_an_input_file(self, tmp_path, monkeypatch):
        """The whole reason for subcommands: -i is meaningless for a refresh."""
        db = tmp_path / "t.db"
        with Datastore(db):
            pass
        monkeypatch.setattr("sys.argv", ["airchivist-crawler", "refresh", "--db", str(db)])
        main()  # must not raise SystemExit(2) for a missing -i


class TestIngestStaysBackwardCompatible:
    def test_a_bare_input_output_invocation_still_ingests(self, tmp_path, monkeypatch):
        """The README documents this exact form; it must keep working verbatim."""
        bookmarks = tmp_path / "bm.json"
        bookmarks.write_text("[]")
        called = {}

        def fake_parse(path):
            called["parsed"] = path
            return []

        monkeypatch.setattr("crawler.cli.parse", fake_parse)
        monkeypatch.setattr(
            "sys.argv",
            ["airchivist-crawler", "-i", str(bookmarks), "-o", str(tmp_path / "out.db")],
        )
        main()
        assert called["parsed"] == bookmarks

    def test_an_explicit_ingest_subcommand_also_works(self, tmp_path, monkeypatch):
        bookmarks = tmp_path / "bm.json"
        bookmarks.write_text("[]")
        monkeypatch.setattr("crawler.cli.parse", lambda path: [])
        monkeypatch.setattr(
            "sys.argv",
            ["airchivist-crawler", "ingest", "-i", str(bookmarks), "-o", str(tmp_path / "out.db")],
        )
        main()  # must not raise
```

Ensure `pytest`, `Datastore` and `main` are imported in the test file.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/crawler/test_cli.py -k "Refresh or BackwardCompatible" -v --no-cov`
Expected: FAIL — argparse exits 2 on the unrecognized `refresh` argument.

- [ ] **Step 3: Implement the dispatch**

In `crawler/cli.py`, add the imports:

```python
from crawler.refresh import DEFAULT_LIMIT, run_refresh
```

Rename the existing `main()` body (everything after `args = parser.parse_args()` and the `logging.basicConfig` call) into `def _run_ingest(args) -> None:`. Then:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Airchivist Bookmark Crawler")
    _add_common_args(parser)
    _add_ingest_args(parser)   # -i/-o remain on the top-level parser for compatibility

    subparsers = parser.add_subparsers(dest="command")

    ingest = subparsers.add_parser("ingest", help="Ingest bookmarks and fetch metadata")
    _add_common_args(ingest)
    _add_ingest_args(ingest)

    refresh = subparsers.add_parser(
        "refresh", help="Re-fetch metadata for videos already in the database"
    )
    _add_common_args(refresh)
    refresh.add_argument("--db", required=True, type=Path, metavar="FILE",
                        help="Path to the existing SQLite database")
    refresh.add_argument("--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
                        help=f"How many of the stalest videos to refresh (default: {DEFAULT_LIMIT})")
    return parser


def _run_refresh(args) -> None:
    if not args.db.exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        sys.exit(1)
    with Datastore(args.db) as ds:
        summary = run_refresh(ds, limit=args.limit, delay=args.delay)
    print(summary.line())


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "refresh":
        _run_refresh(args)
        return
    # No subcommand means ingest, so the invocation the README documents —
    # `airchivist-crawler -i bookmarks.json -o airchivist.db` — keeps working.
    _run_ingest(args)
```

`_add_common_args(p)` adds `--delay`, `--log-level`, and `--api-key`; `_add_ingest_args(p)` adds `-i/--input`, `-o/--output`, `--limit`, `--force-refresh`, `--backfill-channels`. Move the existing `add_argument` calls into these two helpers verbatim, except that `-i` and `-o` become `required=False` on the top-level parser and `_run_ingest` exits 2 with `Error: -i/--input and -o/--output are required for ingest` when either is missing.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/crawler/test_cli.py -v --no-cov`
Expected: all PASS, including the file's pre-existing CLI tests.

- [ ] **Step 5: Verify both invocations by hand**

```bash
airchivist-crawler --help
airchivist-crawler refresh --help
```

Expected: the top-level help lists `ingest` and `refresh` as commands and still documents `-i`/`-o`; the refresh help shows `--db`, `--limit`, `--delay` and does **not** mention `-i`.

- [ ] **Step 6: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **689 passed**, warnings summary empty.

- [ ] **Step 7: Document and commit**

Update the crawler usage section of `README.md` to show both forms, stating that the bare `-i/-o` form is unchanged. Document the subcommand structure and the compatibility shim in `plan-crawler.md`, including why `refresh --db` differs from `ingest -o` (ingest has an input and an output; refresh has one database it both reads and writes). Add a `CHANGELOG.md` entry.

```bash
git add -u && git commit -m "feat: add the refresh subcommand to airchivist-crawler

A missing subcommand dispatches to ingest, so the documented
`airchivist-crawler -i ... -o ...` form keeps working verbatim."
```

---

## Task 6: launchd scheduling

**Files:**
- Create: `scripts/com.airchivist.refresh.plist`
- Create: `tests/scripts/test_refresh_plist.py`
- Modify: `README.md`, `docs/feature-sheet.html`

**Interfaces:**
- Consumes: the `airchivist-crawler refresh` CLI from Task 5.
- Produces: nothing other tasks call.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_refresh_plist.py`:

```python
import plistlib
from pathlib import Path

import pytest

PLIST = Path(__file__).resolve().parents[2] / "scripts" / "com.airchivist.refresh.plist"


@pytest.fixture
def plist():
    with PLIST.open("rb") as f:
        return plistlib.load(f)


class TestRefreshPlist:
    def test_is_valid_plist_xml(self, plist):
        """A malformed plist fails at `launchctl load` with an unhelpful message, so
        parse it here where the error is readable."""
        assert plist["Label"] == "com.airchivist.refresh"

    def test_runs_the_refresh_subcommand(self, plist):
        args = plist["ProgramArguments"]
        assert "refresh" in args
        assert "--db" in args

    def test_runs_daily_at_3am(self, plist):
        assert plist["StartCalendarInterval"] == {"Hour": 3, "Minute": 0}

    def test_does_not_run_at_load(self, plist):
        """Loading the job must not immediately start a multi-minute run."""
        assert plist["RunAtLoad"] is False

    def test_captures_both_streams_to_a_log(self, plist):
        assert plist["StandardOutPath"].endswith("airchivist-refresh.log")
        assert plist["StandardErrorPath"].endswith("airchivist-refresh.log")

    def test_uses_absolute_paths_only(self, plist):
        """launchd does no shell expansion and does not inherit an interactive PATH,
        so a bare `airchivist-crawler` or a `~` would silently never run."""
        for arg in plist["ProgramArguments"]:
            if arg.startswith("-") or arg == "refresh":
                continue
            assert arg.startswith("/"), f"{arg!r} is not an absolute path"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/scripts/test_refresh_plist.py -v --no-cov`
Expected: FAIL — `FileNotFoundError` for `scripts/com.airchivist.refresh.plist`.

- [ ] **Step 3: Implement**

Create `scripts/com.airchivist.refresh.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!--
  Nightly Airchivist metadata refresh.

  Replace the two /REPLACE/ paths below with absolute paths before loading:
    1. the installed airchivist-crawler (`which airchivist-crawler`)
    2. your database

  Absolute paths are mandatory. launchd performs no shell expansion, so a `~` is a
  literal directory name, and a launchd job does not inherit an interactive PATH, so
  a bare `airchivist-crawler` is never found. Either mistake fails silently.

  Install:  cp scripts/com.airchivist.refresh.plist ~/Library/LaunchAgents/
            launchctl load ~/Library/LaunchAgents/com.airchivist.refresh.plist
-->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.airchivist.refresh</string>

    <key>ProgramArguments</key>
    <array>
        <string>/REPLACE/with/path/to/airchivist-crawler</string>
        <string>refresh</string>
        <string>--db</string>
        <string>/REPLACE/with/path/to/airchivist.db</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>/tmp/airchivist-refresh.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/airchivist-refresh.log</string>
</dict>
</plist>
```

The log path is `/tmp` in the template rather than `~/Library/Logs` because `~` does not expand; the README tells the user to replace it with their own absolute path, and the test only asserts the filename.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/scripts/test_refresh_plist.py -v --no-cov`
Expected: PASS (6 tests).

- [ ] **Step 5: Document**

Add a "Scheduling the refresh" section to `README.md`:

```markdown
## Scheduling the refresh

`airchivist-crawler refresh` re-fetches the 200 least-recently-updated videos, so
running it nightly cycles a 3,000-video library about every two weeks. A `launchd`
template is in `scripts/com.airchivist.refresh.plist`.

1. Find the absolute path to the installed command: `which airchivist-crawler`
2. Edit the copy of the plist, replacing both `/REPLACE/` paths and the log path.
   launchd does no shell expansion — a `~` is a literal directory name, and a
   relative command is never found.
3. Run it by hand once first, so a misconfiguration surfaces where you can see it:
   `airchivist-crawler refresh --db airchivist.db --limit 5`
4. Install and load it:

```bash
cp scripts/com.airchivist.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.airchivist.refresh.plist
```

Check that launchd knows about it with `launchctl list | grep airchivist`, and read
the log to see what a run did — each run ends with one line like
`refreshed 200 of 2958 (196 ok, 3 deleted, 1 private) in 5m12s`.

To stop it: `launchctl unload ~/Library/LaunchAgents/com.airchivist.refresh.plist`.
```

In `docs/feature-sheet.html`, add a bullet to the collection/library area describing that the library keeps itself up to date overnight and marks videos that have disappeared — in plain language, no route names or file paths — and update the stat line counts.

- [ ] **Step 6: Verify the suite and commit**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **695 passed**, warnings summary empty.

Add a `CHANGELOG.md` entry noting that scheduling is opt-in (the plist is a template the user installs, not something the app does on its own) and that `RunAtLoad` is false on purpose.

```bash
git add scripts/com.airchivist.refresh.plist tests/scripts/test_refresh_plist.py && git add -u
git commit -m "feat: add a launchd template for the nightly refresh

Absolute paths are mandatory and both /REPLACE/ markers are checked by a
test — launchd does no shell expansion and does not inherit an
interactive PATH, so either mistake would fail silently at 3am."
```

---

## Task 7: `fetch_status` filter in the DB layer

**Files:**
- Modify: `webapp/db/videos.py` (`_build_where`, `get_all_videos`, `count_videos`)
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_ALLOWED_FETCH_STATUSES` (module-private frozenset) and a `fetch_status: str | None` keyword on `_build_where`, `get_all_videos`, and `count_videos`.

**The trap:** `_build_where`'s base clause list starts `["v.fetch_status = 'ok'", "v.is_hidden = 0"]`. A `fetch_status` filter that simply appends another clause would produce `fetch_status = 'ok' AND fetch_status = 'deleted'` and always return zero rows. The base clause must become conditional.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py`:

```python
class TestFetchStatusFilter:
    def _seed_dead(self, db_conn):
        db_conn.executescript("""
            INSERT INTO videos (video_id, url, title, channel_name, date_added, fetch_status)
            VALUES
              ('dead0000001', 'u', 'Deleted Video', 'C', '2024-01-01', 'deleted'),
              ('priv0000001', 'u', 'Private Video', 'C', '2024-01-02', 'private'),
              ('err00000001', 'u', 'Error Video',   'C', '2024-01-03', 'error');
        """)
        db_conn.commit()

    def test_default_still_shows_only_ok_videos(self, db_conn):
        self._seed_dead(db_conn)
        titles = {r["title"] for r in get_all_videos(db_conn)}
        assert "Deleted Video" not in titles
        assert "Guitar Lesson 1" in titles

    def test_filtering_to_deleted_overrides_the_base_ok_clause(self, db_conn):
        # The clause the base WHERE hardcodes is exactly the one this must replace.
        self._seed_dead(db_conn)
        titles = {r["title"] for r in get_all_videos(db_conn, fetch_status="deleted")}
        assert titles == {"Deleted Video"}

    def test_filtering_to_private(self, db_conn):
        self._seed_dead(db_conn)
        titles = {r["title"] for r in get_all_videos(db_conn, fetch_status="private")}
        assert titles == {"Private Video"}

    def test_filtering_to_ok_matches_the_default(self, db_conn):
        """Review Focus #4: an explicit ?fetch_status=ok must not double-add the
        clause or return nothing."""
        self._seed_dead(db_conn)
        explicit = {r["video_id"] for r in get_all_videos(db_conn, fetch_status="ok")}
        default = {r["video_id"] for r in get_all_videos(db_conn)}
        assert explicit == default
        assert explicit

    def test_dead_filter_matches_every_non_ok_status(self, db_conn):
        self._seed_dead(db_conn)
        titles = {r["title"] for r in get_all_videos(db_conn, fetch_status="dead")}
        assert titles == {"Deleted Video", "Private Video", "Error Video"}

    def test_an_unrecognized_status_raises_value_error(self, db_conn):
        with pytest.raises(ValueError, match="fetch_status"):
            get_all_videos(db_conn, fetch_status="bogus")

    def test_count_videos_honors_the_filter(self, db_conn):
        self._seed_dead(db_conn)
        assert count_videos(db_conn, fetch_status="deleted") == 1
        assert count_videos(db_conn, fetch_status="dead") == 3

    def test_the_filter_still_excludes_hidden_videos(self, db_conn):
        """Archived is a separate axis: the Archived page owns hidden videos."""
        self._seed_dead(db_conn)
        db_conn.execute("UPDATE videos SET is_hidden = 1 WHERE video_id = 'dead0000001'")
        db_conn.commit()
        assert count_videos(db_conn, fetch_status="deleted") == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py -k FetchStatusFilter -v --no-cov`
Expected: FAIL — `TypeError: get_all_videos() got an unexpected keyword argument 'fetch_status'`.

- [ ] **Step 3: Implement**

In `webapp/db/videos.py`, beside `_DURATION_BUCKETS`:

```python
# Values the ?fetch_status= filter accepts. "dead" is the useful one — "show me
# everything that is no longer watchable" — and the three concrete statuses let the
# user narrow further. Keep in sync with the <select> in webapp/templates/index.html
# and with FetchStatusFilter in webapp/video_filters.py.
_FETCH_STATUS_CLAUSES = {
    "ok": "v.fetch_status = 'ok'",
    "dead": "v.fetch_status != 'ok'",
    "deleted": "v.fetch_status = 'deleted'",
    "private": "v.fetch_status = 'private'",
    "error": "v.fetch_status = 'error'",
}
```

In `_build_where`, add the parameter and make the base clause conditional:

```python
def _build_where(*, channel=None, tag=None, search=None, favorites_only=False,
                 unwatched_only=False, duration=None, added_within=None,
                 fetch_status=None):
    params = []
    # The status clause is REPLACED, not appended to: the default "only watchable
    # videos" view is itself a fetch_status filter, so appending would produce
    # `fetch_status = 'ok' AND fetch_status = 'deleted'` and always match nothing.
    if fetch_status is not None:
        if fetch_status not in _FETCH_STATUS_CLAUSES:
            raise ValueError(f"Invalid fetch_status: {fetch_status!r}")
        status_clause = _FETCH_STATUS_CLAUSES[fetch_status]
    else:
        status_clause = _FETCH_STATUS_CLAUSES["ok"]
    clauses = [status_clause, "v.is_hidden = 0"]
```

Add `fetch_status: str | None = None` to both `get_all_videos` and `count_videos`, and pass it through in each of their `_build_where(...)` calls.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py -v --no-cov`
Expected: all PASS — the pre-existing `TestGetAllVideos` and `TestCountVideos` classes are the proof the default view is unchanged.

- [ ] **Step 5: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **703 passed**, warnings summary empty.

- [ ] **Step 6: Document and commit**

In `plan-webapp.md`, document the filter beside `duration`/`added_within`, and state explicitly that the status clause replaces rather than appends to the base clause, with the always-zero-rows reason. Add a `CHANGELOG.md` entry.

```bash
git add -u && git commit -m "feat: add a fetch_status filter to the video queries

The base WHERE hardcodes fetch_status = 'ok', so the filter replaces that
clause rather than appending — appending would produce a contradiction
that always matches nothing."
```

---

## Task 8: Wire the filter through `VideoListFilters` and the route

**Files:**
- Modify: `webapp/video_filters.py`
- Modify: `webapp/routes.py` (`index`)
- Test: `tests/webapp/test_video_filters.py`, `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: the `fetch_status` keyword on `count_videos`/`get_all_videos` from Task 7.
- Produces: `FetchStatusFilter` (StrEnum) and `VideoListFilters.fetch_status: str | None`, included in `db_kwargs()` and counted by `active_count`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_video_filters.py`:

```python
class TestFetchStatusFilterField:
    def test_absent_by_default(self):
        assert VideoListFilters.from_args({}).fetch_status is None

    def test_empty_string_normalizes_to_none(self):
        assert VideoListFilters.from_args({"fetch_status": ""}).fetch_status is None

    def test_parsed_from_the_query_string(self):
        assert VideoListFilters.from_args({"fetch_status": "dead"}).fetch_status == "dead"

    def test_counts_toward_the_active_filter_badge(self):
        assert VideoListFilters.from_args({"fetch_status": "dead"}).active_count == 1

    def test_reaches_the_db_layer(self):
        kwargs = VideoListFilters.from_args({"fetch_status": "dead"}).db_kwargs()
        assert kwargs["fetch_status"] == "dead"
        assert set(kwargs) == {
            "channel", "tag", "search", "favorites_only",
            "unwatched_only", "duration", "added_within", "fetch_status",
        }
```

Add to `tests/webapp/test_routes.py`:

```python
class TestFetchStatusRouteFilter:
    def _seed_dead(self, client):
        with closing(sqlite3.connect(client.application.config["DATABASE"])) as conn:
            conn.executescript("""
                INSERT INTO videos (video_id, url, title, channel_name, date_added, fetch_status)
                VALUES ('dead0000001', 'u', 'Deleted Video', 'C', '2024-01-01', 'deleted');
            """)
            conn.commit()

    def test_dead_filter_lists_videos_the_default_view_hides(self, client):
        self._seed_dead(client)
        body = client.get("/?fetch_status=dead", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "Deleted Video" in body
        assert "Guitar Lesson 1" not in body

    def test_default_view_still_hides_them(self, client):
        self._seed_dead(client)
        body = client.get("/", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "Deleted Video" not in body

    def test_an_unrecognized_status_is_a_400(self, client):
        assert client.get("/?fetch_status=bogus").status_code == 400

    def test_the_select_reflects_the_current_choice(self, client):
        body = client.get("/?fetch_status=dead").get_data(as_text=True)
        option_line = next(l for l in body.splitlines() if 'value="dead"' in l)
        assert "selected" in option_line
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_video_filters.py -k FetchStatus tests/webapp/test_routes.py -k FetchStatusRoute -v --no-cov`
Expected: FAIL — `AttributeError: 'VideoListFilters' object has no attribute 'fetch_status'`.

- [ ] **Step 3: Implement**

In `webapp/video_filters.py`, beside `WatchStatus` and `GroupBy`:

```python
class FetchStatusFilter(StrEnum):
    """Values of the toolbar's availability select. Empty string = only watchable.

    Keep in sync with _FETCH_STATUS_CLAUSES in webapp/db/videos.py.
    """

    DEAD = "dead"
    DELETED = "deleted"
    PRIVATE = "private"
    ERROR = "error"
    OK = "ok"
```

Add the field to `VideoListFilters` after `added_within`:

```python
    fetch_status: str | None = None
```

In `from_args`, add `fetch_status=args.get("fetch_status") or None,`. In `active_count`'s tuple, add `self.fetch_status is not None,`. In `db_kwargs`, add `"fetch_status": self.fetch_status,`.

In `webapp/routes.py`'s `index`, add `current_fetch_status=filters.fetch_status,` to `template_vars`. No other route change is needed — `db_kwargs()` already flows into both DB calls, and the existing `except ValueError: abort(400)` turns an unrecognized value into a 400.

- [ ] **Step 4: Add the `<select>` to the toolbar**

In `webapp/templates/index.html`, beside the existing `duration` and `watch_status` selects, inside the same auto-submitting filter form:

Place it immediately after the `added_within` select. The surrounding selects carry
**no class and no HTMX attributes of their own** — the enclosing form owns the
auto-submit — so this one must not invent either:

```html
      {# Keep options in sync with _FETCH_STATUS_CLAUSES in webapp/db/videos.py #}
      <select name="fetch_status">
        <option value="" {% if not current_fetch_status %}selected{% endif %}>Available</option>
        <option value="dead"    {% if current_fetch_status == 'dead'    %}selected{% endif %}>Unavailable (any)</option>
        <option value="deleted" {% if current_fetch_status == 'deleted' %}selected{% endif %}>Deleted</option>
        <option value="private" {% if current_fetch_status == 'private' %}selected{% endif %}>Private</option>
        <option value="error"   {% if current_fetch_status == 'error'   %}selected{% endif %}>Fetch error</option>
      </select>
```

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_video_filters.py tests/webapp/test_routes.py -v --no-cov`
Expected: all PASS.

- [ ] **Step 6: Verify the suite**

Run: `ruff check . && mypy && python -m pytest -q`
Expected: **712 passed**, warnings summary empty.

- [ ] **Step 7: Document and commit**

Document the new filter and its select in `plan-webapp.md` alongside the other quick filters, noting that it contributes 1 to `active_filter_count`. Add a `CHANGELOG.md` entry.

```bash
git add -u && git commit -m "feat: expose the fetch_status filter on the main list"
```

---

## Task 9: The status badge

**Files:**
- Modify: `webapp/templates/_video_card.html`
- Modify: `webapp/static/style.css`
- Modify: `docs/feature-sheet.html`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: the `fetch_status` filter from Task 8 (the badge is only visible on cards the filter surfaces).
- Produces: nothing.

- [ ] **Step 1: Write the failing tests**

```python
class TestUnavailableBadge:
    def _seed(self, client, status, video_id="dead0000001"):
        with closing(sqlite3.connect(client.application.config["DATABASE"])) as conn:
            conn.execute(
                "INSERT INTO videos (video_id, url, title, channel_name, date_added, fetch_status) "
                "VALUES (?, 'u', 'Dead Video', 'C', '2024-01-01', ?)",
                (video_id, status),
            )
            conn.commit()

    @pytest.mark.parametrize("status,label", [
        ("deleted", "Deleted"),
        ("private", "Private"),
        ("error", "Unavailable"),
    ])
    def test_shows_the_right_label_per_status(self, client, status, label):
        self._seed(client, status)
        body = client.get(f"/?fetch_status={status}", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "status-badge" in body
        assert label in body

    def test_an_ok_video_has_no_badge(self, client):
        body = client.get("/", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "status-badge" not in body

    def test_the_badge_carries_the_status_as_a_class(self, client):
        self._seed(client, "deleted")
        body = client.get("/?fetch_status=deleted", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "status-badge--deleted" in body
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py -k UnavailableBadge -v --no-cov`
Expected: FAIL — `assert "status-badge" in body` finds nothing.

- [ ] **Step 3: Implement the template**

In `webapp/templates/_video_card.html`, inside the thumbnail anchor beside the existing `duration-overlay` and `queue-position-badge` spans:

```html
      {% if video.fetch_status and video.fetch_status != 'ok' %}
      <span class="status-badge status-badge--{{ video.fetch_status }}">
        {% if video.fetch_status == 'deleted' %}Deleted
        {% elif video.fetch_status == 'private' %}Private
        {% else %}Unavailable{% endif %}
      </span>
      {% endif %}
```

- [ ] **Step 4: Implement the CSS**

In `webapp/static/style.css`, next to `.queue-position-badge`:

```css
/* Availability badge on a video whose YouTube source is gone. The three
   background/foreground pairs are literal rather than tokens on purpose: a
   "deleted" badge must read as a warning in both themes, so these are
   intentionally theme-invariant — see the design-token rule in CLAUDE.md. */
.status-badge {
  position: absolute;
  bottom: 4px;
  left: 4px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  padding: 1px 5px;
  border-radius: 3px;
  pointer-events: none;
}
.status-badge--deleted { background: #7f1d1d; color: #fff; }
.status-badge--private { background: #78350f; color: #fff; }
.status-badge--error   { background: #374151; color: #fff; }
```

Bottom-left is free: `.duration-overlay` is `bottom: 4px; right: 4px` and
`.queue-position-badge` is `top: 4px; left: 4px` (both verified in
`webapp/static/style.css` while writing this plan), so the three never overlap.

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py -k UnavailableBadge -v --no-cov`
Expected: PASS (5 tests).

- [ ] **Step 6: Confirm it renders, in-process**

Per the `feedback-sandbox-localhost-port-unreliable` memory, do **not** verify with `curl` against a locally started server here — use the test client:

`create_app` calls `init_webapp_tables`, so pointing it at `airchivist.db` would
**write** to it. Work on a copy:

```bash
python3 -c "
import sqlite3, sys; sys.path.insert(0, '.')
src, dst = sqlite3.connect('airchivist.db'), sqlite3.connect('/tmp/badge-check.db')
with dst: src.backup(dst)
dst.close(); src.close()
from webapp.app import create_app
body = create_app('/tmp/badge-check.db').test_client().get('/?fetch_status=dead').get_data(as_text=True)
print('badges rendered:', body.count('status-badge'))
"
rm -f /tmp/badge-check.db /tmp/badge-check.db-wal /tmp/badge-check.db-shm
```

Expected: a non-zero count — the library already holds roughly 53 deleted, 37 private
and 8 error videos.

- [ ] **Step 7: Verify everything and commit**

Run: `ruff check . && mypy && python -m pytest -q && npm test`
Expected: **717 passed** and **123 passed**, warnings summary empty.

In `docs/feature-sheet.html`, add the badge to the browsing/library area in plain language and update the stat line counts. In `plan-webapp.md`, document the badge, its three labels, and why its colors are literal rather than tokens. Add a `CHANGELOG.md` entry. In `TODO.md`, strike through all three items this plan closes.

```bash
git add -u && git commit -m "feat: badge videos whose YouTube source is gone

Closes the loop: the refresh discovers a video is deleted or private, the
filter lists them, and the badge makes it visible on the card."
```

Say explicitly in the response that this change needs a **server restart** (Python + templates) and a **browser hard-reload** (static CSS).

---

## Self-Review Notes

- **Spec coverage:** Intent → T2/T4/T9. Measured starting state → used in T3's ordering and T9's Step 6 verification. What already exists → T3 (`last_fetched_at`), T4 (`_classify_error` byproduct). The hazard → **T2**. Design §1 Selection → T3. §2 Write path → T2. §3 CLI → T5. §4 Scheduling → T6. §5 Surfacing → T7 (filter), T8 (wiring), T9 (badge). §6 WAL → T1. Testing §1–8 → T2 (1, 2, 3), T3 (4), T5 (5), T4 (6), T7 (7), T9 (8). Out-of-scope items are not implemented. No gaps.
- **Type consistency:** `refresh_video(metadata)` defined in T2, consumed in T4. `get_stale_video_ids(limit)` / `count_videos()` defined in T3, consumed in T4. `run_refresh(ds, limit, delay, fetch=)` and `RefreshSummary.line()` defined in T4, consumed in T5. `DEFAULT_LIMIT` defined in T4, consumed in T5. The `fetch_status` keyword defined in T7, consumed in T8. `FetchStatusFilter`'s members match `_FETCH_STATUS_CLAUSES`' keys exactly. Note `Datastore.count_videos()` (T3) and `webapp.db.count_videos(conn, ...)` (T7) are different functions in different layers that share a name — that mirrors the existing `get_video_by_id` duplication the spec leaves out of scope.
- **Test-count chain:** 652 → 655 (T1) → 664 (T2) → 672 (T3) → 682 (T4) → 689 (T5) → 695 (T6) → 703 (T7) → 712 (T8) → 717 (T9). (Corrected 2026-09-26: Task 2 adds 9 tests, not the 10 originally counted.) Extension stays 123 throughout.
- **Review Focus placement:** #1 → T3 Step 1 (`test_a_non_positive_limit_selects_nothing`). #2 → T4 (`test_an_unexpected_exception_does_not_abort_the_run`). #3 → T2 (`test_a_video_coming_back_to_life_clears_the_stale_error`). #4 → T7 (`test_filtering_to_ok_matches_the_default`). #5 → T4 (`test_an_empty_library_is_a_clean_zero_run`).
