# "Watched" Toggle — Design

**Date:** 2026-08-07
**Status:** Approved
**Scope:** A per-video "watched" toggle on the video card, backed by a new `is_watched` boolean. "Watched-ness" moves from being inferred from the click-through counter (`personal_view_count`) to an explicit, reversible flag. The "Unwatched only" filter and the rediscover shelf are redefined to key off `is_watched`. Out of scope: a "Watched only" filter, and "sort by unwatched first" (a separate open TODO).

---

## Summary

Today the only signal for "have I seen this?" is `personal_view_count`, which increments when you open a video from ViewTube (`record_visit`). The "Unwatched only" filter and the rediscover shelf both treat `personal_view_count = 0` as "unwatched." That conflates *"opened from ViewTube"* with *"watched,"* offers no way to mark something watched without clicking through, and can't be reversed.

This adds `is_watched` as the single source of truth for watched-ness, and keeps `personal_view_count` as a **permanent historical tally** that the toggle never modifies. The two become independent fields: `is_watched` = the resettable state that drives "unwatched"; `personal_view_count` = "opened N times," shown on the card, never wiped.

**Watched-ness model:**
- `is_watched = 1` ⟺ watched. `is_watched = 0` ⟺ unwatched. Single, clean definition everywhere.
- Opening a video (`record_visit`) also sets `is_watched = 1` — so click-through still marks watched.
- A one-time migration backfill sets `is_watched = 1` for every existing video with `personal_view_count > 0`, so nothing already opened regresses into the unwatched pool.
- The toggle flips `is_watched` only; `personal_view_count` is preserved so its history survives even when a video is marked unwatched.

This mirrors the existing `is_favourite` / `set_favourite` / `video_toggle_favourite` / `.favourite-btn` pattern end to end.

---

## Section 1: Schema & migration

Add `is_watched` to `webapp/db/schema.py`'s `init_webapp_tables`. **It cannot go in the generic `try/except OperationalError` migration loop**, because the one-time backfill must run exactly once — only when the column is first created. Use a dedicated guarded block:

```python
# is_watched: add column + one-time backfill from personal_view_count.
# The backfill runs ONLY when the ALTER succeeds (first migration); on later
# startups the ALTER raises OperationalError and we skip it — so a video the
# user later marks unwatched is never silently re-marked watched on restart.
try:
    conn.execute("ALTER TABLE videos ADD COLUMN is_watched BOOLEAN NOT NULL DEFAULT 0")
    conn.execute("UPDATE videos SET is_watched = 1 WHERE personal_view_count > 0")
    conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists; backfill already ran once
```

**Restart safety is the critical property here:** the backfill is tied to column creation, so it fires once. A test must assert that a second `init_webapp_tables` does NOT re-mark a video that was manually set `is_watched = 0` despite `personal_view_count > 0`.

---

## Section 2: DB layer (`webapp/db/videos.py`)

- **`set_watched(conn, video_id, value)`** — mirrors `set_favourite`; `UPDATE videos SET is_watched = ? WHERE video_id = ?` + commit. Never touches `personal_view_count`.
- **`record_visit`** — extend the existing statement to also set the flag:
  ```sql
  UPDATE videos
  SET personal_view_count = personal_view_count + 1,
      date_last_viewed = ?,
      is_watched = 1
  WHERE video_id = ?
  ```
- **`_build_where` (`unwatched_only`)** — change the clause from `v.personal_view_count = 0` to `v.is_watched = 0`.
- **Rediscover shelf** (`get_current_rediscover_shelf` / pool builder) — change the unwatched pool from `personal_view_count = 0` to `is_watched = 0`, and the viewed pool from `personal_view_count > 0` to `is_watched = 1`. (Behaviour is otherwise unchanged: unwatched first by `date_added`, then viewed by `date_last_viewed`.)

Export `set_watched` from `webapp/db/__init__.py`.

---

## Section 3: Route (`webapp/routes.py`)

Add `video_toggle_watched`, mirroring `video_toggle_favourite`:

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

**The existing `mark-watched` route is unchanged and retained** — it's still called when you favourite a video from the rediscover shelf or watch-later list (implying "watched, drop it from the shelf"). It delegates to `record_visit`, which now also sets `is_watched = 1`, so that flow keeps working and correctly marks the video watched.

---

## Section 4: Frontend

