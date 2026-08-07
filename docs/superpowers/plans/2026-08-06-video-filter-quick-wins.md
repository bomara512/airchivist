# Video Filter Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three filters to the main video index — **unwatched-only**, **duration** (short/medium/long), and **added-within** (7/30/90/365 days) — extending the existing shared `_build_where` composer and the filter form.

**Architecture:** Two layers. (1) `webapp/db/videos.py`: extend `_build_where` with three keyword params (plus two allow-list constants) and thread them through `get_all_videos` and `count_videos`; invalid `duration`/`added_within` raise `ValueError`. (2) `webapp/routes.py` + `index.html`: the `index` route reads/passes the three params (ValueError → `abort(400)`, as sort validation already does) and the filter form gains a checkbox and two selects. No new tables, no new query paths.

**Tech Stack:** Python, Flask, SQLite, Jinja2, htmx; pytest.

## Global Constraints

- New/changed public functions in `webapp/db/*.py` and routes in `webapp/routes.py` require tests in the same change (happy path + at least one edge case).
- Never interpolate user input into SQL — `duration`/`added_within` are validated against allow-lists; the day count is passed as a bound `'-N days'` modifier, never interpolated.
- `/` is a normal server-rendered page — no `_CORS_HEADERS`/OPTIONS.
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry, update `plan-webapp.md`, and update `TODO.md` for the implementation change.
- Run `python -m pytest -q` at the end; all tests must pass.

---

### Task 1: Extend `_build_where`, `get_all_videos`, `count_videos`

