# ViewTube — Tag Distillation Plan

## Problem

The crawler ingests raw YouTube tags from video metadata. These are creator-supplied and highly inconsistent:

- Spelling variants: `meal prep`, `meal-prep`, `mealprep`
- Specificity variants: `meal prep`, `meal prep recipes`, `meal prep for the week`, `bulk meal prep`
- Synonyms: `guitar lesson`, `learn guitar`, `guitar tutorial`, `beginner guitar`
- Noise: `#shorts`, `2024`, `HD`, creator names

A library of 500 videos might accumulate thousands of raw tags, most of which are useless for browsing or discovery. Distillation maps this noise to a small set of canonical concepts that the user actually cares about.

---

## What Distillation Is (and Isn't)

Distillation is **not** automatic deduplication of tags. It is **user-curated mapping**: the user defines that "meal prep recipes", "how to meal prep", and "weekly meal prep" should all resolve to the canonical tag `meal-prep`. The system enforces those mappings as new videos arrive.

This is distinct from:
- **Tag keywords** (already implemented): keywords that make a tag *searchable* by extra terms
- **Tag merging**: collapsing two tags into one in the DB (destructive, loses history)

Distillation is additive and non-destructive — raw tags are preserved; canonical tags are layered on top.

---

## Data Model

### Current state
```
tags (id, name)
tag_keywords (id, tag_id, keyword)
video_tags (video_id_fk, tag_id_fk)
```

Tags are created by the crawler from raw YouTube tags and by the user manually. `tag_keywords` enables search by extra terms.

### Proposed addition: canonical tags and alias rules

```sql
-- A canonical tag is just a regular tag marked as canonical
ALTER TABLE tags ADD COLUMN is_canonical BOOLEAN NOT NULL DEFAULT 0;

-- Alias rules: raw string patterns that map to a canonical tag
CREATE TABLE tag_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT NOT NULL,          -- raw tag name or substring/prefix
    match_type  TEXT NOT NULL DEFAULT 'exact',  -- 'exact' | 'prefix' | 'contains'
    canonical_tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(pattern, match_type)
);
```

When a video is ingested, each of its raw YouTube tags is checked against `tag_aliases`. Matching aliases cause the video to be associated with the corresponding canonical tag (in addition to or instead of the raw tag — see "Association strategy" below).

### Association strategy options

**Option A — Additive**: raw tags and canonical tags both appear in `video_tags`. Video is findable by either. Raw tags accumulate but canonical tags become the primary browsing surface.
- Pro: no information lost; reversible
- Con: tag list grows; raw tags still pollute the tag cloud

**Option B — Replace on ingest**: when a raw tag matches an alias, only the canonical tag is stored (raw tag dropped).
- Pro: clean tag cloud from day one
- Con: destructive; re-running distillation on existing data is complex

**Option C — Virtual layer**: raw tags stored as-is; canonical associations are computed on the fly from alias rules (no write to `video_tags`).
- Pro: no schema migration; aliases can be changed and results update immediately
- Con: query complexity; slower search

**Recommendation: Option A.** Store both. Filter the tag cloud to show only canonical tags by default (`WHERE is_canonical = 1 OR id NOT IN (SELECT canonical_tag_id FROM tag_aliases)`), but keep raw tags for data completeness. Reversible at any point.

---

## When Distillation Runs

### 1. On crawler ingest (batch)
After `upsert_video`, run alias matching against the video's raw `yt_tags`. This is the primary path — the crawler already has the raw tags in memory.

### 2. On bookmarklet add
Same alias matching after `fetch_metadata` returns, before inserting into `video_tags`. Single-video version of the same logic.

### 3. On alias rule change (retroactive)
When the user creates or modifies an alias rule, a retroactive pass should run: find all videos whose raw tags match the new rule and associate them with the canonical tag. This is the "ongoing maintenance" trigger — new rules propagate backwards automatically.

### 4. Manual trigger (optional)
A "Re-apply all rules" button in the UI for cases where the user wants to force a full rescan (e.g. after a bulk import).

### Is it ongoing maintenance?
Yes, in a lightweight sense. The alias rules themselves are stable once defined, but:
- New videos bring new raw tags that may need new rules
- A periodic review ("you have 47 unaliased tags used on 3+ videos") would surface when new rules are worth adding

The maintenance burden is low if rules are added incrementally as the library grows, rather than trying to define them all upfront.

---

## Distillation Workflow (User-Facing)

### Step 1: Suggestion surface
The app identifies candidate clusters — groups of tags that look similar — and surfaces them to the user as suggestions. Clustering can be done by:
- **Edit distance** (Levenshtein): `meal prep` and `meal-prep` are distance 1
- **Token overlap**: `meal prep recipes` shares 2/3 tokens with `meal prep`
- **Prefix matching**: `guitar lesson` and `guitar lessons` share a prefix

This does not require an LLM. A simple Python pass with `difflib.SequenceMatcher` or token overlap scoring is sufficient for a personal library.

### Step 2: User reviews and confirms
The UI presents candidate groups: "These tags look similar — create a canonical tag?" The user names the canonical tag and confirms which raw tags become aliases.

### Step 3: Rules stored, retroactive pass runs
Alias rules written to `tag_aliases`. Canonical tag created in `tags` with `is_canonical = 1`. Retroactive pass associates all matching existing videos.

---

## Features Enabled by Distillation

