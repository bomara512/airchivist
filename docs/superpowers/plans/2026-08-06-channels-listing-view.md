# Channels Listing View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/channels` page that lists all tracked channels from the `channels` table, with sort, search, a "has saved videos" toggle, and load-more pagination.

**Architecture:** Three layers, in dependency order: (1) two DB functions in `webapp/db/channels.py` (`get_channels_page` with a `video_count` join, `count_channels`); (2) a server-rendered `GET /channels` route in `webapp/routes.py` plus its templates, mirroring the index route's htmx container/load-more pattern; (3) the nav link, CSS, and docs. The route reuses the index's `append=1` fragment mechanism and the module-level `PAGE_SIZE`.

**Tech Stack:** Python, Flask, SQLite, Jinja2, htmx; pytest.

## Global Constraints

- New/changed public functions in `webapp/db/*.py` and routes in `webapp/routes.py` require tests in the same change (happy path + at least one edge case).
- Never use `rowid` with `sqlite3.Row`; reference named columns (`channel_id`).
- `/channels` is a normal server-rendered page, NOT an extension API — do NOT add `_CORS_HEADERS` or an OPTIONS handler.
- Name CSS classes for their shared purpose (`.channel-grid`, `.channel-card`), not by borrowing video-specific names.
- Remove any debug logging before finishing.
- Append a `CHANGELOG.md` entry, update `plan-webapp.md`, and update `TODO.md` for the implementation change.
- Run `python -m pytest -q` at the end; all tests must pass.

---

### Task 1: DB functions — `get_channels_page` and `count_channels`

**Files:**
- Modify: `webapp/db/channels.py`
- Modify: `webapp/db/__init__.py` (export the two new functions)
- Test: `tests/webapp/test_db.py`

