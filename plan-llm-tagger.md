# ViewTube — LLM Tag Categorization Plan

## Problem

The manual tag pool (Phase 3) works well but requires the user to recognize which tags belong together. Surface-form similarity (edit distance, token overlap) handles obvious cases like `meal prep` → `meal-prep`, but it cannot handle:

- **Semantic synonyms**: `culinary arts`, `home cooking`, `recipes from scratch` → `cooking`
- **Different phrasings of the same concept**: `beginner guitar`, `learn to play guitar`, `first guitar lesson` → `guitar`
- **Implicit category membership**: `chicken tikka masala`, `pasta bolognese`, `homemade bread` → `recipes`
- **Noise identification**: `#ad`, `collab`, `2024`, `HD 1080p` → should be dismissed, not canonicalized
- **Cross-language**: `cocina casera`, `Kochen lernen` alongside their English equivalents

An LLM pass can understand all of these because it reasons about meaning, not surface form. The result is that the user's unclassified pool can be pre-organized into suggested groups, dramatically reducing the manual work.

---

## Design Principles

1. **LLM proposes, user confirms.** No LLM suggestion writes to the database without the user reviewing and accepting it. This is consistent with the existing tag pool UX and prevents quiet pollution of the canonical tag system.

2. **Additive to the existing workflow.** The manual pool remains the primary interface. LLM suggestions appear as pre-selected groups that the user can accept, edit, or dismiss. The user is not forced to engage with the LLM path at all.

3. **On-demand, not automatic.** Running an LLM costs tokens. The user triggers the suggestion pass explicitly. There is an optional hook for running it after a bulk import (crawler batch), but it is never triggered automatically on individual video adds.

4. **Existing canonical tags as anchors.** The prompt includes the user's current canonical tags. The LLM maps unclassified tags to those first, before suggesting new canonical names. This reduces drift and keeps the taxonomy the user has already built intact.

---

## How It Works

### Input to the LLM

```
Existing canonical tags:
  meal-prep (47 videos), guitar (23 videos), cooking (18 videos)

Unclassified tags (sorted by video count):
  "chicken recipes" (8), "beginner guitar" (6), "learn to play guitar" (5),
  "home cooking" (4), "weekly meal prep" (4), "pasta from scratch" (3),
  "#ad" (3), "collab 2024" (2), "HD" (1), "culinary arts" (1)
```

### Output from the LLM (structured JSON)

```json
{
  "assignments": [
    {
      "canonical": "meal-prep",
      "members": ["weekly meal prep"],
      "confidence": "high"
    },
    {
      "canonical": "guitar",
      "members": ["beginner guitar", "learn to play guitar"],
      "confidence": "high"
    },
    {
      "canonical": "cooking",
      "members": ["chicken recipes", "home cooking", "pasta from scratch", "culinary arts"],
      "confidence": "high"
    }
  ],
  "noise": ["#ad", "collab 2024", "HD"],
  "unassigned": []
}
```

`assignments` maps to existing canonical tags. `noise` tags are identified as not worth canonicalizing (the user can create a `_noise` canonical tag and alias them all, or simply ignore them). `unassigned` holds anything the LLM wasn't confident about.

### What the user sees

The unclassified tag pool on the Tags page gains a **"Smart Suggest"** button. Clicking it:
1. Sends the unclassified tags + existing canonical tags to the LLM
2. Renders the results as pre-populated suggestion cards, one card per suggested grouping
3. Each card shows: the proposed canonical name, the member tags (pre-checked), and the confidence level
4. The user can uncheck individual members, edit the canonical name, or dismiss the whole card
5. Accepting a card calls the existing `confirm_suggestion` route — no new backend logic for the confirm step

This reuses the existing `confirm_suggestion` → `add_alias` → `retroactive_apply` pipeline unchanged.

---

## Suggestion Cards UI