**Files:**
- Modify: `webapp/db/videos.py`
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: the seeded `videos` table (conftest). The base seed inserts `personal_view_count` (rows 1,4,5 = 0; rows 2,3 > 0) but NO `duration_seconds` (all NULL) and `date_added` in 2024 — duration/date tests insert their own rows.
- Produces:
  - `_build_where(channel, tag, search, favourites_only=False, unwatched_only=False, duration=None, added_within=None) -> (str, list)` — raises `ValueError` for unknown `duration`/`added_within`.
  - `get_all_videos(..., unwatched_only=False, duration=None, added_within=None)` and `count_videos(..., unwatched_only=False, duration=None, added_within=None)` pass the three through.
  - Module constants `_DURATION_BUCKETS: dict[str,str]` and `_ADDED_WITHIN_DAYS: frozenset[int]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py` (extend the `from webapp.db import (...)` block if `get_all_videos`/`count_videos` aren't already imported — they are, per existing tests):

```python
class TestVideoFilterQuickWins:
    def _seed_extra(self, db_conn):
        # Rows with explicit duration + recent/old date_added for bucket/window tests.
        db_conn.executescript(
            """
            INSERT INTO videos (video_id, url, title, channel_name, personal_view_count,
                                duration_seconds, date_added, fetch_status) VALUES
              ('durshort001', 'u', 'Short One', 'C', 0, 120,  date('now','-2 days'),  'ok'),
              ('durmed00001', 'u', 'Med One',   'C', 0, 600,  date('now','-20 days'), 'ok'),
              ('durlong0001', 'u', 'Long One',  'C', 0, 3600, date('now','-200 days'),'ok'),
              ('durnull0001', 'u', 'Null Dur',  'C', 0, NULL, date('now','-1 days'),  'ok');
            """
        )
        db_conn.commit()

    def test_unwatched_only_returns_only_zero_view_count(self, db_conn):
        rows = get_all_videos(db_conn, unwatched_only=True)
        assert rows, "expected some unwatched rows in the base seed"
        assert all(r["personal_view_count"] == 0 for r in rows)

    def test_duration_short_bucket(self, db_conn):
        self._seed_extra(db_conn)
        ids = [r["video_id"] for r in get_all_videos(db_conn, duration="short")]
        assert "durshort001" in ids
        assert "durmed00001" not in ids and "durlong0001" not in ids
        assert "durnull0001" not in ids  # NULL duration excluded from every bucket

    def test_duration_medium_bucket(self, db_conn):
        self._seed_extra(db_conn)
        ids = [r["video_id"] for r in get_all_videos(db_conn, duration="medium")]
        assert ids and "durmed00001" in ids
        assert "durshort001" not in ids and "durlong0001" not in ids

    def test_duration_long_bucket(self, db_conn):
        self._seed_extra(db_conn)
        ids = [r["video_id"] for r in get_all_videos(db_conn, duration="long")]
        assert "durlong0001" in ids
        assert "durshort001" not in ids and "durmed00001" not in ids

    def test_added_within_window(self, db_conn):
        self._seed_extra(db_conn)
        ids = [r["video_id"] for r in get_all_videos(db_conn, added_within=7)]
        assert "durshort001" in ids   # -2 days
        assert "durmed00001" not in ids  # -20 days
        assert "durlong0001" not in ids  # -200 days

    def test_invalid_duration_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_all_videos(db_conn, duration="epic")

    def test_invalid_added_within_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_all_videos(db_conn, added_within=5)

    def test_count_videos_matches_filtered_rows(self, db_conn):
        self._seed_extra(db_conn)
        rows = get_all_videos(db_conn, duration="short")
        assert count_videos(db_conn, duration="short") == len(rows)

    def test_count_videos_invalid_duration_raises(self, db_conn):
        with pytest.raises(ValueError):
            count_videos(db_conn, duration="epic")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py::TestVideoFilterQuickWins -q`
Expected: FAIL — `TypeError: _build_where() got an unexpected keyword argument` (or `get_all_videos` rejecting `unwatched_only`).

- [ ] **Step 3: Implement**

In `webapp/db/videos.py`, add the constants near `ALLOWED_SORT_COLUMNS`:

```python
_DURATION_BUCKETS = {
    "short": "v.duration_seconds < 300",
    "medium": "v.duration_seconds >= 300 AND v.duration_seconds < 1200",
    "long": "v.duration_seconds >= 1200",
}
_ADDED_WITHIN_DAYS = frozenset({7, 30, 90, 365})
```

Replace `_build_where`'s signature and add the three clauses (before the final `where_sql` assembly):

```python
def _build_where(channel, tag, search, favourites_only=False,
                 unwatched_only=False, duration=None, added_within=None):
    params = []
    clauses = ["v.fetch_status = 'ok'", "v.is_hidden = 0"]
    # ... existing channel / tag / search / favourites_only clauses unchanged ...
    if unwatched_only:
        clauses.append("v.personal_view_count = 0")
    if duration is not None:
        if duration not in _DURATION_BUCKETS:
            raise ValueError(f"Invalid duration: {duration!r}")
        clauses.append(f"({_DURATION_BUCKETS[duration]})")
    if added_within is not None:
        if added_within not in _ADDED_WITHIN_DAYS:
            raise ValueError(f"Invalid added_within: {added_within!r}")
        clauses.append("v.date_added >= date('now', ?)")
        params.append(f"-{added_within} days")
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params
```

Note: `duration` fragments come only from the `_DURATION_BUCKETS` constant (never user text); `added_within` is a bound param. Keep the existing clause order; append the three new clauses after `favourites_only` and, for `added_within`, remember its param goes on `params` in the same relative position as its clause (append clause and param together, as shown).

Thread the three params through both callers. `get_all_videos`: add `unwatched_only: bool = False, duration: Optional[str] = None, added_within: Optional[int] = None` to the signature and change the call to `_build_where(channel, tag, search, favourites_only, unwatched_only, duration, added_within)`. `count_videos`: same three params added to its signature and its `_build_where(...)` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py::TestVideoFilterQuickWins -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/db/videos.py tests/webapp/test_db.py
git commit -m "feat(webapp/db): add unwatched/duration/added_within video filters"
```

---

### Task 2: Wire the `index` route + filter form

**Files:**
- Modify: `webapp/routes.py`
- Modify: `webapp/templates/index.html`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `get_all_videos`/`count_videos` with the three new params (Task 1).
- Produces: `GET /` accepting `unwatched=1`, `duration=short|medium|long`, `added_within=7|30|90|365`; template vars `unwatched_only`, `current_duration`, `current_added_within`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`:

```python
class TestIndexFilterQuickWins:
    def _seed(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.executescript(
            """
            INSERT INTO videos (video_id, url, title, channel_name, personal_view_count,
                                duration_seconds, date_added, fetch_status) VALUES
              ('qwshort0001', 'u', 'QW Short Vid', 'C', 0, 120,  date('now','-1 days'),  'ok'),
              ('qwlong00001', 'u', 'QW Long Vid',  'C', 5, 3600, date('now','-300 days'),'ok');
            """
        )
        conn.commit()
        conn.close()

    def test_unwatched_filter(self, client):
        self._seed(client)
        body = client.get("/?unwatched=1", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body      # personal_view_count 0
        assert "QW Long Vid" not in body   # personal_view_count 5

    def test_duration_filter(self, client):
        self._seed(client)
        body = client.get("/?duration=short", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body
        assert "QW Long Vid" not in body

    def test_added_within_filter(self, client):
        self._seed(client)
        body = client.get("/?added_within=7", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "QW Short Vid" in body      # -1 day
        assert "QW Long Vid" not in body   # -300 days

    def test_invalid_duration_returns_400(self, client):
        assert client.get("/?duration=epic").status_code == 400

    def test_invalid_added_within_returns_400(self, client):
        assert client.get("/?added_within=5").status_code == 400

    def test_controls_render_current_state(self, client):
        body = client.get("/?duration=short&unwatched=1").get_data(as_text=True)
        assert 'name="duration"' in body and 'name="unwatched"' in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestIndexFilterQuickWins -q`
Expected: FAIL — unwatched/duration/added_within not filtering (all rows present); invalid values return 200 not 400.

- [ ] **Step 3: Implement the route changes**

In `webapp/routes.py` `index()`, after the `favourites_only` line add:

```python
    unwatched_only = request.args.get("unwatched") == "1"
    duration = request.args.get("duration") or None
    try:
        added_within = int(request.args["added_within"]) if request.args.get("added_within") else None
    except ValueError:
        added_within = None
```

Pass all three to both DB calls inside the existing `try` (which already maps `ValueError` → `abort(400)`):

```python
        total = _db.count_videos(
            g.db, channel=channel, tag=tag, search=search,
            favourites_only=favourites_only, unwatched_only=unwatched_only,
            duration=duration, added_within=added_within,
        )
        videos = _db.get_all_videos(
            g.db, sort_by=sort_by, sort_dir=sort_dir,
            channel=channel, tag=tag, search=search,
            page=page, page_size=PAGE_SIZE, group=group,
            favourites_only=favourites_only, unwatched_only=unwatched_only,
            duration=duration, added_within=added_within,
        )
```

Add to `template_vars`:

```python
        unwatched_only=unwatched_only,
        current_duration=duration,
        current_added_within=added_within,
```

Note: a non-integer `added_within` becomes `None` (treated as "no filter", like the `page` guard); an integer that isn't in the allow-list (e.g. `5`) reaches `_build_where`, raises `ValueError`, and the existing `except ValueError: abort(400)` returns 400 — which `test_invalid_added_within_returns_400` asserts.

- [ ] **Step 4: Add the form controls**

In `webapp/templates/index.html`, extend `active_filter_count` (the `{% set %}` at the top) by adding:

```jinja
    + unwatched_only | int
    + (current_duration is not none and current_duration != '') | int
    + (current_added_within is not none) | int
```

Add these controls inside `#filter-panel`, after the Favourites `<label>`:

```html
      <select name="duration">
        <option value="" {% if not current_duration %}selected{% endif %}>Any duration</option>
        <option value="short"  {% if current_duration == 'short'  %}selected{% endif %}>Short (&lt; 5 min)</option>
        <option value="medium" {% if current_duration == 'medium' %}selected{% endif %}>Medium (5–20 min)</option>
        <option value="long"   {% if current_duration == 'long'   %}selected{% endif %}>Long (&gt; 20 min)</option>
      </select>

      <select name="added_within">
        <option value="" {% if not current_added_within %}selected{% endif %}>Any time</option>
        <option value="7"   {% if current_added_within == 7   %}selected{% endif %}>Last 7 days</option>
        <option value="30"  {% if current_added_within == 30  %}selected{% endif %}>Last 30 days</option>
        <option value="90"  {% if current_added_within == 90  %}selected{% endif %}>Last 90 days</option>
        <option value="365" {% if current_added_within == 365 %}selected{% endif %}>Last year</option>
      </select>

      <label class="filter-toggle">
        <input type="checkbox" name="unwatched" value="1" {% if unwatched_only %}checked{% endif %}>
        Unwatched only
      </label>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestIndexFilterQuickWins -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes.py webapp/templates/index.html tests/webapp/test_routes.py
git commit -m "feat(webapp): wire unwatched/duration/added_within filters into index"
```

---

### Task 3: Docs, verification, and TODO

**Files:**
- Modify: `CHANGELOG.md`, `plan-webapp.md`, `TODO.md`

**Interfaces:**
- Consumes: the delivered filters (Tasks 1–2). No new code interfaces.

- [ ] **Step 1: Manual verification**

Start the server (`python -m webapp.cli --db viewtube.db --port 8080`) and open `http://localhost:8080/`. Confirm:
- The filter panel shows **Duration**, **Added within**, and **Unwatched only** controls.
- Selecting each narrows the list without a full reload; the Filters badge count increases per active filter.
- Combining filters (e.g. Unwatched + Short) composes correctly; **Reset** clears them; pagination/load-more preserves them.
- An invalid manual URL (`/?duration=epic`) returns 400.

- [ ] **Step 2: Update docs**

- `CHANGELOG.md`: append a dated entry — three new index filters (unwatched-only, duration buckets, added-within presets) via `_build_where`; validated allow-lists (invalid → 400). Implication: faster navigation of a large library; note the accepted call that NULL-duration videos match no duration bucket.
- `plan-webapp.md`: document the new `_build_where` params, the `_DURATION_BUCKETS`/`_ADDED_WITHIN_DAYS` allow-lists, and the three form controls.
- `TODO.md`: mark **"Unwatched only" filter**, **Date range filter**, and **Duration filter** delivered (strike through). Leave "sort by unwatched first" and the "Watched" toggle open (the toggle is a separate follow-up).

- [ ] **Step 3: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS (all tests).

```bash
git add CHANGELOG.md plan-webapp.md TODO.md
git commit -m "docs: record video filter quick wins (unwatched/duration/date-range)"
```

---

## Self-Review Notes

- **Spec coverage:** `_build_where`/callers extension (Task 1) ← Section 1; `index` route + form (Task 2) ← Sections 2 & 3; docs/TODO (Task 3) ← File Map. The three decisions from Section 4 (unwatched = `personal_view_count = 0`; NULL-duration excluded from buckets; presets not a picker) are all realized and tested (NULL-duration exclusion has an explicit assertion in Task 1 Step 1).
- **Type consistency:** `_build_where(..., unwatched_only, duration, added_within)`, `get_all_videos(..., unwatched_only, duration, added_within)`, `count_videos(..., unwatched_only, duration, added_within)` used identically across Tasks 1–2; template vars `unwatched_only`/`current_duration`/`current_added_within` match between the route's `template_vars` and `index.html`. `added_within` is an `int` end-to-end (route casts the query string; template compares `== 7`).
- **Verified against codebase:** `_build_where` already takes `favourites_only` as the precedent boolean; `index`'s `try/except ValueError: abort(400)` already exists and wraps both DB calls; `page_url` strips only `page`/`append` so new filters persist across pagination; the conftest seed has `personal_view_count` (0 and >0 rows) but NULL `duration_seconds` and 2024 `date_added`, so duration/date tests insert their own rows (reflected in the test seeds above).