**Interfaces:**
- Consumes: the `channels` and `videos` tables (conftest's `_setup_db` creates both).
- Produces:
  - `get_channels_page(conn, *, sort_by="video_count", sort_dir="desc", search=None, has_videos=False, page=1, page_size=100) -> list[dict]` — each dict has the channel columns plus a computed `video_count`.
  - `count_channels(conn, *, search=None, has_videos=False) -> int`.
  - `_CHANNEL_SORT_COLUMNS` (module constant) mapping allowed `sort_by` → SQL column/alias.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_db.py` (extend the `from webapp.db import (...)` block with `get_channels_page, count_channels`):

```python
class TestGetChannelsPage:
    def _seed(self, conn):
        conn.executescript(
            """
            INSERT INTO channels (channel_id, channel_name, channel_url, subscriber_count, fetch_status) VALUES
              ('UCaaa', 'Alpha',   'https://youtube.com/channel/UCaaa', 1000, 'ok'),
              ('UCbbb', 'Bravo',   'https://youtube.com/channel/UCbbb', 5000, 'ok'),
              ('UCccc', 'Charlie', 'https://youtube.com/channel/UCccc', NULL, 'ok');
            INSERT INTO videos (video_id, url, title, channel_name, channel_id, date_added, fetch_status) VALUES
              ('chvid00001', 'u', 'V1', 'Alpha', 'UCaaa', '2024-01-01', 'ok'),
              ('chvid00002', 'u', 'V2', 'Alpha', 'UCaaa', '2024-01-02', 'ok'),
              ('chvid00003', 'u', 'V3', 'Bravo', 'UCbbb', '2024-01-03', 'ok');
            """
        )
        conn.commit()

    def test_computes_video_count(self, db_conn):
        self._seed(db_conn)
        rows = {r["channel_id"]: r["video_count"]
                for r in get_channels_page(db_conn, page_size=10)}
        assert rows == {"UCaaa": 2, "UCbbb": 1, "UCccc": 0}

    def test_has_videos_excludes_zero(self, db_conn):
        self._seed(db_conn)
        ids = [r["channel_id"] for r in get_channels_page(db_conn, has_videos=True, page_size=10)]
        assert "UCccc" not in ids
        assert set(ids) == {"UCaaa", "UCbbb"}

    def test_search_matches_name_substring(self, db_conn):
        self._seed(db_conn)
        ids = [r["channel_id"] for r in get_channels_page(db_conn, search="alp", page_size=10)]
        assert ids == ["UCaaa"]

    def test_sort_by_video_count_desc(self, db_conn):
        self._seed(db_conn)
        ids = [r["channel_id"] for r in get_channels_page(db_conn, sort_by="video_count", sort_dir="desc", page_size=10)]
        assert ids == ["UCaaa", "UCbbb", "UCccc"]

    def test_sort_by_subscriber_count_desc_nulls_last(self, db_conn):
        self._seed(db_conn)
        ids = [r["channel_id"] for r in get_channels_page(db_conn, sort_by="subscriber_count", sort_dir="desc", page_size=10)]
        assert ids == ["UCbbb", "UCaaa", "UCccc"]

    def test_sort_by_channel_name_asc(self, db_conn):
        self._seed(db_conn)
        ids = [r["channel_id"] for r in get_channels_page(db_conn, sort_by="channel_name", sort_dir="asc", page_size=10)]
        assert ids == ["UCaaa", "UCbbb", "UCccc"]

    def test_invalid_sort_by_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_channels_page(db_conn, sort_by="DROP TABLE", page_size=10)

    def test_invalid_sort_dir_raises(self, db_conn):
        with pytest.raises(ValueError):
            get_channels_page(db_conn, sort_dir="sideways", page_size=10)

    def test_pagination(self, db_conn):
        self._seed(db_conn)
        page1 = get_channels_page(db_conn, sort_by="channel_name", sort_dir="asc", page=1, page_size=2)
        page2 = get_channels_page(db_conn, sort_by="channel_name", sort_dir="asc", page=2, page_size=2)
        assert [r["channel_id"] for r in page1] == ["UCaaa", "UCbbb"]
        assert [r["channel_id"] for r in page2] == ["UCccc"]


class TestCountChannels:
    def _seed(self, conn):
        TestGetChannelsPage._seed(self, conn)

    def test_counts_all(self, db_conn):
        self._seed(db_conn)
        assert count_channels(db_conn) == 3

    def test_counts_has_videos(self, db_conn):
        self._seed(db_conn)
        assert count_channels(db_conn, has_videos=True) == 2

    def test_counts_search(self, db_conn):
        self._seed(db_conn)
        assert count_channels(db_conn, search="alp") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_db.py::TestGetChannelsPage tests/webapp/test_db.py::TestCountChannels -q`
Expected: FAIL — `ImportError: cannot import name 'get_channels_page'`.

- [ ] **Step 3: Implement the functions**

Append to `webapp/db/channels.py`:

```python
_CHANNEL_SORT_COLUMNS = {
    "video_count": "video_count",
    "subscriber_count": "c.subscriber_count",
    "channel_name": "c.channel_name",
    "date_added": "c.date_added",
}


def _channel_where(search):
    if search:
        return " WHERE c.channel_name LIKE '%' || ? || '%'", [search]
    return "", []


def get_channels_page(conn, *, sort_by="video_count", sort_dir="desc",
                      search=None, has_videos=False, page=1, page_size=100):
    if sort_by not in _CHANNEL_SORT_COLUMNS:
        raise ValueError(f"invalid sort_by: {sort_by}")
    if sort_dir not in ("asc", "desc"):
        raise ValueError(f"invalid sort_dir: {sort_dir}")

    where_sql, params = _channel_where(search)
    having_sql = " HAVING video_count > 0" if has_videos else ""
    col = _CHANNEL_SORT_COLUMNS[sort_by]
    # NULLs (e.g. subscriber_count) sort last regardless of direction; stable tiebreak on name.
    order_sql = f" ORDER BY {col} IS NULL, {col} {sort_dir.upper()}, c.channel_name ASC"

    sql = (
        "SELECT c.channel_id, c.channel_name, c.channel_url, c.description, "
        "c.subscriber_count, c.thumbnail_url, c.date_added, "
        "COUNT(v.video_id) AS video_count "
        "FROM channels c LEFT JOIN videos v ON v.channel_id = c.channel_id"
        + where_sql
        + " GROUP BY c.channel_id"
        + having_sql
        + order_sql
        + " LIMIT ? OFFSET ?"
    )
    params = [*params, page_size, (page - 1) * page_size]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def count_channels(conn, *, search=None, has_videos=False):
    where_sql, params = _channel_where(search)
    having_sql = " HAVING COUNT(v.video_id) > 0" if has_videos else ""
    sql = (
        "SELECT COUNT(*) FROM ("
        "SELECT c.channel_id FROM channels c "
        "LEFT JOIN videos v ON v.channel_id = c.channel_id"
        + where_sql
        + " GROUP BY c.channel_id"
        + having_sql
        + ")"
    )
    return conn.execute(sql, params).fetchone()[0]
```

In `webapp/db/__init__.py`, add `get_channels_page, count_channels` to the `from webapp.db.channels import (...)` block and to the `# channels` export line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_db.py::TestGetChannelsPage tests/webapp/test_db.py::TestCountChannels -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add webapp/db/channels.py webapp/db/__init__.py tests/webapp/test_db.py
git commit -m "feat(webapp/db): add get_channels_page and count_channels"
```

---

### Task 2: Route `GET /channels` + templates

**Files:**
- Modify: `webapp/routes.py`
- Create: `webapp/templates/channels.html`, `webapp/templates/_channels_container.html`, `webapp/templates/_channels_load_more.html`, `webapp/templates/_channel_card.html`
- Test: `tests/webapp/test_routes.py`

**Interfaces:**
- Consumes: `get_channels_page`, `count_channels` (Task 1); `PAGE_SIZE`, `math`, `url_for`, `render_template`, `g`, `request`, `abort` (all already imported in `routes.py`); the `view_count` Jinja filter (registered in `webapp/app.py`).
- Produces: endpoint `main.channels` at `GET /channels`. A single `sort` query param selects a preset; `search`, `has_videos=1`, `page`, `append=1` behave like the index route.

- [ ] **Step 1: Write the failing tests**

Add to `tests/webapp/test_routes.py`:

```python
class TestChannelsPage:
    def _seed(self, client):
        conn = sqlite3.connect(client.application.config["DATABASE"])
        conn.executescript(
            """
            INSERT INTO channels (channel_id, channel_name, channel_url, subscriber_count, fetch_status) VALUES
              ('UCaaa', 'AlphaChan',   'https://youtube.com/channel/UCaaa', 1000, 'ok'),
              ('UCbbb', 'BravoChan',   'https://youtube.com/channel/UCbbb', 5000, 'ok'),
              ('UCccc', 'CharlieChan', 'https://youtube.com/channel/UCccc', NULL, 'ok');
            INSERT INTO videos (video_id, url, title, channel_name, channel_id, date_added, fetch_status) VALUES
              ('chrt000001', 'u', 'V1', 'AlphaChan', 'UCaaa', '2024-01-01', 'ok');
            """
        )
        conn.commit()
        conn.close()

    def test_returns_200_and_lists_channels(self, client):
        self._seed(client)
        resp = client.get("/channels")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "AlphaChan" in body and "CharlieChan" in body

    def test_has_videos_filter_hides_zero(self, client):
        self._seed(client)
        body = client.get("/channels?has_videos=1").get_data(as_text=True)
        assert "AlphaChan" in body
        assert "CharlieChan" not in body

    def test_search_filters_by_name(self, client):
        self._seed(client)
        body = client.get("/channels?search=alpha").get_data(as_text=True)
        assert "AlphaChan" in body
        assert "BravoChan" not in body

    def test_invalid_sort_returns_400(self, client):
        self._seed(client)
        assert client.get("/channels?sort=bogus").status_code == 400

    def test_append_fragment_omits_page_chrome(self, client):
        self._seed(client)
        resp = client.get("/channels?append=1", headers={"HX-Request": "true"})
        body = resp.get_data(as_text=True)
        assert "AlphaChan" in body
        assert "<!doctype html>" not in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/webapp/test_routes.py::TestChannelsPage -q`
Expected: FAIL — 404 (route not registered) / TemplateNotFound.

- [ ] **Step 3: Add the route**

In `webapp/routes.py`, add (place it after the `index` route). The `sort` preset maps to a `(sort_by, sort_dir)` pair so the UI needs one select, not two:

```python
_CHANNEL_SORT_PRESETS = {
    "video_count": ("video_count", "desc"),
    "subscriber_count": ("subscriber_count", "desc"),
    "channel_name": ("channel_name", "asc"),
    "date_added": ("date_added", "desc"),
}


@bp.route("/channels")
def channels():
    sort = request.args.get("sort", "video_count")
    if sort not in _CHANNEL_SORT_PRESETS:
        abort(400)
    sort_by, sort_dir = _CHANNEL_SORT_PRESETS[sort]
    search = request.args.get("search") or None
    has_videos = request.args.get("has_videos") == "1"
    append = request.args.get("append") == "1"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total = _db.count_channels(g.db, search=search, has_videos=has_videos)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    channel_rows = _db.get_channels_page(
        g.db, sort_by=sort_by, sort_dir=sort_dir,
        search=search, has_videos=has_videos, page=page, page_size=PAGE_SIZE,
    )

    def page_url(p):
        args = {k: v for k, v in request.args.to_dict().items() if k not in ("page", "append")}
        args["page"] = p
        return url_for("main.channels", **args)

    template_vars = dict(
        channels=channel_rows,
        current_sort=sort,
        current_search=search,
        has_videos=has_videos,
        page=page,
        total_pages=total_pages,
        total=total,
        next_url=page_url(page + 1) if page < total_pages else None,
    )

    if request.headers.get("HX-Request"):
        if append:
            return render_template("_channels_load_more.html", **template_vars)
        return render_template("_channels_container.html", **template_vars)
    return render_template("channels.html", **template_vars)
```

- [ ] **Step 4: Create the templates**

`webapp/templates/_channel_card.html` (expects loop var `ch`):

```html
<div class="channel-card">
  <a href="{{ url_for('main.index', channel=ch.channel_name) }}" class="channel-avatar">
    {% if ch.thumbnail_url %}
    <img src="{{ ch.thumbnail_url }}" alt="{{ ch.channel_name }}" loading="lazy">
    {% else %}
    <div class="no-thumb"></div>
    {% endif %}
  </a>
  <div class="channel-info">
    <a href="{{ url_for('main.index', channel=ch.channel_name) }}" class="channel-name">{{ ch.channel_name }}</a>
    <div class="channel-meta">
      {% if ch.subscriber_count %}<span>{{ ch.subscriber_count | view_count }} subscribers</span>{% endif %}
      <span>{{ ch.video_count }} video{{ '' if ch.video_count == 1 else 's' }}</span>
    </div>
    {% if ch.description %}<p class="channel-desc">{{ ch.description | truncate(140) }}</p>{% endif %}
    <a href="{{ ch.channel_url }}" target="_blank" rel="noopener" class="channel-external">View on YouTube &#8599;</a>
  </div>
</div>
```

`webapp/templates/_channels_container.html`:

```html
<div id="channel-grid" class="channel-grid">
  {% for ch in channels %}
  {% include "_channel_card.html" %}
  {% else %}
  <p class="empty">No channels found.</p>
  {% endfor %}
</div>
<div id="load-more">
  {% if next_url %}
  <button class="load-more-btn"
          hx-get="{{ next_url }}&append=1"
          hx-target="#channel-grid"
          hx-swap="beforeend">
    Load more
  </button>
  {% endif %}
</div>
```

`webapp/templates/_channels_load_more.html`:

```html
{% for ch in channels %}
{% include "_channel_card.html" %}
{% endfor %}
<div id="load-more" hx-swap-oob="true">
  {% if next_url %}
  <button class="load-more-btn"
          hx-get="{{ next_url }}&append=1"
          hx-target="#channel-grid"
          hx-swap="beforeend">
    Load more
  </button>
  {% endif %}
</div>
```

`webapp/templates/channels.html`:

```html
{% extends "base.html" %}
{% block title %}ViewTube — Channels{% endblock %}
{% block content %}
<form id="channel-filter-form"
      hx-get="{{ url_for('main.channels') }}"
      hx-target="#channel-container"
      hx-push-url="true"
      hx-trigger="change from:select, change from:input[type=checkbox], keyup changed delay:300ms from:input[name=search]">
  <div class="filter-row">
    <input name="search" value="{{ current_search or '' }}" placeholder="Search channels…" autocomplete="off">
    <select name="sort">
      <option value="video_count"      {% if current_sort == 'video_count'      %}selected{% endif %}>Most saved videos</option>
      <option value="subscriber_count" {% if current_sort == 'subscriber_count' %}selected{% endif %}>Most subscribers</option>
      <option value="channel_name"     {% if current_sort == 'channel_name'     %}selected{% endif %}>Name A–Z</option>
      <option value="date_added"       {% if current_sort == 'date_added'       %}selected{% endif %}>Recently added</option>
    </select>
    <label class="filter-check">
      <input type="checkbox" name="has_videos" value="1" {% if has_videos %}checked{% endif %}>
      Has saved videos
    </label>
  </div>
</form>

<h2 class="section-label">Channels ({{ total }})</h2>
<div id="channel-container">
  {% include "_channels_container.html" %}
</div>
{% endblock %}
```

Note: `base.html` declares `{% block title %}` and `{% block content %}` (verified) — `index.html` and `watch-later.html` both use `content`. Use `content` as written above.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/webapp/test_routes.py::TestChannelsPage -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/routes.py webapp/templates/channels.html webapp/templates/_channels_container.html webapp/templates/_channels_load_more.html webapp/templates/_channel_card.html tests/webapp/test_routes.py
git commit -m "feat(webapp): add GET /channels listing route and templates"
```

---

### Task 3: Nav link, styling, docs, and manual verification

**Files:**
- Modify: `webapp/templates/base.html` (nav link)
- Modify: `webapp/static/style.css` (channel card/grid styles)
- Modify: `CHANGELOG.md`, `plan-webapp.md`, `TODO.md`

**Interfaces:**
- Consumes: the `main.channels` endpoint (Task 2). No new code interfaces produced.

- [ ] **Step 1: Add the nav link**

In `webapp/templates/base.html`, inside the `<nav>`, add a Channels link next to the Tags link (match the existing inline style of the sibling links):

```html
<a href="{{ url_for('main.channels') }}" style="font-size:0.9rem;font-weight:400;">Channels</a>
```

- [ ] **Step 2: Add channel styles**

Append to `webapp/static/style.css` (horizontal card: round avatar left, info right; grid mirrors `.video-grid`):

```css
/* Channels */
.channel-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
.channel-card { background: #1a1a1a; border-radius: 8px; padding: 0.85rem; display: flex; gap: 0.85rem; }
.channel-avatar { flex: 0 0 auto; width: 64px; height: 64px; border-radius: 50%; overflow: hidden; background: #222; display: block; }
.channel-avatar img { width: 100%; height: 100%; object-fit: cover; }
.channel-avatar .no-thumb { width: 100%; height: 100%; background: #2a2a2a; }
.channel-info { min-width: 0; display: flex; flex-direction: column; gap: 0.25rem; }
.channel-name { color: #e8e8e8; text-decoration: none; font-weight: 600; line-height: 1.3; }
.channel-name:hover { color: #ff4444; }
.channel-meta { font-size: 0.8rem; color: #888; display: flex; flex-wrap: wrap; gap: 0.4rem; }
.channel-meta span::after { content: "·"; margin-left: 0.4rem; }
.channel-meta span:last-of-type::after { content: ""; }
.channel-desc { font-size: 0.8rem; color: #999; line-height: 1.4; margin: 0.15rem 0 0; }
.channel-external { font-size: 0.78rem; color: #888; text-decoration: none; margin-top: 0.15rem; }
.channel-external:hover { color: #cc0000; }
```

- [ ] **Step 3: Manual verification**

Start the server (`python -m webapp.cli --db viewtube.db --port 8080`) and open `http://localhost:8080/channels`. Confirm:
- The Channels nav link appears and loads the page; cards show avatar, name, subscriber count, saved-video badge, and description.
- The sort select reorders (Most saved videos / Most subscribers / Name A–Z / Recently added); the search box filters as you type; the "Has saved videos" toggle hides 0-video channels.
- "Load more" appends the next page without reloading; a channel card's name/avatar links to that channel's filtered video list on `/`, and "View on YouTube" opens the channel in a new tab.

- [ ] **Step 4: Update docs**

- `CHANGELOG.md`: append a dated entry — new `/channels` listing page (grid of channel cards; sort/search/has-videos toggle; load-more), backed by `get_channels_page`/`count_channels` and a `GET /channels` route. Implication: channels are now browsable as entities; note the accepted limitation that card→videos links are by channel name (two channels sharing an exact name would collapse into one filtered list).
- `plan-webapp.md`: document the `/channels` route, the two DB functions, the `sort` preset mapping, and the templates.
- `TODO.md`: update the Creator pages item — mark the **UI: channels view** portion as delivered for the listing (tagging channels and channel-specific stats remain open).

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS (all tests).

```bash
git add webapp/templates/base.html webapp/static/style.css CHANGELOG.md plan-webapp.md TODO.md
git commit -m "feat(webapp): channels nav link, card styling, and docs"
```

---

## Self-Review Notes

- **Spec coverage:** `get_channels_page`/`count_channels` (Task 1) ← Section 1; `GET /channels` route + templates (Task 2) ← Section 2 & 3; nav link, styling, docs (Task 3) ← Section 3 & File Map. The single-`sort`-preset UI (Task 2) realizes Section 3's "sort select with 4 options" while keeping the DB function's general `sort_by`/`sort_dir` signature from Section 1. Name-based card→videos link and the has-videos toggle default (Section 4) are honored.
- **Type consistency:** `get_channels_page(conn, *, sort_by, sort_dir, search, has_videos, page, page_size)` and `count_channels(conn, *, search, has_videos)` are called identically in Task 2's route; the template loop var is `ch` in both `_channels_container.html`/`_channels_load_more.html` and `_channel_card.html`; `current_sort`/`has_videos`/`next_url`/`channels` template vars match between the route and templates.
- **Verified against codebase:** `PAGE_SIZE = 100`, `view_count` filter registered in `app.py`, `#load-more`/`.load-more-btn` CSS already exist and are reused, `.no-thumb` class already exists, the index route's `HX-Request`/`append` render split is mirrored. `base.html` declares `{% block content %}` (verified; used by `index.html` and `watch-later.html`), so `channels.html` matches.
