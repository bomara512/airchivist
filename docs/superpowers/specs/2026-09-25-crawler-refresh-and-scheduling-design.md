# Crawler Metadata Refresh and Scheduling — Design

**Date:** 2026-09-25
**Status:** Approved for planning
**Closes:** TODO "Auto-schedule the crawler (launchd / cron)", "Way to refresh
YouTube metadata (e.g. view count) for existing videos", and "Detect and flag dead
videos (deleted/private) with a badge rather than silently hiding them"

## Intent

The library is frozen at ingest time. Every video's title, channel name, view count,
and thumbnail is whatever yt-dlp saw the day it was first fetched, and there is no
code path that updates any of it. The only way to learn that a video has been deleted
is to click it and land on YouTube's error page.

This adds a refresh pass over existing rows and a schedule to run it unattended, then
surfaces the one thing a refresh discovers that the user cannot see today: that a
video is gone.

**Success looks like:** view counts and titles track reality without anyone
remembering to do anything, and a video that dies is visibly marked as dead in the
library rather than discovered by accident.

### Measured starting state (2026-09-25)

These numbers drove the design and are worth re-checking if it is revisited:

| Fact | Value |
|---|---|
| Videos in the library | 2,958 |
| `fetch_status = 'ok'` | 2,860 |
| `fetch_status = 'deleted'` | 53 |
| `fetch_status = 'private'` | 37 |
| `fetch_status = 'error'` | 8 |
| `last_fetched_at IS NULL` | 117 |
| Oldest `last_fetched_at` | 2026-05-28 |
| Newest `last_fetched_at` | 2026-08-05 |
| `fetch_metadata` delay between calls | 1.5 s (default) |

Two consequences: the freshest metadata in the library is about seven weeks old, and
98 videos are **already** flagged non-`ok` — so the badge has real data to display on
the day it ships, without waiting for a refresh run.

## What already exists

Worth stating explicitly, because it means this needs no schema migration:

- **`videos.last_fetched_at`** is already a column, and `Datastore.upsert_video`
  already writes it on every call. It is the staleness cursor.
- **`crawler.metadata_fetcher._classify_error`** already maps yt-dlp's failure text to
  `FetchStatus.PRIVATE`, `FetchStatus.DELETED`, or `FetchStatus.ERROR`. The dead-video
  signal is a byproduct of any refresh; nothing new is needed to detect it.
- **`FetchStatus`** is a `StrEnum` in `crawler/models.py` with exactly these members.

## The hazard this design exists to avoid

`fetch_metadata`'s failure path returns:

```python
return VideoMetadata(
    video_id=video_id,
    url=url,
    fetch_status=status,      # private | deleted | error
    fetch_error=str(exc),
)
```

Every other field defaults to `None`. `Datastore.upsert_video`'s
`ON CONFLICT(video_id) DO UPDATE` then assigns `title`, `description`,
`channel_name`, `channel_id`, `yt_view_count`, `duration_seconds`, `thumbnail_url`,
and `date_published` from `excluded` — that is, to `NULL`.

**So refreshing a video that has since been deleted erases the record of what it
was.** A nightly job would quietly hollow out precisely the videos the user most
wants remembered, and it would do so silently, one row at a time, over weeks.

This hazard is latent in the code today: `--force-refresh` over a bookmarks file
containing a since-deleted video does the same thing. It has simply never been
triggered, because nobody re-runs ingest over old bookmarks. The fix below applies to
both paths.

## Design

### 1. Selection and runtime

```sql
SELECT video_id FROM videos ORDER BY last_fetched_at ASC LIMIT ?
```

Oldest-refreshed first, capped per run. `--limit` defaults to **200**, which is about
5 minutes at the existing 1.5 s delay and cycles the whole library every ~15 days.

- SQLite sorts `NULL` first, so the 117 never-fetched videos are picked up before
  anything else. That is the correct priority and it costs nothing to get.
