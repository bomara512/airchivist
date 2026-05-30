# ViewTube Changelog

Decisions are listed chronologically. Dates before 2026-05-28 are approximate — the project was built across multiple sessions without recorded timestamps.

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
