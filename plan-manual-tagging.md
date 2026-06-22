# Plan: Manual Tag Addition for a Single Video

## Context

Came up while debugging a video that ended up with zero canonical tags. Root cause turned out to be expected behavior (thin source metadata, the one raw tag it had was already marked noise) — but it surfaced that there's no way to manually give a video a tag directly. The only existing tagging mechanisms are automatic alias-matching at ingest time, and the `/tags` admin page's "unclassified tag pool" flow, which only works on raw tags that already exist on 2+ videos. A video with zero or noise-only raw tags has nothing to select there.

Goal: a lightweight, per-video "add a tag" action, available from wherever video cards already render.

## Design Decisions (Locked In)

**Trigger:** right-click context menu (the existing `#video-card-menu`, currently just "Archive video") — not a new visible button on the card. The thumbnail-overlay corner is already crowded (favourite, watch-later, and on the shelf, remove).

**Scope:** available everywhere video cards render, including the Hidden/Archived page. (Archive itself still doesn't show there — see Frontend Implementation for how the two are decoupled.)

**Input flow:** clicking "Add tag…" replaces the context menu with an inline `<input>` — not a modal. Enter submits, Escape or clicking outside cancels, mirroring the existing context-menu dismiss behavior. This matches how this app already handles small inline edits elsewhere (e.g. the `/tags` page's alias-edit flow replaces a pill with an input rather than opening a dialog).

**One tag per action.** No comma-separated multi-tag input. Repeat the action to add a second tag. Keeps the input itself trivial and matches how every other single-purpose card action already works.

**Autocomplete suggestions are canonical tags only**, not all tags. Reasons:
- Mirrors the existing `canonical-datalist` pattern on `/tags`, which is also canonical-only.
- The real database has 26,438 raw (non-canonical) tags vs. a much smaller canonical set — surfacing all of them would be unwieldy and mostly junk.
- Promoting a raw tag to canonical is already a distinct, deliberate workflow on `/tags`'s unclassified pool; this feature shouldn't blur into that.

**Typing a name with no canonical match creates a new canonical tag immediately**, no extra confirmation — matches existing behavior elsewhere in the app (the `/tags` page's "+ New canonical tag" form works the same way).

**Typing a name matching an existing raw (non-canonical) tag promotes it to canonical.** This is pre-existing behavior of `create_canonical_tag` (used today by the `/tags` page), not new risk introduced by this feature. Side effect worth being aware of: every other video that already carries that raw tag will retroactively show it as a canonical pill too, not just the one being tagged. The datalist being canonical-only makes this less likely to happen by accident (you'd have to type a raw tag's exact name by hand), but doesn't prevent it.

**Canonical tag names for the datalist are fetched eagerly**, via the existing global context processor (same pattern as `stats` in `webapp/app.py`), not lazily on first use. The canonical tag set is small, so this is cheap and avoids adding fetch-latency/loading-state handling to the input.

**The server returns rendered HTML (the tag-pills partial), not JSON.** Single source of truth for what a tag pill looks like — the client just swaps in the response, rather than duplicating pill markup in JS.

## Data Model

No schema changes. Uses the existing `tags` and `video_tags` tables.

## Backend Implementation

### New DB function — `webapp/db/tags.py`

```python
def get_canonical_tags_for_video(conn: sqlite3.Connection, video_id: str) -> list[str]:
    """Same as get_tags_for_video, but filtered to canonical tags only —
    matches what _video_card.html actually displays."""
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN video_tags vt ON vt.tag_id_fk = t.id
        JOIN videos v ON v.id = vt.video_id_fk
        WHERE v.video_id = ? AND t.is_canonical = 1
    """, (video_id,)).fetchall()
    return [r[0] for r in rows]
```

`get_tags_for_video` (existing) returns *all* tags including raw/noise ones — wrong shape for re-rendering the card's pill list, hence the new function rather than reusing it.

### Reused existing functions — no changes needed

- `create_canonical_tag(conn, name) -> int` (`webapp/db/tags.py`) — idempotent: creates a new canonical tag, or promotes an existing raw tag to canonical, either way returning its id.
- `add_video_tag(conn, video_id, tag_id) -> None` (`webapp/db/tags.py`) — `INSERT OR IGNORE`, so re-adding a tag the video already has is a harmless no-op.

### New route — `webapp/routes.py`

```python
@bp.route("/videos/<video_id>/tags/add", methods=["POST"])
def video_add_tag(video_id):
    tag_name = request.form.get("tag_name", "").strip()
    if not tag_name:
        abort(400)
    video = _db.get_video_by_id(g.db, video_id)
    if not video:
        abort(404)
    tag_id = _db.create_canonical_tag(g.db, tag_name)
    _db.add_video_tag(g.db, video_id, tag_id)
    tags = _db.get_canonical_tags_for_video(g.db, video_id)
    return render_template("_tag_pills.html", video={"video_id": video_id, "tags": ",".join(tags)})
```

Form-encoded `tag_name`, mirroring the existing `/videos/<id>/tags/remove` exactly (same param name, same encoding). No CORS headers — page-internal route, not extension-facing, consistent with `/tags/remove`.

### New partial — `webapp/templates/_tag_pills.html`

Extracted verbatim from `_video_card.html`'s existing inline tags block — pure refactor, zero behavior change:

```html
{% if video.tags %}
<div class="video-tags" data-video-id="{{ video.video_id }}">
  {% for tag_name in video.tags.split(',') %}
  <a href="{{ url_for('main.index', tag=tag_name) }}" class="tag-pill" data-tag-name="{{ tag_name | e }}">{{ tag_name }}</a>
  {% endfor %}
</div>
{% endif %}
```

`_video_card.html` replaces that inline block with `{% include "_tag_pills.html" %}` — `video` stays in scope via Jinja's default ambient-context include, so this is a no-op change to the existing rendering path. The route above constructs an equivalent `video` dict (`video_id` + comma-joined `tags`) so the same partial renders identically from both call sites.

### Global context processor — `webapp/app.py`

Extend `inject_stats` to also inject canonical tag names (e.g. `canonical_tag_names`), rendered into one global `<datalist id="canonical-tag-datalist">` added once in `base.html` — not duplicated per card.

## Frontend Implementation

### Context menu — `base.html`

Add a new item to the existing `#video-card-menu`:

```html
<button id="video-card-add-tag">Add tag…</button>
```

Change the `contextmenu` handler: remove the `.hidden-videos-grid` early-return exclusion that currently skips showing the menu entirely on the Hidden page. Instead, toggle just the Archive item's visibility right before showing the menu:

```js
document.getElementById('video-card-hide').style.display =
  card.closest('.hidden-videos-grid') ? 'none' : '';
```

`#video-card-add-tag` is unconditional — visible in every context.

### Inline input

Clicking "Add tag…": hide `cardMenu`, create a small `<input list="canonical-tag-datalist">` positioned where the menu was, autofocus it.

- **Enter** → `fetch('/videos/' + videoId + '/tags/add', { method: 'POST', body: new URLSearchParams({ tag_name: input.value }) })`. On success, replace the card's `.video-tags` div with the returned HTML if it exists, or insert it fresh (at the same position `_video_card.html` places it) if this was the video's first tag. Remove the input.
- **Escape / click outside** → remove the input, no request sent.

## Tests

### DB layer — `tests/webapp/test_db.py`

- `get_canonical_tags_for_video` returns only canonical tags, excluding raw and noise tags
- returns `[]` for a video with no canonical tags

### Route layer — `tests/webapp/test_routes.py`

- attaching an existing canonical tag → response includes that pill
- typing a brand-new name → creates it, response includes it
- typing a name matching an existing raw tag → promotes it; verify the cross-video side effect (another video already carrying that raw tag now shows it as canonical too)
- re-adding a tag the video already has → no duplicate, same pills returned
- blank `tag_name` → 400
- unknown `video_id` → 404

### Manual verification

No JS test framework exists in this codebase yet (tracked separately in `TODO.md`'s tech-debt list). The context-menu/inline-input/datalist behavior will be verified structurally via `curl`/`grep` against a copy of real data, consistent with this session's established pattern — actual click-testing in a real browser is left to the user, since no browser automation tooling is available in this environment.

## Edge Cases & Considerations

- Tag name normalization (`.strip().lower()`) is already handled by `create_canonical_tag` — no new validation needed.
- Re-adding an already-attached tag is a harmless no-op.
- Promoting a raw tag to canonical affects every video sharing that raw tag, not just the one being tagged — pre-existing behavior, not a new risk this feature introduces, but worth remembering since it's now reachable from a much more casual, frequent entry point than the `/tags` admin page.

## Out of Scope

- Multi-tag input in one action
- Removing tags via this same UI (already exists via the tag-pill right-click menu)
- Any change to automatic alias-matching / `retroactive_apply` behavior