| Feature | How distillation helps |
|---|---|
| **Cleaner tag cloud** | Tag browser shows 20 canonical concepts instead of 400 raw tags |
| **Better search** | Searching "guitar" finds videos tagged with any guitar-related alias |
| **Group by tag** | Grouping by canonical tags produces meaningful, non-redundant sections |
| **"More like this"** | Canonical tags are a stable signal for similarity — two videos sharing a canonical tag are genuinely related, not just coincidentally tagged |
| **Recommendations / discovery** | "You haven't watched anything tagged `meal-prep` in 3 months" is a useful prompt; raw tags can't support this |
| **Tag-based stats** | "You have 47 guitar videos" is only meaningful with canonical tags |
| **Bulk operations** | "Archive all videos tagged `#shorts`" — only practical once noise tags are identified as a group |

---

## UI Surface Points

### Tag distillation page (new admin section)
- List of all tags, with a count of videos and a flag for whether each is canonical
- "Cluster suggestions" section: groups of similar-looking tags with a one-click "Create canonical tag from this cluster" action
- Alias rule editor: for each canonical tag, show and edit its alias patterns

### Inline suggestion on filter bar
When the user types a search term, if that term matches several similar tags, a subtle hint: "Did you mean the canonical tag `meal-prep`? (covers 6 related tags)"

### Tag cloud / Tags page
Show only canonical tags by default. Toggle to show raw tags. Clicking a canonical tag filters by it (matching all its aliases).

### Video card
Show canonical tags instead of (or in addition to) raw tags on the card. Raw tags accessible via an expand or detail view.

---

## Implementation Phases

### Phase 1 — Schema and rules (no UI) ✅ IMPLEMENTED (2026-05-29)
- `is_canonical BOOLEAN NOT NULL DEFAULT 0` added to `tags` in crawler `_SCHEMA`; migration via `ALTER TABLE` in `init_webapp_tables` for existing DBs
- `tag_aliases (id, pattern, match_type, canonical_tag_id)` table created in `init_webapp_tables`; `match_type` supports `'exact'`, `'prefix'`, `'contains'`; matching is case-insensitive
- `apply_aliases(conn, video_id)` in `webapp/db.py`: reads all alias rules, tests each against the video's current tags, inserts matching canonical tag associations into `video_tags` (idempotent via `INSERT OR IGNORE`); gracefully handles missing `tag_aliases` table
- Hooked into crawler `Datastore.upsert_video` (after `_apply_yt_tags`) and webapp `api_add` (via `add_video`)
- `add_video` now accepts `yt_tags: list[str]` and stores them as regular tags before calling `apply_aliases`
- Manual rule entry via direct DB (`INSERT INTO tag_aliases ...`)
- **Note**: crawler imports `apply_aliases` from `webapp.db` — deliberate cross-package dependency within the same project; routes.py already imports from crawler, establishing the precedent

### Phase 2 — Retroactive pass and rule management UI ✅ IMPLEMENTED (2026-05-29)
- `retroactive_apply(conn, alias_rule_id=None)` — single-pass SQL: for each rule, INSERTs matching video-canonical associations in bulk; returns count of new rows created; idempotent via `INSERT OR IGNORE`
- `get_canonical_tags(conn)` — returns canonical tags with video count and their alias rules
- `create_canonical_tag(conn, name)` — creates new tag with `is_canonical=1`, or promotes existing tag
- `add_alias(conn, tag_id, pattern, match_type)` — adds alias rule; returns its id
- `delete_alias(conn, alias_id)` — removes alias rule
- `GET/POST /tags` — tag admin page; POST creates a canonical tag
- `POST /tags/<id>/alias` — adds alias and auto-applies it retroactively
- `POST /tags/<id>/alias/<aid>/delete` — deletes alias
- `POST /tags/retroactive` — re-applies all rules; redirects with `?applied=N` count
- Tags link added to nav in `base.html`
- Adding an alias auto-applies it retroactively (one step instead of two)

### Phase 3 — Manual tag pool UX ✅ IMPLEMENTED (2026-05-29)
- Replaced automated cluster suggestion engine with a user-driven tag pool.
- `get_unclassified_tags(conn, max_tags=500) -> tuple[list, int]` in `webapp/db.py`: queries tags that are not canonical and not yet used as an alias pattern, ordered by video count desc; returns `(rows, total_count)` where total_count can exceed max_tags
- `confirm_suggestion(conn, canonical_name, member_names)`: creates canonical tag if it doesn't exist (or promotes existing), adds exact aliases for all selected members, runs `retroactive_apply`; reused from prior Phase 3 implementation
- `POST /tags/suggest/confirm` route: reads `canonical_name` and list of `member` form fields
- Tags page shows an "Unclassified Tags" section at the top when unclassified tags exist: a scrollable pool of checkbox pill buttons (`:has(input:checked)` CSS for selection state), a sticky assign bar with a datalist-backed canonical name input and "Assign selected" button
- Selected tags are submitted together as a batch; on confirm they become exact aliases of the named canonical tag and disappear from the pool
- **Decision**: automated clustering (tag_suggester.py) was built but rejected by the user as unintuitive — the manual pool was preferred because the user can see all unclassified tags at once, select any subset they consider related, and name the canonical grouping themselves without relying on algorithmic similarity judgments
- `tag_suggester.py` retained but not used in the main UI flow

---

## What This Does Not Solve

- **Noise tags with no natural canonical form** (e.g. `#ad`, `2024`, `HD`) — these are best handled by a blocklist rather than distillation
- **Cross-language tags** — tags in other languages won't cluster with English equivalents without a translation step
- **Semantic similarity beyond surface form** — `cooking` and `culinary arts` won't cluster via edit distance; see `plan-llm-tagger.md` for the Phase 4 LLM-based suggestion pass
