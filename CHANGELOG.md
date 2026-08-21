# Airchivist Changelog

Decisions are listed chronologically. Dates before 2026-05-28 are approximate — the project was built across multiple sessions without recorded timestamps.

---

## 2026-08-20

### chore: reorder filter panel — Favorites checkbox now follows Unwatched only

Pure markup reorder in `index.html`'s filter panel, no behavior change.

### feat: Rediscover shelf collapses/expands based on active filters

The shelf now auto-collapses whenever any filter (channel, tag, sort, group,
favorites, unwatched, duration, added-within) is active, and auto-expands
when cleared. Reuses the existing `active_filter_count` expression (now
computed once in `routes.py:index()` instead of duplicated in Jinja) so this
matches the "Filters N" badge exactly. Since the shelf lives outside
`#video-container`, a hidden OOB marker (`#rediscover-filter-state`) rides
along on every filter-triggered HTMX swap and an inline script syncs the
shelf's `.collapsed` class from it. This also required moving `#video-container`
itself from `index.html` into `_video_container.html`, so the marker is a
sibling rather than a descendant of the element HTMX replaces — nesting it
inside caused the OOB-updated marker to be immediately wiped out by the
parent's own innerHTML swap. Clicking the shelf header still works as a
temporary peek, but the next filter change overrides it back to the
filter-driven state — as a trade-off, this drops the old `localStorage`
persistence, so there's no longer a way to keep the shelf permanently
collapsed while unfiltered, only the transient peek.

### fix: demo seed data — published dates, real channel avatars, swap freeCodeCamp for Spring I/O

Three follow-ups after trying the demo end to end. `date_published` was never passed to
`add_video()`, so every demo video showed "Published unknown" — fixed by fetching each
video's real upload date via `yt-dlp` and wiring it through. Channel avatars: an initial
attempt to add real `yt3.googleusercontent.com` avatar URLs was reverted after browser
testing showed 8 of 12 failing to load — that "finding" turned out to be a test artifact
(claude-in-chrome automation tabs report `document.hidden=true`, and Chrome never fires
`loading="lazy"` image requests in a hidden tab, independent of image count or the CDN's
health); confirmed via direct `new Image()` loads bypassing the lazy-load gate, and by the
real app's own `/channels` page loading the same avatars fine, before re-applying real
avatars for all 12 channels. Also swapped the freeCodeCamp.org channel for Spring I/O
(real 2026 conference talks) at the user's request — the "Coding & Tech" tag group's
canonical tags changed from generic language names (`python`, `machine-learning`,
`javascript`, `web-dev`) to Spring-specific ones (`keynote`, `spring-ai`,
`spring-security`, `spring-boot`) to stay authentic to the new content, and the `sql`
unclassified tag became `queries`. Trade-off: swapping a channel now means touching six
different lists in `seed_demo_db.py` (content, tags, favorites, watch-later, hidden,
watched) since a video's role is spread across all of them by ID — a future swap could
warrant a lookup-by-role helper if this happens often enough to be worth the abstraction.

## 2026-08-19

### fix: address final-review findings on the demo seed data branch

Bundled fix pass addressing all findings from the whole-branch review of the demo seed data
work: `ANCHOR` now defaults to `datetime.now(timezone.utc)` instead of a fixed date, and the
leading `date_added` offset dropped from 10 to 2 days, so a freshly seeded demo always has at
least one video inside the app's own "added in the last 7 days" filter (previously the
newest video was already outside the window, and it only got worse as time passed);
`date_last_viewed` for watched videos is now derived from each video's own `date_added` plus
a small positive spread instead of from `ANCHOR` independently, so it can no longer predate
`date_added` (a state the real app can never produce); the `sql` and `guitar-maintenance`
unclassified tags each picked up a second video so they clear `get_unclassified_tags()`'s
`min_videos=2` threshold and actually appear in the demo's `/tags` pool; `seed_demo_db.py`
now seeds to a temporary `<output>.tmp` path and only moves it to the real path via
`Path.replace()` on full success, so a crash partway through no longer leaves a broken
`demo.db` that `demo.sh` will never retry; `demo.sh`'s final line uses `exec` for cleaner
Ctrl-C handling; 4 of the 8 `WATCH_LATER_VIDEO_IDS` were swapped for unwatched videos so the
watch-later queue shows a mix instead of every card being watched; `docs/feature-sheet.html`
picked up the demo-mode bullet and stat-line update it was missing; and "~50 real, public
YouTube videos" was corrected to the exact, already-known count of 44 in `README.md`,
`CHANGELOG.md`, and `plan-webapp.md`. Trade-off: `ANCHOR` no longer being fixed means seeded
timestamps are no longer bit-for-bit reproducible across runs (by design — the previous fixed
date is exactly what caused the 7-day filter to go stale over time).

### docs: add demo.sh wrapper and README fast-path section

Added `scripts/seed_demo_db.py` (a hardcoded list of 44 real, public YouTube videos seeded
with a fabricated favorites/watch-later/tags/watch-history layer, no network calls) and
`demo.sh`, a thin wrapper that seeds `demo.db` if it's missing and then runs
`viewtube-web --db demo.db --port 8080`. Added a "Try it with sample data" section to
`README.md` right after Setup, so trying the app no longer requires a real Firefox bookmarks
export first. Trade-off: the video list is a fixed snapshot verified 2026-08-19 — view counts
will drift over time and any individual video could eventually be taken down or go private —
mitigated by structuring the list as easily-swappable data in one place rather than scattering
video IDs/titles as inline literals across the codebase.

While verifying `demo.sh`, found that `demo.db` did **not** actually match the existing
`viewtube*.db*` gitignore pattern (that pattern requires a `viewtube` prefix), so a freshly
seeded demo database could have been committed by accident. Added an explicit `demo.db` line
to `.gitignore` to close the gap.

## 2026-08-16

### docs: add README with setup instructions; fix pip install -e . packaging

Added `README.md` covering setup, bookmark ingestion, running the webapp, the browser
extension, optional AI tag suggestions, and running tests — reflecting the current real
setup path (a real Firefox bookmarks export via the crawler; no demo/seed data exists yet,
see `brainstorm-demo-onboarding.md`). While verifying the install step, found `pip install -e .`
fails on a clean checkout: `pyproject.toml` had no `[build-system]` table, so setuptools fell
back to auto-discovery and refused to guess which of the several top-level directories
(`webapp/`, `crawler/`, `tools/`, `tests/`, `extension/`) were packages. Added an explicit
`[tool.setuptools.packages.find]` include list (`webapp*`, `crawler*`) plus the
`[build-system]` table; verified in an isolated venv that `pip install -e .` now succeeds and
both `viewtube-crawler --help`/`viewtube-web --help` work as installed console scripts.
Trade-off (pro): the README's install step actually works, and anyone following it lands on a
real, tested command rather than a workaround. Trade-off (con): `tools/` (the tag categorizer
script) is intentionally left out of the packages list since it has no `__init__.py` and isn't
exposed as a console script today — restructuring it wasn't in scope for this fix.

## 2026-08-13

### test(webapp): add coverage for is_favourite->is_favorite rename migration