- **Bounded runtime is the point.** A staleness-threshold policy ("refresh anything
  older than 14 days") was considered and rejected: its first run touches all 2,958
  videos (~75 minutes) and its runtime grows with the library. One knob that always
  produces the same run length is easier to schedule and easier to trust.
- **Already-dead videos are refreshed on the same rotation, with no backoff.** They
  are 98 of 2,958 rows — about 3% of the budget — and a private video can become
  public again. Learning that is worth more than the seconds saved. No
  special-casing, no extra state to reason about.
- **Hidden videos are included.** They are still in the library, and an archived
  video that gets deleted upstream is exactly the case where preserving the
  last-known title matters most.

### 2. The write path

A new method, deliberately separate from `upsert_video`:

```python
def refresh_video(self, metadata: VideoMetadata) -> None
```

Two behaviors, chosen by `metadata.fetch_status`:

- **`ok`** — update `url`, `title`, `description`, `channel_name`, `channel_id`,
  `yt_view_count`, `duration_seconds`, `thumbnail_url`, `date_published`,
  `fetch_status`, `fetch_error` (to `NULL`), `last_fetched_at`. Also re-apply yt-tags
  and aliases, as `upsert_video` does.
- **anything else** — update **only** `fetch_status`, `fetch_error`, and
  `last_fetched_at`. Every descriptive column keeps its last successful value.

Never written by either branch, on any path: `date_added`, `personal_view_count`,
`date_last_viewed`, `is_watched`, `is_favorite`, `is_hidden`, `date_hidden`. These are
the user's own data; the crawler has no business touching them.

`refresh_video` takes no `Bookmark`. `upsert_video` requires one for `date_added`,
which is meaningless on a row that already exists — that mismatch is the main reason
these are two methods rather than one with a flag.

**`upsert_video` gets the same preserve-on-failure fix**, so `--force-refresh` stops
carrying the hazard. This is a behavior change to an existing code path and should be
called out as such in the changelog.

### 3. CLI

```
airchivist-crawler refresh --db airchivist.db [--limit 200] [--delay 1.5]
```

Implemented with `argparse` subparsers, where **a missing subcommand dispatches to
today's ingest behavior**, so the documented invocation keeps working verbatim:

```
airchivist-crawler -i bookmarks.json -o airchivist.db     # unchanged
```

`ingest` also becomes available as an explicit subcommand name. The compatibility
shim is a deliberate cost: it means one branch in argument handling, in exchange for
not breaking a command the README documents and the user has muscle memory for.

`refresh` takes `--db` where `ingest` takes `-o/--output`. The asymmetry is
intentional and should not be "fixed": ingest has an input and an output, while
refresh has one database it both reads and writes, and calling that an output would
misdescribe it.

Each run ends with one scannable summary line on stdout:

```
refreshed 200 of 2958 (196 ok, 3 deleted, 1 private, 0 error) in 5m12s
```

### 4. Scheduling

A `launchd` plist template at `scripts/com.airchivist.refresh.plist`:

- `StartCalendarInterval` at 03:00 daily.
- `StandardOutPath` and `StandardErrorPath` to
  `~/Library/Logs/airchivist-refresh.log`, so the summary line above is the log.
- `RunAtLoad` false — loading it should not immediately start a 5-minute job.

The template carries placeholders for the absolute paths to the installed
`airchivist-crawler` and the database, since launchd has no shell expansion and
`launchd` jobs do not inherit an interactive `PATH`. README gets a section covering
`launchctl load`/`unload`, how to confirm it ran, and how to run the job by hand once
before trusting it.

**launchd over cron** because it is the supported mechanism on macOS, it survives
reboots, and it will run a missed job when the machine wakes rather than silently
skipping it.

### 5. Surfacing dead videos

- A badge on any video card whose `fetch_status` is not `ok`, reading `Deleted`,
  `Private`, or `Unavailable`. It reuses the existing badge pattern and the
  `webapp/static/style.css` design tokens; per CLAUDE.md, a status badge's own
  background/foreground pair may stay literal if it is intentionally
  theme-invariant, with a comment saying so.
- A `?fetch_status=` filter on the main list, validated against an allow-list in the
  same style as `duration` and `added_within` (an unrecognized value raises
  `ValueError` from the DB layer and becomes a 400). This is what turns "90 videos are
  dead" into a list the user can act on.
- The main list's base `WHERE` currently includes `v.fetch_status = 'ok'`, so dead
  videos are invisible there today. **The filter must be able to override that base
  clause**, or it will always return zero rows — this is the one place the
  implementation is most likely to go wrong, and it needs a test that would fail if
  the clause were left unconditional.

### 6. Concurrency: WAL

`airchivist.db` is in `journal_mode=delete`, where a writer holds an exclusive lock.
A refresh commits roughly every 1.5 s for the length of a run, so browsing during a
run can block for up to the 5 s busy timeout and then fail with "database is locked".

**Switch to `journal_mode=WAL`**, applied in **both** `init_webapp_tables` and
`Datastore`'s connection setup. The setting is persistent, so whichever runs first
does the work and the other is a no-op — but applying it in only one of them would
leave a database unconverted for anyone who has run the crawler and never started the
webapp, which is the exact case a scheduled refresh creates. Readers then never block
writers.

Accepted costs, which the README must state:

- SQLite creates `airchivist.db-wal` and `airchivist.db-shm` next to the database. A
  file-copy backup should include them, or run `PRAGMA wal_checkpoint(TRUNCATE)`
  first.
- The existing `.bak` copy habit needs that note, or a backup taken mid-write could
  miss committed data still sitting in the WAL.

## Testing

Per CLAUDE.md, new DB functions and routes get tests in the same change. The ones that
carry the design's weight:

1. **`refresh_video` preserves metadata on a failed fetch.** Seed an `ok` video with a
   title and channel, refresh it into `deleted`, assert `fetch_status` changed *and*
   the title, channel, thumbnail, view count, and duration are untouched. This is the
   single most important test in the change.
2. **`refresh_video` never touches user columns** — `personal_view_count`,
   `date_last_viewed`, `is_watched`, `is_favorite`, `is_hidden`, `date_added` survive
   both an `ok` and a failed refresh.
3. **`upsert_video` gets the same preserve-on-failure coverage**, since its behavior
   changes too.
4. **Selection order puts `NULL last_fetched_at` first**, then ascending, and honors
   `--limit`.
5. **CLI dispatch both ways** — a bare `-i/-o` invocation still ingests; `refresh`
   routes to the refresh path and does not require `-i`.
6. **The summary counts** match the statuses actually written.
7. **The `fetch_status` filter overrides the base `ok` clause** and returns dead
   videos; an unrecognized value is a 400.
8. **The badge renders** for each non-`ok` status and not at all for `ok`.

## Out of scope

- **Refreshing channel metadata.** `--backfill-channels` already exists for stub
  channel records and is a different selection problem. Worth its own pass.
- **Retrying `error` videos more aggressively than the rotation.** `error` means
  yt-dlp failed for a reason that was not classified as private or deleted — often
  transient. Eight rows do not justify a policy; the rotation will retry them.
- **Notifying the user when a video dies.** The badge is a passive signal. An active
  notification (a count on the header, an email) is a separate feature and a separate
  decision about how noisy this should be.
- **A migrations table.** WAL is set with a persistent PRAGMA and needs no version
  tracking. The broader migrations item in `TODO.md` stays deferred.
