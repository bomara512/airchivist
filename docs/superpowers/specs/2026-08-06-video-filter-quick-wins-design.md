# Video Filter Quick Wins — Design

**Date:** 2026-08-06
**Status:** Approved
**Scope:** Three new filters on the main video index — **unwatched-only**, **duration**, and **added-within (date range)** — added to the existing filter form and the shared `_build_where` query composer. Out of scope (follow-ups): a "Watched" toggle card action, and a "sort by unwatched first" option.

---

## Summary

The main index (`GET /`) already filters videos by channel, tag, search, and a `favourites_only` checkbox, all composed by `_build_where` in `webapp/db/videos.py` and shared by `get_all_videos` and `count_videos`. This adds three more filters that make a ~2,900-video library easier to navigate. Each is a small, homogeneous extension of the same machinery — no new tables, no new query paths.

---

## Section 1: Backend — `_build_where` and callers

`_build_where(channel, tag, search, favourites_only=False)` gains three keyword params, threaded through `get_all_videos` and `count_videos` (both call `_build_where`):

- **`unwatched_only: bool = False`** → appends `v.personal_view_count = 0`. Direct analogue of the existing `favourites_only` → `v.is_favourite = 1` clause.
- **`duration: Optional[str] = None`** → validated against `_DURATION_BUCKETS` (an allow-list dict mapping key → constant SQL fragment); an unknown value raises `ValueError`:
  - `short` → `v.duration_seconds < 300`
  - `medium` → `v.duration_seconds >= 300 AND v.duration_seconds < 1200`
  - `long` → `v.duration_seconds >= 1200`
  Videos with `duration_seconds IS NULL` (98 of them) match no bucket — acceptable, they are metadata-incomplete.
- **`added_within: Optional[int] = None`** → validated against `_ADDED_WITHIN_DAYS = {7, 30, 90, 365}`; an unknown value raises `ValueError`. Clause: `v.date_added >= date('now', ?)` with a bound `'-<N> days'` modifier (never interpolated).

`ValueError` from `_build_where` is caught by the `index` route and turned into `abort(400)`, exactly as invalid `sort_by`/`sort_dir` already are. The base clauses (`fetch_status = 'ok'`, `is_hidden = 0`) and all existing filters are unchanged.

Since `duration` and `added_within` validation lives in `_build_where`, both `get_all_videos` and `count_videos` reject bad values identically, keeping page counts and rows consistent.

---

## Section 2: Route — `index`

`GET /` reads three more query params:
- `unwatched` (`"1"` → `unwatched_only=True`),
- `duration` (`short|medium|long` or absent),
- `added_within` (int string `7|30|90|365` or absent; non-integer → treated as absent, like the existing `page` guard).

They are passed to both `count_videos` and `get_all_videos`, added to `template_vars` for control state (`unwatched_only`, `current_duration`, `current_added_within`), and included in the `active_filter_count`. `ValueError` → `abort(400)`. The existing `page_url` helper already carries all query params, so pagination and htmx load-more preserve the new filters.

---

## Section 3: Frontend — `index.html` filter form

Three controls added to the existing filter panel (`#filter-panel`), styled like the current controls:
- **Unwatched only** — `<input type="checkbox" name="unwatched" value="1">`, mirroring the `favourites` checkbox.
- **Duration** — `<select name="duration">`: Any duration / Short (< 5 min) / Medium (5–20 min) / Long (> 20 min), values `""|short|medium|long`, current one `selected`.
- **Added within** — `<select name="added_within">`: Any time / Last 7 days / Last 30 days / Last 90 days / Last year, values `""|7|30|90|365`, current one `selected`.

All three participate in the existing htmx `hx-trigger` on the filter form (`change from:select`, `change from:input[type=checkbox]`), so they behave like the current filters. The template's `active_filter_count` expression is extended so the three new filters light up the filter-panel toggle when active.

---

## Section 4: Decisions & non-goals

- **"Unwatched" = `personal_view_count = 0`** — never opened *from ViewTube* (what the counter records), not a YouTube watch state. Consistent with the rediscover shelf's existing definition.
- **Duration cutoffs: 5 min / 20 min.** NULL-duration videos are excluded from every bucket.
- **Date filter is presets, not a custom picker** (YAGNI): 7 / 30 / 90 / 365 days.
- **Out of scope:** "sort by unwatched first" (a sort option, deferrable) and the "Watched" toggle card action (a write-action with toggle semantics — its own slice).

---

## File Map

| File | Action |
|---|---|
| `webapp/db/videos.py` | Extend `_build_where` (+ `_DURATION_BUCKETS`, `_ADDED_WITHIN_DAYS`); thread new params through `get_all_videos` and `count_videos` |
| `webapp/routes.py` | Read/validate/pass `unwatched`, `duration`, `added_within` in `index`; add to `template_vars` + `active_filter_count` |
| `webapp/templates/index.html` | Add the checkbox + two selects; extend `active_filter_count` |
| `tests/webapp/test_db.py` | Tests for the three filters + invalid duration/added_within raising |
| `tests/webapp/test_routes.py` | Tests for each param filtering + invalid → 400 |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Document the new filter params |
| `TODO.md` | Mark unwatched-only + duration + date-range delivered (leave watched-toggle and sort-by-unwatched open) |

---

## Testing Strategy

- **DB** — pytest against the seeded temp DB (the conftest seed has videos with varied `personal_view_count`; extend seed or insert rows with distinct `duration_seconds`/`date_added` as needed): `unwatched_only` returns only `personal_view_count = 0`; each duration bucket returns the right rows and excludes NULLs; `added_within` windows correctly; invalid `duration`/`added_within` raise `ValueError`; `count_videos` agrees with `get_all_videos` under each filter.
- **Route** — Flask test client: `/?unwatched=1`, `/?duration=short`, `/?added_within=30` each narrow the list; combined filters compose; invalid `duration`/`added_within` → 400; the filter controls render current state.