- **`_video_card.html`** — add a watched-toggle button next to the existing `.favourite-btn`, mirroring its markup (a checkmark glyph, `data-video-id`, an `--active` class when `video.is_watched`, and a title that flips between "Mark as watched" / "Mark as unwatched"). Shown in the same contexts as the favourite button (i.e. not on the hidden/archived view unless the favourite button is).
- **`base.html`** — add a click handler mirroring the favourite handler: delegate on `.watched-btn`, `POST /videos/<id>/watched`, and update all buttons with that `data-video-id` (handles carousel clones) from the returned `is_watched`.
- **`style.css`** — add `.watched-btn` / `.watched-btn--active` styles paralleling `.favourite-btn` (distinct color from the favourite gold so the two reads apart).
- **Card view-count display is unchanged** — `personal_view_count` still shows as the "[N] · opened N× from ViewTube" tally, now clearly the historical stat independent of watched state.

---

## Section 5: Decisions, ripples & non-goals

- **Toggle never modifies `personal_view_count`.** Marking unwatched sets `is_watched = 0` only; the open-count (history) is preserved. This is the whole point of splitting the two fields.
- **Backfill is one-time / restart-safe** (Section 1) — the key correctness property.
- **Test/seed ripple (must handle):** redefining "unwatched" from `personal_view_count = 0` to `is_watched = 0` breaks tests that seeded rows with `personal_view_count > 0` and expected them to read as watched, because test seeds insert rows *after* `init_webapp_tables` runs (so the backfill doesn't touch them and `is_watched` defaults to 0). The fix is to make seeded data coherent with the model:
  - Update `tests/webapp/conftest.py` `SEED_SQL` to set `is_watched = 1` on the rows whose `personal_view_count > 0` (currently rows with counts 3 and 1), `0` otherwise.
  - Update `TestIndexFilterQuickWins` in `test_routes.py`: its seeded `personal_view_count = 5` row must set `is_watched = 1` so it still reads as watched under the new definition.
  - Audit rediscover-shelf tests for the same assumption and fix seeds accordingly.
  This ripple is expected and is part of the task, not a regression.
- **No "Watched only" filter** and **no "sort by unwatched first"** in this slice (YAGNI / separate TODO).
- **Mirrors `is_favourite` throughout** — schema migration, DB function, toggle route, card button, JS handler, CSS all follow the favourite pattern for consistency.

---

## File Map

| File | Action |
|---|---|
| `webapp/db/schema.py` | Add `is_watched` column + one-time guarded backfill |
| `webapp/db/videos.py` | Add `set_watched`; `record_visit` sets `is_watched = 1`; `_build_where` unwatched → `is_watched = 0`; rediscover pools → `is_watched` |
| `webapp/db/__init__.py` | Export `set_watched` |
| `webapp/routes.py` | Add `POST /videos/<id>/watched` toggle route |
| `webapp/templates/_video_card.html` | Add the watched-toggle button |
| `webapp/templates/base.html` | Add the `.watched-btn` click handler |
| `webapp/static/style.css` | Add `.watched-btn` / `--active` styles |
| `tests/webapp/conftest.py` | Seed `is_watched` coherently with `personal_view_count` |
| `tests/webapp/test_db.py` | Tests: `set_watched`, `record_visit` sets flag, unwatched via `is_watched`, migration backfill (incl. one-time/restart-safe), rediscover pools |
| `tests/webapp/test_routes.py` | Tests: toggle route (happy/404/CORS-N/A/returns flag); fix `TestIndexFilterQuickWins` seed |
| `CHANGELOG.md` | Append entry |
| `plan-webapp.md` | Document the flag, redefinition, and toggle |
| `TODO.md` | Strike through the "Watched toggle" item |

---

## Testing Strategy

- **DB** (`test_db.py`): `set_watched` sets the flag and leaves `personal_view_count` untouched; `record_visit` sets `is_watched = 1` (and still increments the count); `_build_where(unwatched_only=True)` returns rows with `is_watched = 0`; the migration adds the column and backfills `is_watched = 1` where `personal_view_count > 0`; a **second** `init_webapp_tables` does NOT re-mark a video manually reset to `is_watched = 0` (restart-safety); rediscover pools split on `is_watched`.
- **Routes** (`test_routes.py`): `POST /videos/<id>/watched` toggles and returns `{is_watched}`; unknown id → 404; toggling twice returns to the original state; the "Unwatched only" filter now reflects `is_watched`. Fix the existing `TestIndexFilterQuickWins` seed for the new definition.
- **Manual:** click the watched button on a card — it flips state and, with "Unwatched only" active, the card drops out; marking a previously-opened video unwatched returns it to the unwatched list while the "opened N×" tally remains; `python -m pytest -q` green.
