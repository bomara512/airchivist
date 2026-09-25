# Code Quality Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplication and inconsistency catalogued in the 2026-09-24 audit, and put a linter behind the conventions currently enforced only by prose in `CLAUDE.md` — with zero user-facing behavior change.

**Architecture:** Every task is a refactor of working, tested code, so the existing suite is the safety net: each task runs the full suite before and after and expects the same result. New tests are added only where a task newly *pins* behavior that nothing currently asserts (the append-param leak, the 404 contract, the extracted pure functions). Tasks are ordered so the linter lands first (it prevents new drift while the rest proceeds) and the riskiest structural work is excluded entirely.

**Tech Stack:** Python 3.12+ (venv runs 3.14), Flask 3, sqlite3 stdlib, pytest + pytest-cov + pytest-mock, ruff, mypy, vanilla JS browser extension with Jest.

**Spec:** `docs/superpowers/specs/2026-09-24-code-quality-audit.md`

## Global Constraints

- **No user-facing behavior change** in any task, with exactly two intended exceptions, both bug fixes pinned by new tests: the `append=1` leak into Archived-page pagination links (Task 8) and the inconsistent 404s on `video_hide`/`video_unhide`/`video_delete` (Task 7).
- After **every** task: `python -m pytest -q` passes **with an empty warnings summary**, and `npm test` passes. Per `CLAUDE.md`, a warning is a blocker, not cleanup for later.
- Per `CLAUDE.md`, in the same response as each task's code change: update `plan-webapp.md` (and `plan-extension.md` for Task 14) to reflect current behavior, append a `CHANGELOG.md` entry with at least one implication, and check `TODO.md` for items this closes.
- US English throughout (`favorite`, `color`, `behavior`). Do not "fix" spelling in `CHANGELOG.md` or anything under `docs/superpowers/` — those are historical records.
- Use design tokens for any CSS touched (Task 14); never introduce a new hex color or bare `rem` font-size.
- Never introduce a new hardcoded API status literal — add to the `ApiStatus` enum from Task 4 instead.
- `python -m pytest -q` currently reports **585 passed**; `npm test` reports **24 passed**. Task 2 intentionally reduces the Python count (it deletes two test files); Tasks 7, 8, 9, 10, 12, 13 add tests. No task may *reduce* the count for any other reason.

## Review Focus

Input classes the spec implies but which no task's tests exercise, most likely to bite first. Each has a test assigned to the task that owns the code:

1. **`?page=abc` / `?page=-5` / `?page=99999` on all three paginated routes** — must fall back to page 1 or clamp to the last page, never 500. Pinned in Task 8.
2. **`?added_within=notanumber` and `?added_within=5` (not in the allowlist)** — the first is swallowed to `None` by a try/except, the second raises `ValueError` from the DB layer and becomes a 400. Both behaviors must survive the `VideoListFilters` extraction. Pinned in Task 9.
3. **A JSON API call with no body at all, or `{"url": null}`** — `request.get_json(silent=True) or {}` must keep yielding a 400, not a `TypeError`, once the parsing moves into the `resolve_video` decorator. Pinned in Task 4.
4. **An `OPTIONS` preflight on every migrated API route** — must stay 204 with CORS headers after the decorator refactor. Existing tests cover this per-route; Task 5 adds the assertion for the routes that only have happy-path coverage today.
5. **A video row whose `tags` column is SQL `NULL`** — the extracted `_to_video_dicts` helper must still coerce to `""`, or templates that call `.split(",")` break. Pinned in Task 10.

---

## Task 1: Lint, format, and dependency tooling

**Files:**
- Modify: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Modify: `README.md` (setup + running-tests sections)
- Modify: every file ruff auto-fixes (expect ~20 real findings plus import sorting across ~30 files)

**Interfaces:**
- Consumes: nothing.
- Produces: `ruff check .` as the gate every later task must keep clean; `pip install -e ".[dev]"` as the documented dev install.

- [ ] **Step 1: Add dev extras and ruff config to `pyproject.toml`**

Insert after the `dependencies = [...]` block:

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "pytest-mock",
    "ruff",
]
```

And append at the end of the file:

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
# F = pyflakes (dead imports, f-strings without placeholders)
# I = import sorting
# Deliberately deferred: "E"/"W" (line-length noise on existing prose-heavy
# comments), "UP" (owned by Task 13 so the typing diff is reviewable alone),
# "B"/"SIM" (findings need judgment; revisit once this baseline is green).
select = ["F", "I"]
```

- [ ] **Step 2: Install the dev extras**

Run: `pip install -e ".[dev]"`
Expected: succeeds, and `ruff --version` now works.

- [ ] **Step 3: Look at the findings before fixing them**

Run: `ruff check .`
Expected: roughly 21 `F` findings plus `I001` on many files. The `F` findings must include: `F401` for `os` in `webapp/routes.py`, `typing.Optional` in `webapp/llm_tagger.py` and `webapp/db/tags.py`; `F541` for 7 f-strings in `webapp/db/aliases.py` and `webapp/db/suggestions.py`; and `F401` for ~10 unused imports in `tests/`.

Read the `F541` sites specifically and confirm each is genuinely a parameterized query with no interpolation (it is — the fix is deleting the `f` prefix, not adding placeholders). If any turns out to *need* interpolation, stop: that is a latent bug, not a lint nit, and needs its own task.

- [ ] **Step 4: Auto-fix**

Run: `ruff check --fix .`
Then: `ruff check .`
Expected: clean exit.

- [ ] **Step 5: Verify nothing broke**

Run: `python -m pytest -q`
Expected: 585 passed, warnings summary empty.

Run: `npm test`
Expected: 24 passed.

- [ ] **Step 6: Add the pre-commit hook**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
```

Add `pre-commit` to the `dev` extras list in `pyproject.toml`, reinstall (`pip install -e ".[dev]"`), then run `pre-commit install`.

Run: `pre-commit run --all-files`
Expected: passes.

- [ ] **Step 7: Document the new install steps in `README.md`**

The "Running tests" section currently tells the reader to run `python -m pytest -q` and `npm test`. Per the `CLAUDE.md` clean-checkout rule, add that dev tooling comes from `pip install -e ".[dev]"` (replacing or alongside the `requirements-dev.txt` instruction), that `npm install` is required before `npm test`, and that `pre-commit install` is a one-time step per clone. Verify by reading the section back as though from a fresh clone: every command named must have its install step stated above it.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml README.md
git add -u
git commit -m "chore: add ruff + pre-commit, declare dev extras, fix lint findings"
```

---

## Task 2: Delete dead modules and dead functions

