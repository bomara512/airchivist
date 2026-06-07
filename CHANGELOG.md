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
