# Code Quality Audit — Design / Findings

**Date:** 2026-09-24
**Scope reviewed:** all production Python (`webapp/`, `crawler/`, `tools/`, `scripts/` — ~5,100 lines), plus `extension/popup/popup.js`. Templates, `content.js`, `background.js`, and SQL index/query performance were *not* audited.
**Plan:** `docs/superpowers/plans/2026-09-24-code-quality-remediation.md`

## Goal

Reduce duplication and inconsistency in the existing codebase without changing user-facing behavior, and put machine enforcement behind the conventions that are currently enforced only by prose in `CLAUDE.md`.

## Overall assessment

The architecture is sound: the webapp/crawler split is real, `webapp/db/` is already decomposed by domain, SQL is parameterized with a column allowlist rather than string-built, and test coverage is substantial (~4,800 lines of tests against ~5,100 of production, 68% line coverage).

The problems are accretion problems, not design problems. They cluster in three places: the route layer has grown by copy-paste, two modules were superseded but never deleted, and there is no linter — so every convention depends on a human or agent noticing.

## Findings

### F1 — No linter, formatter, or type checker is configured

No `ruff`, `black`, `flake8`, `mypy`, `isort`, or `pre-commit` anywhere in `pyproject.toml` or as config files. A one-off `pyflakes` run immediately surfaced:

- Dead imports in production: `os` (`webapp/routes.py:2`), `typing.Optional` (`webapp/llm_tagger.py:6`, `webapp/db/tags.py:2`)
- 10 more dead imports across `tests/`
- 7 `f"""` prefixes on SQL strings with no placeholders (`webapp/db/aliases.py:178,185,192,236,243,250`, `webapp/db/suggestions.py:157`)

The f-strings are harmless today but actively misleading: they make parameterized SQL *look* interpolated, which is the exact pattern a reviewer scans for when auditing for injection, and it normalizes f-string SQL for the next author.

This is the root cause of most other findings, and it is why fixing it is sequenced first.

**Related gap:** `requirements-dev.txt` exists, but `pyproject.toml` declares no `[project.optional-dependencies]`, so `pip install -e ".[dev]"` does not work. This is the same class of gap the "Keep README setup/test instructions runnable from a clean checkout" rule in `CLAUDE.md` was written about.

### F2 — Two modules are entirely dead

`webapp/tag_suggester.py` (71 lines) and `webapp/keyword_matcher.py` (39 lines) have zero callers in `webapp/`, `crawler/`, `scripts/`, `tools/`, or templates — only their own test files (a further 170 lines). They were superseded by `webapp/llm_tagger.py` plus the alias system. This violates the project's own "Remove old approaches when replacing them" rule.

Also dead: `is_rediscover_shelf_expired` and `get_watch_later_count` in `webapp/db/videos.py` — defined, imported into the `webapp/db/__init__.py` facade, listed in `__all__`, and never called by anything, including tests.

Both dead modules also carry latent performance traps that matter only if they are ever revived, and are recorded here so the decision is not re-litigated from scratch:
- `keyword_matcher.find_matching_tags` compiles a fresh regex per keyword *inside* a nested loop over videos.
- `tag_suggester.suggest_clusters` is O(n²) and calls `_normalize()` twice per pair rather than once per name.

**Decision:** delete both modules and their tests rather than fix them. Recovering them from git history is cheap; carrying them is not.

### F3 — The API route layer is ~130 lines of copy-paste

`webapp/routes.py` is 884 lines. Measured duplication:

| Duplicated block | Occurrences |
|---|---|
| `resp.headers.update(_CORS_HEADERS)` | 38 |
| `if request.method == "OPTIONS": return make_response("", 204, _CORS_HEADERS)` | 12 |
| 4-line `"Not a YouTube URL"` 400 block | 8 |
| 4-line `"Video not found"` 404 block | 7 |
| `m = _YT_ID_RE.search(url)` / `m.group(1)` dance | 9 |

`api_favorite_add`, `api_favorite_remove`, and `api_favorite_status` differ from one another by exactly one line of real logic.

**Decision:** two decorators (`cors_json` for preflight + JSON encoding + headers; `resolve_video` for URL parsing and row lookup) in a new `webapp/api.py`, which also houses `_CORS_HEADERS` and an `ApiStatus` StrEnum. The split across routes is not uniform and must be respected:

- `cors_json` + `resolve_video` (404 when the video is absent): `api_hide`, `api_watch_later_add`, `api_watch_later_remove`, `api_watch_later_status`, `api_favorite_add`, `api_favorite_remove`, `api_favorite_status` — 7 routes.
- `cors_json` only: `api_add` (creates the video when missing), `api_status` (returns `not_found` with HTTP 200, not 404), `api_status_batch`, `api_channel_status`, `api_channel_add` (channel URLs, not video URLs) — 5 routes.

### F4 — Magic strings where the project already has an enum convention