```
┌─────────────────────────────────────────────────────┐
│ cooking                            [high confidence] │
│                                                      │
│ [✓] chicken recipes (8)  [✓] home cooking (4)        │
│ [✓] pasta from scratch (3)  [✓] culinary arts (1)    │
│                                                      │
│  Canonical name: [cooking          ]  [Accept]  [✕]  │
└─────────────────────────────────────────────────────┘
```

Noise tags get their own section: "Suggested noise tags (will not be canonicalized)" — shown as read-only pills with an option to bulk-ignore them (assign to a hidden `_noise` canonical tag, or just leave them in the pool).

---

## When It Runs

### Primary: on-demand from the Tags page

A "Smart Suggest" button in the Unclassified Tags section header. Grayed out if:
- `ANTHROPIC_API_KEY` is not set (shows "Configure API key in settings")
- The unclassified pool is empty
- A suggestion run is already cached and current (button becomes "Refresh Suggestions")

### Optional: after a crawler batch import

The crawler CLI gains a `--suggest` flag:
```bash
python -m crawler.cli --db ~/viewtube.db --suggest
```

This runs the LLM pass after ingestion and stores suggestions in the DB. The user sees them the next time they open the Tags page. Does not auto-confirm anything.

### What it does NOT do

- **Does not run on every bookmarklet add.** A single video adds a small number of new tags; the latency and cost aren't worth it. The user sees new unclassified tags accumulate in the pool and can trigger a suggestion pass when they want.
- **Does not auto-apply suggestions.** Even high-confidence suggestions wait for user confirmation.

---

## Caching and Staleness

Suggestions are stored in a `llm_suggestions` table so they persist across app restarts. They are considered **stale** when the unclassified tag pool has changed since the last run (new tags added or tags removed from the pool). Staleness is detected by comparing a hash/count of the current unclassified tags against what was sent in the last run.

```sql
CREATE TABLE llm_suggestions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical    TEXT NOT NULL,       -- proposed canonical name
    members      TEXT NOT NULL,       -- JSON array of tag name strings
    confidence   TEXT,                -- 'high', 'medium', 'low'
    is_noise     BOOLEAN NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    pool_hash    TEXT NOT NULL        -- hash of unclassified tag list at time of run
);
```

Accepting or dismissing a suggestion deletes its row. The pool_hash check means clicking "Smart Suggest" on a stale cache triggers a fresh LLM run rather than showing outdated groupings.

---

## Prompt Design

The prompt is structured to minimize hallucination and ensure the output is parseable.

**Model**: `claude-haiku-4-5` by default (fast and cheap; sufficient for tag grouping). Configurable to `claude-sonnet-4-6` for better semantic reasoning on ambiguous cases.

**Key prompt design decisions**:

1. **Enumerate existing canonical tags explicitly** — prevents the LLM from suggesting a new canonical name when an existing one fits.
2. **Request assignments to existing canonicals first** — new canonical suggestions only for things that genuinely don't fit any existing tag.
3. **Use tool use / structured output** — define a JSON schema and use Claude's tool use to guarantee parseable output. No regex parsing of freeform text.
4. **Include video counts** — higher-count tags are more important to classify; the LLM should prioritize them.
5. **Noise identification built in** — the LLM is explicitly asked to identify tags that are noise rather than silently assigning them somewhere wrong.
6. **Cap input size** — send at most 200 unclassified tags per run (the most-used ones first). Larger pools should be processed in batches.

**Approximate cost**: 200 tags × ~6 tokens/tag + prompt overhead ≈ 2,000 input tokens + ~500 output tokens = ~2,500 tokens per run ≈ $0.0003 on Haiku. Negligible.

---

## API Key Management

`ANTHROPIC_API_KEY` is read from the environment. The app does not store it in the DB or config files.

```bash
# In shell profile or .env
export ANTHROPIC_API_KEY=sk-ant-...
```

