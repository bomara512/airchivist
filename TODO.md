# Airchivist TODO

## High priority

- ~~Watch Later queue — ordered list of videos to watch next, browse on dedicated page, add from main list or rediscover shelf~~
- ~~"Watched" toggle — mark a video as fully watched without clicking through to YouTube~~
- ~~"Unwatched only" filter (is_watched = 0)~~
- ~~Sort by unwatched first~~
- ~~Date range filter (e.g. added in the last 30 days)~~
- ~~Duration filter (short < 5 min, medium, long > 20 min)~~
- [ ] Auto-schedule the crawler (launchd / cron)
- [ ] Way to refresh YouTube metadata (e.g. view count) for existing videos

## Discovery

- [ ] Surface old content — random video button (related to rediscover shelf)
- [ ] "More like this" button on video cards
- ~~Rediscover shelf — least recently viewed videos, 20 random from pool, sticky for 7 days, manually refreshable~~
- [ ] "Continue watching" section — videos started but not finished (requires progress tracking)
- ~~Minimize the Rediscover panel when the main list is filtered~~
- [ ] Per-channel Rediscover shelf — when filtered to a single channel (e.g. arrived via the channels listing), surface that channel's own rediscover pool instead of just collapsing the shelf. *(Future, brainstorm-only: a per-channel Rediscover shelf mirroring the global rediscover feature — not scoped yet.)*

## Organization

- ~~Unify video card UI and functionality — single `_video_card.html` used across main list, rediscover shelf, and watch-later page~~
- ~~Drag-to-reorder watch-later queue (DB function `reorder_watch_later` exists; needs a JS drag library wired up)~~
- ~~Extension: toggle watch-later membership at any time (not just on initial add) — button should add if absent, remove if already queued~~
- ~~Extension: mark a video as favorite (★) at capture time — so a standout video can be starred the moment it's added to Airchivist, not just later from the web UI~~
- ~~Extension: toggle favorite status on a video already in Airchivist (not just at capture time) — mirrors how the watch-later toggle grew from add-time-only to anytime~~
- [ ] Rediscover shelf countdown timer — currently shows static "expires in X days" at page load; could refresh periodically
- [ ] Notes field per video — freeform text to add while watching
- [ ] Playlists / collections — group videos manually beyond tags
- [ ] Bulk tag assignment — select multiple videos and tag them at once
- ~~Manually add a tag to a single existing video — direct affordance (e.g. from the main list/card), for videos that arrived with thin/noise-only metadata and never got a canonical tag~~
- ~~Archive button — hide videos from main view without deleting them (Hide does this)~~
- ~~Tag distillation — consolidate many similar tags into a single canonical concept for cleaner search and grouping~~
- [ ] Decide the fate of tag keywords — `tag_keywords` rows can only be written by `set_tag_keywords`, which has had no caller since `tag_detail.html` (its only UI) was deleted on 2026-09-25, so the table is permanently empty in production: the search join in `_build_where` can never match and `delete_tag`'s cleanup is a no-op. Either (a) build the keyword-editing UI the table was designed for, or (b) delete `get_tag_keywords` / `get_tags_with_keywords` / `set_tag_keywords`, the dead search join, and the table itself. Do not leave it in this half state a third time
- [ ] Show ungrouped canonical tags on the /tags page — canonical tags not assigned to any tag group are currently invisible unless you use Auto-assign
- [ ] Creator pages support — full support for bookmarking and tracking YouTube creator channels (not just videos)
  - [x] Crawler: extract and store channel URLs from Firefox bookmarks (Phase 1 complete)
  - [x] Schema: channel entity with name, URL, subscriber count, description (Phase 1 complete)
  - [x] Extension: "bookmark channel" action on youtube.com/c/* and youtube.com/@* pages
  - [x] UI: channels listing view alongside videos (`/channels` — sortable/searchable grid, nav link)
  - [ ] UI: tagging channels, channel-specific stats
  - [ ] Features: all existing functionality (tags, viewing history, search) should work for channels where appropriate

## Metadata / Quality of life

- [ ] Find duplicates — detect and surface videos that appear more than once in the library
- [ ] Detect and flag dead videos (deleted/private) with a badge rather than silently hiding them
- ~~Rating system for videos — favorite toggle (★) on video cards with filter~~
- [ ] Import from YouTube Watch Later playlist or a public playlist URL
- ~~Fix font consistency — audit typography across pages/components and unify to a single consistent font system~~
- ~~Dark/light mode toggle — theme switcher for the web UI, ideally following OS preference by default~~

---

## Tech debt

Items identified in the 2026-06-07 architectural review. Completed items are struck through.

### Done
- ~~Fix test schema drift — conftest hardcoded schema diverged from real schema~~
- ~~Coverage config only measured crawler (92% false) — now measures all packages (55% true)~~
- ~~`collapse_case_variants` ran on every startup — moved to `--normalize-tags` CLI flag~~
- ~~Magic string literals for `fetch_status` and `match_type` — replaced with `FetchStatus` / `MatchType` StrEnums~~
- ~~Break `crawler` → `webapp` dependency: `crawler/datastore.py` imports `apply_aliases` from `webapp/db.py` — the crawler should not depend on the web layer; move shared alias logic to a neutral location~~
- ~~Split `webapp/db.py` (1000+ lines, 6 domains) into focused submodules: `db/videos.py`, `db/tags.py`, `db/aliases.py`, `db/suggestions.py`~~
- ~~Unify CORS handling — `api_add` uses a local dict, `api_status`/`api_hide` use a module-level constant, with a subtle method-list divergence between them~~
- ~~Move multi-step route transactions into the DB layer — e.g. `tag_suggest_confirm` does 4 distinct DB operations inline in the route handler with no single transaction wrapping them~~
- ~~Manual tag assignment to existing canonical tags — assigning an unclassified tag without a Smart Suggest now correctly creates aliases~~

### Medium (next)

- [ ] Add JS test framework (e.g. Jest) for the browser extension — `background.js` and `content.js` are still untested; `popup.js` has Jest coverage for `doAdd`/`initWatchLaterToggle`/`initFavoriteToggle` only (`doAddChannel`, `doHide`, `doRestore`, `doDelete`, `renderState`, `renderChannelState`, `run` remain untested)
- [ ] Code quality remediation — Tasks 1–7 of 14 done (ruff + pre-commit + dev extras; two dead modules deleted; public `extract_video_id`; `cors_json`/`resolve_video`/`video_api_route` decorators; all 12 API routes now go through `webapp/api.py`, `routes.py` 885→699 lines; zero raw SQL left in `routes.py`; uniform 404 contract on video mutation routes). Remaining, in plan order: Task 8 pagination helper (fixes an `append=1` leak), Task 9 `VideoListFilters` + splitting `index()`, Task 10 `db/videos.py` fragments, Task 11 presentation logic into `filters.py`, Task 12 the LLM error hierarchy, Task 13 typing + mypy, Task 14 the extension popup cleanup. Spec: `docs/superpowers/specs/2026-09-24-code-quality-audit.md`. Plan: `docs/superpowers/plans/2026-09-24-code-quality-remediation.md`

### Larger lifts

- [ ] Proper migrations table — replace the ALTER TABLE wrapped in try/except with a tracked migration history. Pairs with unifying the two persistence layers (`crawler.Datastore` vs `webapp/db/*`), deliberately deferred out of the 2026-09-24 code-quality plan — see that spec's "Out of scope" section for the full knot
- [ ] Background processing for blocking operations — `fetch_metadata` (yt-dlp, ~2–5s) and LLM calls (~3–10s) both block a Flask worker thread synchronously