The codebase established `FetchStatus` and `MatchType` StrEnums (per the 2026-06 changelog entry), but API responses still use bare literals: `"added"`, `"removed"`, `"exists"`, `"not_found"`, `"hidden"`, `"already_in_queue"`, `"error"`. Same for `watch_status`'s `"unwatched"` / `"unwatched_first"` and `group`'s `"channel"` / `"tag"`.

### F5 — `_YT_ID_RE` is a private name imported across package boundaries

`webapp/routes.py:7` does `from crawler.models import _YT_ID_RE, _YT_CHANNEL_RE`. A leading underscore means "not part of this module's public API"; importing it from another package contradicts that.

**Decision:** rename to `YT_ID_RE` / `YT_CHANNEL_RE` and add `extract_video_id(url) -> str | None` to `crawler/models.py`. The function is what callers actually want and removes the search/`group(1)` dance from 9 sites. `tests/crawler/test_models.py` references `_YT_CHANNEL_RE` 8 times and must be updated with the rename.

### F6 — Three routes repeat the same pagination block, and have already drifted

`index()`, `channels()`, and `hidden()` each re-implement: parse `page` with a try/except, compute `total_pages`, clamp `page`, and define a local `page_url()` closure.

They have drifted: `index()` and `channels()` strip `("page", "append")` from the carried-over query args, but `hidden()` (`webapp/routes.py:638`) strips only `"page"` — so an `append=1` param leaks into the Archived page's Prev/Next links. **This is a live bug**, and it is the standard cost of a thrice-copied closure.

### F7 — `index()` does six jobs in ~115 lines

Query-param parsing, two DB calls, pagination math, grouping transformation, filter counting, and HTMX content negotiation. The consequence is testability: `active_filter_count` — a pure function of the request — can currently only be exercised through a full HTTP round trip.

### F8 — Inconsistent 404 contract on video mutation routes

`video_toggle_favorite`, `video_toggle_watched`, `video_mark_watched`, and `video_remove_from_rediscover_shelf` all `abort(404)` for an unknown `video_id`. `video_hide`, `video_unhide`, and `video_delete` silently succeed.

**Decision:** make all of them 404. Silent success on a mutation hides bugs, and no existing test asserts the silent behavior (verified), so nothing breaks.

### F9 — Raw SQL in a route handler

`webapp/routes.py:213` (`video_remove_tag`) runs `SELECT id FROM tags WHERE name = ?` directly against `g.db`, bypassing `webapp/db/`. One line, but it is the precedent that erodes the layering.

### F10 — Internal exception text is interpolated into redirect URLs

`webapp/routes.py:488` and `:531` build `llm_error=f"Auto-assign failed: {e}"` / `f"LLM error: {e}"` into a redirect, and `tags.html:48` renders it raw. Internal exception detail ends up in the address bar and browser history.

**Decision:** pass a stable error *code* and let the template own the copy. `flask.flash` would be the idiomatic choice but `create_app` sets no `secret_key` (verified), so flash would raise; adding a secret key to fix an error-message leak is a larger change than the leak warrants.

### F11 — `webapp/llm_tagger.py` duplicates its own API-call preamble, and uses a deprecated exception

`get_suggestions` and `suggest_group_assignments` repeat ~20 lines of import-guard, API-key check, client construction, `messages.create`, and `tool_use` extraction. They have already drifted: one `ImportError` message includes install instructions, the other does not.

Both raise `EnvironmentError`, a deprecated alias of `OSError` since Python 3.3. `routes.py` then catches `EnvironmentError` / `ImportError` / `Exception` in a three-branch ladder, duplicated across two routes.

**Decision:** an `LLMError` hierarchy (`LLMUnavailableError`, `LLMResponseError`) collapses the ladder to one `except LLMError`. `tests/webapp/test_llm_tagger.py:158,163,176` assert on the old exception types and must be updated.

### F12 — Duplication inside `webapp/db/videos.py`

- `SELECT id FROM videos WHERE video_id = ?` appears 6 times.
- The row→dict + `tags or ""` normalization loop appears 4 times.
- The `LEFT JOIN video_tags / LEFT JOIN tags` + `GROUP_CONCAT(CASE WHEN t.is_canonical ...)` SQL fragment appears 4 times.
- `_build_where(...)` is called positionally with 7 arguments from two call sites.

**Explicitly rejected:** merging `get_hidden_videos` into `get_all_videos`. They look like near-clones but their WHERE clauses differ meaningfully — `_build_where` always adds `v.fetch_status = 'ok'`, while `get_hidden_videos` deliberately omits it, so archived videos whose metadata fetch failed still appear on the Archived page. Unifying them would silently hide those rows. Extract the shared *fragments*; keep the two functions and add a comment recording why the `fetch_status` difference exists.

### F13 — Presentation logic in the DB layer