**Files:**
- Delete: `webapp/tag_suggester.py`, `webapp/keyword_matcher.py`
- Delete: `tests/webapp/test_tag_suggester.py`, `tests/webapp/test_keyword_matcher.py`
- Modify: `webapp/db/videos.py` (remove two functions)
- Modify: `webapp/db/__init__.py` (remove from import block and `__all__`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This task is pure subtraction.

- [ ] **Step 1: Prove they are unreferenced before deleting**

```bash
grep -rn "tag_suggester\|keyword_matcher\|suggest_clusters\|find_matching_tags\|group_videos_by_tags" \
  --include="*.py" --include="*.html" webapp/ crawler/ tools/ scripts/
grep -rn "is_rediscover_shelf_expired\|get_watch_later_count" \
  --include="*.py" --include="*.html" webapp/ crawler/ tools/ scripts/ tests/
```

Expected: the first prints only the definitions inside the two doomed modules. The second prints only `webapp/db/videos.py` definitions and `webapp/db/__init__.py` re-export lines. **If either prints a real call site, stop and re-scope this task** — the audit's premise was wrong.

- [ ] **Step 2: Delete the modules and their tests**

```bash
git rm webapp/tag_suggester.py webapp/keyword_matcher.py \
       tests/webapp/test_tag_suggester.py tests/webapp/test_keyword_matcher.py
```

- [ ] **Step 3: Remove the two dead DB functions**

In `webapp/db/videos.py`, delete `is_rediscover_shelf_expired` (and its docstring) and `get_watch_later_count` (and its docstring) entirely.

In `webapp/db/__init__.py`, delete `get_watch_later_count,` and `is_rediscover_shelf_expired,` from the `from webapp.db.videos import (...)` block, and delete `"get_watch_later_count",` and `"is_rediscover_shelf_expired",` from `__all__`.

- [ ] **Step 4: Verify**

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean. Pytest passes with 585 minus the tests in the two deleted files (the two files hold 30 tests between them, so expect **555 passed**), warnings summary empty. Coverage percentages will shift — that is expected, since dead code was being measured.

Run: `npm test`
Expected: 24 passed (unaffected).

- [ ] **Step 5: Check the living docs for references**

```bash
grep -rn "tag_suggester\|keyword_matcher\|suggest_clusters\|is_rediscover_shelf_expired\|get_watch_later_count" \
  plan-webapp.md plan-crawler.md plan-extension.md TODO.md
```

Edit any hit to reflect that the code is gone — remove the sentence rather than appending a correction, per the `CLAUDE.md` living-docs rule. Leave `CHANGELOG.md` and `docs/superpowers/` history alone.

- [ ] **Step 6: Commit**

```bash
git add -u && git add CHANGELOG.md
git commit -m "refactor: delete superseded tag_suggester and keyword_matcher modules

Both had zero production callers -- superseded by llm_tagger plus the
alias system -- along with two never-called DB functions. Per the
project's own 'remove old approaches when replacing them' rule; git
history is the reference copy."
```

---

## Task 3: Public YouTube regexes and `extract_video_id`

**Files:**
- Modify: `crawler/models.py`
- Modify: `webapp/routes.py` (import line only)
- Modify: `tests/crawler/test_models.py` (8 references)
- Test: `tests/crawler/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `crawler.models.extract_video_id(url: str) -> str | None`, `crawler.models.YT_ID_RE`, `crawler.models.YT_CHANNEL_RE`. Task 4 depends on `extract_video_id`.

- [ ] **Step 1: Write the failing test**

Add to `tests/crawler/test_models.py`:

```python
class TestExtractVideoId:
    def test_returns_id_from_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=aaaaaaaaaa1") == "aaaaaaaaaa1"

    def test_returns_id_from_short_url(self):
        assert extract_video_id("https://youtu.be/aaaaaaaaaa1") == "aaaaaaaaaa1"

    def test_returns_none_for_non_youtube_url(self):
        assert extract_video_id("https://example.com") is None

    def test_returns_none_for_empty_string(self):
        assert extract_video_id("") is None

    def test_returns_none_for_none(self):
        assert extract_video_id(None) is None
```

Add `extract_video_id` to the module's import line at the top of the file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/crawler/test_models.py::TestExtractVideoId -v`
Expected: FAIL — `ImportError: cannot import name 'extract_video_id'`.

- [ ] **Step 3: Implement**

In `crawler/models.py`, rename `_YT_ID_RE` to `YT_ID_RE` and `_YT_CHANNEL_RE` to `YT_CHANNEL_RE` (including the two internal uses inside `Bookmark.youtube_video_id` and `Bookmark.youtube_channel_url`), and add below them:

```python
def extract_video_id(url: str | None) -> str | None:
    """Return the 11-character YouTube video ID in `url`, or None if there isn't one."""
    m = YT_ID_RE.search(url or "")
    return m.group(1) if m else None
```

Do not leave `_YT_ID_RE = YT_ID_RE` compatibility aliases — per `CLAUDE.md`, remove the old approach in the same change.

- [ ] **Step 4: Update the two consumers**

In `webapp/routes.py`, change the import to `from crawler.models import YT_ID_RE, YT_CHANNEL_RE, FetchStatus` and update the 11 use sites (9 `YT_ID_RE`, 2 `YT_CHANNEL_RE`). They keep their current `m = YT_ID_RE.search(url)` shape for now — Task 4 replaces them with `extract_video_id`.

In `tests/crawler/test_models.py`, update the 8 `_YT_CHANNEL_RE` references.

- [ ] **Step 5: Verify no private references remain**

Run: `grep -rn "_YT_ID_RE\|_YT_CHANNEL_RE" --include="*.py" .`
Expected: no output.

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 555 + 5 = **560 passed**, warnings summary empty.

- [ ] **Step 6: Commit**

```bash
git add -u && git add CHANGELOG.md plan-crawler.md
git commit -m "refactor: make YouTube regexes public, add extract_video_id helper"
```

---

## Task 4: `webapp/api.py` — CORS/JSON decorators and the 7 video-resolving routes

**Files:**
- Create: `webapp/api.py`
- Modify: `webapp/routes.py` (remove `_CORS_HEADERS`; migrate 7 routes)
- Test: `tests/webapp/test_api.py` (new), `tests/webapp/test_routes.py` (existing coverage is the safety net)

**Interfaces:**
- Consumes: `crawler.models.extract_video_id` (Task 3).
- Produces: `webapp.api.ApiStatus` (StrEnum), `webapp.api.CORS_HEADERS`, `webapp.api.cors_json` (decorator), `webapp.api.resolve_video` (decorator, passes the video row as the view's first positional argument). Task 5 migrates the remaining routes onto `cors_json`.

- [ ] **Step 1: Write the failing test**

Create `tests/webapp/test_api.py`:

```python
from webapp.api import ApiStatus


class TestApiStatusEnum:
    def test_members_are_plain_strings(self):
        assert ApiStatus.ADDED == "added"
        assert ApiStatus.REMOVED == "removed"
        assert ApiStatus.EXISTS == "exists"
        assert ApiStatus.NOT_FOUND == "not_found"
        assert ApiStatus.HIDDEN == "hidden"
        assert ApiStatus.ALREADY_IN_QUEUE == "already_in_queue"
        assert ApiStatus.ERROR == "error"


class TestResolveVideoDecorator:
    """Review Focus #3: a malformed or absent JSON body must still be a 400."""

    def test_missing_body_returns_400(self, client):
        resp = client.post("/api/favorite/add")
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_null_url_returns_400(self, client):
        resp = client.post("/api/favorite/add", json={"url": None})
        assert resp.status_code == 400
        assert resp.get_json()["status"] == "error"

    def test_cors_header_on_400(self, client):
        resp = client.post("/api/favorite/add", json={"url": "https://example.com"})
        assert "Access-Control-Allow-Origin" in resp.headers
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/webapp/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webapp.api'`.

- [ ] **Step 3: Create `webapp/api.py`**

```python
import functools
from enum import StrEnum

from flask import g, jsonify, make_response, request

from crawler.models import extract_video_id
from webapp import db as _db

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type",
}


class ApiStatus(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    HIDDEN = "hidden"
    ALREADY_IN_QUEUE = "already_in_queue"
    ERROR = "error"


def _request_url() -> str:
    """The `url` the caller sent — query string on GET, JSON body otherwise."""
    if request.method == "GET":
        return (request.args.get("url") or "").strip()
    data = request.get_json(silent=True) or {}
    return (data.get("url") or "").strip()


def cors_json(fn):
    """Answer the OPTIONS preflight, JSON-encode the return value, attach CORS headers.

    The wrapped view returns either a body dict (implying 200) or a
    (body, status) tuple.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return make_response("", 204, CORS_HEADERS)
        result = fn(*args, **kwargs)
        body, status = result if isinstance(result, tuple) else (result, 200)
        resp = jsonify(body)
        resp.headers.update(CORS_HEADERS)
        return resp, status
    return wrapper


def resolve_video(fn):
    """Parse the request's `url` and load its video row, or return the shared errors.

    Passes the row to the view as its first positional argument. Must be applied
    *below* `cors_json`, which encodes the error bodies returned here.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        video_id = extract_video_id(_request_url())
        if video_id is None:
            return {"status": ApiStatus.ERROR, "error": "Not a YouTube URL"}, 400
        video = _db.get_video_by_id(g.db, video_id)
        if not video:
            return {"status": ApiStatus.ERROR, "error": "Video not found"}, 404
        return fn(video, *args, **kwargs)
    return wrapper
```

- [ ] **Step 4: Run to verify the enum tests pass and route tests still fail**

Run: `python -m pytest tests/webapp/test_api.py -v`
Expected: `TestApiStatusEnum` PASSES. `TestResolveVideoDecorator::test_missing_body_returns_400` may already pass against the un-migrated route — that is fine and expected; it is a characterization test that must keep passing through Step 5.

- [ ] **Step 5: Migrate the 7 video-resolving routes**

In `webapp/routes.py`, replace the module-level `_CORS_HEADERS` dict with `from webapp.api import ApiStatus, CORS_HEADERS, cors_json, resolve_video` (keep `CORS_HEADERS` imported — Task 5's routes still reference it until migrated), then rewrite these seven bodies. Each keeps its existing `@bp.route(...)` line unchanged:

```python
@bp.route("/api/hide", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_hide(video):
    _db.hide_video(g.db, video["video_id"])
    return {"status": ApiStatus.HIDDEN, "title": video.get("title")}


@bp.route("/api/watch-later/add", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_watch_later_add(video):
    if not _db.add_to_watch_later(g.db, video["video_id"]):
        return {"status": ApiStatus.ALREADY_IN_QUEUE}, 409
    return {"status": ApiStatus.ADDED}


@bp.route("/api/watch-later/remove", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_watch_later_remove(video):
    if not _db.remove_from_watch_later(g.db, video["video_id"]):
        return {"status": ApiStatus.ERROR, "error": "Not in queue"}, 404
    return {"status": ApiStatus.REMOVED}


@bp.route("/api/watch-later/status", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_watch_later_status(video):
    return {"in_queue": _db.is_in_watch_later(g.db, video["video_id"])}


@bp.route("/api/favorite/add", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_favorite_add(video):
    _db.set_favorite(g.db, video["video_id"], True)
    return {"status": ApiStatus.ADDED}


@bp.route("/api/favorite/remove", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_favorite_remove(video):
    _db.set_favorite(g.db, video["video_id"], False)
    return {"status": ApiStatus.REMOVED}


@bp.route("/api/favorite/status", methods=["POST", "OPTIONS"])
@cors_json
@resolve_video
def api_favorite_status(video):
    return {"is_favorite": bool(video.get("is_favorite"))}
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: 560 + 4 = **564 passed**, warnings summary empty. The pre-existing `TestApiHide`, `TestApiWatchLater*`, and `TestApiFavorite*` classes are the real proof here — 40+ assertions covering happy paths, 400s, 404s, 409s, CORS headers, and OPTIONS preflights, all unchanged.

Run: `ruff check .`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add webapp/api.py tests/webapp/test_api.py && git add -u
git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: extract cors_json/resolve_video decorators, add ApiStatus enum

Collapses ~110 lines of per-route CORS and URL-parsing boilerplate across
the seven video-resolving API routes into two decorators."
```

---

## Task 5: Migrate the remaining 5 CORS routes

**Files:**
- Modify: `webapp/routes.py` (`api_add`, `api_status`, `api_status_batch`, `api_channel_status`, `api_channel_add`)
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `webapp.api.cors_json`, `webapp.api.ApiStatus` (Task 4); `crawler.models.extract_video_id`, `YT_CHANNEL_RE` (Task 3).
- Produces: `CORS_HEADERS` no longer referenced anywhere in `webapp/routes.py`.

These five cannot use `resolve_video`: `api_add` *creates* the video when it is missing, `api_status` returns `not_found` with HTTP **200** rather than a 404, `api_status_batch` takes a list of IDs rather than a URL, and the two channel routes parse channel URLs.

- [ ] **Step 1: Add the missing preflight assertions (Review Focus #4)**

Add to `tests/webapp/test_routes.py`, in the classes covering these routes:

```python
class TestCorsPreflightCoverage:
    @pytest.mark.parametrize("path", [
        "/api/add",
        "/api/status",
        "/api/status/batch",
        "/api/channel/status",
        "/api/channel/add",
    ])
    def test_options_preflight_returns_204_with_cors(self, client, path):
        resp = client.options(path)
        assert resp.status_code == 204
        assert "Access-Control-Allow-Origin" in resp.headers
```

- [ ] **Step 2: Run to confirm it passes before the refactor**

Run: `python -m pytest tests/webapp/test_routes.py::TestCorsPreflightCoverage -v`
Expected: 5 PASSED. This is a characterization test — it must still pass after Step 3, which is the point.

- [ ] **Step 3: Migrate the five routes**

Apply `@cors_json` below each `@bp.route(...)`, delete each body's `OPTIONS` check and every `resp = jsonify(...)` / `resp.headers.update(...)` / `return resp` triple, and return plain dicts or `(dict, status)` tuples. Replace `m = YT_ID_RE.search(url)` with `extract_video_id`, and swap literals for `ApiStatus` members. For example `api_status` becomes:

```python
@bp.route("/api/status", methods=["GET", "OPTIONS"])
@cors_json
def api_status():
    video_id = extract_video_id((request.args.get("url") or "").strip())
    if video_id is None:
        return {"status": ApiStatus.ERROR, "error": "Not a YouTube URL"}, 400
    video = _db.get_video_by_id(g.db, video_id)
    if video is None:
        return {"status": ApiStatus.NOT_FOUND}
    status = ApiStatus.HIDDEN if video.get("is_hidden") else ApiStatus.EXISTS
    return {"status": status, "video_id": video_id, "title": video.get("title")}
```

and `api_status_batch`:

```python
@bp.route("/api/status/batch", methods=["POST", "OPTIONS"])
@cors_json
def api_status_batch():
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("ids") or []
    ids = [v.strip() for v in raw_ids if isinstance(v, str) and v.strip()][:50]
    found = _db.get_videos_status_batch(g.db, ids)
    return {vid: found.get(vid, ApiStatus.NOT_FOUND) for vid in ids}
```

`api_add` keeps its full body (existence check, `fetch_metadata`, `add_video`, `retroactive_apply`, `record_visit`) — only the response plumbing changes. Keep its local `from crawler.metadata_fetcher import fetch_metadata` import and add the same explanatory comment `api_channel_add` already has, so the reason (test monkeypatching) is recorded at both sites rather than one.

- [ ] **Step 4: Verify `CORS_HEADERS` is gone from routes.py**

Run: `grep -n "CORS_HEADERS\|make_response" webapp/routes.py`
Expected: only the import line mentions `CORS_HEADERS`; remove it from the import if nothing else uses it. No `make_response` remains.

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 564 + 5 = **569 passed**, warnings summary empty.

- [ ] **Step 5: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: migrate remaining API routes onto cors_json decorator"
```

---

## Task 6: Move `video_remove_tag`'s raw SQL into the DB layer

**Files:**
- Modify: `webapp/db/tags.py`
- Modify: `webapp/db/__init__.py`
- Modify: `webapp/routes.py:209-216`
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `webapp.db.get_tag_id_by_name(conn, name: str) -> int | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/webapp/test_db.py`:

```python
class TestGetTagIdByName:
    def test_returns_id_for_existing_tag(self, db_conn):
        assert get_tag_id_by_name(db_conn, "guitar") == 1

    def test_returns_none_for_unknown_tag(self, db_conn):
        assert get_tag_id_by_name(db_conn, "does-not-exist") is None
```

Add `get_tag_id_by_name` to the `from webapp.db import (...)` block at the top of the file.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/webapp/test_db.py::TestGetTagIdByName -v`
Expected: FAIL — `ImportError: cannot import name 'get_tag_id_by_name'`.

- [ ] **Step 3: Implement**

In `webapp/db/tags.py`:

```python
def get_tag_id_by_name(conn: sqlite3.Connection, name: str) -> int | None:
    """The `tags.id` for an exact tag name, or None if no such tag exists."""
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None
```

Add it to both the import block and `__all__` in `webapp/db/__init__.py`.

- [ ] **Step 4: Use it in the route**

```python
@bp.route("/videos/<video_id>/tags/remove", methods=["POST"])
def video_remove_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if tag_name:
        tag_id = _db.get_tag_id_by_name(g.db, tag_name)
        if tag_id is not None:
            _db.remove_video_tag(g.db, video_id, tag_id)
    return "", 204
```

- [ ] **Step 5: Verify**

Run: `grep -n "g.db.execute" webapp/routes.py`
Expected: no output — no route touches SQL directly any more.

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, **571 passed**, warnings summary empty.

- [ ] **Step 6: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: move tag lookup out of the route and into webapp/db/tags"
```

---

## Task 7: Make the 404 contract consistent on video mutation routes

**Files:**
- Modify: `webapp/routes.py` (`video_hide`, `video_unhide`, `video_delete`)
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: all seven `/videos/<id>/...` mutation routes 404 on an unknown ID.

This is one of the plan's two intended behavior changes. No existing test asserts the current silent-success behavior (verified), so nothing should break.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`:

```python
class TestVideoMutationRoutes404:
    @pytest.mark.parametrize("path", [
        "/videos/zzzzzzzzzz9/hide",
        "/videos/zzzzzzzzzz9/unhide",
        "/videos/zzzzzzzzzz9/delete",
    ])
    def test_unknown_video_id_returns_404(self, client, path):
        assert client.post(path).status_code == 404

    @pytest.mark.parametrize("path", [
        "/videos/zzzzzzzzzz9/watched",
        "/videos/zzzzzzzzzz9/mark-watched",
        "/videos/zzzzzzzzzz9/favorite",
        "/videos/zzzzzzzzzz9/rediscover-shelf/remove",
    ])
    def test_siblings_already_return_404(self, client, path):
        assert client.post(path).status_code == 404
```

- [ ] **Step 2: Run to verify the first three fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestVideoMutationRoutes404 -v`
Expected: the three `test_unknown_video_id_returns_404` cases FAIL (they currently return 204 or a 302 redirect); the four `test_siblings_already_return_404` cases PASS.

- [ ] **Step 3: Implement**

```python
@bp.route("/videos/<video_id>/hide", methods=["POST"])
def video_hide(video_id):
    if not _db.get_video_by_id(g.db, video_id):
        abort(404)
    _db.hide_video(g.db, video_id)
    return "", 204


@bp.route("/videos/<video_id>/unhide", methods=["POST"])
def video_unhide(video_id):
    if not _db.get_video_by_id(g.db, video_id):
        abort(404)
    _db.unhide_video(g.db, video_id)
    return redirect(url_for("main.hidden"))


@bp.route("/videos/<video_id>/delete", methods=["POST"])
def video_delete(video_id):
    if not _db.get_video_by_id(g.db, video_id):
        abort(404)
    _db.delete_video(g.db, video_id)
    return redirect(url_for("main.hidden"))
```

- [ ] **Step 4: Verify**

Run: `python -m pytest -q`
Expected: **578 passed**, warnings summary empty. If any pre-existing test fails, it was asserting the silent behavior — read it, and only update it if the test was documenting the bug rather than a requirement.

- [ ] **Step 5: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "fix: 404 on unknown video id for hide/unhide/delete

These three silently succeeded while their four sibling mutation routes
aborted with 404. Silent success on a mutation hides caller bugs."
```

---

## Task 8: Extract the pagination helper (fixes the `append` leak)

**Files:**
- Create: `webapp/pagination.py`
- Create: `tests/webapp/test_pagination.py`
- Modify: `webapp/routes.py` (`index`, `channels`, `hidden`)

**Interfaces:**
- Consumes: nothing.
- Produces: `webapp.pagination.requested_page(args) -> int` and `webapp.pagination.pagination_context(endpoint, *, requested_page, total, page_size) -> dict` returning the keys `page`, `total_pages`, `total`, `prev_url`, `next_url` — exactly the template variables all three routes already pass.

This is the plan's other intended behavior change: `hidden()` currently leaks `append=1` into its Prev/Next links because it strips only `page`, while its two siblings strip `page` and `append`.

- [ ] **Step 1: Write the failing tests**

Create `tests/webapp/test_pagination.py`:

```python
import pytest

from webapp.pagination import pagination_context, requested_page


class TestRequestedPage:
    """Review Focus #1: junk page params must never 500."""

    @pytest.mark.parametrize("raw,expected", [
        ("3", 3),
        ("1", 1),
        ("abc", 1),
        ("-5", 1),
        ("0", 1),
        ("", 1),
        (None, 1),
    ])
    def test_coerces_to_a_sane_page_number(self, raw, expected):
        args = {} if raw is None else {"page": raw}
        assert requested_page(args) == expected


class TestPaginationContext:
    def test_clamps_page_beyond_the_last(self, app):
        with app.test_request_context("/?page=99999"):
            ctx = pagination_context("main.index", requested_page=99999, total=10, page_size=100)
        assert ctx["page"] == 1
        assert ctx["total_pages"] == 1
        assert ctx["next_url"] is None
        assert ctx["prev_url"] is None

    def test_builds_next_and_prev_when_multiple_pages(self, app):
        with app.test_request_context("/?page=2"):
            ctx = pagination_context("main.index", requested_page=2, total=300, page_size=100)
        assert ctx["page"] == 2
        assert ctx["total_pages"] == 3
        assert "page=1" in ctx["prev_url"]
        assert "page=3" in ctx["next_url"]

    def test_carries_other_query_params_into_the_urls(self, app):
        with app.test_request_context("/?channel=SomeChannel&page=1"):
            ctx = pagination_context("main.index", requested_page=1, total=300, page_size=100)
        assert "channel=SomeChannel" in ctx["next_url"]

    def test_drops_the_append_param(self, app):
        """The bug this helper exists to make unrepeatable."""
        with app.test_request_context("/?append=1&page=1"):
            ctx = pagination_context("main.index", requested_page=1, total=300, page_size=100)
        assert "append" not in ctx["next_url"]

    def test_zero_total_still_yields_one_page(self, app):
        with app.test_request_context("/"):
            ctx = pagination_context("main.index", requested_page=1, total=0, page_size=100)
        assert ctx["page"] == 1
        assert ctx["total_pages"] == 1
```

These need an `app` fixture. `tests/webapp/conftest.py` currently exposes `client` and `db_conn`; add an `app` fixture beside them that returns the same configured app the `client` fixture builds (extract the app construction into `app`, and have `client` depend on it) so both fixtures share one setup path rather than duplicating it.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_pagination.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webapp.pagination'`.

- [ ] **Step 3: Implement**

Create `webapp/pagination.py`:

```python
import math
from typing import Any, Mapping

from flask import request, url_for

# Params that describe *which* page is being fetched, rather than what is being
# filtered — they must never be carried into a generated pagination link.
_TRANSIENT_ARGS = ("page", "append")


def requested_page(args: Mapping[str, Any]) -> int:
    """The caller's requested page number, coerced to at least 1."""
    try:
        return max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def pagination_context(endpoint: str, *, requested_page: int, total: int, page_size: int) -> dict:
    """Page numbers plus Prev/Next URLs for a paginated route.

    Returns the template variables the paginated routes all pass through:
    `page`, `total_pages`, `total`, `prev_url`, `next_url`. Filter params from
    the current request are carried into the URLs; `_TRANSIENT_ARGS` are not.
    """
    total_pages = max(1, math.ceil(total / page_size))
    page = min(max(1, requested_page), total_pages)

    def url_for_page(target: int) -> str:
        params = {k: v for k, v in request.args.to_dict().items() if k not in _TRANSIENT_ARGS}
        params["page"] = target
        return url_for(endpoint, **params)

    return {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "prev_url": url_for_page(page - 1) if page > 1 else None,
        "next_url": url_for_page(page + 1) if page < total_pages else None,
    }
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_pagination.py -v`
Expected: all PASS.

- [ ] **Step 5: Migrate the three routes**

In each of `index`, `channels`, and `hidden`: delete the local try/except page parse, the `total_pages` / `page = min(...)` lines, and the local `page_url` closure. Replace with `page = requested_page(request.args)` before the DB count, and merge the context into the template variables afterward. In `index`:

```python
    page = requested_page(request.args)
    # ... existing count_videos / get_all_videos calls, using `page` ...
    template_vars = dict(
        videos=videos,
        # ... unchanged keys ...
        **pagination_context("main.index", requested_page=page, total=total, page_size=PAGE_SIZE),
    )
```

Remove the now-duplicate `page=`, `total_pages=`, `total=`, `prev_url=`, `next_url=` keys from each `template_vars`/`render_template` call so the merged dict is the only source. `channels()` does not currently pass `prev_url`; it now receives one, which `channels.html` simply ignores — harmless, and it makes a Prev link available if that template ever wants it.

Note that `get_all_videos` / `get_channels_page` / `get_hidden_videos` must still receive the **pre-clamp** `page`, exactly as today: all three routes currently query first and clamp afterward. Do not reorder that.

- [ ] **Step 6: Add the route-level regression test for the leak**

Add to `tests/webapp/test_routes.py`:

```python
class TestHiddenPaginationUrls:
    def test_append_param_is_not_carried_into_pagination_links(self, client, monkeypatch):
        monkeypatch.setattr("webapp.routes.PAGE_SIZE", 1)
        client.post("/videos/aaaaaaaaaa1/hide")
        client.post("/videos/aaaaaaaaaa2/hide")
        body = client.get("/hidden?append=1").get_data(as_text=True)
        assert "page=2" in body       # pagination is reachable at this page size
        assert "append" not in body   # ...and the transient param was dropped
```

`hidden.html` contains no other occurrence of the string `append` (verified), so the negative assertion is safe.

- [ ] **Step 7: Verify**

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 578 + 12 + 1 = **591 passed**, warnings summary empty.

- [ ] **Step 8: Commit**

```bash
git add webapp/pagination.py tests/webapp/test_pagination.py && git add -u
git add CHANGELOG.md plan-webapp.md
git commit -m "fix: stop leaking append=1 into Archived pagination links

Extracts the pagination block the three paginated routes each had their
own copy of; hidden() stripped only 'page' where its siblings stripped
'page' and 'append'. The helper makes the drift unrepeatable."
```

---

## Task 9: Extract `VideoListFilters` and split `index()`

**Files:**
- Create: `webapp/video_filters.py`
- Create: `tests/webapp/test_video_filters.py`
- Modify: `webapp/routes.py` (`index`)

**Interfaces:**
- Consumes: nothing.
- Produces: `webapp.video_filters.WatchStatus` (StrEnum), `webapp.video_filters.GroupBy` (StrEnum), `webapp.video_filters.VideoListFilters` (frozen dataclass with `from_args`, `db_kwargs`, `unwatched_only`, `unwatched_first`, `active_count`), and `webapp.video_filters.group_videos(videos, group) -> list | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/webapp/test_video_filters.py`:

```python
from webapp.video_filters import VideoListFilters, group_videos


class TestFromArgs:
    def test_defaults_when_no_args(self):
        f = VideoListFilters.from_args({})
        assert f.sort_by == "date_added"
        assert f.sort_dir == "desc"
        assert f.channel is None
        assert f.watch_status == ""
        assert f.active_count == 0

    def test_empty_string_params_are_normalized_to_none(self):
        f = VideoListFilters.from_args({"channel": "", "tag": "", "duration": ""})
        assert f.channel is None
        assert f.tag is None
        assert f.duration is None
        assert f.active_count == 0

    def test_watch_status_drives_the_two_derived_flags(self):
        assert VideoListFilters.from_args({"watch_status": "unwatched"}).unwatched_only is True
        assert VideoListFilters.from_args({"watch_status": "unwatched"}).unwatched_first is False
        assert VideoListFilters.from_args({"watch_status": "unwatched_first"}).unwatched_first is True
        assert VideoListFilters.from_args({"watch_status": "unwatched_first"}).unwatched_only is False

    def test_unrecognized_watch_status_sets_neither_flag(self):
        f = VideoListFilters.from_args({"watch_status": "bogus"})
        assert f.unwatched_only is False
        assert f.unwatched_first is False
        assert f.active_count == 1  # still counts as "a filter is active"


class TestAddedWithin:
    """Review Focus #2: junk is swallowed here; out-of-allowlist is the DB layer's 400."""

    def test_non_numeric_becomes_none(self):
        assert VideoListFilters.from_args({"added_within": "notanumber"}).added_within is None

    def test_numeric_is_kept_verbatim_even_if_not_in_the_db_allowlist(self):
        # 5 is not in _ADDED_WITHIN_DAYS; get_all_videos raises ValueError on it,
        # which the index route turns into a 400. Parsing must not swallow it.
        assert VideoListFilters.from_args({"added_within": "5"}).added_within == 5


class TestActiveCount:
    def test_counts_each_active_filter_once(self):
        f = VideoListFilters.from_args({
            "channel": "SomeChannel",
            "tag": "some-tag",
            "sort_by": "title",
            "sort_dir": "asc",
            "group": "channel",
            "favorites": "1",
            "watch_status": "unwatched",
            "duration": "short",
            "added_within": "7",
        })
        assert f.active_count == 9

    def test_search_does_not_count(self):
        assert VideoListFilters.from_args({"search": "anything"}).active_count == 0


class TestDbKwargs:
    def test_maps_watch_status_onto_unwatched_only(self):
        kwargs = VideoListFilters.from_args({"watch_status": "unwatched"}).db_kwargs()
        assert kwargs["unwatched_only"] is True
        assert "unwatched_first" not in kwargs   # get_all_videos takes that separately
        assert set(kwargs) == {
            "channel", "tag", "search", "favorites_only",
            "unwatched_only", "duration", "added_within",
        }


class TestGroupVideos:
    VIDEOS = [
        {"video_id": "v1", "channel_name": "A", "tags": "x,y"},
        {"video_id": "v2", "channel_name": "B", "tags": ""},
        {"video_id": "v3", "channel_name": "A", "tags": "x"},
    ]

    def test_returns_none_when_not_grouping(self):
        assert group_videos(self.VIDEOS, None) is None
        assert group_videos(self.VIDEOS, "") is None

    def test_groups_by_channel(self):
        groups = group_videos(self.VIDEOS, "channel")
        assert [g["tag"]["name"] for g in groups] == ["A", "B"]
        assert len(groups[0]["videos"]) == 2

    def test_missing_channel_name_becomes_unknown(self):
        groups = group_videos([{"video_id": "v9", "channel_name": None, "tags": ""}], "channel")
        assert groups[0]["tag"]["name"] == "Unknown"

    def test_groups_by_tag_with_untagged_last(self):
        groups = group_videos(self.VIDEOS, "tag")
        assert [g["tag"]["name"] for g in groups] == ["x", "y", "Untagged"]

    def test_a_video_with_two_tags_appears_in_both_groups(self):
        groups = {g["tag"]["name"]: g["videos"] for g in group_videos(self.VIDEOS, "tag")}
        assert groups["x"] == [self.VIDEOS[0], self.VIDEOS[2]]
        assert groups["y"] == [self.VIDEOS[0]]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_video_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webapp.video_filters'`.

- [ ] **Step 3: Implement**

Create `webapp/video_filters.py`:

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

DEFAULT_SORT_BY = "date_added"
DEFAULT_SORT_DIR = "desc"


class WatchStatus(StrEnum):
    """Values of the toolbar's single watch-status select. Empty string = all videos."""
    UNWATCHED = "unwatched"
    UNWATCHED_FIRST = "unwatched_first"


class GroupBy(StrEnum):
    CHANNEL = "channel"
    TAG = "tag"


@dataclass(frozen=True)
class VideoListFilters:
    """The main video list's filter/sort state, parsed from the query string."""

    sort_by: str = DEFAULT_SORT_BY
    sort_dir: str = DEFAULT_SORT_DIR
    channel: str | None = None
    tag: str | None = None
    search: str | None = None
    group: str | None = None
    favorites_only: bool = False
    watch_status: str = ""
    duration: str | None = None
    added_within: int | None = None

    @classmethod
    def from_args(cls, args: Mapping[str, Any]) -> "VideoListFilters":
        try:
            added_within = int(args["added_within"]) if args.get("added_within") else None
        except ValueError:
            added_within = None
        return cls(
            sort_by=args.get("sort_by", DEFAULT_SORT_BY),
            sort_dir=args.get("sort_dir", DEFAULT_SORT_DIR),
            channel=args.get("channel") or None,
            tag=args.get("tag") or None,
            search=args.get("search") or None,
            group=args.get("group") or None,
            favorites_only=args.get("favorites") == "1",
            watch_status=args.get("watch_status", ""),
            duration=args.get("duration") or None,
            added_within=added_within,
        )

    @property
    def unwatched_only(self) -> bool:
        return self.watch_status == WatchStatus.UNWATCHED

    @property
    def unwatched_first(self) -> bool:
        return self.watch_status == WatchStatus.UNWATCHED_FIRST

    @property
    def active_count(self) -> int:
        """How many filters differ from their default — the `Filters N` badge.

        Search deliberately does not count: it lives outside the collapsible
        filter panel the badge describes. See plan-webapp.md.
        """
        return sum((
            self.channel is not None,
            self.tag is not None,
            self.sort_by != DEFAULT_SORT_BY,
            self.sort_dir != DEFAULT_SORT_DIR,
            bool(self.group),
            self.favorites_only,
            bool(self.watch_status),
            bool(self.duration),
            self.added_within is not None,
        ))

    def db_kwargs(self) -> dict:
        """The subset of this state that both count_videos and get_all_videos take."""
        return {
            "channel": self.channel,
            "tag": self.tag,
            "search": self.search,
            "favorites_only": self.favorites_only,
            "unwatched_only": self.unwatched_only,
            "duration": self.duration,
            "added_within": self.added_within,
        }


def group_videos(videos: list[dict], group: str | None) -> list[dict] | None:
    """Partition a page of videos for the grouped views, or None when not grouping.

    Shape is `[{"tag": {"name": label}, "videos": [...]}, ...]`, consumed by
    `_video_container.html`. A video with several canonical tags appears in each
    matching group, so groups can overlap; channel groups cannot.
    """
    if group == GroupBy.CHANNEL:
        grouped: dict[str, list[dict]] = {}
        for video in videos:
            grouped.setdefault(video.get("channel_name") or "Unknown", []).append(video)
        return [{"tag": {"name": name}, "videos": vids} for name, vids in grouped.items()]

    if group == GroupBy.TAG:
        grouped = {}
        untagged: list[dict] = []
        for video in videos:
            names = [t.strip() for t in (video.get("tags") or "").split(",") if t.strip()]
            if not names:
                untagged.append(video)
            for name in names:
                grouped.setdefault(name, []).append(video)
        groups = [{"tag": {"name": name}, "videos": vids} for name, vids in sorted(grouped.items())]
        if untagged:
            groups.append({"tag": {"name": "Untagged"}, "videos": untagged})
        return groups

    return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_video_filters.py -v`
Expected: all PASS.

- [ ] **Step 5: Rewrite `index()` to use them**

```python
@bp.route("/")
def index():
    filters = VideoListFilters.from_args(request.args)
    append = request.args.get("append") == "1"
    page = requested_page(request.args)

    try:
        total = _db.count_videos(g.db, **filters.db_kwargs())
        videos = _db.get_all_videos(
            g.db,
            sort_by=filters.sort_by, sort_dir=filters.sort_dir,
            group=filters.group, unwatched_first=filters.unwatched_first,
            page=page, page_size=PAGE_SIZE,
            **filters.db_kwargs(),
        )
    except ValueError:
        abort(400)

    template_vars = dict(
        videos=videos,
        channels=_db.get_video_channel_names(g.db),
        canonical_tags=_db.get_canonical_tags_for_filter_grouped(g.db),
        groups=group_videos(videos, filters.group),
        sort_by=filters.sort_by,
        sort_dir=filters.sort_dir,
        current_channel=filters.channel,
        current_tag=filters.tag,
        current_search=filters.search,
        group=filters.group,
        favorites_only=filters.favorites_only,
        watch_status=filters.watch_status,
        current_duration=filters.duration,
        current_added_within=filters.added_within,
        active_filter_count=filters.active_count,
        **pagination_context("main.index", requested_page=page, total=total, page_size=PAGE_SIZE),
    )

    if request.headers.get("HX-Request"):
        if append:
            return render_template("_load_more.html", **template_vars)
        return render_template("_video_container.html", **template_vars)

    shelf = _db.get_current_rediscover_shelf(g.db)
    template_vars["shelf"] = shelf
    template_vars["expires_label"] = shelf_expires_label(shelf.get("expires_at"))
    return render_template("index.html", **template_vars)
```

Keep the template variable **names** exactly as they are (`current_channel`, not `channel`) — renaming them would mean touching every template, which is out of scope for a behavior-free refactor.

Note `shelf_expires_label` is still `_shelf_expires_label` in `routes.py` at this point; Task 11 moves and renames it. Leave the call as `_shelf_expires_label(...)` until then.

- [ ] **Step 6: Verify**

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 591 + 14 = **605 passed**, warnings summary empty. The existing `TestIndexRoute`, `TestIndexFilterQuickWins`, and the watch-status and rediscover-shelf-marker tests are the real proof the refactor is behavior-free.

- [ ] **Step 7: Commit**

```bash
git add webapp/video_filters.py tests/webapp/test_video_filters.py && git add -u
git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: extract VideoListFilters and group_videos out of index()

index() was ~115 lines doing six jobs; filter parsing and the grouping
transform are now pure functions with direct unit tests, where before
they could only be exercised through a full HTTP request."
```

---

## Task 10: Extract the repeated SQL fragments and row handling in `webapp/db/videos.py`

**Files:**
- Modify: `webapp/db/videos.py`
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: module-private `_video_pk`, `_to_video_dicts`, `_CANONICAL_TAGS_SELECT`, `_VIDEO_TAGS_JOIN` inside `webapp/db/videos.py`. Nothing outside the module may import these.

**Explicitly not doing:** merging `get_hidden_videos` into `get_all_videos`. `_build_where` always adds `v.fetch_status = 'ok'`; `get_hidden_videos` deliberately omits it so archived videos whose metadata fetch failed still show on the Archived page. Unifying them would silently hide those rows. Extract the shared fragments only, and record the difference in a comment.

- [ ] **Step 1: Write the failing test**

Add to `tests/webapp/test_db.py`, in `TestGetAllVideos` (Review Focus #5):

```python
    def test_video_with_no_tags_gets_empty_string_not_none(self, db_conn):
        # aaaaaaaaaa4 has no canonical tags, so GROUP_CONCAT yields SQL NULL.
        # Templates call .split(",") on this, so it must be "" and never None.
        rows = {r["video_id"]: r for r in get_all_videos(db_conn)}
        assert rows["aaaaaaaaaa4"]["tags"] == ""

    def test_hidden_videos_keep_the_same_tags_contract(self, db_conn):
        db_conn.execute("UPDATE videos SET is_hidden = 1 WHERE video_id = 'aaaaaaaaaa4'")
        db_conn.commit()
        rows = {r["video_id"]: r for r in get_hidden_videos(db_conn)}
        assert rows["aaaaaaaaaa4"]["tags"] == ""
```

- [ ] **Step 2: Run to confirm they pass before the refactor**

Run: `python -m pytest tests/webapp/test_db.py -k "empty_string_not_none or same_tags_contract" -v`
Expected: both PASS. These are characterization tests: they pin the contract the extraction must not break.

- [ ] **Step 3: Add the helpers**

Near the top of `webapp/db/videos.py`, below `_ADDED_WITHIN_DAYS`:

```python
# Shared SQL for "a video row plus its canonical tag names". Both list queries
# below GROUP BY v.id, so GROUP_CONCAT collapses the joined tag rows into one
# comma-separated column — NULL when the video has no canonical tags, which
# _to_video_dicts normalizes to "".
_CANONICAL_TAGS_SELECT = "GROUP_CONCAT(CASE WHEN t.is_canonical = 1 THEN t.name ELSE NULL END) AS tags"
_VIDEO_TAGS_JOIN = """
        LEFT JOIN video_tags vt ON vt.video_id_fk = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id_fk
"""


def _video_pk(conn: sqlite3.Connection, video_id: str) -> int | None:
    """The `videos.id` surrogate key for a YouTube video ID, or None if absent."""
    row = conn.execute("SELECT id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return row[0] if row else None


def _to_video_dicts(rows) -> list[dict]:
    """Row objects to plain dicts, with a NULL `tags` column normalized to ""."""
    result = []
    for row in rows:
        d = dict(row)
        d["tags"] = d.get("tags") or ""
        result.append(d)
    return result
```

- [ ] **Step 4: Use them**

Replace the four copies of the row→dict loop (in `get_all_videos`, `get_hidden_videos`, `get_watch_later_queue`, and the tag-normalization inside `get_current_rediscover_shelf`) with `_to_video_dicts(rows)`. In `get_current_rediscover_shelf` the loop also builds the `reason` string — keep that loop for now (Task 11 moves `reason` out) but have it start from `_to_video_dicts(rows)`.

Substitute `{_CANONICAL_TAGS_SELECT}` and `{_VIDEO_TAGS_JOIN}` into the four f-string queries that spell them out.

Replace the six `SELECT id FROM videos WHERE video_id = ?` lookups with `_video_pk(conn, video_id)` in `add_to_watch_later`, `remove_from_watch_later`, `is_in_watch_later`, `reorder_watch_later`, and `add_video`. Each call site currently reads `video["id"]` or `video_row[0]` afterward — replace with the returned int, and the `if not video: return False` guards with `if pk is None: return False`.

Then make `_build_where`'s parameters keyword-only so its two callers can never drift positionally:

```python
def _build_where(*, channel=None, tag=None, search=None, favorites_only=False,
                 unwatched_only=False, duration=None, added_within=None):
```

and update both call sites to pass by keyword. Add a comment above `get_hidden_videos`'s `WHERE v.is_hidden = 1`:

```python
    # No fetch_status filter here, unlike _build_where: a video you archived
    # should stay visible on the Archived page even if its metadata fetch failed.
```

- [ ] **Step 5: Verify**

Run: `grep -c "SELECT id FROM videos WHERE video_id" webapp/db/videos.py`
Expected: `1` (only inside `_video_pk`).

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 605 + 2 = **607 passed**, warnings summary empty. `tests/webapp/test_db.py` is 1,575 lines and covers these functions heavily — it is the proof.

- [ ] **Step 6: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: extract repeated SQL fragments and row handling in db/videos

Six copies of the video-PK lookup, four of the row->dict + tags
normalization, four of the canonical-tags JOIN. Deliberately did not
merge get_hidden_videos into get_all_videos: their fetch_status
semantics differ on purpose, now noted in a comment."
```

---

## Task 11: Move presentation logic into `webapp/filters.py`

**Files:**
- Modify: `webapp/filters.py`
- Modify: `webapp/db/videos.py` (`get_current_rediscover_shelf`)
- Modify: `webapp/routes.py` (remove `_shelf_expires_label`)
- Modify: `webapp/app.py` (register the new Jinja filter)
- Modify: `webapp/templates/_shelf_cards.html` (apply the filter)
- Test: `tests/webapp/test_filters.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `webapp.filters.shelf_expires_label(expires_at: str | None) -> str` and `webapp.filters.last_viewed_reason(personal_view_count: int, date_last_viewed: str | None, *, now=None) -> str`, the latter registered as the Jinja filter `last_viewed_reason`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_filters.py`:

```python
from datetime import datetime, timedelta, timezone

from webapp.filters import last_viewed_reason, shelf_expires_label


class TestShelfExpiresLabel:
    def test_none_is_an_em_dash(self):
        assert shelf_expires_label(None) == "—"

    def test_unparseable_is_an_em_dash(self):
        assert shelf_expires_label("not-a-date") == "—"

    def test_past_is_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert shelf_expires_label(past) == "expired"

    def test_days_are_pluralized(self):
        assert shelf_expires_label((datetime.now(timezone.utc) + timedelta(days=3)).isoformat()) == "3 days"
        assert shelf_expires_label((datetime.now(timezone.utc) + timedelta(days=1, hours=1)).isoformat()) == "1 day"

    def test_under_a_day_falls_back_to_hours(self):
        soon = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        assert shelf_expires_label(soon) == "5 hours"


class TestLastViewedReason:
    NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    def test_never_opened(self):
        assert last_viewed_reason(0, None, now=self.NOW) == "Never opened"

    def test_no_date_but_viewed(self):
        assert last_viewed_reason(3, None, now=self.NOW) == "Not recently viewed"

    def test_today(self):
        same_day = datetime(2026, 9, 24, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, same_day, now=self.NOW) == "Last viewed today"

    def test_one_day_is_singular(self):
        yesterday = datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, yesterday, now=self.NOW) == "Last viewed 1 day ago"

    def test_many_days(self):
        older = datetime(2026, 9, 14, 1, 0, tzinfo=timezone.utc).isoformat()
        assert last_viewed_reason(1, older, now=self.NOW) == "Last viewed 10 days ago"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_filters.py -v`
Expected: FAIL — `ImportError: cannot import name 'last_viewed_reason'`.

- [ ] **Step 3: Implement in `webapp/filters.py`**

```python
def shelf_expires_label(expires_at: str | None) -> str:
    """Human label for how long the rediscover shelf has left ("3 days", "5 hours")."""
    if not expires_at:
        return "—"
    try:
        expires = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return "—"
    diff = expires - datetime.now(timezone.utc)
    if diff.total_seconds() <= 0:
        return "expired"
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''}"
    hours = diff.seconds // 3600
    return f"{hours} hour{'s' if hours != 1 else ''}"


def last_viewed_reason(
    personal_view_count: int,
    date_last_viewed: str | None,
    *,
    now: datetime | None = None,
) -> str:
    """Why a video is on the rediscover shelf, as shown on its card."""
    if not personal_view_count:
        return "Never opened"
    if not date_last_viewed:
        return "Not recently viewed"
    reference = now or datetime.now(timezone.utc)
    days = (reference - datetime.fromisoformat(date_last_viewed)).days
    if days == 0:
        return "Last viewed today"
    if days == 1:
        return "Last viewed 1 day ago"
    return f"Last viewed {days} days ago"
```

Note the narrowed `except (TypeError, ValueError)` — the original caught bare `Exception`.

- [ ] **Step 4: Remove the logic from its old homes**

Delete `_shelf_expires_label` from `webapp/routes.py` (and its `datetime`/`timezone` imports if nothing else there uses them); import and call `shelf_expires_label` instead.

In `webapp/db/videos.py`, delete the `reason`-building branch from `get_current_rediscover_shelf`'s loop so it only returns data. Register the filter in `webapp/app.py` beside the existing three:

```python
    app.jinja_env.filters["last_viewed_reason"] = _filters.last_viewed_reason
```

In `webapp/templates/_shelf_cards.html`, replace the use of `video.reason` with a call that passes the two fields the filter needs — Jinja cannot call a two-argument filter ergonomically, so pass the video and unpack inside a one-argument wrapper instead:

```python
def shelf_reason(video: dict) -> str:
    """Jinja-friendly wrapper: reads the two fields off a shelf video row."""
    return last_viewed_reason(video.get("personal_view_count") or 0, video.get("date_last_viewed"))
```

Register `shelf_reason` as the filter and use `{{ video | shelf_reason }}` in the template.

- [ ] **Step 5: Verify**

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 607 + 10 = **617 passed**, warnings summary empty.

Load the page to confirm the shelf still shows its reason lines and expiry label. Per the `feedback-sandbox-localhost-port-unreliable` memory, **do not** verify with `curl` against a locally started server in this environment — use an in-process render instead:

```bash
python3 -c "
from webapp.app import create_app
c = create_app('airchivist-test.db').test_client()
body = c.get('/').get_data(as_text=True)
assert 'Refreshes automatically in' in body
print([l.strip() for l in body.splitlines() if 'Last viewed' in l or 'Never opened' in l][:3])
"
```

Expected: prints a few reason strings, proving the filter renders.

- [ ] **Step 6: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: move shelf label and last-viewed copy into webapp/filters

User-facing strings were being built in the DB layer and the route
module; filters.py is where this project already puts them. Also
narrows a bare 'except Exception' to (TypeError, ValueError)."
```

---

## Task 12: `LLMError` hierarchy, shared tool-call helper, and error codes instead of raw exception text

**Files:**
- Modify: `webapp/llm_tagger.py`
- Modify: `webapp/routes.py` (`tags_llm_suggest`, `tag_groups_auto_assign`, `tags`)
- Modify: `webapp/templates/tags.html:47-49`
- Test: `tests/webapp/test_llm_tagger.py:158,163,176`, `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `webapp.llm_tagger.LLMError` (base), `LLMUnavailableError`, `LLMResponseError`; module-private `_client()` and `_call_tool(...)`. Routes catch `LLMError` only.

- [ ] **Step 1: Update the existing exception expectations**

In `tests/webapp/test_llm_tagger.py`, change the three `pytest.raises` lines:

```python
# line 158
            with pytest.raises(LLMUnavailableError, match="ANTHROPIC_API_KEY"):
# line 163
            with pytest.raises(LLMUnavailableError, match="anthropic"):
# line 176
            with pytest.raises(LLMResponseError, match="categorize_tags"):
```

and import the three new names at the top. Add one test pinning the hierarchy, so callers can rely on the single base class:

```python
class TestErrorHierarchy:
    def test_both_subclass_llm_error(self):
        assert issubclass(LLMUnavailableError, LLMError)
        assert issubclass(LLMResponseError, LLMError)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/webapp/test_llm_tagger.py -v`
Expected: FAIL — `ImportError: cannot import name 'LLMError'`.

- [ ] **Step 3: Implement in `webapp/llm_tagger.py`**

```python
class LLMError(RuntimeError):
    """Base for every failure of an LLM-backed feature."""


class LLMUnavailableError(LLMError):
    """The anthropic package is missing, or no API key is configured."""


class LLMResponseError(LLMError):
    """The model replied, but not in the shape we require."""


def _client():
    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailableError(
            "The 'anthropic' package is required for LLM tag suggestions. "
            "Install it with: pip install anthropic"
        ) from exc
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailableError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _call_tool(*, system: str, tool: dict, user_message: str, model: str, max_tokens: int) -> dict:
    """Force one tool call and return its input, or raise LLMResponseError."""
    response = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_message}],
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise LLMResponseError(f"LLM did not call the {tool['name']} tool")
    return tool_use.input
```

Add the two max-token values as module constants beside `DEFAULT_MODEL` (`_SUGGEST_MAX_TOKENS = 4096`, `_GROUP_ASSIGN_MAX_TOKENS = 1024`) and the `"_noise"` sentinel as `NOISE_CANONICAL = "_noise"`, then rewrite both public functions to start from `_call_tool(...)` and keep only their own result-shaping logic. Update their docstrings: they now raise `LLMUnavailableError` / `LLMResponseError`, not `ImportError` / `EnvironmentError` / `ValueError`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/webapp/test_llm_tagger.py -v`
Expected: all PASS.

- [ ] **Step 5: Replace the raw-exception-text redirects**

Both `tags_llm_suggest` and `tag_groups_auto_assign` currently build `llm_error=f"...: {e}"` into a redirect, which `tags.html` renders raw — putting internal exception detail in the address bar and browser history. `flask.flash` would be idiomatic but `create_app` sets no `secret_key`, so it would raise; pass a stable code instead:

```python
    try:
        suggestions = _llm.get_suggestions(canonical, unclassified)
    except _llm.LLMError:
        return redirect(url_for("main.tags", llm_error="unavailable"))
```

Use `llm_error="unavailable"` for both routes' `LLMError` branch and drop the three-branch ladders entirely. In `webapp/templates/tags.html`, map the code to copy rather than echoing it:

```html
  {% if llm_error %}
  <div class="llm-error">
    {% if llm_error == 'unavailable' %}
      Smart Suggest is unavailable — check that the anthropic package is installed and ANTHROPIC_API_KEY is set.
    {% else %}
      Smart Suggest failed. Check the server log for details.
    {% endif %}
  </div>
  {% endif %}
```

- [ ] **Step 6: Pin the new behavior**

Add to `tests/webapp/test_routes.py`:

```python
class TestLlmErrorSurfacing:
    def test_llm_failure_redirects_with_a_code_not_exception_text(self, client, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("psycopg2 connection string with a secret in it")
        monkeypatch.setattr("webapp.llm_tagger.get_suggestions", boom)
        resp = client.post("/tags/llm-suggest")
        assert resp.status_code == 302
        assert "secret" not in resp.headers["Location"]
```

Note this asserts the *generic* branch: a bare `RuntimeError` is not an `LLMError`, so it must not be swallowed into the URL either. Keep a broad `except Exception` in the route *only* if it also maps to a code — otherwise let it 500 and be visible in the log. Choose the latter unless an existing test requires the redirect; if this test fails because the exception propagates as a 500, change the assertion to `assert resp.status_code == 500` and note the decision in the changelog.

- [ ] **Step 7: Verify**

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 617 + 2 = **619 passed**, warnings summary empty.

- [ ] **Step 8: Commit**

```bash
git add -u && git add CHANGELOG.md plan-webapp.md
git commit -m "refactor: LLMError hierarchy, shared tool-call helper, error codes in URLs

Replaces the deprecated EnvironmentError (an OSError alias) with a real
domain hierarchy, collapsing a duplicated three-branch except ladder to
one clause, and stops interpolating raw exception text into redirect
URLs and browser history."
```

---

## Task 13: Typing modernization and mypy

**Files:**
- Modify: `pyproject.toml` (add `UP` to ruff's select list; add `[tool.mypy]`; add `mypy` to dev extras)
- Modify: every file with `Optional[...]` or a bare generic return (`webapp/db/*.py`, `crawler/*.py`)
- Modify: `crawler/models.py` (enum-typed fields)

**Interfaces:**
- Consumes: nothing.
- Produces: `mypy webapp crawler` as a second gate alongside ruff.

- [ ] **Step 1: Let ruff do the mechanical part**

Add `"UP"` to `select` in `[tool.ruff.lint]`, then:

Run: `ruff check --fix .`
Expected: rewrites the 59 `Optional[X]` annotations to `X | None` and removes the now-unused `from typing import Optional` imports.

Run: `ruff check . && python -m pytest -q`
Expected: ruff clean, 619 passed, warnings summary empty.

- [ ] **Step 2: Tighten the bare generics by hand**

ruff cannot infer these. Replace bare returns with parameterized ones across `webapp/db/*.py` and `crawler/datastore.py`:

- `-> list` → `-> list[dict]` (every `get_*` returning rows)
- `-> dict` → `-> dict[str, Any]` on `get_stats` and `get_current_rediscover_shelf`
- `-> set` → `-> set[str]` on `get_watch_later_video_ids`
- `tags: list` → `tags: list[dict]`

Add `from typing import Any` where needed.

- [ ] **Step 3: Type the enum-valued dataclass fields**

In `crawler/models.py`, change `fetch_status: str = FetchStatus.PENDING` to `fetch_status: FetchStatus = FetchStatus.PENDING` on `VideoMetadata`, and the same on `ChannelMetadata` (default `FetchStatus.OK`). Add `-> None` to `VideoMetadata.__post_init__`.

Run: `python -m pytest -q`
Expected: 619 passed. `FetchStatus` is a `StrEnum`, so any code comparing against or writing the raw string still works.

- [ ] **Step 4: Add mypy, configured to be useful rather than absolute**

Add `mypy` to the `dev` extras and append to `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
files = ["webapp", "crawler"]
# Deliberately not strict: this codebase is ~50% annotated today, and
# --strict would produce hundreds of findings with no path to green.
# These three catch real bugs without demanding full annotation.
warn_redundant_casts = true
warn_unused_ignores = true
warn_unreachable = true
```

Run: `mypy`
Expected: some findings. Fix the ones that indicate real type confusion; add a narrowly scoped `# type: ignore[code]` with a one-line reason for anything that is a false positive from an untyped third-party call (`yt_dlp`, `anthropic`). Do not add blanket `ignore_errors` for whole modules.

- [ ] **Step 5: Add mypy to pre-commit**

```yaml
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [flask]
```

Run: `pre-commit run --all-files`
Expected: passes.

- [ ] **Step 6: Verify and commit**

Run: `ruff check . && mypy && python -m pytest -q && npm test`
Expected: all clean; 619 passed, 24 passed, warnings summary empty.

```bash
git add -u && git add CHANGELOG.md plan-webapp.md plan-crawler.md
git commit -m "chore: modernize typing to PEP 604 unions, add mypy gate"
```

---

## Task 14: Extension popup cleanup

**Files:**
- Modify: `extension/popup/popup.js`
- Modify: `extension/popup/popup.css` (create if absent — check first)
- Test: `tests/extension/popup.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `initToggle(config)` replacing `initWatchLaterToggle` and `initFavoriteToggle`; both names stay exported as thin wrappers so the existing 16 toggle tests keep passing unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/extension/popup.test.js`:

```javascript
describe('initToggle', () => {
  const airchivistUrl = 'http://localhost:8080';
  const tabUrl = 'https://www.youtube.com/watch?v=abc123';

  test('is exported and drives an arbitrary checkbox/endpoint pair', async () => {
    document.getElementById('root').innerHTML = `
      <input type="checkbox" id="chk-generic" disabled>
      <div id="generic-error" style="display:none"></div>
    `;
    global.fetch = mockFetchRouter([
      ['/api/thing/status', () => jsonResponse({ on: true })],
    ]);

    await popup.initToggle({
      checkboxId: 'chk-generic',
      errorBoxId: 'generic-error',
      statusPath: '/api/thing/status',
      statusKey: 'on',
      addPath: '/api/thing/add',
      removePath: '/api/thing/remove',
      addSuccessStatuses: ['added'],
      errorLabel: '✗ Thing update failed',
      airchivistUrl,
      tabUrl,
    });

    const chk = document.getElementById('chk-generic');
    expect(chk.checked).toBe(true);
    expect(chk.disabled).toBe(false);
  });
});
```

Add `initToggle` to the `module exports` assertions at the top of the file.

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- tests/extension/popup.test.js`
Expected: FAIL — `popup.initToggle is not a function`.

- [ ] **Step 3: Implement `initToggle` and reduce both callers to config**

```javascript
async function initToggle({
  checkboxId, errorBoxId, statusPath, statusKey,
  addPath, removePath, addSuccessStatuses, removeSuccessStatus = 'removed',
  errorLabel, airchivistUrl, tabUrl,
}) {
  const chk = document.getElementById(checkboxId);
  const errBox = document.getElementById(errorBoxId);

  let initial;
  try {
    const data = await postJson(`${airchivistUrl}${statusPath}`, { url: tabUrl });
    initial = !!data[statusKey];
  } catch {
    return; // Leave disabled — unknown state, nothing safe to toggle.
  }

  chk.checked = initial;
  chk.disabled = false;

  chk.addEventListener('change', async () => {
    const wantOn = chk.checked;
    chk.disabled = true;
    errBox.style.display = 'none';

    let ok;
    try {
      const data = await postJson(`${airchivistUrl}${wantOn ? addPath : removePath}`, { url: tabUrl });
      ok = wantOn
        ? addSuccessStatuses.includes(data.status)
        : data.status === removeSuccessStatus;
    } catch {
      ok = false;
    }

    if (!ok) {
      chk.checked = !wantOn;
      errBox.textContent = errorLabel;
      errBox.style.display = 'block';
    }
    chk.disabled = false;
  });
}

async function initWatchLaterToggle(airchivistUrl, tabUrl) {
  return initToggle({
    checkboxId: 'chk-watch-later', errorBoxId: 'wl-error',
    statusPath: '/api/watch-later/status', statusKey: 'in_queue',
    addPath: '/api/watch-later/add', removePath: '/api/watch-later/remove',
    addSuccessStatuses: ['added', 'already_in_queue'],
    errorLabel: '✗ Watch Later update failed',
    airchivistUrl, tabUrl,
  });
}

async function initFavoriteToggle(airchivistUrl, tabUrl) {
  return initToggle({
    checkboxId: 'chk-favorite', errorBoxId: 'fav-error',
    statusPath: '/api/favorite/status', statusKey: 'is_favorite',
    addPath: '/api/favorite/add', removePath: '/api/favorite/remove',
    addSuccessStatuses: ['added'],
    errorLabel: '✗ Favorite update failed',
    airchivistUrl, tabUrl,
  });
}
```

Note this also routes both toggles through the file's existing `postJson` helper instead of hand-rolling `fetch`. Add `initToggle` to `module.exports`.

- [ ] **Step 4: Run the existing toggle suites unchanged**

Run: `npm test -- tests/extension/popup.test.js`
Expected: 24 + 1 = **25 passed**. The 16 pre-existing `initWatchLaterToggle` / `initFavoriteToggle` tests must pass **without modification** — that is the proof the extraction is behavior-free.

- [ ] **Step 5: Replace the remaining hand-rolled fetches and the repeated inline style**

Convert the other raw `fetch(` calls that POST JSON (in `doHide`, `doRestore`, `doDelete`, `checkStatus`) to `postJson` where the shape matches; leave any that genuinely differ (no JSON body, or a non-JSON response) alone and add a one-line comment saying why.

Check whether `extension/popup/popup.html` already loads a stylesheet. Move the 5 repeated `style="display:block;margin-top:0.4rem;font-size:0.8rem;cursor:pointer;color:#aaa"` occurrences to a single `.popup-check-label` class in the extension's CSS and use `class="popup-check-label"` in the five template strings. The extension is a separate document from the webapp, so it does not share `style.css` tokens — keep its literals, and note that in the comment above the class.

- [ ] **Step 6: Verify**

Run: `npm test`
Expected: 25 passed.

Manually load the extension (`about:debugging` → reload the temporary add-on, per the `feedback-flag-restart-and-cache-refresh` memory) and confirm both checkboxes in the `exists` state still reflect and change state. **State this reload requirement explicitly in the response** — an extension change does not take effect until the add-on is reloaded.

- [ ] **Step 7: Commit**

```bash
git add -u && git add CHANGELOG.md plan-extension.md
git commit -m "refactor: extract initToggle in the extension popup

The two toggles were ~90% identical (a knowingly-accepted duplication
when the second landed) and both hand-rolled fetch calls the file's own
postJson helper already covered."
```

---

## Deferred — not in this plan

These came out of the audit but are deliberately left for later, with reasons:

- **Unifying `crawler.Datastore` with `webapp/db/*`** (~7 duplicated read/write paths, `apply_aliases` living in the crawler, DDL defined twice, per-function `conn.commit()` preventing composable transactions). This is the only audit item with real regression risk, it pairs with the "proper migrations table" item already in `TODO.md`, and it needs its own brainstorm to decide where shared code belongs. See the "Out of scope" section of the spec.
- **Slimming `webapp/db/__init__.py`** (134 lines, every symbol listed twice, in two different orders). Low value relative to the churn; revisit if the facade drifts out of sync.
- **Tests for `tools/tag_categorizer.py`** (728 lines, 0% coverage, measured by `--cov=tools`). Worth a small task covering the pure helpers (`_noise_category`, `_build_suggest_prompt`, `_save_approved`) rather than the interactive commands. Not blocking anything else.
- **Enabling ruff's `B` and `SIM`** rule sets. Their findings need case-by-case judgment, so they deserve their own pass once this baseline is green.

## Self-review notes

- **Spec coverage:** F1→T1, F2→T2, F3→T4+T5, F4→T4+T9, F5→T3, F6→T8, F7→T9, F8→T7, F9→T6, F10→T12, F11→T12, F12→T10, F13→T11, F14→T13, F17→T14. F15 and F16 are in Deferred with reasons. Every finding is either assigned or explicitly deferred.
- **Type consistency:** `extract_video_id` (T3) is consumed by name in T4 and T5. `cors_json`/`resolve_video`/`ApiStatus` (T4) are consumed in T5. `requested_page`/`pagination_context` (T8) are consumed in T9. `_video_pk`/`_to_video_dicts` (T10) stay module-private. `shelf_expires_label` is called as `_shelf_expires_label` in T9 and renamed in T11 — flagged inline in T9 Step 5 so the executor is not surprised.
- **Test-count arithmetic** is stated at each task so a drifting total is caught immediately: 585 → 555 (T2 deletes 30) → 560 → 564 → 569 → 571 → 578 → 591 → 605 → 607 → 617 → 619, and 24 → 25 on the JS side.