If the key is absent, the "Smart Suggest" button is replaced by a notice: *"Set ANTHROPIC_API_KEY to enable smart tag suggestions."* The rest of the tag management UI is unaffected.

The `anthropic` Python package is added as an optional dependency (`requirements.txt` with a comment, or a separate `requirements-llm.txt` to avoid forcing it on users who don't want the LLM feature).

---

## New-Video Flow with LLM

When a video is added (bookmarklet or crawler):

```
video added
  → apply_aliases (instant, no LLM)
  → new raw tags stored in video_tags
  → unclassified pool grows

next time user opens Tags page:
  → pool shows new unclassified tags
  → if pool is stale, "Smart Suggest" button prompts a refresh
  → user clicks → LLM runs → suggestions rendered
  → user confirms → aliases written, pool shrinks
```

The key insight: alias rules established from past LLM passes propagate automatically to new videos via `apply_aliases`. Over time, as the user builds up their canonical tag vocabulary, new videos will mostly be classified automatically on ingest — the LLM suggestion pass is needed less often.

---

## Implementation Phases

### Phase 4a — LLM suggestion engine ✓ DONE

- `webapp/llm_tagger.py`: `get_suggestions`, `compute_pool_hash`, `is_available`, `_build_user_message`
  - Lazy `import anthropic` — `ImportError` raised at call time if not installed, not at module import
  - `tool_choice={"type": "tool", "name": "categorize_tags"}` forces structured JSON output
  - Noise tags bundled as `{"canonical": "_noise", "is_noise": True}`
  - `compute_pool_hash`: SHA256 of sorted tag names, first 16 hex chars
- `webapp/db.py`: `save_llm_suggestions`, `get_llm_suggestions`, `dismiss_llm_suggestion`, `is_llm_suggestion_cache_stale`; `llm_suggestions` DDL in `init_webapp_tables`
- `webapp/routes.py`: `POST /tags/llm-suggest`, `POST /tags/llm-suggest/<id>/dismiss`; `tags()` GET passes `llm_available`, `llm_stale`, `llm_suggestions`, `llm_error` to template
- Tests: `tests/webapp/test_llm_tagger.py` (19 tests), `TestLLMSuggestions` in `test_db.py` (9 tests); all pass without `anthropic` installed (mock via `sys.modules`)

### Phase 4b — Suggestion cards UI

- `webapp/templates/tags.html`: add LLM suggestion cards section above the manual pool; each card is a pre-populated form pointing to the existing `confirm_suggestion` route
- `webapp/static/style.css`: suggestion card styles; confidence badge (green/yellow/grey)

### Phase 4c — Crawler `--suggest` flag (optional)

- `crawler/cli.py`: add `--suggest` flag; after batch ingest, call `get_suggestions` and write results to DB via `save_llm_suggestions`

---

## Trade-offs and Risks

| Risk | Mitigation |
|---|---|
| LLM assigns a tag to the wrong canonical | Confidence score surfaced in UI; user reviews before confirming |
| LLM hallucinates new canonical tag names | Existing canonicals listed in prompt; LLM instructed to prefer them |
| API key not set → feature silently missing | UI shows clear notice, not a broken button |
| Stale suggestions mislead the user | Pool hash comparison detects staleness; stale cache prompts a refresh |
| Large tag pools → high token cost | Cap at 200 tags per run; Haiku pricing makes even 200-tag runs negligible |
| `anthropic` package not installed → import error | Lazy import in `llm_tagger.py`; feature degrades gracefully if package missing |

---

## What This Doesn't Solve

- **Tags in non-English languages**: the LLM handles these well semantically, but the canonical tag system is English-first. Cross-language tags may be assigned to English canonicals (usually correct) or left unassigned.
- **Highly personal/niche tags**: tags meaningful only to the user (e.g. `watch-later-dan`) are opaque to the LLM and will land in `unassigned`.
- **Real-time classification of individual video adds**: the per-video cost and latency make this impractical. The batch suggestion pass is the right granularity.