`get_current_rediscover_shelf` builds user-facing strings (`"Never opened"`, `"Last viewed 3 days ago"`) inside `webapp/db/videos.py`. `webapp/filters.py` exists for exactly this. `_shelf_expires_label` in `routes.py:21` is the same kind of logic in the wrong layer, and catches bare `Exception`.

### F14 — Legacy typing style on a modern Python floor

`pyproject.toml` declares `requires-python = ">=3.12"` (the venv runs 3.14), but the code uses `Optional[...]` 59 times against `| None` twice. Return types are frequently bare (`-> list`, `-> dict`, `-> set`). Type-hint coverage in `webapp/` is roughly 49% (77 annotated defs vs 81 unannotated) — `routes.py` and `filters.py` are almost entirely unannotated.

`VideoMetadata.fetch_status` and `ChannelMetadata.fetch_status` are typed `str` while defaulting to a `FetchStatus` member, which forfeits the enum at the type level.

### F15 — The `webapp/db/__init__.py` facade lists every symbol twice

134 lines, in which each name appears once in a `from ... import (...)` block and again in `__all__`, in a *different* grouping order. It exists for internal import-path compatibility only.

### F16 — `tools/tag_categorizer.py`: 728 lines, 0% coverage

`pyproject.toml` explicitly measures `--cov=tools`, so this drags the reported number down while contributing nothing. It also contains `_retroactive_apply_inline`, a hand-copied duplicate of `webapp.db.aliases.retroactive_apply` (a deliberate fallback so the tool runs standalone), and its own `ensure_noise_column` migration.

**Decision:** test the pure helpers (`_noise_category`, `_build_suggest_prompt`, `_save_approved`) rather than the interactive commands. Deliberately not unified with `webapp/db/` — standalone operation is the point of the tool.

### F17 — `extension/popup/popup.js`: an existing abstraction going unused

12 raw `fetch(` calls against only 3 uses of the file's own `postJson` helper. `initWatchLaterToggle` and `initFavoriteToggle` are ~90% identical (introduced knowingly on 2026-09-24 with the trade-off recorded in the changelog; with two call sites now, extraction is justified). The same inline `style="display:block;margin-top:0.4rem;..."` string is repeated 5 times and belongs in CSS.

## Out of scope for this plan

**Unifying the two persistence layers.** `crawler/datastore.py` exposes a `Datastore` class (owns its connection, context manager, holds base-table DDL in `_SCHEMA`); `webapp/db/*` exposes module-level functions taking `conn` as the first argument. They target the same tables and duplicate at least seven read/write paths under near-identical names: `get_video_by_id`, `get_all_videos`, `get_tags_for_video`, `count_videos`, `upsert_channel`, `add_tag`/`create_tag`, `tag_video`/`add_video_tag`. Both are separately tested, so the duplication is doubled downstream.

Related symptoms, all part of the same knot:
- `apply_aliases` — a canonical-tag concern, which is a webapp feature — lives in `crawler/datastore.py` and is imported *back* into `webapp/db/videos.py`. The 2026-06 changelog describes breaking the crawler→webapp dependency by moving alias logic "to a neutral location"; the location chosen inverted the dependency rather than neutralizing it.
- Schema DDL is defined in two places (`crawler._SCHEMA` plus `webapp/db/schema.py`'s try/except `ALTER`s), which is why the test conftest hand-builds schema and why it drifted before.
- `apply_aliases` uses `except sqlite3.OperationalError` as schema *detection*, which will also swallow genuine SQL errors.
- Every DB function calls `conn.commit()` itself, which is why multi-step atomicity required inventing bespoke combined functions (`confirm_and_dismiss_suggestion`, `add_alias_and_apply`, `edit_alias_and_apply`, `accept_noise_and_dismiss_suggestion`) and `_`-prefixed no-commit twins (`_remove_from_rediscover_shelf`). A `transaction(conn)` context manager would let callers compose without a new function per combination.

This is the only item in the audit that carries real regression risk, it pairs naturally with the "proper migrations table" item already in `TODO.md`, and it needs its own brainstorm to settle where shared code should live. Deliberately excluded here so the low-risk work can ship independently.

**Also deliberately not doing:**
- Introducing an ORM. Parameterized SQL with a column allowlist fits this project, and `_build_where` is honest, readable code.
- Parameterizing `video_toggle_favorite` / `video_toggle_watched` into one route. Two instances of six obvious lines does not justify the indirection.
- Deduplicating the YouTube regexes between `crawler/models.py` and `popup.js`. The "keep in sync" comment is the right answer for two consumers.

## Success criteria

- `ruff check .` exits clean, and is wired to run before commits.
- No module in `webapp/` or `crawler/` is unreferenced by production code.
- No API response literal appears outside an enum.
- The append-param leak (F6) and the inconsistent 404s (F8) are fixed and pinned by tests.
- Full suite green with an empty warnings summary (`python -m pytest -q`), and `npm test` green, after every task.
- No user-facing behavior change anywhere in this plan.
