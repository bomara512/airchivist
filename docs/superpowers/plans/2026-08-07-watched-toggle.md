# "Watched" Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reversible per-video "watched" toggle backed by a new `is_watched` boolean; redefine "unwatched" (filter + rediscover shelf) to key off `is_watched` while `personal_view_count` becomes a preserved historical tally.

**Architecture:** Four layers, in dependency order: (1) schema — add `is_watched` + a one-time restart-safe backfill; (2) DB — `set_watched`, `record_visit` sets the flag, `_build_where`/rediscover pools switch to `is_watched`, plus the test-seed fixes the redefinition forces; (3) route — a `POST /videos/<id>/watched` toggle; (4) frontend — card button, click handler, CSS, docs. Mirrors the existing `is_favourite` pattern throughout.

**Tech Stack:** Python, Flask, SQLite, Jinja2; pytest.

## Global Constraints

- Mirror the existing `is_favourite` pattern (schema migration, `set_favourite`, `video_toggle_favourite`, `.favourite-btn`, its base.html handler) — same shapes, new names.
- The toggle and `set_watched` MUST NOT modify `personal_view_count` — it is preserved history.
- The migration backfill MUST run exactly once (only when the column is first created), so a manually-unwatched video is never re-marked on restart.
- New/changed public functions in `webapp/db/*.py` and routes in `webapp/routes.py` require tests in the same change.
- Never use `rowid` with `sqlite3.Row`; reference named columns.
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry, update `plan-webapp.md`, and strike the "Watched toggle" item in `TODO.md`.
- Run `python -m pytest -q` at the end of each task; all tests must pass.

---

### Task 1: Schema — `is_watched` column + one-time restart-safe backfill