- The final whole-branch review of the US-spelling rename found the migration itself (`webapp/db/schema.py`'s guarded `ALTER TABLE videos RENAME COLUMN is_favourite TO is_favorite`) had zero test coverage — deleting the migration line left all 541 tests passing. Added `TestFavoriteRenameMigration` in `tests/webapp/test_db.py` (3 tests: renames + preserves data, idempotent on second run, fresh DB gets `is_favorite` directly via the ADD COLUMN loop instead), mirroring the existing `TestIsWatchedMigration` pattern. Confirmed with RED/GREEN: temporarily disabling the migration failed 2 of the 3 new tests (the third, covering the ADD-COLUMN path for brand-new databases, correctly still passed); restoring it turned all 3 green.
- Documented the rename's ordering requirement (must run before the generic ADD-COLUMN migration loop) in `plan-webapp.md` alongside the analogous `is_watched` migration note.
- Trade-off (pro): the migration path most likely to silently break existing users' databases (a rename, not an additive column) now has direct regression coverage instead of relying on incidental coverage from feature tests.
- Trade-off (con): none identified — this is pure test/doc addition with no behavior change.

### docs: sweep British spellings from current docs, add US English rule

- Renamed the `is_favourite` DB column, `/videos/<id>/favourite` and `/api/favourite/add` routes, `set_favourite` function, `.favourite-btn`/`.favourite-btn--active` CSS classes, and all related test/template/JS references to US spelling (`is_favorite`, `/favorite`, `set_favorite`, `.favorite-btn`). Swept `colour`/`behaviour`/`organise`/`catalogue`/`grey`/`initialised` out of current-state prose docs (`CLAUDE.md`, `TODO.md`, `plan-*.md`, `docs/feature-sheet.html`). Added a `CLAUDE.md` rule requiring US English going forward in all new code and documentation.
- Trade-off (pro): the codebase and its own docs now consistently use one dialect, matching the user's locale, and a new migration makes the DB rename automatic and lossless for existing installs.
- Trade-off (con): historical `CHANGELOG.md` entries and `docs/superpowers/` specs/plans below this one still contain British spelling by design (a deliberate exception, not an inconsistency) — a reader skimming project history will see both spellings depending on how far back they scroll.

## 2026-08-10

### test(extension): Jest + jsdom test framework for popup.js

- Jest + jsdom test framework completed for the extension (`npm test`), with the first suite covering `popup.js`'s `doAdd` (8 tests from Task 2) and `initWatchLaterToggle` (8 tests from Task 3) — the two functions with non-trivial async/checkbox logic. `popup.js` gained a guarded `module.exports` (no-op in the real browser) to make this possible without a bundler.
- Trade-off (pro): this closes a long-open gap and gives durable automated evidence for exactly the kind of async/checkbox logic that's been shipping in this extension lately, replacing one-off manual/code-reading verification.
- Trade-off (con): `background.js`, `content.js`, and the rest of `popup.js` remain untested — this is a first slice, not full coverage.

## 2026-08-09

### feat(extension): mark video as favorite at capture time

- The extension popup's `not_found` state (when adding a brand-new video) now includes an "Also mark as favorite (★)" checkbox alongside the existing "Also add to Watch Later" checkbox. Checking it at capture time adds the video to ViewTube's favourites list immediately, without requiring a return trip to the web UI.
- Backend: `POST /api/favourite/add` (Task 1) reuses the existing `set_favourite` DB function. No 409/already-case (unlike watch-later) since `is_favourite` is a plain boolean; the route returns `{status: "added"}` on success (200) or `{status: "error", error}` on failure (400 for bad URL, 404 if video isn't in DB yet).
- Frontend: `doAdd` now accepts an `alsoFavorite` parameter (5th arg). The watch-later and favorite follow-up calls run in parallel via `Promise.allSettled` rather than sequentially, since neither depends on the other (both only fire if the main add succeeds). A new `postJson` helper abstracts the fetch/JSON boilerplate for both.
- Success path shows `★ Marked as favorite` if favoriting succeeded, or `✗ Favorite failed` if it failed (gated by the checkbox). Partial-failure path shows the same lines when applicable.
- Trade-off (pro): a standout video can be starred the instant it's captured, with no return trip to the web UI. Trade-off (con): favoriting is capture-time only for now — toggling favorite status on an already-added video is a separate deferred TODO item (tracked separately, same as watch-later's own history).

## 2026-08-08

### feat(extension): toggle watch-later membership at any time from the popup

- The extension popup's `exists` state (when a video is already in ViewTube) now renders an "Add to Watch Later" checkbox that reflects current queue membership and lets you toggle it without visiting the web UI. Closes the gap where toggling watch-later required the `/watch-later` page.
- Markup: checkbox starts disabled/unchecked. On render, `initWatchLaterToggle` fetches `POST /api/watch-later/status` to get `in_queue` state, sets the checkbox, and enables it.
- Interaction: toggling the checkbox calls `/api/watch-later/add` (if checking) or `/api/watch-later/remove` (if unchecking), disables the checkbox during the request, and reverts + shows an inline error if the request fails.
- Status-success semantics: `/add` treats both `added` and `already_in_queue` (409) as success; `/remove` treats only `removed` (200) as success (404 "Not in queue" reverts the checkbox and shows the error).
- Trade-off (con): every popup open now makes a live status fetch (small extra round trip vs. the `not_found`-state checkbox, which reads at add-time only). Trade-off (pro): the checked state is always current with the backend.

## 2026-08-07

### fix(webapp): rediscover shelf cards now reflect watched state

- `get_current_rediscover_shelf`'s per-video SELECT was missing `v.is_watched`, so shelf cards always rendered as unwatched regardless of actual state (the `watched-btn--active` class never applied on the shelf). Added `v.is_watched` to the query.

### feat(webapp): marking a shelf video watched drops it from the rediscover queue

- In the `.watched-btn` handler, marking a video watched *from a rediscover shelf card* now also removes it from the current shelf (POST `/videos/<id>/rediscover-shelf/remove` + fade), since marking watched is a strong "already rediscovered" signal.
- Uses the shelf-remove route (no `personal_view_count` change), not `mark-watched`, to preserve the watched toggle's contract that marking watched never bumps the open-count. Frontend-only — the route and DB function already existed. Only fires when marking watched (not un-marking) and only on the shelf.

### fix(webapp): watched button reveals on hover, not always

- Dropped `opacity: 1 !important` from `.watched-btn--active`; the active state now only tints the button green. The button is hidden by default and revealed on card hover via the existing `.thumb-wrap:hover` rule — matching the watch-later button.
- Why: unlike favourites (rare), nearly every video is `is_watched` after the backfill/opens, so the favourite-style "always show when active" made the ✓ appear on essentially every card. Trade-off: you can no longer tell watched-vs-unwatched at a glance without hovering — use the "Unwatched only" filter for that.

### feat(webapp): per-video watched toggle button on video cards

- Added a `.watched-btn` (&#10003;) overlay button to every video card, next to the existing `.favourite-btn` star, mirroring its markup/click-handler/CSS shape exactly (same absolute-positioned thumbnail overlay, same carousel-clone-aware delegated click handler in `base.html`, same fetch-then-update-all-matching-buttons pattern) but with its own colour (`#4caf50`, distinct from the star's gold) and its own route, `POST /videos/<id>/watched`, which toggles `videos.is_watched` via `set_watched` and returns `{"is_watched": bool}`.
- This is the UI-facing piece of the `is_watched` work landed earlier today: a video can now be marked watched/unwatched directly from the card, without clicking through to YouTube. Since "unwatched" (the index filter and both rediscover-shelf pool queries) already key off `is_watched` rather than `personal_view_count`, toggling this button immediately moves a card in or out of those views. Opening a video (`record_visit`) still sets `is_watched = 1` as before; the one-time backfill already marked every previously-opened video watched, so this button is additive, not a replacement for that flow.
- The toggle intentionally does not touch `personal_view_count` — that counter still exists purely as "times opened from ViewTube" history and is unaffected by marking something watched/unwatched by hand. Trade-off: a video's watched state and its open-count history can now diverge (e.g. a video opened 3 times can still be marked "unwatched"), which is the intended behavior — "watched" is now a user judgment, not a derived count — but is a mental-model shift from before this feature.
- Trade-off already noted when the `is_watched` column and schema migration landed: this required an `ALTER TABLE` plus a backfill and a redefinition of what "unwatched" means across the codebase, more surface area than a purely additive button would have needed.
- No new automated tests — the DB function (`set_watched`) and the route (`video_toggle_watched`) already have full coverage from the earlier steps of this feature; this change is templates/CSS/JS only. Manually verified: pending (see `plan-webapp.md` and the task report for the outstanding browser checks).

### feat(webapp/db): watched state via `is_watched`; `set_watched`, `record_visit`, filter/shelf

- Added `set_watched(conn, video_id, value)`, mirroring `set_favourite`: sets `videos.is_watched` and commits, never touching `personal_view_count` — the view-count history stays intact regardless of how the watched flag is toggled.
- `record_visit` (fired by clicking through to YouTube) now also sets `is_watched = 1` in the same `UPDATE`, so a normal visit still marks a video watched even though "watched" is no longer driven by the counter.
- Redefined "unwatched" across the DB layer from `personal_view_count = 0` to `is_watched = 0`: `_build_where(unwatched_only=True)`, and both pool queries in `generate_rediscover_shelf` (unwatched pool `is_watched = 0`, viewed pool `is_watched = 1`) now key off the flag. This is the behavioral point of Task 1's backfill — a video can now be marked unwatched independent of how many times it was historically visited.
- Test-seed fallout: `tests/webapp/conftest.py` (`SEED_SQL`) and `tests/webapp/test_routes.py` (`TestIndexFilterQuickWins._seed`) insert rows *after* `init_webapp_tables` runs, so Task 1's backfill never touches them and every seeded row defaulted to `is_watched = 0` — which silently broke the unwatched-filter and rediscover-shelf pool-composition tests once the redefinition landed. Fixed by appending `UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0;` to both seed scripts, keeping seeded data coherent with the new definition and pool composition unchanged from before this change.
- Route/UI toggle (the actual "click to mark watched/unwatched" affordance) is not part of this change — DB layer only.
- Tests: `tests/webapp/test_db.py::TestSetWatched`, `TestRecordVisitSetsWatched`, `TestUnwatchedFilterUsesIsWatched`. Full suite (528 tests) passes after the seed fixes.

### feat(webapp/db): add `is_watched` column with one-time restart-safe backfill

- `init_webapp_tables` now adds `videos.is_watched` (BOOLEAN NOT NULL DEFAULT 0) via a dedicated guarded `ALTER`/`UPDATE` block, separate from the generic column-migration loop. On first run the `ALTER` succeeds and a one-time backfill sets `is_watched = 1` for every row with `personal_view_count > 0`; on every later startup the `ALTER` raises `sqlite3.OperationalError` (column already exists) and the whole block — including the backfill — is skipped.
- The one-time-ness is load-bearing: without it, a video the user manually marks unwatched would flip back to watched on the next app restart. Tied the backfill to the `ALTER` succeeding rather than a separate flag/table, so there is no extra state to keep in sync.
- Schema only — Task 1 of the watched-toggle feature. No DB read/write functions, route, or UI consume the column yet.
- Tests: `tests/webapp/test_db.py::TestIsWatchedMigration` (backfill correctness, and restart-safety — manually clearing `is_watched` then re-running `init_webapp_tables` must not re-set it).

### feat(extension): green channel title on captured channel pages

- The content script now colors a YouTube channel page's header title green (`TITLE_COLOR.exists`, `#388e3c`) when that channel is already tracked in ViewTube, mirroring the existing captured-video title behaviour. It calls a new `fetchChannelStatus` background action, which hits the already-existing `GET /api/channel/status?url=<canonicalChannelUrl>` (no backend changes).
- Green-only: unlike video titles, there's no red/hidden case for channels, since channels don't have a "hidden" state.
- `extension/manifest.json` content-script `matches` broadened from `https://www.youtube.com/watch*` alone to also include `/@*`, `/channel/*`, `/c/*`, and `/user/*`, so the script now injects on channel pages too.
- `run()` in `content.js` now branches: video-ID URLs still run `checkCurrentVideo`/`watchRelated` unchanged; otherwise, if the URL matches the (new, popup.js-synced) `YT_CHANNEL_RE`, it runs `checkCurrentChannel()`, which guards against stale color from SPA navigation the same way `checkCurrentVideo` does (re-checks the URL after each `await`).
- Implication: an at-a-glance "already tracked" signal on channel pages without opening the popup. Trade-off: the status check is URL-based, so a channel viewed via a different URL form than the one it was stored under may not light up (a missing signal, never a false green — not a correctness risk, just a coverage gap). Trade-off: `CHANNEL_TITLE_SELECTOR` targets several known YouTube channel-header DOM shapes but is inherently DOM-version-dependent and may need maintenance as YouTube changes its markup.

## 2026-08-06

### feat(webapp): add unwatched/duration/date-range quick filters to the index

- Added three filters to the main video list: **Unwatched only** (`personal_view_count = 0`), **Duration** buckets (`short` &lt; 5 min, `medium` 5–20 min, `long` &gt; 20 min), and **Added within** presets (7/30/90/365 days). All three compose through the existing shared `_build_where` helper in `webapp/db/videos.py` alongside `channel`/`tag`/`search`/`favourites_only`, so they combine with every existing filter and with pagination/grouping for free.
- `duration` and `added_within` are validated against allow-lists (`_DURATION_BUCKETS`, `_ADDED_WITHIN_DAYS`) before being interpolated into SQL; an unrecognized value raises `ValueError`, which the `index` route's existing `try/except ValueError: abort(400)` turns into an HTTP 400 (e.g. `/?duration=epic`).
- Rendered as three new controls in the filter form (`webapp/templates/index.html`): a checkbox and two `<select>`s, wired into the existing HTMX auto-submit form and the `Filters` badge count.
- Implication: makes it much faster to narrow a large library down to "what haven't I watched yet" or "what's short and recent" without scrolling through everything. Trade-off (accepted): videos with a NULL `duration_seconds` (98 in the current library) match no duration bucket — they simply don't show up under Short/Medium/Long, which is judged less confusing than guessing a bucket for missing data.

### fix(crawler): channel thumbnails were never stored (avatar lives in `thumbnails` list)

- `fetch_channel_metadata` read `info.get("thumbnail")`, but yt-dlp leaves the singular `thumbnail` field unset for channels — the avatar is in the `thumbnails` list alongside the wide banner. Every channel row was stored with `thumbnail_url = NULL`, so the `/channels` cards showed the empty placeholder.
- Added `_pick_channel_thumbnail`, which prefers the uncropped avatar, then the largest square thumbnail, then any thumbnail — never the banner. Fixes future adds via both the crawler and the extension's "add channel".
- Extended `get_channel_ids_for_backfill` so `--backfill-channels` also re-fetches channels whose `thumbnail_url IS NULL`, and — via a `UNION` on the `channels` table — reaches bookmark-only channels (those with no saved videos), which the video-driven query previously skipped.
- Implication: existing channels stay thumbnail-less until a `--backfill-channels` re-run (~1 fetch/channel). Trade-off: that re-run is another full pass over ~1,900 channels.

## 2026-08-06

### feat(webapp): add GET /channels listing route and templates

- Added the `main.channels` route (`GET /channels`) and its four templates (`channels.html`, `_channels_container.html`, `_channels_load_more.html`, `_channel_card.html`), consuming Task 1's `get_channels_page`/`count_channels`. Mirrors the index route's pagination and HTMX append pattern exactly (`HX-Request` header + `append=1` selects the fragment vs. full page), so `search`, `has_videos=1`, `page`, and `append=1` behave the same way users already expect from `/`.
- `sort` collapses `(sort_by, sort_dir)` into four named presets (`_CHANNEL_SORT_PRESETS`) so the filter form only needs one `<select>`; an unrecognized preset is a 400, same as an invalid `sort_by` on `/`.
- This is a plain server-rendered page, not an extension API route — deliberately does *not* use `_CORS_HEADERS` or an `OPTIONS` handler, unlike the `/api/*` routes in the same file.
- No nav link added yet (that's a later task in the same plan), so the page is only reachable by direct URL for now.
- Tests seed `channels`/`videos` directly via `sqlite3.connect` (same pattern as `TestApiChannelStatus`), covering the happy path, `has_videos` filter, `search` filter, invalid `sort` (400), and the append-fragment response omitting page chrome (`<!doctype html>`).
- **Wired up (same day, Task 3):** added the `main.channels` nav link to `base.html` (alongside Tags/Watch Later) and `.channel-*`/`.filter-row`/`.filter-check` CSS to `style.css` — the page is now reachable from every screen, not just by direct URL.

**Implications**
- **+** Channels are now browsable as entities: a sort/search/has-videos-filtered grid of channel cards, each linking to that channel's filtered video list on `/` or out to YouTube — not just a per-video `channel=<name>` filter.
- **−** Card→videos links match by exact `channel_name` string, not `channel_id`; two distinct channels sharing an exact display name would collapse into one filtered list on `/`. Accepted for now (rare in practice); would need the index route's channel filter to accept `channel_id` to close fully.

### feat(webapp/db): add get_channels_page and count_channels

- Added `get_channels_page` and `count_channels` to `webapp/db/channels.py`, plus a `_CHANNEL_SORT_COLUMNS` allow-list and shared `_channel_where` helper. `get_channels_page` computes `video_count` per channel via `LEFT JOIN videos ... GROUP BY channel_id` so channels with zero videos still appear by default; `has_videos=True` filters them out via `HAVING`. Sort/direction are validated against an allow-list (mirroring `ALLOWED_SORT_COLUMNS` in `webapp/db/videos.py`) before being interpolated into SQL, since SQLite can't parameterize column/direction names.
- This is Task 1 of the channels listing view (`.superpowers/sdd/2026-08-06-channels-listing-view/`) — DB layer only, no route or template yet, so nothing user-visible changed.
- Trade-off: NULL `subscriber_count` always sorts last regardless of `sort_dir`, which is friendlier UX but means "ascending by subscribers" doesn't put NULLs first the way a naive SQL `ASC` would — documented in `plan-webapp.md` so the later route/template tasks don't have to rediscover it.

## 2026-08-05

### feat(extension): animated spinner for in-progress popup states

- Added a `working(label)` helper and a `.spinner` CSS animation to the extension popup. All transient states — Checking, Adding, Adding channel, Hiding, Restoring, Deleting — now render an animated spinner instead of a static text line, so the popup reads as actively working during a request.
- Motivated by channel-add feeling slow: `POST /api/channel/add` blocks on a ~2–4s yt-dlp fetch. We deliberately kept the fetch **synchronous** (rather than moving it to a background thread) so genuine fetch failures — private/deleted channels, bad URLs — are still reported at click time; the spinner addresses the *perceived* responsiveness without giving up that click-time error feedback.
- Trade-off: the underlying add is still ~2–4s; the spinner improves feel, not actual latency. Making it truly instant would require background processing and losing synchronous error reporting (see the "Background processing for blocking operations" tech-debt item).

## 2026-07-25

### feat(extension): add bookmark-channel action on channel pages

- `extension/popup/popup.js` now detects channel pages (`/channel/UC…`, `/c/<name>`, `/user/<name>`, `/@<handle>`) via a new `YT_CHANNEL_RE` and branches `run()` three ways: video (existing behaviour), channel (new), or neither ("Not a YouTube video or channel.", replacing the old video-only message).
- On a channel page, the popup pre-checks `GET /api/channel/status` and either shows "Already tracked: `<name>`" or an "Add channel to ViewTube" button. Clicking Add calls the new `doAddChannel`, which creates a Firefox bookmark in the ViewTube folder and calls `POST /api/channel/add` in parallel (via `Promise.allSettled`), reporting partial failures the same way `doAdd` does for videos.
- Completes the extension task of the "bookmark channel" feature (Task 4 of `.superpowers/sdd/2026-07-25-extension-bookmark-channel/`), consuming the `/api/channel/status` and `/api/channel/add` routes and `get_channel_by_source_url`/`upsert_channel` added in Tasks 1–3.

**Implications**
- **+** Channels are now first-class from the browser — no need to open the webapp to start tracking a creator.
- **−** The status pre-check is URL-based (`get_channel_by_source_url` matches `channel_url` or `source_url` string equality), so viewing a channel via `@handle` after it was added via `/channel/UC…` (or vice versa) can show "Add channel" for an already-tracked channel. Resolved correctly on click — `/api/channel/add` upserts by `channel_id`, so no duplicate row is created — but the pre-check itself can be misleading until then.

---

### feat(webapp/db): add `upsert_channel` and `get_channel_by_source_url`

- Added `upsert_channel(conn, meta: ChannelMetadata, source_url=None)` and `get_channel_by_source_url(conn, url)` to `webapp/db/channels.py`, re-exported from `webapp.db`. These are the webapp-side counterparts to the crawler's own `upsert_channel`/lookup functions (`crawler/datastore.py`), giving the Flask app the same upsert-by-`channel_id` and `channel_url`-or-`source_url` lookup behaviour.
- `upsert_channel` commits internally (matching the `webapp/db/aliases.py` write-function pattern) and preserves an existing `source_url` via `COALESCE(excluded.source_url, channels.source_url)` when a later call omits one.
- Task 1 of the extension "bookmark channel" feature — the API route and extension UI that will call these functions are separate, later tasks. See `plan-webapp.md` and `.superpowers/sdd/2026-07-25-extension-bookmark-channel/`.
- Added `TestUpsertChannel` and `TestGetChannelBySourceUrl` test classes (4 cases) to `tests/webapp/test_db.py`.

**Implications**
- **+** The webapp can now upsert and look up channels by either their canonical URL or the `@handle`/source URL a browser bookmark used, mirroring the crawler-side idempotency fix from 2026-07-08.
- **−** Two modules (`crawler/datastore.py` and `webapp/db/channels.py`) now each define an `upsert_channel` function with near-identical SQL; acceptable for now since they operate on different `sqlite3.Connection` instances (crawler DB vs. webapp DB) but worth watching for drift if the upsert logic changes again.

---

## 2026-07-08

### fix(crawler): store `source_url` to fix `@handle` channel idempotency

- Added `source_url TEXT` column to the `channels` table in both `crawler/datastore.py` (`_SCHEMA`) and `webapp/db/schema.py` (DDL + ALTER TABLE migration for existing databases).
- `upsert_channel(meta, source_url=None)` now accepts an optional `source_url` and stores it in the database. `COALESCE(excluded.source_url, channels.source_url)` ensures a subsequent call without a source_url never clears a previously stored bookmark URL.
- `has_full_channel_record(url)` now checks `channel_url = ? OR source_url = ?` so an `@handle` bookmark URL stored as `source_url` is matched on second run, preventing redundant yt-dlp fetches.
- CLI channel-bookmark loop now passes `bookmark.url` as `source_url` when calling `upsert_channel()`.
- Added `TestHasFullChannelRecord` test class (5 cases) and one new CLI test (`test_channel_bookmark_skipped_on_second_run`); also strengthened the existing `TestUpsertChannelStub.test_does_not_overwrite_description_after_full_upsert` with a `thumbnail_url` assertion.

**Implications**
- **+** Channels bookmarked via `@handle` URLs are now skipped on re-runs, eliminating wasteful yt-dlp round-trips.
- **+** The fix is backward-compatible: existing rows simply have `source_url = NULL` and continue to match by `channel_url` as before.
- **−** The ALTER TABLE migration runs at webapp startup; production DBs that cannot tolerate brief schema migrations need a maintenance window (extremely unlikely to matter at this scale).

---

## 2026-07-02

### Creator Pages Support — Schema & Crawler (Phase 1)

- Added `channels` table to both `crawler/datastore.py` and `webapp/db/schema.py`. Two tiers of record: **stub** (free, from video processing side effect — no description/subscriber_count) and **full** (from channel bookmarks or `--backfill-channels`).
- Added `ChannelMetadata` dataclass and `Bookmark.youtube_channel_url` property in `crawler/models.py`. Supports all four YouTube channel URL forms (`/@handle`, `/c/name`, `/channel/UCxxx`, `/user/name`).
- Added `fetch_channel_metadata()` in `crawler/metadata_fetcher.py` using yt-dlp with `extract_flat: True` to read channel-level metadata without iterating individual videos.
- Crawler CLI now processes channel bookmarks in a new loop after the video loop. Channel bookmarks are idempotent: channels with an existing full record (non-null description) are skipped unless `--force-refresh` is set.
- Every video fetch creates a stub channel record as a side effect using `upsert_channel_stub()`, which deliberately never overwrites `description`, `subscriber_count`, or `thumbnail_url` set by a prior full fetch.
- New `--backfill-channels` CLI flag: fetches full metadata (one yt-dlp call per unique channel) for all channels missing description. Expensive for large libraries — opt-in only.
- Renamed `get_all_channels()` in `webapp/db/videos.py` to `get_video_channel_names()` (it returns `list[str]` for the filter dropdown). New `get_all_channels()` in `webapp/db/channels.py` returns `list[dict]` of full channel entity rows.
- **Trade-off:** No FK from `videos` to `channels` — joined via `channel_id TEXT`. Avoids migration complexity and lets the two tables evolve independently, but loses referential integrity.
- **Trade-off:** Channel stubs use `fetch_status = 'ok'` rather than a pending state. Backfill candidates are identified by `description IS NULL`, not `fetch_status`. This means the status field cannot distinguish "stub-ok" from "fully-fetched-ok" without inspecting description.

**Implications**
- **+** Foundation for creator pages support — channels can now be stored and tracked alongside videos.
- **+** Stub-vs-full logic allows the crawler to incrementally build channel records without losing data when a stub is written after a full fetch.
- **+** `--backfill-channels` allows opt-in full enrichment of existing channel records without blocking the main crawl.
- **−** Migration required for existing databases: running the crawler will automatically create the new table on next init, but existing live DBs need manual schema update or DB recreation.
- **−** No UI or routes yet — the channels table exists in the database but is not yet exposed via the web interface.

---

### Extension: show Add-to-ViewTube prompt with optional Watch Later checkbox (2026-07-02)

When the extension popup is opened on a YouTube video not yet in ViewTube, it now renders a prompt ("Add to ViewTube" button + "Also add to Watch Later" checkbox) rather than firing the add immediately. Clicking the button triggers the add; if the checkbox is ticked, `/api/watch-later/add` is called sequentially after the ViewTube add succeeds (sequential because the endpoint 404s if the video is not yet in the DB). `already_in_queue` (409) is treated as success so re-adding an already-queued video does not surface an error.

**Implications**
- **+** Users can enqueue a video in Watch Later at the same moment they add it, without a second popup interaction.
- **+** Follows the existing opt-in checkbox pattern from the Archive flow ("Also remove browser bookmark").
- **−** The extra click is minor friction for the common case (add without Watch Later) — this is the cost of the explicit intent model.
- **−** Watch Later failure is surfaced as a secondary status line but does not prevent the popup auto-close; the user may not notice if the queueing silently failed.

### Add a right-click "Add tag…" action for manually tagging a single video (2026-06-22)

New backend route, partial, global datalist, and context-menu UI letting a tag be attached to any video without leaving the page or using the bookmarklet/extension. Came up while debugging a video that ended up with zero canonical tags — there was previously no way to give a video a tag directly; the only existing mechanisms were automatic alias-matching at ingest time and the `/tags` admin page's unclassified-pool flow, which only works on raw tags that already exist on 2+ videos.

Extracted the inline tag-pills markup out of `_video_card.html` into a new `_tag_pills.html` partial (pure refactor, verified non-regressive against the full suite before writing new tests) so the pill-rendering logic has one source of truth shared by the initial page render and the new route's response. Added `POST /videos/<video_id>/tags/add`, which reuses the existing `create_canonical_tag` (idempotent — creates new or promotes an existing raw tag) and `add_video_tag` (`INSERT OR IGNORE`) DB functions and re-renders `_tag_pills.html` with the video's current canonical tags. A new context processor injects the full canonical tag name list into one global `<datalist id="canonical-tag-datalist">` in `base.html` (not duplicated per card), powering autocomplete that is canonical-only — mirroring the existing `/tags` page pattern and avoiding surfacing the much larger, mostly-junk raw tag pool.

On the frontend, the video card's right-click menu gained an "Add tag…" item that opens an inline popover (text input bound to the global datalist) positioned at the menu's location; Enter submits to the new route and the response HTML replaces/inserts the card's tag pills directly without a page reload, updating every on-page instance of that video (carousel clones included). Also decoupled the card menu's Hidden-page exclusion: right-clicking a card inside `.hidden-videos-grid` now opens the menu (previously suppressed entirely), with "Archive video" hidden there since a hidden video can't be hidden again, while "Add tag…" remains available everywhere.

**Implications**
- **+** Tags can now be added in a couple of clicks, uniformly across the main grid, Watch Later, the Rediscover shelf, and the Hidden page — closing a real gap for videos with thin/noise-only source metadata.
- **+** The pill-rendering logic now has a single source of truth, so future markup changes only need to happen in one place.
- **−** Typing a tag name that matches an existing *raw* (non-canonical) tag promotes it to canonical for every other video that already carries it, not just the one being tagged — pre-existing `create_canonical_tag` behavior, not a new risk, but now reachable from a much more casual, frequent entry point than the `/tags` admin page.
- **−** The "Add tag…" button's click handler needs `e.stopPropagation()` to avoid the document-level outside-click handler immediately closing the popover it just opened — a subtle bubbling interaction worth remembering if more menu-triggered popovers are added later (the same pattern was already fixed once for the rediscover-shelf toggle button).
- **−** No JS test coverage for the new popover/click interaction — no JS test framework exists yet in this codebase (tracked separately as tech debt); coverage here is DB/route-layer tests plus structural `curl`/`grep` verification against a copy of real data, not real-browser click-testing.

---

### Hide rediscover carousel arrows when nothing to scroll to (2026-06-19)

The carousel always showed prev/next arrows and built wraparound clones even when there were fewer real videos than fit in one view — and the unused viewport space would have shown the start of the clone strip (a duplicate-looking card), not empty space. Now `initCarousel()` checks `realCount > visibleCount` (the existing 4/3/2/1 responsive breakpoint) and, when false, skips the clone/transform machinery entirely, renders the real cards as a static row, and hides both arrows. This is reactive to window resize (re-checked on every resize, not just at load) since visible-count is breakpoint-driven and can change independent of the shelf's video count. Also fixes a latent gap where the empty-shelf case left the arrows visible but silently inert. Removed three write-only state variables discovered to be dead code while rewriting this function.

**Trade-off:** cards in the under-full case keep the same per-card width a full row would have, leaving a trailing gap rather than stretching to fill the row — chosen for consistent card sizing over a fuller-looking row.

---

### Add a remove-from-Rediscover button (2026-06-19)

New ✕ button on shelf cards, to the right of the ⏱ watch-later button, that removes a video from the current rediscover shelf without touching `personal_view_count` or `date_last_viewed` — distinct from favouriting (which intentionally marks watched) or visiting. New `remove_from_rediscover_shelf` DB function (a thin public wrapper around the private helper `record_visit`/`add_to_watch_later` already used internally) and `POST /videos/<id>/rediscover-shelf/remove` route.

Restructured the top-right thumbnail overlay buttons (`.watch-later-btn`, `.queue-remove-btn`, now also `.shelf-remove-btn`) from each being individually absolutely-positioned into a single `.thumb-actions-right` flex wrapper, since shelf cards now need two buttons side by side in that corner rather than one. This also simplified the hover-opacity rule from two selectors to one (`.thumb-wrap:hover .thumb-actions-right button`).

**Trade-off:** there was no existing test coverage at all for any rediscover-shelf DB function before this change (a pre-existing gap, not introduced here) — added tests for the new function and route, but the gap remains for the older shelf functions (`generate_rediscover_shelf`, `get_current_rediscover_shelf`, etc.).

---

### Favouriting from Rediscover or Watch Later marks watched and removes from the list (2026-06-18)

Marking a video as a favourite while viewing it on the rediscover shelf or the Watch Later page now also marks it watched (new `POST /videos/<id>/mark-watched` route, reusing the existing `record_visit` DB function — same increment-`personal_view_count`/set-`date_last_viewed` logic `/visit/<id>` already uses) and removes it from whichever list it was favourited from: fades it out of the shelf carousel, or removes it from the watch later queue via the existing remove endpoint. `record_visit` already drops the video from the persisted rediscover shelf as a side effect, so this also survives a page reload, not just the in-page DOM removal. Un-favouriting does nothing special, and this only applies on the shelf and Watch Later page — the main list and Archived page are unaffected.

While wiring this up, extracted two small JS helpers (`fadeOutShelfCards`, `removeFromWatchLaterUI`) in `base.html` that were about to become a third copy-pasted instance of existing logic — the shelf-card fade-out and the watch-later removal/reindex sequence were each already duplicated once. Minor side effect: the shelf-card fade-out used to be 0.3s in one place and 0.2s in another; both are now 0.2s for consistency.

**Trade-off:** the mark-watched call is fire-and-forget (no error handling if it fails) — same pattern already used elsewhere in this file (e.g. the watch-later-add button), consistent rather than newly risky.

---

### Fix slight vertical shift of the Rediscover label on toggle (2026-06-18)

`.shelf-header` is a flex row with `align-items: center`; its height is set by its tallest child. With the refresh button only present in the expanded state (`.shelf-controls` is `display: none` when collapsed), the row's height shrunk when collapsing — from the button's 32px down to the `<h2>` line's own (smaller) height — and the centered label shifted up by roughly half that difference. Fixed with `min-height: 2rem` on `.shelf-header`, matching `.shelf-icon-btn`'s height, so the row's cross-axis size never depends on which children are present. Coupled to the icon button's current size — if that size ever changes, this value needs to move with it.

---

### Add hover tooltip to rediscover refresh button (2026-06-18)

Added `title="Refresh"` to the now icon-only (`↻`) refresh button, matching the existing convention elsewhere in this codebase (e.g. the watch-later and favourite icon buttons) of using `title` for hover tooltips on icon-only controls.

---

### Add a "Videos" section label above the main list (2026-06-18)

A plain `<h2 class="section-label">Videos</h2>` now sits above `#video-container`, styled to match the "Rediscover" label's weight (same font-size, no border/box) rather than reusing the heavier `.page-header` treatment from other pages (border-bottom + 2rem margin) — this isn't a standalone page heading, just a lightweight section break so the rediscover shelf and the main video list read as two distinct sections instead of one continuous block. `.section-label` is named generically rather than e.g. `.videos-label` since it's a reusable pattern, not tied to this one use.

---

### Adjust rediscover shelf spacing (2026-06-18)

Two small gaps: more horizontal space between the chevron icon and the "Rediscover" label (moved from a trailing space in the CSS `content` string to an explicit `margin-right`, which is easier to tune), and more vertical space below the shelf before the main video grid, in both collapsed and expanded states, so the shelf reads as a distinct section rather than visually attached to the grid.

---

### Fix jarring header jump when toggling the rediscover shelf (2026-06-18)

The "Rediscover" label visually shifted position every time you clicked it, because the box's padding (1rem, applied to everything inside `.rediscover-shelf` including the header) dropped to 0 on collapse — so the thing you just clicked moved out from under your cursor. Fixed by moving the box styling (padding/background/border/border-radius) off `.rediscover-shelf` and onto a new wrapper, `.shelf-body`, around just the carousel and footer. The header is now a sibling of `.shelf-body` rather than a padded child of the box, so it renders identically — and stays put — in both states. Collapsing also simplified from a 4-property override back to a single `display: none` on `.shelf-body`.

**Side effect (intentional improvement):** the label now aligns with the toolbar/search bar above it and with `.page-header h1` on other pages, instead of being extra-inset by the box's own padding.

---

### Simplify rediscover shelf header controls (2026-06-18)

Follow-up to the collapsed-state redesign below. The dedicated toggle button is gone — Refresh moves into that same square slot (`.shelf-icon-btn`, renamed from `.toggle-btn` since it now sizes the refresh button, not a toggle), shown as an icon (`↻`) instead of the text "Refresh", with `aria-label="Refresh shelf"` added since it's icon-only now. The "Rediscover" label itself is now the single toggle target for both expanding and collapsing. Since the label and the refresh button are siblings rather than nested, the `e.stopPropagation()` workaround from the previous redesign is no longer needed and was removed. The chevron also grew from `0.75em` to `1.3em` for visibility.

**Trade-off:** the toggle action now has no visible button affordance at all — just a label that happens to be clickable — which is less discoverable at a glance than a dedicated button. Traded for a cleaner two-element header (label + one icon button) instead of three separate click targets.

---

### Redesign rediscover shelf collapsed state (2026-06-18)

Collapsed state used to keep the full bordered box (border, background, padding) and both header buttons (Refresh, toggle) visible — only the carousel and footer were hidden. Now collapsing strips the box chrome entirely and removes the Refresh button, leaving a single full-width line (`▸ Rediscover`) that's the click target to re-expand. No HTML changes were needed — purely a CSS restructuring plus a small rewrite of the existing toggle script (`webapp/templates/index.html`, `webapp/static/style.css`).

The toggle button's old `+`/`−` text-swapping was removed as dead code: the button is now only ever visible in the expanded state (where its action is always "collapse"), so a static `−` is correct in every state it's shown in. Required adding `e.stopPropagation()` to the toggle button's click handler — without it, the click would bubble into the header's own click-to-expand listener and immediately undo the collapse.

**Trade-off:** the expand affordance in the collapsed state is just a static chevron + label with no button styling, which is less visually obvious as "clickable" than a real button — accepted in exchange for the minimal/quiet look that was the point of this change.

---

### Fix missing personal view count on Watch Later cards (2026-06-18)

`get_watch_later_queue` built its `SELECT` column list by hand and omitted `v.personal_view_count`, so the `[N]` watched-count badge in `_video_card.html` silently never rendered for queued videos even though the shared template has always supported it. Root-caused by comparing against the three other card-producing queries (`get_all_videos` uses `v.*`; `get_hidden_videos` uses `v.*`; `get_current_rediscover_shelf` already explicitly selects the column) — `get_watch_later_queue` was the only one missing it. Added `v.personal_view_count` to its `SELECT`.

The Rediscover shelf appearing to lack the badge is not a bug: the shelf algorithm deliberately prioritizes never-watched videos (`personal_view_count = 0`), so the badge correctly stays hidden for most shelf entries by design.

---

### Drag-to-reorder Watch Later queue (2026-06-18)

Wired up the existing (unused) `reorder_watch_later` DB function to the UI. New route `POST /videos/<id>/watch-later/reorder` accepts `{position}` and persists the move; `.video-card` is made `draggable="true"` only in `context="watch_later"`, with a delegated dragstart/dragover/dragend handler added to the existing vanilla-JS IIFE in `base.html`.

Implemented with the native HTML5 drag-and-drop API rather than vendoring a sortable library, matching the project's zero-JS-dependency convention (only `htmx.min.js` is vendored). The `dragover` reorder logic compares DOM index of the dragged vs. hovered card (not cursor position within the target's bounding rect), which works correctly for the queue's CSS grid layout — a Y-midpoint heuristic would only be correct for a single-column list.

**Trade-offs:** Drag-and-drop only — no keyboard/touch alternative, so reordering is unavailable on mobile or via assistive tech. No optimistic-rollback UI if the reorder POST fails (matches the existing queue-remove behavior on this page).

---

### Consistent video card metadata across all surfaces (2026-06-17)

Every card now shows the same base meta row regardless of context:
`views [personal_count] · published · added · last-viewed`

Each surface adds one context-specific secondary line below it:
- **Shelf** → `Never watched` / `Last viewed X days ago` (italic)
- **Watch Later** → `Queued X`
- **Hidden** → `Hidden X`
- **Main** → no secondary line

Hidden page cards now use `_video_card.html` with `context="hidden"`, eliminating the last hand-rolled card implementation. Hidden cards link through `/visit/` for consistency (records a view). Restore/Delete buttons rendered inside the unified card template for `hidden` context. `.shelf-reason` CSS class replaced by shared `.card-secondary-meta` / `.card-secondary-meta--italic`.

---

### Unify video card UI across all surfaces (2026-06-16)

Replaced three divergent card implementations (main list `_video_card.html`, JS-rendered rediscover shelf, hand-rolled watch-later list) with a single `_video_card.html` Jinja partial that renders context-appropriately via a `context` variable (`"main"` / `"shelf"` / `"watch_later"`).

Key changes:
- **Single card template**: one source of truth for thumbnail, title, channel, metadata row, tags, and action buttons. Context controls which elements appear (e.g. reason label on shelf, position badge on watch-later, channel filter icon on main only).
- **Watch Later pre-state**: new `get_watch_later_video_ids()` DB function; a Jinja context processor in `app.py` injects `watch_later_ids` into every template so the ⏱ button renders disabled on page load for already-queued videos.
- **Server-rendered shelf**: the rediscover shelf JS IIFE (~130 lines) is removed entirely. Initial render is now handled by the index route + Jinja. Refresh uses HTMX (`hx-post="/rediscover-shelf/refresh"` → HTML partial swap). The two JSON shelf API endpoints (`GET /api/rediscover-shelf`, `POST /api/rediscover-shelf/refresh`) are deleted.
- **Unified JS handlers**: tag-pill menu, video-card hide menu, watch-later add, and queue remove are all event-delegated listeners in `base.html`, so they work on all pages and on HTMX-swapped content.
- **DB queries expanded**: `get_current_rediscover_shelf` and `get_watch_later_queue` now return full video data including `channel_id`, `duration_seconds`, `date_published`, `date_added`, `tags` (GROUP_CONCAT), enabling consistent metadata display everywhere.

**Trade-offs:** Watch-later page cards now use the same grid-card layout as the main list (thumbnail at top) rather than the old horizontal-row layout — this is a visual change but achieves true structural unity. Rediscover shelf countdown timer is no longer live-updating (static "expires in X days" label computed at render time).

---

### Implement Watch Later queue feature (2026-06-14)

Added a dedicated Watch Later queue for bookmarking videos to watch later. Features:
- DB layer: `watch_later` table with position-based ordering, `add_to_watch_later`, `remove_from_watch_later`, `is_in_watch_later`, `get_watch_later_queue` functions
- API routes: POST /api/watch-later/add, /api/watch-later/remove, /api/watch-later/status with CORS headers and video validation
- UI: /watch-later dedicated page with horizontal list layout, remove buttons, expiration counter badges
- Integration: ⏱ button on main video list cards and rediscover shelf cards (fade/disable on click)
- Navigation: Watch Later link in main header between Tags and Hidden

**Trade-offs:** Watches single video — no multi-select bulk operations. Page reloads when queue becomes empty (could use HTMX swap instead). (Drag-to-reorder added later — see 2026-06-18 entry.)

---

### Fix manual tag assignment to existing canonical tags (2026-06-14)

When manually assigning an unclassified tag to an existing canonical tag (e.g., select "srv strat", enter "blues guitar", click "Assign selected"), the alias was not being created. Root cause: `tag_suggest_confirm` route required `suggestion_id` to be present, but manual assignments (from the unclassified tag pool, not Smart Suggest) have no suggestion. Condition `if canonical_name and members and suggestion_id` failed; nothing happened.

**Fix:** Split the route logic to handle `canonical_name + members` separately from `suggestion_id`. The `confirm_and_dismiss_suggestion` function now accepts `Optional[int]` for suggestion_id and only dismisses suggestions if one is provided. Result: manual assignments now create aliases correctly, and raw tags disappear from the unclassified list (excluded via `NOT IN (SELECT pattern FROM tag_aliases)` check).

---

### Move multi-step route transactions into the DB layer (2026-06-14)

Four routes performed multi-step writes sequentially across separate DB functions, each committing independently. Failure after an intermediate commit left the database in partial state. Fixed by consolidating each flow into a single composite DB function:

- `confirm_and_dismiss_suggestion(conn, canonical_name, accepted_members, suggestion_id, all_suggestion_members)` — consolidates 3 DB calls in `tag_suggest_confirm`; creates canonical tag, adds exact aliases, retroactively applies, records rejections, dismisses suggestion; single transaction
- `accept_noise_and_dismiss_suggestion(conn, suggestion_id, noise_members, rejected_members)` — consolidates 3 DB calls in `tags_llm_suggest_accept_noise`; marks members as noise, records rejections, dismisses suggestion; single transaction
- `add_alias_and_apply(conn, tag_id, pattern, match_type)` — consolidates 2 DB calls in `tag_add_alias`; adds alias and retroactively applies in one transaction
- `edit_alias_and_apply(conn, alias_id, pattern, match_type)` — consolidates 2 DB calls in `tag_edit_alias`; edits alias and retroactively applies in one transaction

**Trade-offs:** Existing single-step DB functions (`add_alias`, `edit_alias`, `retroactive_apply`, etc.) remain unchanged — still used directly by tests and other code paths. Composite functions inline their SQL to avoid premature transaction termination from sub-function commits. No external API change; routes are the only callers of the new functions.

---

## 2026-06-07

### Fix content script badge injected into stale DOM reference

After the async `fetch()`, YouTube's reactive renderer had already replaced the `#title` node that `waitFor` had resolved with. Re-querying the DOM fresh after each fetch resolved it. Added a one-shot `MutationObserver` guard as a belt-and-suspenders in case YouTube wipes the badge in a subsequent render pass. Works with and without Enhancer for YouTube.

---

### Split webapp/db.py into focused submodules

Converted the 988-line monolithic `webapp/db.py` into a package with five domain files:

| File | Responsibility |
|---|---|
| `webapp/db/videos.py` | Video CRUD, filtering, pagination, stats |
| `webapp/db/tags.py` | Tag management, canonical tags, noise, unclassified pool |
| `webapp/db/groups.py` | Tag group CRUD and membership |
| `webapp/db/aliases.py` | Alias engine: add, delete, cleanup, retroactive apply |
| `webapp/db/suggestions.py` | LLM suggestion storage and retrieval |
| `webapp/db/schema.py` | `init_webapp_tables` |

`webapp/db/__init__.py` re-exports the entire public API, so all existing import paths (`from webapp import db as _db`, `from webapp.db import func_name`) are unchanged.

**Implications**
- **+** Each file is ~60–220 lines and covers a single domain — much easier to navigate
- **+** Cross-domain dependencies are now explicit imports between submodules
- **−** `webapp/db/suggestions.py` imports from `tags.py` and `aliases.py` — the inter-module graph is a DAG but adds a layer of indirection

---

### Break crawler → webapp dependency

`crawler/datastore.py` had a deferred `from webapp.db import apply_aliases` inside `upsert_video`, making the crawler depend on the web layer. Fixed by:
- Moving `MatchType` from `webapp/db.py` to `crawler/models.py` (alongside `FetchStatus` — both are domain constants, not webapp concerns)
- Moving `apply_aliases` from `webapp/db.py` to `crawler/datastore.py` (where it's primarily called during ingestion)
- `webapp/db.py` re-exports both via `from crawler.models import MatchType` and `from crawler.datastore import apply_aliases`, so all existing call sites are unchanged

**Implications**
- **+** `crawler/` has zero imports from `webapp/` — the dependency is now strictly one-way (webapp → crawler)
- **+** The crawler can be run standalone without Flask installed
- **−** `webapp/db.py` imports from `crawler.datastore`, adding a cross-package import in that direction; this is acceptable and consistent with existing `webapp` → `crawler` imports

---

### Review and complete test coverage for YouTube in-page indicator feature

Reviewed all code for the feature (content.js, background.js, manifest, db, routes). No dead code found. Added missing tests: `TestGetVideosStatusBatch` (5 tests in test_db.py) and `TestApiStatusBatch` (6 tests in test_routes.py) covering mixed results, hidden videos, empty input, non-string IDs, CORS headers, and OPTIONS preflight.

**Implications**
- **+** `/api/status/batch` and `get_videos_status_batch` now have the same test coverage as `/api/status`
- **−** None

---

### Fix: marking a tag as noise doesn't remove it from Smart Suggest cards

`get_llm_suggestions` was filtering out `llm_suggestion_rejections` entries but not tags marked `is_noise = 1` in the `tags` table. Marking a tag as noise from the unclassified pool now immediately hides it from any suggestion card that listed it as a member.

**Implications**
- **+** Noise tags vanish from suggestion cards on the next page load without needing a separate dismiss action
- **−** None — noise tags were already excluded from the unclassified pool display; this makes suggestions consistent with that

---

### Add in-page ViewTube status indicators to YouTube via content script

New content script (`extension/content/content.js`) injected on YouTube watch pages. Shows a coloured pill below the current video title (✓ In ViewTube / ⊘ Hidden) and a smaller version on each related video card in the side panel. Re-runs on YouTube SPA navigations via `yt-navigate-finish`. New server endpoint `POST /api/status/batch` resolves up to 50 video IDs in one SQL query.

**Implications**
- **+** Instant visual signal whether a video is already saved, without opening the popup
- **+** Side-panel badges let you see at a glance which related videos you've already bookmarked
- **+** `yt-navigate-finish` is stable and well-documented; no polling needed
- **−** YouTube DOM selectors (`ytd-compact-video-renderer`, `#above-the-fold #title`) may break when YouTube updates its layout — needs periodic re-checking
- **−** Requires reloading the extension in `about:debugging` after this update; the new `http://localhost:*/*` permission must be accepted

---

### Add date_last_viewed and title tooltips to video card metadata

Added `date_last_viewed` to the card metadata row (conditional — hidden when null, i.e. never opened from ViewTube). Added `title` attributes to all metadata spans with descriptive text and the exact ISO date as context behind the relative display value.

**Implications**
- **+** Hovering any metadata item explains what it means and shows the precise date
- **+** Last-viewed date gives a quick signal for recently revisited videos
- **−** `date_last_viewed` only reflects opens via ViewTube's redirect, not direct YouTube visits

---

### Add `FetchStatus` and `MatchType` enums; replace magic string literals

Added `FetchStatus(StrEnum)` in `crawler/models.py` (`PENDING`, `OK`, `ERROR`, `PRIVATE`, `DELETED`) and `MatchType(StrEnum)` in `webapp/db.py` (`EXACT`, `PREFIX`, `CONTAINS`). Updated all Python-side comparisons and default parameter values to use the enum members. SQL string literals inside queries are left as raw strings (correct practice — they're SQL syntax, not Python logic).

**Implications**
- **+** Typos in status/match-type values are now a `ValueError` at the call site instead of a silent DB mismatch
- **+** IDE autocomplete and type-checking work for both enums
- **+** `StrEnum` members compare equal to their string values, so no test changes were needed
- **−** `webapp/db.py` now imports from `crawler.models` — this is acceptable but reinforces the need to eventually move shared types to a neutral `core/` package

---

### Remove `collapse_case_variants` from startup

`collapse_case_variants()` was called inside `init_webapp_tables()`, which runs on every `create_app()`. Removed it from startup and exposed it as `viewtube-web --db <path> --normalize-tags` instead.

**Implications**
- **+** App startup no longer does a full tag-table scan on every launch
- **+** The operation is now explicit and auditable (prints how many rows were merged)
- **−** Existing installations that relied on auto-normalization on startup will need to run `--normalize-tags` once manually if they have case-duplicate tags

---

### Fix: coverage config only measured crawler, not webapp or tools

Added `--cov=webapp` and `--cov=tools` to `pyproject.toml`. Overall coverage is 55% (was reported as 92% but only reflected the crawler). Notable gaps now visible: `routes.py` at 50%, `db.py` at 71%, `llm_tagger.py` at 60%, `tools/tag_categorizer.py` at 0%.

**Implications**
- **+** Coverage numbers now reflect the full codebase; previously misleading 92% hid large untested areas
- **−** The headline number dropped from 92% to 55%, which is the accurate picture

---

### Fix: test schema drift causing 5 failing tests

Replaced the hardcoded `SCHEMA_SQL` string in `tests/webapp/conftest.py` with a `_setup_db()` helper that builds the DB the same way production does — crawler base schema (`crawler/datastore._SCHEMA`) followed by `init_webapp_tables()`. Updated `test_cli.py` to use the same helper.

**Implications**
- **+** Tests can no longer drift from the real schema; adding a table to `init_webapp_tables` will automatically be present in all test fixtures
- **+** Fixes the immediate failures caused by the missing `llm_suggestion_rejections` table
- **−** `db_conn` fixture now requires `tmp_path` (file-based) instead of `:memory:`; marginally slower but negligible at this scale

---

## Prior Sessions (before 2026-05-28)

### Initial Implementation
Core webapp built: Flask app factory, SQLite query layer (`webapp/db.py`), Jinja2 templates, HTMX partial swaps, CLI entry point.

**Implications**
- **+** No build step, no JS framework — easy to run locally and modify
- **+** HTMX partial swaps give SPA-like feel without client-side state management
- **−** HTMX adds a runtime dependency (vendored `htmx.min.js`); if the API changes significantly, rewrites are nontrivial

---

### Fix: `tag_keywords` table missing on startup (503 error)
`init_webapp_tables()` is now called inside `create_app()` on every startup.

**Implications**
- **+** App is self-healing — no manual migration step needed when deploying to a new DB
- **+** Idempotent (`CREATE TABLE IF NOT EXISTS`)
- **−** Minor overhead on every cold start (negligible in practice)

---

### Remove tag pills from video cards
Tags were removed from the individual card display.

**Implications**
- **+** Cards are cleaner and less visually noisy
- **−** No at-a-glance tag context on individual videos; user must open the video or use tag filter to see tags

---

### Auto-update search on filter change (no Apply button)
HTMX triggers on `change` for selects and `keyup delay:300ms` for the search input.

**Implications**
- **+** Instant feedback; no extra click required
- **+** 300ms debounce prevents flooding the server on fast typing
- **−** Every keystroke (after 300ms) issues a request; with a large library this could be noticeable on a slow machine
- **−** No way to compose multiple filter changes atomically before the query fires

---

### Add `date_published` and `date_added` to video card metadata row
Both dates shown without labels, separated by the dot separator.

**Implications**
- **+** Lets user quickly assess content freshness vs. when they saved it
- **−** Two unlabeled dates close together can be ambiguous on first glance

---

### Channel name links to YouTube channel page (new tab)
`.channel-link` opens `https://www.youtube.com/channel/<channel_id>`.

**Implications**
- **+** Quick navigation to a channel without leaving ViewTube
- **−** Relies on `channel_id` being populated by the crawler; falls back to plain text if absent

---

### Videos open in a new tab
Both the thumbnail and the title link use `target="_blank" rel="noopener noreferrer"`.

**Implications**
- **+** ViewTube page stays open while watching; easy to return and continue browsing
- **−** Tab proliferation over a long browsing session

---

### Channel on its own line above metadata
`.video-channel` is a separate line between title and the metadata row.

**Implications**
- **+** Visual hierarchy is clearer: title → channel → stats
- **−** Cards are slightly taller

---

### Friendly sort labels; remove tag selector from filter bar; visible Reset button
Sort select uses human-readable labels (no underscores). Tag filter removed. Reset is a styled button at the end of the filter form.

**Implications**
- **+** Filter bar is simpler and less intimidating
- **+** Reset is visible and easy to find
- **−** Tag filtering is gone from the main workflow — users must rely on search to surface tag-related results

---

### Duration overlay on thumbnail (YouTube-style)
`position: absolute` badge in the bottom-right corner of the thumbnail.

**Implications**
- **+** Familiar YouTube UI convention; no extra layout space consumed
- **−** Only shown when `duration_seconds` is populated by the crawler

---

### Pagination (20 per page, Prev/Next)
Initial pagination implementation with Prev/Next links and HTMX partial swap.

**Implications**
- **+** Limits DOM size on large libraries
- **−** 20 was quickly felt as too small for casual browsing (subsequently replaced)

---

### Group by channel; remove group by keywords
Group select offers "No grouping" and "By channel" only.

**Implications**
- **+** Channel grouping is the most natural way to browse by creator
- **−** Removing keyword grouping loses a potentially useful secondary axis; can be revisited

---

### Remove Tags top-level nav and all tag management UI
The Tags page (create/edit/delete tags, assign keywords) was removed entirely.

**Implications**
- **+** App is simpler; less surface area to maintain
- **+** Tags still work as a data concept and can be searched
- **−** No UI to create or manage tags; tags must be assigned via direct DB access or a future admin tool
- **Note**: This decision was made because the tag management UI was not yet providing enough value to justify its complexity

---

### Word-prefix search (not mid-word, not whole-word)
Regex pattern `\bterm` — matches words that *start with* the search term, not mid-word matches.

**Implications**
- **+** "guitar" matches "guitarist" but "uitar" does not match "guitar" — intuitive
- **+** Avoids noise from mid-word substrings (e.g. "prik" would not match "paprika")
- **−** Won't match a word unless the search begins at a word boundary — slightly surprising if user expects substring search
- **Note**: Went through two iterations — whole-word (`\bterm\b`) was tried first, then corrected to prefix-only (`\bterm`)

---

### Search covers tag names and tag keywords
Search query is matched against title, description, tag names, and tag keywords via four subqueries.

**Implications**
- **+** A video tagged "guitar" with keyword "lesson" is found by searching "lesson" even if the word doesn't appear in the title or description
- **+** Tags act as a manual enrichment layer that improves discovery
- **−** Four subqueries per search; acceptable for SQLite at this scale but worth monitoring on a large library
- **−** Results can include videos the user doesn't expect if tag keywords are broad

---

### Exclude `fetch_status != 'ok'` videos from all list views
`fetch_status = 'ok'` is a permanent base condition in `_build_where`.

**Implications**
- **+** Private, deleted, and errored videos are silently hidden — clean browsing experience
- **+** Stats page still counts them (so the user knows errors exist)
- **−** A video that was fetchable when added but later goes private will silently disappear from results

---

### CLAUDE.md: always update plans without being asked
Instructions added to ensure plan files are kept current in the same response as code changes.

**Implications**
- **+** Plan files reflect actual implementation rather than drifting out of date
- **+** Reduces back-and-forth prompting

---

## 2026-05-28

### Personal view count shown inline: `1,234 [5] views`
Replaces the separate "Watched N×" metadata item.

**Implications**
- **+** One fewer metadata item; same information in less space
- **+** Visually connects personal watch count to the YouTube view count for easy comparison
- **−** Square brackets are a somewhat arbitrary convention; could be confused for other metadata

---

### Filter icon beside channel name
Small funnel SVG beside each channel name; clicking it navigates to `/?channel=<name>`.

**Implications**
- **+** One-click channel filter from any video card
- **+** Full page load means the channel dropdown updates to reflect the active filter
- **−** Full page load is slightly slower than an HTMX swap; chosen for simplicity and consistency

---

### Stats summary (video/channel count) moved to header; errors excluded
Stats injected via Flask context processor so they're available in all templates without route boilerplate.

**Implications**
- **+** Persistent visibility regardless of scroll position
- **+** Error count removed from casual display — less alarming for normal use
- **−** Stats are fetched on every request (one extra `COUNT` query); negligible cost

---

### Group by channel as primary ORDER BY
When "By channel" is selected, SQL `ORDER BY channel_name ASC, {sort_by} {sort_dir}` ensures all videos from a channel are contiguous.

**Implications**
- **+** Channel grouping is now meaningful — videos within a channel are sorted by the user's chosen field
- **−** A channel with more videos than `PAGE_SIZE` will still span pages; the group heading will not repeat on the next page

---

### Bookmarklet + `POST /api/add` endpoint
Firefox bookmarklet calls `http://localhost:8080/api/add`, fetches metadata via yt-dlp, inserts video, counts as a personal view.

**Implications**
- **+** Adds a video to ViewTube in one click while watching on YouTube
- **+** Bookmarklet use counts as a personal view (intentional — user is watching the video when they bookmark it)
- **+** "Already in ViewTube" response still increments personal view count
- **−** Blocks the HTTP request for 2–3 seconds while yt-dlp runs (acceptable for single-user; see `plan-production.md` for async path)
- **−** `POST /api/add` has no authentication — safe only on localhost; needs an API key for any networked deployment
- **−** Bookmarklet hardcodes `localhost:8080`; must be updated if port or host changes

---

### "Load more" replaces pagination in flat view; page size increased to 100
Grouped view retains Prev/Next. HTMX `beforeend` appends new cards; `hx-swap-oob` updates the button.

**Implications**
- **+** Casual browsing feels more natural — scroll and load rather than click through pages
- **+** 100 per page means most collections fit on one load
- **+** Grouped view keeps Prev/Next to avoid the complexity of appending across channel section boundaries
- **−** Browser DOM grows unboundedly as user loads more — could slow down on very large libraries
- **−** No way to deep-link to a specific page of results (URL doesn't update on load-more)

---

### Channels dropdown alphabetized
`ORDER BY channel_name` added to `get_all_channels` query.

**Implications**
- **+** Predictable, scannable list regardless of insertion order
- No downsides

---

## 2026-05-29

### Tag distillation Phase 3 — replaced suggestion engine with manual tag pool

The automated cluster suggestion engine was built and then replaced. The original approach (`tag_suggester.py`) grouped similar-looking tags via edit similarity + token Jaccard and presented them as "clusters to confirm". The user found this unintuitive: algorithmic clusters don't always match conceptual groupings, and there was no way to see the full unclassified set or pick an arbitrary subset.

**Replacement**: Tags page now shows an "Unclassified Tags" section — a scrollable pool of all non-canonical, non-aliased tags as checkbox pills. The user selects any combination they consider related, types a canonical name, and clicks "Assign selected". Selected tags become exact aliases of the canonical tag and vanish from the pool. Process repeats until the pool is empty.

`tag_suggester.py` is retained but not used in the main UI flow.

**Implications**
- **+** User has full visibility into all unclassified tags at once
- **+** No algorithm decides what "belongs together" — the user's domain knowledge drives grouping
- **+** Any subset of tags can be combined, including non-similar ones (e.g. merging `#shorts` and `short-video` even if their similarity score is low)
- **+** Pool shrinks as tags are classified — gives a clear sense of progress
- **−** Requires manual effort proportional to library size; automated clustering would have been faster for large libraries
- **−** No "suggest a name" based on the selection — user must type it themselves

---

### Tag distillation Phase 2 — retroactive pass and tag admin UI

`retroactive_apply(conn, alias_rule_id=None)` applies alias rules to all existing videos in a single SQL pass per rule (`INSERT OR IGNORE INTO video_tags SELECT ...`), returning the count of new associations. Five new db functions: `get_canonical_tags`, `create_canonical_tag`, `add_alias`, `delete_alias`, `retroactive_apply`. New `GET/POST /tags` admin page lists canonical tags with their aliases, a create form, and a "Re-apply all rules" button. Adding an alias auto-applies it retroactively immediately. Tags link added to nav.

**Implications**
- **+** Retroactive pass is a bulk SQL operation — efficient regardless of library size
- **+** Auto-applying on alias creation means the user sees results immediately without a separate step
- **+** "Re-apply all rules" with `?applied=N` feedback gives confidence the pass ran
- **−** Deleting an alias does not remove already-applied canonical tag associations — those remain in `video_tags` (intentional: non-destructive; Phase 3 could add a "revoke" option)

---

### Tag distillation Phase 1 — schema, `apply_aliases`, crawler and bookmarklet hooks

`tags` gains `is_canonical BOOLEAN NOT NULL DEFAULT 0`. New `tag_aliases (pattern, match_type, canonical_tag_id)` table supports `exact`, `prefix`, and `contains` matching (case-insensitive). `apply_aliases(conn, video_id)` in `webapp/db.py` checks a video's current tags against all alias rules and inserts matching canonical tag associations (idempotent). Hooked into `Datastore.upsert_video` (crawler) and `add_video` (bookmarklet). `add_video` now also stores raw `yt_tags`. `init_webapp_tables` migrates existing DBs via `ALTER TABLE`. Rules are entered manually via direct DB for now; Phase 2 adds a UI.

**Implications**
- **+** New videos automatically get canonical tags applied at ingest time — no manual backfill needed for future additions
- **+** Alias rules are additive and non-destructive — raw tags are preserved
- **+** `apply_aliases` is safe to call on a DB without the `tag_aliases` table (graceful no-op), so the crawler won't break on old DBs
- **−** Crawler now imports from `webapp.db` — cross-package dependency that slightly muddles the module boundary; acceptable for a monorepo but worth noting
- **−** No rules exist yet, so the feature is dormant until rules are entered directly in the DB

---

### Firefox extension Phase 1 — dual bookmark in one click

New `extension/` directory. A browser action popup that, on any YouTube video page, simultaneously creates a Firefox bookmark (in an auto-created "ViewTube" folder) and posts to `/api/add`. Both operations run in parallel via `Promise.allSettled`. On full success the popup shows the video title and auto-closes after 1.5 s. On partial failure it shows per-action status (green ✓ / red ✗). ViewTube URL defaults to `localhost:8080` and is readable from `browser.storage.local` so the Phase 2 options page can configure it without changing popup.js.

**Implications**
- **+** Single click replaces the bookmarklet + Ctrl+D workflow
- **+** Firefox bookmark survives even if ViewTube is unreachable; partial failure is clearly reported rather than silently dropped
- **+** Bookmark folder "ViewTube" keeps extension saves separate from regular bookmarks; folder ID is cached so subsequent opens don't re-search the bookmarks tree
- **−** No options page yet — ViewTube URL and bookmark folder are not user-configurable (Phase 2)
- **−** Icon is always visible in the toolbar regardless of whether the current page is YouTube (Phase 3 adds page-detection)
- **−** Must be loaded as a temporary add-on via `about:debugging`; permanent installation requires signing (Phase 2+ or web-ext sign)

---

### "By tag" grouping added to group select

Group select now offers "No grouping", "By channel", and "By tag". Tag grouping partitions the current page of videos by their canonical tags in Python; a video with multiple canonical tags appears under each. Groups are sorted alphabetically; videos with no canonical tags appear at the end in an "Untagged" section.

**Implications**
- **+** Lets the user browse by topic (e.g. see all "meal-prep" videos together) without leaving the main view
- **+** Videos appear in multiple groups when they have multiple canonical tags — useful for cross-topic content
- **−** Pagination is at the video level, not the group level — a group may be split across pages on large libraries
- **−** Groups only appear once canonical tags are assigned; before distillation everything lands in "Untagged"

---

### Canonical tags surfaced in filter bar and video cards

`get_all_videos` now uses `GROUP_CONCAT(CASE WHEN t.is_canonical = 1 THEN t.name ELSE NULL END)` so the `tags` field on each video row contains only canonical tag names (raw YouTube tags are preserved in the DB and still used for search, but are not displayed). A new `get_canonical_tags_for_filter` query returns canonical tag names that have at least one video associated. The toolbar gains a tag `<select>` dropdown (shown only when canonical tags exist) that filters via the existing `?tag=` param. Video cards gain canonical tag pills that link to `/?tag=<name>` for one-click filtering.

**Implications**
- **+** Tag filter and tag pills only show meaningful, curated tags — not the hundreds of raw YouTube tags
- **+** Clicking a tag pill is equivalent to using the tag filter dropdown — consistent and bookmarkable
- **+** Tag filter integrates cleanly with channel filter and search (all composed in `_build_where`)
- **−** Videos with no canonical tags show no pills — until the user distills their tag pool, cards look the same as before
- **−** Raw tags are still stored but invisible in the UI; there's no way to browse them without going to the Tags admin page

---

### Fix: FOREIGN KEY constraint failed when assigning tags to existing canonical tag

`retroactive_apply` queried all alias rules with a plain `SELECT ... FROM tag_aliases`. SQLite's `INSERT OR IGNORE` suppresses UNIQUE/PRIMARY KEY conflicts but **not** FK violations, so if any alias rule had an orphaned `canonical_tag_id` (e.g. from a manually-inserted row or a delete without cascade), the `INSERT OR IGNORE INTO video_tags` would fail. Fixed by joining `tag_aliases` with `tags` in the rules query, which naturally excludes any rule whose `canonical_tag_id` no longer exists. Also added `PRAGMA foreign_keys = ON` to the test DB connection so this class of bug is caught in future.

**Implications**
- **+** Orphaned alias rules are silently skipped rather than crashing the page
- **+** Tests now enforce FK constraints, matching the production connection settings
- **−** Orphaned rules are skipped silently — they won't surface in the UI; the user would need to inspect the DB directly to detect them

---

### `plan-production.md` created
Documents the path to hosted/multi-user deployment: WSGI, auth, database migration, background jobs, API key security.

**Implications**
- Informational only; no code changes

---

## 2026-05-29

### Compact metadata display: time-ago dates and K/M view counts

`format_date` now returns time-ago strings (`5d`, `2mo`, `3yr`, `today`) instead of `Jan 15, 2024`. `format_view_count` now uses suffix notation with up to 2 significant decimal places (`1.5K`, `12.35K`, `7.65M`) instead of comma-separated full numbers. The `_today` parameter on `format_date` allows tests to inject a fixed reference date rather than mocking `datetime.date.today`.

Boundary cases handled: values 999,500–999,999 that round K to `1000` are promoted to `1M`; dates 360–364 days ago display as `12mo` rather than `0yr`.

**Implications**
- **+** Metadata row is more scannable — dates and counts take less horizontal space
- **+** Time-ago is more useful than an absolute date for a personal library (you see recency at a glance)
- **−** Absolute dates are no longer visible without hovering or inspecting — could add a `title` tooltip for exact dates if needed
- **−** `12.35K` has four digits before the suffix — slightly longer than the common `12.3K` style, though accurate

---

### Phase 4b: LLM suggestion cards UI

The Tags page Unclassified section now shows LLM suggestion cards above the manual pool. A "Smart Suggest" button triggers the LLM run; it reads "Refresh Suggestions" when a fresh cache exists. If `ANTHROPIC_API_KEY` is not set or the `anthropic` package is absent, a notice replaces the button. API errors are shown inline as a red banner.

Each normal suggestion card has an editable canonical name field (pre-filled, autocompletes from existing canonicals), a confidence badge (green/amber/grey for high/medium/low), pre-checked member checkboxes the user can uncheck, and an Accept button that submits to the existing `confirm_suggestion` route. A dismiss button (×, positioned top-right) submits to the new dismiss route without affecting the pool. Noise tags get their own read-only card with a dismiss button. When the cache is fresh but the model returned no suggestions, a "pool looks well-organized" notice is shown instead.

**Implications**
- **+** Accept reuses the existing `confirm_suggestion` → `add_alias` → `retroactive_apply` pipeline — no new confirm logic
- **+** Member checkboxes let the user accept a suggestion partially (uncheck disagreements before submitting)
- **+** Canonical name is editable — the user can correct the LLM's proposed name before accepting
- **−** Accepting a suggestion card dismisses it implicitly (tags leave the pool), but the suggestion row stays in `llm_suggestions` until the next refresh — minor stale-row leak, harmless

---

### Phase 4a: LLM tag categorization backend

`webapp/llm_tagger.py` added with `get_suggestions`, `compute_pool_hash`, `is_available`, and `_build_user_message`. `get_suggestions` uses Anthropic's tool-use API with `tool_choice={"type":"tool","name":"categorize_tags"}` to guarantee structured JSON output — no regex parsing of freeform text. The `anthropic` package is lazily imported so the module always loads; `ImportError` surfaces only when a user actually triggers a suggestion run. Noise tags are returned as a single `{"canonical":"_noise","is_noise":True}` entry rather than individual entries. `compute_pool_hash` takes a SHA256 of the sorted tag name list (first 16 hex chars) for staleness detection.

`webapp/db.py` extended with `save_llm_suggestions`, `get_llm_suggestions`, `dismiss_llm_suggestion`, `is_llm_suggestion_cache_stale`, and the `llm_suggestions` DDL in `init_webapp_tables`. Noise suggestions sort last in `get_llm_suggestions`.

`webapp/routes.py` updated: `tags()` GET now passes `llm_available`, `llm_stale`, `llm_suggestions`, and `llm_error` to the template. New routes: `POST /tags/llm-suggest` (trigger LLM run) and `POST /tags/llm-suggest/<id>/dismiss`.

28 new tests across `test_llm_tagger.py` and `TestLLMSuggestions` in `test_db.py`. Tests mock `anthropic` via `sys.modules` injection (not `patch("anthropic.Anthropic", ...)`), allowing the full suite to run without the package installed.

**Implications**
- **+** Feature degrades gracefully: app starts, imports, and functions fully without `anthropic` installed or API key set
- **+** Structured output via tool use eliminates the need for prompt-engineering the response format
- **+** Staleness detection prevents stale suggestions from showing after new videos are added
- **−** UI for suggestion cards not yet built (Phase 4b) — backend is wired but the Tags page doesn't render suggestions yet
- **−** `anthropic` is not yet in `requirements.txt` (optional dependency, needs a comment or separate requirements file)

---

## 2026-06-04

## 2026-06-05

### Right-click to remove a canonical tag from a video card

Right-clicking any tag pill on a video card shows a "Remove from video" context menu. The removal is optimistic — the pill disappears from the DOM immediately via `fetch()` with no page reload. The route (`POST /videos/<video_id>/tags/remove`) deletes the specific `video_tags` row; it does not touch the alias rules, so the tag can be re-applied by "Re-apply all rules" if removed by mistake.

Note: if the association was created by an alias rule, removing it here only removes the one video's association — the alias rule itself is unchanged and will re-associate on the next retroactive apply. This is intentional: removal on the video card is a per-video override, not a rule edit.

### Fix: bookmarklet-added videos now get canonical tags immediately

`/api/add` now calls `retroactive_apply(video_id=<new_video_db_id>)` after a successful fetch. Previously, bookmarked videos only received canonical tag assignments after a manual "Re-apply all rules" click on the admin page.

The call is scoped to the single new video (all 3,200 alias rules run, but only against the one video's tags) rather than a full library-wide pass, so the bookmarklet response time is negligible.

`retroactive_apply` gained an optional `video_id` parameter for this scoping; the existing full-pass and single-alias-rule modes are unchanged.

### Co-occurrence suggestions when selecting unclassified tags

Checking any pill in the unclassified pool fires an HTMX request to `GET /tags/related?tag=<name>`, which returns the top 20 unclassified tags that most frequently appear on the same videos. Results render in a green-tinted suggestion strip above the pool, pre-checked so they're included in the next "Assign selected" submission. Checking a different pill replaces the strip with suggestions for the new tag.

The co-occurrence query joins `video_tags` against itself, filtered to unclassified/non-noise tags, ordered by shared video count. No suggestions are shown if nothing is checked or if no co-occurrences exist.

**Implications**
- **+** Dramatically speeds up grouping sessions — one click surfaces the natural cluster around a tag
- **+** Pre-checked by default so the workflow is: check one tag → review suggestions → uncheck any outliers → assign
- **−** Suggestions are for the most recently checked tag only; no multi-tag intersection query
- **−** Suggested tags may already be checked in the main pool; submitting with duplicates is harmless (alias insert uses INSERT OR IGNORE)

### Right-click "Mark as noise" on unclassified pool tags

Right-clicking any pill in the unclassified tag pool shows a context menu with a single "Mark as noise" option. This sets `is_noise = 1` on the tag, removing it from the pool immediately and permanently — including across future re-crawls (the crawler uses `INSERT OR IGNORE`, so the existing row with `is_noise=1` is preserved). The `video_tags` associations are kept intact; the tag is hidden, not deleted.

Hard delete was not implemented: the crawler would re-add a hard-deleted tag on the next crawl, making the operation pointless. Noise-marking is the durable solution.

New route: `POST /tags/noise` with `tag_name`. New DB function: `mark_tag_noise`.

### Canonical tag merges: stand-up comedy, dog, quick meals

- `stand-up comedy` → `comedy`: stand-up comedy was a near-duplicate (comedy already had "stand up"/"standup" aliases covering the same content); comedy gains 24 aliases, 54 total
- `dog` → `dog training`: dog was a 2-alias stub; all content is already covered by dog training
- `quick meals` → `budget cooking`: quick meals is a cooking-angle subset of the same goal; budget cooking gains 12 aliases and grows to 39 videos

64 → 61 canonical tags. Removed demoted tags from their tag groups (Cooking & Food, Comedy & Entertainment).

### Alias delete now cleans up video associations

`delete_alias_with_cleanup` replaces the bare `delete_alias` call in the alias delete route. When an alias pill is deleted, the function: (1) finds all videos that matched that alias pattern, (2) deletes the alias rule, (3) checks which of those videos are still covered by any remaining alias for the same canonical, and (4) removes `video_tags` rows for videos that are no longer covered by anything. Videos that also match another alias for the same canonical are unaffected.

**Implications**
- **+** Delete now means what it looks like — the raw tag no longer contributes to that canonical
- **+** Recoverable: `retroactive_apply` will restore associations if the alias is re-added
- **−** Can't delete an alias while preserving its video coverage (would need a separate "detach alias only" action)

### Tag groups + merge cooking / cooking recipes

**Merge**: folded "cooking recipes" (743 aliases) into "cooking", giving a single canonical with 1,117 aliases and 832 videos. The "cooking recipes" canonical is demoted (raw tag preserved); the distinction between recipe and technique content was not useful for filtering.

**Tag groups** (`tag_groups` + `tag_group_members` tables): a display-only organizational layer over canonical tags. Groups appear as `<optgroup>` sections in the main tag filter select — no changes to the underlying filtering logic or video-tag associations. Ungrouped canonicals continue to appear as flat options at the end of the select.

Admin UI (new section on `/tags` page): create/delete groups, add/remove canonical members via hover-× pills. Four new routes: `POST /tags/groups`, `POST /tags/groups/<id>/delete`, `POST /tags/groups/<id>/members`, `POST /tags/groups/<id>/members/<tag_id>/delete`.

**Implications**
- **+** Tag select goes from a flat 67-item list to labelled sections once groups are defined — much faster to navigate
- **+** No query changes: filtering by a canonical tag works identically; groups are pure presentation
- **+** Canonicals can belong to zero or multiple groups (edge case, but possible)
- **−** Page reloads to the top after each group edit (consistent with the rest of the admin page)
- **−** Group membership isn't shown on the canonical tag cards — need to go to the group card to see/edit membership

### Alias pills with right-click context menu on canonical tags admin page

Replaced the flat `<ul>` alias list in each canonical tag card with a flex-wrap pill row. Right-clicking any pill shows a floating context menu (vanilla JS, single shared `<div>`, no library) with Edit and Delete actions.

- **Edit**: replaces the pill inline with an `<input>` + match-type `<select>` + Save/Cancel. Cancel restores the original pill without a round-trip. Save POSTs to the new `POST /tags/<tag_id>/alias/<alias_id>/edit` route, which calls `edit_alias` (UPDATE tag_aliases) and runs `retroactive_apply` for the modified alias only.
- **Delete**: submits a hidden form POST to the existing delete route.

Pill visual conventions: no border = exact (default), solid border = prefix, dashed border = contains. Context menu dismisses on click-outside or Escape.

**Implications**
- **+** Alias list is visually compact — cards with 100+ aliases are now scannable instead of a wall of list items
- **+** Edit is in-place; no navigation to a separate page
- **−** Page reloads to the top after Save/Delete (consistent with existing form-POST pattern throughout the admin page); no scroll-position restoration
- **−** Right-click is not discoverable on mobile or for users who don't expect it; there is no hover affordance indicating the pills are actionable

### Tag distillation take 2: `is_noise` schema + CLI categorization tool (Phase 5a–5d)

Rethought the bulk categorization workflow after the web-based manual pool and LLM suggestion cards proved intractable at 28K unclassified tags. Key insight: 82% of tags appear on exactly one video (long-tail publisher noise) and only ~630 tags appear on 5+ videos (the real vocabulary). The new approach tiers the work accordingly.

**Schema change**: `is_noise BOOLEAN NOT NULL DEFAULT 0` added to `tags` in both `crawler/datastore.py` `_SCHEMA` and via `ALTER TABLE` migration in `init_webapp_tables`. Noise tags keep all `video_tags` associations (preserving data) but are excluded from the unclassified pool (`get_unclassified_tags` now filters `AND t.is_noise = 0`). This replaces the previous `_noise` canonical approach — no special-cased canonical pollutes the canonical tag list.

**CLI tool** (`tools/tag_categorizer.py`) with five subcommands:
- `stats` — tag counts broken down by frequency bucket
- `noise [--dry-run]` — pattern-based auto-marking of YouTube category strings, year numbers, hashtags, quality/format descriptors, and generic filler; zero user interaction
- `suggest [--min-videos N] [--batch-size N] [--model M]` — LLM categorization pass with video-context enrichment: each candidate tag is sent with titles of the videos it appears on, giving the LLM substantially better signal than tag names alone; outputs `proposals.json`
- `review PROPOSALS_FILE` — interactive terminal loop: per-proposal approve / rename / edit members / skip; outputs `approved.json`
- `apply APPROVED_FILE [--db PATH]` — writes canonical tags, alias rules, and noise flags to DB; runs retroactive apply; defaults to `viewtube-test.db` so the live DB is never touched accidentally

`plan-tag-distillation-v2.md` created documenting the new strategy, frequency tier analysis, and rationale for CLI-over-webapp approach.

**Implications**
- **+** Reviewing ~30–60 proposed canonical concepts is tractable; reviewing 630 individual tags was not
- **+** Video title context in the LLM prompt dramatically improves assignment accuracy vs. tag-name-only prompts
- **+** Default DB is `viewtube-test.db` — no path to accidentally writing the live DB without `--db viewtube.db`
- **+** Auto-noise pass requires zero review and immediately handles YouTube category strings appearing on hundreds of videos
- **+** Existing webapp manual pool and Smart Suggest remain intact for ongoing maintenance as new videos arrive
- **−** Single-video long-tail tags (23K) are left unclassified — intentional for now; browseable on demand but not processed
- **−** The `_noise` canonical approach (used in llm_tagger.py) is now superseded but the `_noise` canonical and `llm_suggestions` table still exist; should be cleaned up in a future pass

### Canonical tag cleanup pass

Cleaned up the canonical tag list after the initial bulk categorization run. Changes to the live DB:

- **Merged duplicates**: `meal-prep` → `meal prep`, `vocal-reacts` → `vocal reaction & analysis`, `flightsim` → `flight simulation (general)`. Aliases and video associations consolidated into the winner; loser canonical demoted (raw tag preserved).
- **Renamed**: `dev` → `programming & tech talks`. The name was a CLI artifact; the 32 aliases and 200 videos represent tech conference talks and general programming content.
- **Deleted**: `sat bawl pro` and `weeds and sardines` — both were garbled/channel-specific single-alias canonicals whose videos are already covered by cooking and meal-prep canonicals.
- **Deleted alias**: removed `basic` from `calligraphy` — it was a spurious alias that matched unrelated content. The canonical itself (16 videos) is still intact via the raw "calligraphy" tag.
- **Deleted**: `maker` (1 video) and `science` (9 videos, all covered by algorithms/software-engineering canonicals).

Result: 72 → 67 canonical tags.

**Implications**
- **+** No duplicate concepts in the filter sidebar
- **+** Flight sim, meal prep, and vocal reaction content now unified under single canonicals with full alias coverage
- **−** `calligraphy` now has 0 aliases — only exact-match "calligraphy" raw-tag videos are captured; alternate spellings/phrasing would need explicit alias additions

### Unclassified tag pool: minimum video threshold

`get_unclassified_tags` gained a `min_videos: int = 2` parameter. The single-video long-tail (23K tags) is now excluded from the webapp pool entirely — only tags used on 2+ videos appear. Previously the pool showed up to 500 of the top tags by count, which after the categorization pass still surfaced hundreds of 2-4 video tags as an overwhelming checkbox cloud.

**Implications**
- **+** Pool is scoped to tags actually worth reviewing (2+ videos = appears across multiple pieces of content)
- **+** 23K single-video publisher tags are hidden without being deleted — still queryable directly if needed
- **−** Tags that appear on only one video are no longer reachable via the webapp pool; must be handled via the CLI `suggest --min-videos 1` or direct DB query

---

### Group assignment pass: 15 canonicals placed

First run of the auto-assign feature. LLM proposed 9 assignments; `darts → Comedy & Entertainment` was rejected (wrong category). 7 additional obvious placements were applied manually that the LLM left ungrouped due to conservative confidence.

Final placements: angular, keyboard shortcuts, mac, password manager, productivity, Testing, virtual team, network attached storage (nas) → Programming & Tech; calligraphy, dog training, security camera → DIY & Making; country → Music; steak, sous vide → Cooking & Food; The Cardinal Hour → Bands & Artists.

4 canonicals intentionally left ungrouped: `chess`, `darts`, `trivia`, `stargazing` — no existing group fits cleanly.

---

### Auto-assign ungrouped canonicals to tag groups

"Auto-assign N ungrouped" button appears in the Tag Groups section header whenever there are canonical tags not in any group and `ANTHROPIC_API_KEY` is set. Clicking it makes a single LLM call (Haiku) with the full list of ungrouped canonicals (name, video count, top 5 aliases) and all existing groups (with their current members shown as examples). The LLM assigns each canonical to a group or leaves it ungrouped. Assignments are applied immediately; a success notice shows how many were placed.

New `GET /tags/groups/auto-assign` route, `get_ungrouped_canonicals` db function, and `suggest_group_assignments` in `llm_tagger.py`. The tags route now computes and passes `ungrouped_count` and `assigned_groups` to the template.

**Implications**
- **+** After every `tag_categorizer.py apply` run or manual canonical creation, one click cleans up the group backlog
- **+** LLM sees existing group members as examples, so it infers group theme correctly even for ambiguously named groups
- **+** Wrong auto-assignments are trivially corrected via the existing remove button on each group card
- **−** Button is hidden when `ANTHROPIC_API_KEY` is absent — no fallback heuristic for offline use
- **−** No review step — assignments apply directly; deliberate given low stakes of group membership

---

### Related tags section: additive across multiple selections, clears on deselect

Replaced the HTMX-based "Related to" suggestions with a JS accumulator. Previous behavior: each checkbox check replaced the entire suggestions strip with results for only that tag; unchecking did nothing.

New behavior:
- **Deselect clears**: unchecking a pool tag removes its contribution from the suggestions; if no tags remain checked, the strip disappears
- **Additive**: checking a second tag merges its related tags into the existing strip — union of all checked tags' co-occurrences, deduped (highest shared count wins). Label updates to "Related to N selected tags:"
- **Dismissals persist within the session**: a tag dismissed with × is excluded from future recomputes until the page reloads, even if more pool tags are checked
- **Cached per tag**: results are fetched once per page load and reused on subsequent check/uncheck

`/tags/related` now returns JSON (`[{name, shared}]`) instead of an HTML partial; `_tag_related.html` is no longer rendered. All suggestion rendering is client-side.

**Implications**
- **+** Checking a cluster of related tags (e.g. "garageband", "GarageBand", "Logic Pro") shows their combined co-occurrence neighborhood in one strip
- **+** Deselecting a mistaken check immediately trims suggestions without a reload
- **−** `_tag_related.html` is now dead code (route still exists but returns JSON); file should be deleted in a cleanup pass

---

### Right-click pool tag shows associated video titles

Right-clicking a pill in the unclassified tag pool now shows the top 10 video titles (by YT view count) for that tag in the context menu, above the "Mark as noise" button. Titles are fetched via `GET /tags/pool-videos?tag=<name>` on demand — nothing is pre-loaded. A "Loading…" placeholder appears while the fetch resolves; the menu repositions after titles render to stay on screen.

New db function: `get_video_titles_for_tag`. New route: `GET /tags/pool-videos` (returns JSON). Pool context menu widens to 260–360 px; title list scrolls at 200 px max-height.

**Implications**
- **+** Solves the core categorization problem: ambiguous tag names (e.g. `garageband`, `aurora`, `alternative`) can now be evaluated without leaving the page
- **+** On-demand fetch keeps the page fast regardless of pool size
- **−** Titles truncated to one line (ellipsis) — very long titles need a hover tooltip if precision matters

---

### Tag categorization pass: 338 new aliases, 2 new canonicals, 5 noise

Ran `suggest → review → apply` pipeline against the 634 unclassified tags with 2+ videos. Results after apply + retroactive pass:

- **338 alias rules** added across existing canonicals (object oriented → software engineering, acoustic cover → guitar, etc.)
- **2 new canonicals** created: `the cardinal hour` (added to Bands & Artists group) and `garageband` (added to Music group); both promoted from existing raw tags
- **5 noise tags** marked: `trick`, `tricks`, `Tricks`, `Tutorial`, `Revealed` — too generic to assign anywhere, remnants of the vintage cameras alias cleanup
- **177 new video associations** from the main batch; 21 additional from the cleanup fixes
- Unclassified 2-4 video pool: 620 → 286; 5+ video pool: 14 → 2 (remaining: `science` and `weeds and sardines`, both deleted-canonical remnants)

**Implications**
- **+** `object oriented`, `SOLID`, `design patterns`, and similar programming tags now resolve to `software engineering / clean code`
- **+** Acoustic covers, session recordings, and alternate artist name spellings now resolve to existing music/guitar canonicals
- **+** Tag filter and video card pills are meaningfully richer for recently added videos
- **−** 286 tags at 2-4 videos still unclassified — a follow-up suggest pass with `--min-videos 2` will close the gap further as the library grows

---

### False positive cleanup: `vintage cameras` + new `watch repair` canonical

**Problem**: `vintage cameras` had 11 generic aliases (`Tutorial`, `Amazing`, `Trick`, `Tricks`, `trick`, `tricks`, `Revealed`, `revealed`, `control`, `secret`, `film`) that matched 174 unrelated videos — cooking tutorials, dog training, guitar lessons, board game videos, etc. Additionally, watch-repair videos belonged to a conceptually separate cluster inside the same canonical.

**Changes made to the live DB**:
- Deleted 11 generic aliases that caused false positives
- Moved 5 watch-repair aliases (`watches`, `watch repair`, `watch fixing`, `serviced`, `horology`) to a new `watch repair` canonical
- Cleaned up 174 orphaned `video_tags` rows that were no longer covered by any remaining alias for `vintage cameras`
- Ran `retroactive_apply` — 3 watch-repair videos correctly assigned to `watch repair`; vintage cameras dropped from 188 to 15 videos

The cleanup was done via direct SQL (bulk alias deletion) rather than the admin UI, so the standard `delete_alias_with_cleanup` route was not called. The orphan cleanup was performed manually with a `WITH covered_videos AS (...)` CTE.

**Implications**
- **+** `vintage cameras` is now a precise canonical (15 videos, all camera-related content)
- **+** Watch-repair content has its own canonical — browseable independently via the tag filter
- **−** Watch-repair aliases were moved, not copied — any alias still in `vintage cameras` will not match watch-repair content (which is correct)
- **−** Bulk SQL alias deletion bypasses `delete_alias_with_cleanup`; future bulk cleanups need a matching manual orphan-cleanup query or a dedicated bulk-delete script

---

## 2026-06-06

### Hide / Delete Video Feature (all 4 phases)

Full hide-and-delete workflow across the webapp, API, and Firefox extension.

**Phase 1 — Schema + DB layer**

Added `is_hidden BOOLEAN NOT NULL DEFAULT 0` to the `videos` table (crawler schema + webapp migration). New DB functions: `hide_video`, `unhide_video`, `delete_video`, `get_hidden_videos`, `count_hidden_videos`. `_build_where` now includes `AND v.is_hidden = 0` so hidden videos are invisible in all index views. `get_stats` counts only visible videos for `total_videos`/`total_channels` and adds `hidden_count`. The crawler's `ON CONFLICT DO UPDATE SET` does not touch `is_hidden` — the flag survives re-crawls safely.

**Phase 2 — Routes + hidden management page**

New routes:
- `POST /videos/<id>/hide` → 204 (used by right-click JS and extension)
- `POST /videos/<id>/unhide` → redirect to `/hidden`
- `POST /videos/<id>/delete` → redirect to `/hidden`
- `GET /hidden` — paginated management page with Restore and Delete buttons per card
- `GET /api/status?url=` — returns `{status: not_found|exists|hidden, video_id, title}`; CORS-enabled
- `POST /api/hide` — hides by URL, CORS-enabled; used by extension

`POST /api/add` now returns `{status: "hidden"}` when the video already exists in a hidden state, so the extension can show the correct UI without a separate status check.

A shared `_CORS_HEADERS` constant replaces per-route dicts for the API endpoints.

`base.html` nav shows a "Hidden (N)" link (amber colour) when `stats.hidden_count > 0` — the only persistent signal that hidden videos exist.

**Phase 3 — Right-click card menu**

`_video_card.html` gains `data-video-id` on `.video-card`. `index.html` adds `#video-card-menu` alongside the existing `#tag-pill-menu`. The single `contextmenu` listener now handles both menus: tag-pill right-clicks take priority; falling through to the card only if no pill ancestor exists. Hiding a card via the menu sends `POST /videos/<id>/hide` and removes the card from the DOM optimistically.

**Phase 4 — Extension popup redesign**

`popup.html` reduces to `<div id="root">`. `popup.js` is a full rewrite: on open it calls `GET /api/status` first, then renders one of three states:
- **not_found** — single "Add to ViewTube" button (parallel bookmark + api/add, auto-close on success)
- **exists** — title confirmation, "Hide from ViewTube" button, opt-in "Also remove browser bookmark" checkbox
- **hidden** — "⊘ Hidden: title", "Restore to ViewTube" + "Delete permanently" buttons

The `getOrCreateFolder()` call is lazy — only called in the add path. The extension no longer auto-adds on open; hide/restore/delete are now explicit user actions.

**CSS additions** (webapp): `.hidden-actions`, `.btn-restore`, `.btn-delete`, `.empty-state`, `.nav-hidden`. Extension popup: `.action-btn`, `.action-btn--danger`.

**Test count**: 310 → 333 (+23 new route tests across `TestHideRoute`, `TestHiddenPage`, `TestApiStatus`, `TestApiHide`, `TestApiAddHiddenVideo`).

**Implications**
- **+** Videos can be soft-deleted without losing tags, view history, or channel data — reversible from `/hidden`
- **+** Hard delete is a second deliberate step from a dedicated management page; no accidental losses
- **+** Extension shows the actual video state before acting — no more silent re-adds of already-saved videos
- **+** "Also remove browser bookmark" is opt-in; leaving it unchecked preserves the Firefox bookmark even when hiding from ViewTube
- **−** Browser bookmark removal is only possible from the extension — the `/hidden` page has no access to the browser bookmark API (accepted limitation, option 1)
- **−** No `date_hidden` column — hidden list sorts by `date_added`; most-recently-hidden videos are not necessarily at the top
- **−** Extension's Restore/Delete from the hidden state do not offer bookmark re-creation or removal (option 1 scope)

---

### Fix: Smart Suggest shows nothing when LLM returns no assignments

Two bugs caused "nothing happens" after clicking Smart Suggest:

**Bug 1 — Staleness false positive on empty results**: When the LLM put everything in `unassigned` (no `assignments`, no `noise`), `save_llm_suggestions` was called with `[]`, which deleted all rows and inserted nothing. On the next GET, `is_llm_suggestion_cache_stale` saw an empty table → returned `True` (stale) → the template showed neither suggestions nor the "pool looks well-organized" message. The page looked identical to before the click.

Fix: `save_llm_suggestions` now always inserts at least one row — a `_run_marker` sentinel when the list is empty — so the staleness check can distinguish "never run" from "ran and found nothing." `get_llm_suggestions` filters out the sentinel row.

**Bug 2 — No loading feedback**: The POST form triggered a synchronous LLM call (~10 s) with no visual indicator. Fix: JS disables the button and changes its label to "Thinking…" on submit.

**Implications**
- **+** "No grouping suggestions — pool looks well-organized." now correctly appears after a run with no results
- **+** The button label correctly changes to "Refresh Suggestions" after any run (including empty)
- **−** The sentinel row is a mild schema hack — could be replaced with a dedicated `llm_runs` metadata table if the suggestions table grows more complex

---

### Case-collapse tags — normalize all tag names to lowercase

**Problem**: YouTube metadata tags arrive in inconsistent casing ("cooking" vs "Cooking", "blues guitar" vs "Blues Guitar" vs "BLUES GUITAR"), creating separate rows that split video associations and inflate the unclassified pool with what are effectively duplicates. `viewtube-test.db` had 1,604 case-duplicate groups (1,750 redundant tag rows) plus 4,269 single-variant mixed-case tags.

**Changes**:

- `collapse_case_variants(conn)` — new migration function in `webapp/db.py`. For each case-duplicate group, picks a winner (canonical > most video associations > lowest id), merges `video_tags`, `tag_keywords`, `tag_aliases` (as canonical target), and `tag_group_members` from all losers into the winner, deletes losers, then lowercases the winner's name. Finishes with a bulk `UPDATE tags SET name = LOWER(name)` to catch single-variant mixed-case names. Called from `init_webapp_tables` on every startup (idempotent — second run finds nothing to merge).

- `create_tag`, `create_canonical_tag`, `add_video` (yt_tags loop) — all now lowercase tag names before insert.
- `crawler/datastore.py` `add_tag` — lowercases before insert, preventing re-accumulation after each crawl.
- `add_alias`, `edit_alias` — lowercase patterns on write. (Alias matching already lowercased both sides at query time, so this is a storage consistency fix rather than a behaviour change.)
- `get_unclassified_tags` pool exclusion — changed `t.name NOT IN (SELECT pattern FROM tag_aliases)` to `LOWER(t.name) NOT IN (SELECT LOWER(pattern) FROM tag_aliases)` to correctly exclude aliased tags regardless of stored casing.

**Migration result on `viewtube-test.db`**: 28,154 → 26,404 tags (−1,750 rows merged); 4,269 single-variant mixed-case names lowercased. Unclassified pool (≥2 videos): 171 → 1,077 (previously undercounted — many case-split variants now combine into one entry above the threshold).

**Implications**
- **+** Unclassified pool is now accurate — "cooking" and "Cooking" appear as one 873-video entry instead of two ~430-video entries
- **+** Re-crawling the same videos no longer re-creates mixed-case duplicates
- **+** Alias matching already used lowercase; storage now matches
- **−** All existing tag display (pills, filter dropdown, pool checkboxes) is now lowercase — entirely cosmetic
- **−** The pool jumped from 171 to 1,077 entries, since many tags that appeared separately below the 2-video threshold now combine above it — more distillation work to do

---

### Fix: Smart Suggest ignores most of the pool due to ordering and cap

**Root cause**: The unclassified pool was sorted alphabetically and capped at 200 tags sent to the LLM. With 1,077 tags in the pool post-case-collapse, tags at positions 201+ (including all guitar-related tags at ~position 419) were never sent to the model. The LLM saw only alphabetically-early tags (numbers, A–C), declared the pool well-organized, and returned nothing.

**Changes**:
- `get_unclassified_tags` ordering changed from `name ASC` to `video_count DESC, name ASC` — highest-impact tags appear first in both the UI pool display and the LLM prompt.
- `MAX_TAGS` raised 200 → 500 in `llm_tagger.py`.
- `max_tokens` raised 1024 → 4096 to accommodate larger structured responses.

**Also fixed**: `the cardinal hour` and `garageband` were `is_canonical=0` with no aliases in `viewtube-test.db` — canonical work from earlier sessions had been applied to a different database file. Corrected directly.

**Implications**
- **+** Smart Suggest now sees the 500 most-used unclassified tags — far more representative of what's worth classifying
- **+** Pool UI shows highest-count tags first, matching the order the LLM prioritizes
- **−** With 1,077 tags, even 500 doesn't cover everything; a second run will cover the next 500 (cached results cleared when pool changes after accepting suggestions)
- **−** Larger prompts mean slightly higher per-run cost (Haiku is cheap, so negligible in practice)

---

### Fix: `add_alias` crash when pattern already owned by another canonical

**Root cause**: `tag_aliases` has a UNIQUE constraint on `(pattern, match_type)` only — not including `canonical_tag_id`. When Smart Suggest calls `confirm_suggestion`, it calls `add_alias` for each member tag. If a member's name was previously added as an alias for a *different* canonical, the `INSERT OR IGNORE` is silently skipped, but the subsequent `SELECT ... AND canonical_tag_id = ?` finds nothing and returns `None`, causing `row[0]` to crash with `TypeError: 'NoneType' object is not subscriptable`.

**Changes**:
- `add_alias`: removed `AND canonical_tag_id = ?` from the SELECT — queries by `(pattern, match_type)` only, which is what the UNIQUE constraint actually enforces.
- `add_alias`: return type changed `int` → `Optional[int]`; returns `None` when row unexpectedly missing.
- `confirm_suggestion` and `tag_add_alias` route: guard `retroactive_apply` call with `if alias_id is not None`.

**Implications**
- **+** Accepting a Smart Suggest grouping no longer crashes when a member overlaps with an existing alias
- **−** If a pattern belongs to a different canonical, `retroactive_apply` is silently skipped for that member — the alias already exists and points to the other canonical, so no action is taken (correct behavior)

---

### Fix: Smart Suggest member tags show "No titles found" on right-click

The LLM suggestion cards rendered member tags as `<label class="pool-tag">` without a `data-tag-name` attribute. The right-click context menu handler reads `label.dataset.tagName` to construct the `/tags/pool-videos?tag=` fetch — without the attribute the value is `undefined`, returning no results.

Added `data-tag-name="{{ m | e }}"` to suggestion member labels to match the pool section.

**Implications**
- **+** Right-click on Smart Suggest members now shows associated video titles, matching pool tag behavior
- **−** None

---

### Smart Suggest: removable member pills before accepting

Each member pill in a Smart Suggest card now shows a `×` button on hover. Clicking it removes the pill from the card (unchecking the underlying checkbox), so only the remaining members are submitted when Accept is clicked.

**Implications**
- **+** Users can trim bad members from a suggestion without dismissing the whole card
- **−** Removal is not reversible within the card — dismiss and re-run Smart Suggest to get the original suggestion back

---

### Fix: Smart Suggest crashes with `LLM error: 'canonical'`

`get_suggestions` accessed `item["canonical"]` directly, raising `KeyError: 'canonical'` when the LLM returned an assignment object missing that field (despite it being declared `required` in the tool schema — the model occasionally omits it). Changed to `item.get("canonical", "").strip()` and skip the item if empty.

**Implications**
- **+** A partial LLM response no longer aborts the entire suggestion run — valid assignments are still saved
- **−** Any assignment without a canonical name is silently dropped (the correct behavior — there's nothing to do with it)

---

### Smart Suggest: keyword-expansion pool selection

Previously the LLM received the top 500 unclassified tags by video count. Tags like "garageband for beginners" (rank 1,075, 2 videos) were never seen even though "garageband tutorial" (rank 4, 7 videos) was, making it impossible for the LLM to group them.

New strategy: take the top 300 tags as anchors, extract significant words from their names (filtering out generic terms like "tutorial", "guide", "beginner"), then fill the remaining 200 slots with tags from anywhere in the pool that share those words. `_EXPANSION_STOP_WORDS` prevents generic words from creating spurious connections.

Example: "garageband tutorial" (anchor, rank 4) yields the expansion word `garageband`, which pulls in all 50+ garageband-prefixed tags regardless of individual video count.

**Implications**
- **+** Related tag families now appear together in the LLM prompt, enabling better grouping suggestions
- **+** "garageband for beginners" and "garageband noob" (rank 1,075) are now included when "garageband tutorial" is an anchor
- **−** Satellite selection is first-come-first-served within the 200 remaining slots; if many families share words with anchors, some satellites are excluded (but they'll be captured on a subsequent run as the pool shrinks)

---

### Smart Suggest: persistent rejection of bad-fit members

Removing a pill before accepting a suggestion now records a permanent rejection: the `(member_tag, canonical)` pair is stored in `llm_suggestion_rejections` and filtered out of all future suggestion displays.

- Removing a pill from a grouping card and clicking Accept → records that member as rejected for that canonical (won't be suggested under it again)
- Removing a pill from a noise card and clicking Mark all as noise → records that member as rejected for `_noise` (won't be suggested as noise again)
- Dismissing a card with × does **not** record rejections — that means "not now," not "bad fit"

`get_llm_suggestions` filters rejected members from stored suggestions at read time, so rejections apply immediately to the current batch too. If all members of a suggestion are rejected, the card is suppressed entirely.

**Implications**
- **+** The LLM's suggestions improve over time as bad pairings are filtered out
- **+** Rejections survive Smart Suggest re-runs — they're stored independently of the suggestion cache
- **−** No UI to view or undo rejections yet; they can be cleared directly from `llm_suggestion_rejections` in SQLite if needed

---

### Smart Suggest noise cards: "Mark all as noise" button

The noise suggestion card previously only offered a dismiss (×) button, which removed the card but left the tags in the unclassified pool. To actually mark them as noise required right-clicking each tag individually.

Added a "Mark all as noise" button to the noise card header. Accepting it marks every member tag as `is_noise = 1` in one bulk UPDATE and dismisses the suggestion.

**Implications**
- **+** One click clears an entire noise batch from the pool
- **−** No undo — marking as noise is currently irreversible through the UI

**2026-06-07 update**: Fixed two issues with the noise card:
- "Mark all as noise" button was crowding the × dismiss button — fixed with `margin-right: 1.8rem` pushing it clear of the absolute-positioned ×
- Pills are now removable before accepting: each pill has a hover-reveal × button that removes it (and its hidden form input) so only remaining pills are submitted
