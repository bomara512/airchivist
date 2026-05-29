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

### Tag distillation Phase 3 — suggestion engine

`webapp/tag_suggester.py` clusters similar tags using union-find: pairwise similarity is `max(edit_similarity, token_jaccard)` with a default threshold of 0.6. `get_suggestions(conn)` queries non-canonical, non-aliased tags and returns clusters. `confirm_suggestion` creates a canonical tag, adds exact aliases for all cluster members, and retroactively applies. Tags page shows a "Suggested clusters" section when any exist — each cluster shows member pills, a name input, and "Create & apply".

**Implications**
- **+** No external dependencies — `difflib.SequenceMatcher` and set operations only
- **+** Already-aliased tags are excluded from suggestions so processed clusters don't resurface
- **+** On-demand computation is fine at personal-library scale (≤500 tags ≈ 250K comparisons, well under 1 second)
- **−** All cluster-generated aliases use `exact` match type — user may need to manually adjust to `prefix`/`contains` for broader coverage
- **−** No "dismiss" option — unwanted suggestions reappear on every page load until the tags are aliased or the threshold is raised

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

### `plan-production.md` created
Documents the path to hosted/multi-user deployment: WSGI, auth, database migration, background jobs, API key security.

**Implications**
- Informational only; no code changes