**Files:**
- Modify: `webapp/db/schema.py`
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: `init_webapp_tables(db_path)` (existing); the `videos` table with `personal_view_count`.
- Produces: after `init_webapp_tables`, `videos.is_watched` exists (BOOLEAN NOT NULL DEFAULT 0), backfilled to 1 where `personal_view_count > 0` — but only on the run that first creates the column.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py` (uses `init_webapp_tables`, already imported; `sqlite3` and `tmp_path` are available):

```python
class TestIsWatchedMigration:
    def _fresh_db(self, tmp_path):
        from crawler.datastore import _SCHEMA as _CRAWLER_SCHEMA
        db_path = str(tmp_path / "mig.db")
        conn = sqlite3.connect(db_path)
        conn.executescript(_CRAWLER_SCHEMA)
        conn.execute(
            "INSERT INTO videos (video_id, url, title, personal_view_count, fetch_status) "
            "VALUES ('vidopened01', 'u', 'Opened', 5, 'ok'), "
            "       ('vidfresh001', 'u', 'Fresh', 0, 'ok')"
        )
        conn.commit()
        conn.close()
        return db_path

    def test_adds_column_and_backfills_opened_videos(self, tmp_path):
        db_path = self._fresh_db(tmp_path)
        init_webapp_tables(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = {r["video_id"]: r["is_watched"]
                for r in conn.execute("SELECT video_id, is_watched FROM videos")}
        conn.close()
        assert rows["vidopened01"] == 1   # personal_view_count > 0 → backfilled watched
        assert rows["vidfresh001"] == 0   # never opened → unwatched

    def test_backfill_is_one_time_and_restart_safe(self, tmp_path):
        db_path = self._fresh_db(tmp_path)
        init_webapp_tables(db_path)            # first run: adds column + backfills
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE videos SET is_watched = 0 WHERE video_id = 'vidopened01'")
        conn.commit()
        conn.close()
        init_webapp_tables(db_path)            # second run must NOT re-mark it
        conn = sqlite3.connect(db_path)
        val = conn.execute(
            "SELECT is_watched FROM videos WHERE video_id = 'vidopened01'"
        ).fetchone()[0]
        conn.close()
        assert val == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py::TestIsWatchedMigration -q`
Expected: FAIL — `sqlite3.OperationalError: no such column: is_watched`.

- [ ] **Step 3: Implement the migration**

In `webapp/db/schema.py`, after the existing `for col, ddl in [...]` migration loop and its trailing `conn.commit()`, add a dedicated guarded block (NOT inside the loop — the backfill must be tied to column creation):

```python
    # is_watched: add column + one-time backfill from personal_view_count.
    # The backfill runs ONLY when the ALTER succeeds (first migration). On later
    # startups the ALTER raises OperationalError and we skip it, so a video the
    # user later marks unwatched is never silently re-marked watched on restart.
    try:
        conn.execute("ALTER TABLE videos ADD COLUMN is_watched BOOLEAN NOT NULL DEFAULT 0")
        conn.execute("UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists; backfill already ran once
```

Confirm `sqlite3` is imported in `schema.py` (it is used by the existing loop's `except sqlite3.OperationalError`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py::TestIsWatchedMigration -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` (adding a defaulted column shouldn't break anything — nothing reads `is_watched` yet).
Expected: PASS.

```bash
git add webapp/db/schema.py tests/webapp/test_db.py
git commit -m "feat(webapp/db): add is_watched column with one-time restart-safe backfill"
```

---

### Task 2: DB layer — `set_watched`, `record_visit`, unwatched/shelf redefinition, seed fixes

**Files:**
- Modify: `webapp/db/videos.py`, `webapp/db/__init__.py`
- Modify: `tests/webapp/conftest.py` (seed coherence), `tests/webapp/test_routes.py` (`TestIndexFilterQuickWins` seed)
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: `is_watched` column (Task 1); existing `set_favourite`, `record_visit`, `_build_where`, `generate_rediscover_shelf`.
- Produces: `set_watched(conn, video_id, value)`; `record_visit` sets `is_watched = 1`; `_build_where(unwatched_only=True)` filters `is_watched = 0`; rediscover pools split on `is_watched`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py` (extend the `from webapp.db import (...)` block with `set_watched`):

```python
class TestSetWatched:
    def test_sets_flag_without_touching_view_count(self, db_conn):
        before = db_conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id = 'aaaaaaaaaa2'"
        ).fetchone()[0]
        set_watched(db_conn, "aaaaaaaaaa2", False)
        row = db_conn.execute(
            "SELECT is_watched, personal_view_count FROM videos WHERE video_id = 'aaaaaaaaaa2'"
        ).fetchone()
        assert row["is_watched"] == 0
        assert row["personal_view_count"] == before   # history preserved

    def test_marks_unwatched_video_watched(self, db_conn):
        set_watched(db_conn, "aaaaaaaaaa1", True)
        assert db_conn.execute(
            "SELECT is_watched FROM videos WHERE video_id = 'aaaaaaaaaa1'"
        ).fetchone()[0] == 1


class TestRecordVisitSetsWatched:
    def test_record_visit_marks_watched(self, db_conn):
        record_visit(db_conn, "aaaaaaaaaa1")   # was unwatched (count 0, is_watched 0)
        row = db_conn.execute(
            "SELECT is_watched, personal_view_count FROM videos WHERE video_id = 'aaaaaaaaaa1'"
        ).fetchone()
        assert row["is_watched"] == 1
        assert row["personal_view_count"] == 1


class TestUnwatchedFilterUsesIsWatched:
    def test_unwatched_only_keys_off_is_watched(self, db_conn):
        # aaaaaaaaaa1 starts unwatched; mark it watched via the flag only.
        set_watched(db_conn, "aaaaaaaaaa1", True)
        ids = [r["video_id"] for r in get_all_videos(db_conn, unwatched_only=True)]
        assert "aaaaaaaaaa1" not in ids
        # A video with count 0 and is_watched 0 stays unwatched:
        assert "aaaaaaaaaa4" in ids
```

Note: `record_visit`, `get_all_videos` are already imported in `test_db.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py::TestSetWatched tests/webapp/test_db.py::TestRecordVisitSetsWatched tests/webapp/test_db.py::TestUnwatchedFilterUsesIsWatched -q`
Expected: FAIL — `ImportError: cannot import name 'set_watched'` (and the record_visit/filter assertions fail once import is stubbed).

- [ ] **Step 3: Implement the DB changes**

In `webapp/db/videos.py`:

Add `set_watched` next to `set_favourite`:

```python
def set_watched(conn: sqlite3.Connection, video_id: str, value: bool) -> None:
    conn.execute(
        "UPDATE videos SET is_watched = ? WHERE video_id = ?",
        (1 if value else 0, video_id),
    )
    conn.commit()
```

Update `record_visit` to also set the flag:

```python
def record_visit(conn: sqlite3.Connection, video_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE videos SET personal_view_count = personal_view_count + 1, "
        "date_last_viewed = ?, is_watched = 1 WHERE video_id = ?",
        (now, video_id),
    )
    _remove_from_rediscover_shelf(conn, video_id)
```

In `_build_where`, change the unwatched clause:

```python
    if unwatched_only:
        clauses.append("v.is_watched = 0")   # was: v.personal_view_count = 0
```

In `generate_rediscover_shelf`, change the two pool queries and the docstring:
- unwatched pool `WHERE personal_view_count = 0 ...` → `WHERE is_watched = 0 ...`
- viewed pool `WHERE personal_view_count > 0 ...` → `WHERE is_watched = 1 ...`
- docstring "Prioritizes unwatched (personal_view_count = 0)..." → "...(is_watched = 0)...".

In `webapp/db/__init__.py`, add `set_watched` to the `from webapp.db.videos import (...)` block and to the `__all__` export line next to `set_favourite`.

- [ ] **Step 4: Fix the test seeds the redefinition forces**

The suite seeds rows *after* `init_webapp_tables`, so the backfill doesn't touch them and `is_watched` defaults to 0. Make seeded data coherent with the new definition:

In `tests/webapp/conftest.py`, append one line to the end of `SEED_SQL`:

```sql
UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0;
```

In `tests/webapp/test_routes.py`, in `TestIndexFilterQuickWins._seed`, append the same statement to its `executescript(...)` block so its `personal_view_count = 5` row (`qwlong00001`) reads as watched:

```sql
UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0;
```

(This keeps `test_unwatched_filter`'s expectation — "QW Long Vid" excluded — valid. The rediscover-shelf tests remain green because the pool composition is unchanged once `is_watched` mirrors `personal_view_count > 0` in the seed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py::TestSetWatched tests/webapp/test_db.py::TestRecordVisitSetsWatched tests/webapp/test_db.py::TestUnwatchedFilterUsesIsWatched -q`
Expected: PASS. Then the full suite:
Run: `python -m pytest -q`
Expected: PASS (seed fixes keep the previously-count-based tests green).

- [ ] **Step 6: Commit**

```bash
git add webapp/db/videos.py webapp/db/__init__.py tests/webapp/conftest.py tests/webapp/test_db.py tests/webapp/test_routes.py
git commit -m "feat(webapp/db): watched state via is_watched; set_watched, record_visit, filter/shelf"
```

---

### Task 3: Route — `POST /videos/<id>/watched` toggle

**Files:**
- Modify: `webapp/routes.py`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `set_watched`, `get_video_by_id` (Task 2 / existing).
- Produces: `POST /videos/<video_id>/watched` → `{"is_watched": bool}`; 404 for unknown id.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`:

```python
class TestToggleWatched:
    def test_toggles_watched_on(self, client):
        # aaaaaaaaaa1 seeds unwatched (count 0 → is_watched 0)
        data = client.post("/videos/aaaaaaaaaa1/watched").get_json()
        assert data["is_watched"] is True

    def test_toggle_twice_returns_to_original(self, client):
        first = client.post("/videos/aaaaaaaaaa1/watched").get_json()["is_watched"]
        second = client.post("/videos/aaaaaaaaaa1/watched").get_json()["is_watched"]
        assert first is True and second is False

    def test_unknown_video_returns_404(self, client):
        assert client.post("/videos/doesnotexist/watched").status_code == 404

    def test_toggle_does_not_change_view_count(self, client):
        client.post("/videos/aaaaaaaaaa2/watched")  # was watched (count 3) → unwatched
        conn = sqlite3.connect(client.application.config["DATABASE"])
        count = conn.execute(
            "SELECT personal_view_count FROM videos WHERE video_id = 'aaaaaaaaaa2'"
        ).fetchone()[0]
        conn.close()
        assert count == 3   # history preserved

    def test_unwatched_filter_reflects_toggle(self, client):
        client.post("/videos/aaaaaaaaaa1/watched")  # mark watched
        body = client.get("/?unwatched=1", headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "Guitar Lesson 1" not in body   # aaaaaaaaaa1's title now excluded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestToggleWatched -q`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement the route**

In `webapp/routes.py`, add next to `video_toggle_favourite`:

```python
@bp.route("/videos/<video_id>/watched", methods=["POST"])
def video_toggle_watched(video_id):
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    new_value = not video.get("is_watched")
    _db.set_watched(g.db, video_id, new_value)
    return jsonify({"is_watched": new_value})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestToggleWatched -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/routes.py tests/webapp/test_routes.py
git commit -m "feat(webapp): add POST /videos/<id>/watched toggle route"
```

---

### Task 4: Frontend — card button, handler, CSS, docs

**Files:**
- Modify: `webapp/templates/_video_card.html`, `webapp/templates/base.html`, `webapp/static/style.css`
- Modify: `CHANGELOG.md`, `plan-webapp.md`, `TODO.md`

**Interfaces:**
- Consumes: `POST /videos/<id>/watched` (Task 3); `video.is_watched` in the card context.
- Produces: user-facing toggle button. No automated tests (server tests already cover the route/DB); manual verification.

- [ ] **Step 1: Add the card button**

In `webapp/templates/_video_card.html`, directly after the existing `.favourite-btn` block (inside the same `{% if ctx != "hidden" %}` region), add:

```html
    <button class="watched-btn {% if video.is_watched %}watched-btn--active{% endif %}"
            data-video-id="{{ video.video_id }}"
            title="{{ 'Mark as unwatched' if video.is_watched else 'Mark as watched' }}">&#10003;</button>
```

- [ ] **Step 2: Add the click handler**

In `webapp/templates/base.html`, after the existing `.favourite-btn` click handler block, add a parallel handler:

```javascript
    // Watched toggle button — update all cards with same video_id (carousel clones)
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.watched-btn');
      if (!btn) return;
      var videoId = btn.dataset.videoId;
      fetch('/videos/' + videoId + '/watched', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          document.querySelectorAll('.watched-btn[data-video-id="' + videoId + '"]').forEach(function (b) {
            if (data.is_watched) {
              b.classList.add('watched-btn--active');
              b.title = 'Mark as unwatched';
            } else {
              b.classList.remove('watched-btn--active');
              b.title = 'Mark as watched';
            }
          });
        });
    });
```

- [ ] **Step 3: Add CSS**

In `webapp/static/style.css`, after the `.favourite-btn` rules, add (positioned next to the favourite button, distinct green so the two read apart):

```css
.watched-btn {
  position: absolute;
  top: 6px;
  left: 2.6rem;
  background: rgba(0, 0, 0, 0.75);
  border: none;
  border-radius: 4px;
  color: #666;
  cursor: pointer;
  font-size: 0.8rem;
  width: 1.6rem;
  height: 1.6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
  z-index: 1;
}
.thumb-wrap:hover .watched-btn { opacity: 1; }
.watched-btn--active { opacity: 1 !important; color: #4caf50; }
.watched-btn:hover { color: #4caf50; }
```

- [ ] **Step 4: Manual verification**

Start the server (`python -m webapp.cli --db viewtube.db --port 8080`) and open `http://localhost:8080/`. Confirm:
- Each card shows a ✓ button next to the ★; clicking it toggles green/active and the title flips between "Mark as watched"/"Mark as unwatched".
- With **Unwatched only** active, marking a card watched drops it from the list; marking a previously-opened video unwatched returns it while the "opened N×" tally on the card is unchanged.
- The favourite button and the shelf/watch-later favourite→mark-watched flow still work.

- [ ] **Step 5: Update docs**

- `CHANGELOG.md`: append a dated (2026-08-07) entry — per-video watched toggle via a new `is_watched` flag; "unwatched" (filter + rediscover shelf) now keys off `is_watched`; opening still marks watched; one-time backfill of already-opened videos; the toggle preserves `personal_view_count` as history. Implication: you can mark things watched/unwatched without clicking through, reversibly; trade-off: a schema migration + a redefinition of "unwatched".
- `plan-webapp.md`: document the `is_watched` flag, `set_watched`, the `record_visit` change, the unwatched/shelf redefinition, and the toggle route + card button.
- `TODO.md`: strike through the `[ ] "Watched" toggle …` item under High priority.

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS.

```bash
git add webapp/templates/_video_card.html webapp/templates/base.html webapp/static/style.css CHANGELOG.md plan-webapp.md TODO.md
git commit -m "feat(webapp): watched toggle button on video cards"
```

---

## Self-Review Notes

- **Spec coverage:** migration + restart-safe backfill (Task 1) ← spec §1; `set_watched`/`record_visit`/`_build_where`/shelf + seed ripple (Task 2) ← §2 & §5; toggle route (Task 3) ← §3; card button/handler/CSS + docs (Task 4) ← §4. Toggle-preserves-`personal_view_count` is asserted in both Task 2 (`test_sets_flag_without_touching_view_count`) and Task 3 (`test_toggle_does_not_change_view_count`). `mark-watched` is intentionally left unchanged (still used by the shelf/watch-later favourite flow; now also sets the flag via the updated `record_visit`).
- **Type/name consistency:** `set_watched(conn, video_id, value)` used by the route; route returns `{"is_watched": bool}` consumed by the base.html handler and reflected by `.watched-btn--active`; `video.is_watched` read in the card. All mirror the `is_favourite` equivalents verbatim in shape.
- **Verified against codebase:** the `is_favourite` migration entry, `set_favourite`, `record_visit`, `_build_where` unwatched clause (`v.personal_view_count = 0`), `generate_rediscover_shelf`'s two pool queries, the `video_toggle_favourite` route, the `.favourite-btn` card block + base.html handler + CSS, and the conftest `SEED_SQL` (rows with `personal_view_count` 3 and 1) all exist as described. The seed fix uses an appended `UPDATE ... WHERE personal_view_count > 0`, which keeps the rediscover-shelf pool composition identical to today's, so existing shelf/quick-wins tests stay green.
