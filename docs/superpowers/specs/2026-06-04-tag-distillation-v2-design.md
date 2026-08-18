# ViewTube — Tag Distillation Take 2

## Context

The original distillation plan established a solid foundation (Phases 1–2: schema + alias
system, additive model, retroactive apply) and the web-based manual pool (Phase 3) works
well for ongoing maintenance. The LLM suggestion cards (Phase 4) surfaced the right idea
but the wrong interaction model.

The problem: with 28,000+ unclassified tags and only 11 canonical tags established, the
web UI approach — processing tags in chunks, reviewing individual suggestion cards — is
not tractable for initial bulk categorization. This plan rethinks the initial
categorization workflow while keeping the existing infrastructure intact.

---

## What Stays

- The additive alias model (`tag_aliases`, `video_tags`, `retroactive_apply`) — unchanged
- Phases 1–2 of the original plan (fully implemented)
- The per-video tag editing flow in the webapp
- The webapp "Smart Suggest" as a maintenance tool for new tags as the library grows
- The existing 11 canonical tags and 429 alias rules

## What Changes

- **Noise handling**: replace the `_noise` canonical approach with an `is_noise` flag on
  `tags`. Noise tags keep all video associations but are filtered everywhere in the UI. No
  special-cased canonical clutters the canonical list.
- **Bulk categorization workflow**: CLI-based instead of webapp-based. A standalone
  `tools/tag_categorizer.py` drives the initial categorization pass.
- **LLM prompt enrichment**: each candidate tag is sent with the titles of the videos it
  appears on, giving the LLM substantially better signal than tag names alone.
- **Tier-based triage**: categorize by frequency band, not all-at-once.

---

## The Tag Frequency Reality

With 2,801 videos and 28,110 unclassified tags:

```
50+ videos:    13 tags  ← massive coverage, handle first
20-49 videos:  20 tags
10-19 videos:  51 tags
5-9 videos:   546 tags
               ────────
               ~630 tags total worth focusing on (5+ videos)

2-4 videos:  3,937 tags  ← secondary; auto-assign to established canonicals
1 video:    23,118 tags  ← leave unclassified; user can browse on demand
```

The ~630 tags used in 5+ videos represent the real vocabulary of the library. Establishing
canonicals from this set covers nearly every video multiple times over. The long tail is
mostly publisher noise that happens to be unique to a single video.

---

## Schema Change

One addition to the `tags` table:

```sql
ALTER TABLE tags ADD COLUMN is_noise BOOLEAN NOT NULL DEFAULT 0;
```

Noise tags:
- Keep all rows in `video_tags` (associations preserved, recoverable)
- Filtered from the tag cloud (`AND t.is_noise = 0`)
- Filtered from video card tag pills
- Not included in unclassified tag pool queries
- Not included in canonical tag admin view

This replaces the `_noise` canonical approach — no special-cased logic in queries, just
one boolean flag.

---

## Three-Tier Triage Strategy

### Tier 1 — Auto-noise (zero user interaction)

Pattern-based noise marking. No LLM, no review. Run once at the start.

Patterns auto-marked as noise:
- **YouTube category strings**: "Howto & Style", "Entertainment", "People & Blogs",
  "Science & Technology", "Gaming", "Education", "Music", "Film & Animation", "Sports",
  "Travel & Events", "Autos & Vehicles", "Pets & Animals", "News & Politics"
- **Quality/format meta**: HD, 4K, 1080p, 720p, UHD, HQ
- **YouTube meta**: yt:cc=on, #shorts, subscribe, youtube
- **Year numbers**: regex `^\d{4}$` matching 2000–2030
- **Pure hashtags**: regex `^#\w+$`
- **Generic filler**: video, watch, new, latest, official, free (exact, case-insensitive)

Expected to immediately clear several thousand tags including the high-frequency YouTube
category strings (e.g. "Howto & Style" appears on 629 videos).

### Tier 2 — LLM taxonomy pass on 5+ video tags

The ~630 high-value tags are sent to the LLM in batches, enriched with video context.

**Key improvement over current `llm_tagger.py`**: instead of sending tag names and counts
alone, each tag is accompanied by a sample of the video titles it appears on:

```
"modal playing" (6 videos)
  Guitar Modes for Beginners, Jazz Harmony Explained, Modal Jazz vs Tonal Jazz,
  Modes of the Major Scale, Dorian Mode Guitar Lesson, Church Modes Introduction

"sat bawl pro" (22 videos)
  Saxophone Lesson: Long Tones, Alto Sax Beginner Warmup, Sax Tone Exercise...
```

This lets the LLM confidently assign ambiguous tags (e.g. "live" — live performance or
live stream?), identify YouTube category imposters (tags that look like content but apply
too broadly), and distinguish "music" (category → noise) from "music theory" (substantive
concept → canonical candidate).

**What the LLM proposes** (same structured output as Phase 4):
- Assignments to existing canonical tags (strongly preferred)
- New canonical concept suggestions (only when nothing fits)
- Noise identification for tags that slipped through Tier 1

**What is NOT proposed as a new canonical**: terms that apply too broadly to be useful
for filtering (tutorial, lesson, beginner, easy, guide, how to) — the prompt explicitly
instructs against canonicalizing terms that would match >20–30% of the library.

### Tier 3 — Cascade to 2–4 video tags (secondary, optional)

After Tier 2 establishes the canonical vocabulary (~20–60 canonical tags), a second LLM
pass sweeps the 3,937 tags used in 2–4 videos. At this point the LLM has rich anchors to
map against — most will either assign cleanly to existing canonicals or be marked noise.
This pass requires no user review.

Single-video tags (23,118) are left unclassified. Visible on demand but excluded from
the main unclassified pool.

---

## CLI Tool: `tools/tag_categorizer.py`

Standalone script. No Flask server required. Default DB: `viewtube-test.db` in the
project root. The live DB is never touched unless `--db viewtube.db` is specified
explicitly — there is no shortcut to accidentally write to production.

### Subcommands

#### `stats`
```
$ python tools/tag_categorizer.py stats

Tags:         28,121 total
  Canonical:      11
  Noise:           0
  Unclassified: 28,110
    5+ videos:    630
    2-4 videos: 3,937
    1 video:   23,118 (long tail — left unclassified)
Alias rules:    429
```

#### `noise [--dry-run]`
```
$ python tools/tag_categorizer.py noise --dry-run
[dry-run] Would mark 2,847 tags as noise:
  YouTube categories:  682
  Year numbers:        143
  Pure hashtags:       891
  Quality/format:       47
  Generic filler:    1,084

$ python tools/tag_categorizer.py noise
Marked 2,847 tags as noise.
```

#### `suggest [--min-videos N] [--batch-size N] [--model MODEL] [--output FILE]`
```
$ python tools/tag_categorizer.py suggest --min-videos 5

Fetching 630 unclassified tags (5+ videos, with video context)...
Batch 1/11 (60 tags) → 14 proposed groups
Batch 2/11 (60 tags) → 11 proposed groups
...
Wrote 87 proposals to proposals.json
```

`--min-videos` default: 5. `--batch-size` default: 60. `--model` default: haiku (fast,
cheap); override to sonnet for harder batches. `--output` default: `proposals.json`.

#### `review PROPOSALS_FILE [--output FILE]`

Interactive terminal loop. Each proposal is presented in turn:

```
[1/87] NEW CANONICAL: music-theory  (8 tags → 312 videos covered)
  Members: music theory, music theory basics, modal playing, harmony,
           chord theory, intervals, ear training, music fundamentals

  [a]pprove  [r]ename  [e]dit members  [s]kip  [q]uit > a

[2/87] ASSIGN TO EXISTING: guitar-lessons  (6 tags → 89 videos)
  Members: beginner guitar, guitar lesson, learn guitar, guitar tutorial,
           acoustic guitar lessons, electric guitar lessons

  [a]pprove  [r]ename  [e]dit members  [s]kip  [q]uit > r
  New name: guitar >
```

`[e]dit members` drops into a simple remove-by-number sub-prompt. Output: `approved.json`
containing only the accepted/renamed items.

#### `apply APPROVED_FILE [--db PATH]`
```
$ python tools/tag_categorizer.py apply approved.json --db viewtube.db

Created canonical tags:        23
Added alias rules:             87
Retroactive associations: 1,842 new video-tag rows
```

This is the only command that writes to the DB. Writing to anything other than the default
test DB requires `--db` explicitly.

### Recommended First-Run Workflow

```
1. cp viewtube.db viewtube-test.db
2. python tools/tag_categorizer.py stats                   # see baseline
3. python tools/tag_categorizer.py noise --dry-run         # preview noise candidates
4. python tools/tag_categorizer.py noise                   # mark noise in test DB
5. python tools/tag_categorizer.py stats                   # post-noise counts
6. python tools/tag_categorizer.py suggest                 # LLM pass → proposals.json
7. python tools/tag_categorizer.py review proposals.json   # interactive review
8. python tools/tag_categorizer.py apply approved.json     # write to test DB
9. (verify results in webapp pointing at viewtube-test.db)
10. python tools/tag_categorizer.py apply approved.json --db viewtube.db
```

---

## Webapp Changes Required

Four places need to filter `is_noise = 0`:

1. **Tag cloud / filter sidebar** — add to canonical filter query
2. **Video card tag pills** — exclude noise from pill display
3. **Unclassified pool** — `get_unclassified_tags` adds `AND t.is_noise = 0`
4. **Crawler schema** — `_SCHEMA` `CREATE TABLE tags` gains the `is_noise` column

The canonical tag admin page (`GET /tags`) needs no changes — noise tags are neither
canonical nor in the alias patterns view.

Optionally: a "Noise tags" accordion on the admin page, showing noise tags by count,
for audit and recovery if something was incorrectly noise-flagged.

---

## What the Original Phase 3/4 UX Becomes

- **Manual pool (Phase 3)**: retained for ongoing maintenance. As new videos arrive and
  bring small batches of new unclassified tags, the web pool is the right tool. The CLI
  handles the one-time bulk problem; the webapp handles the trickle.
- **Smart Suggest (Phase 4)**: retained for ongoing maintenance. Appropriate for small
  batches (dozens of new tags after a crawl), not for 28K tags.

---

## What This Doesn't Solve

- **Single-video long-tail tags**: left unclassified. User can browse on demand.
- **Cross-language tags**: LLM handles semantic mapping but the canonical system is
  English-first; cross-language tags may assign to English canonicals or stay unassigned.
- **Personal/niche tags**: tags opaque to the LLM (creator names, inside references)
  will land in `unassigned`.
- **Canonical drift**: as the library grows, some current concepts may become too broad.
  Ongoing maintenance concern, not addressed here.

---

## Implementation Phases

### Phase 5a — `is_noise` schema + webapp filtering ✅ IMPLEMENTED (2026-06-04, updated 2026-06-04)
- `is_noise BOOLEAN NOT NULL DEFAULT 0` added to `tags` in `crawler/datastore.py` `_SCHEMA`
- `ALTER TABLE tags ADD COLUMN is_noise ...` migration added to `init_webapp_tables` in
  `webapp/db.py` alongside the existing `is_canonical` migration
- `get_unclassified_tags` updated: `AND t.is_noise = 0` added to base WHERE clause
- Test fixture (`tests/webapp/conftest.py`) `SCHEMA_SQL` updated to include `is_noise`
- **Note**: tag cloud and video card queries are unchanged — `get_all_videos` already
  filters to `is_canonical = 1` only for card display; noise tags are non-canonical by
  definition and so are already excluded from card pills and the filter sidebar
- `get_unclassified_tags` gained a `min_videos: int = 2` parameter — the single-video
  long tail (23K tags) is permanently excluded from the webapp pool; only tags used on
  2+ videos appear; tests updated to seed tags on 2 videos to meet the new threshold

### Phase 5b — CLI: `stats` + `noise` subcommands ✅ IMPLEMENTED (2026-06-04)
- `tools/tag_categorizer.py` created with `stats` and `noise` subcommands
- Noise blocklist: `_YT_CATEGORIES` (15 strings), `_QUALITY_META`, `_YT_META`,
  `_GENERIC_FILLER`; `_YEAR_RE` (2000–2030), `_HASHTAG_RE`
- `ensure_noise_column(conn)` auto-migrates the column if missing — CLI is self-contained
- Default DB: `viewtube-test.db`; `--db` flag per subcommand for any override
- `--dry-run` on `noise` command; shows counts by category + sample names

### Phase 5c — CLI: `suggest` subcommand ✅ IMPLEMENTED (2026-06-04)
- Context-enriched LLM prompt: each tag sent with up to 5 video titles (by view count)
- `is_existing` flag in proposals.json: True when canonical name matches an existing
  canonical exactly — surfaced in the `review` terminal UI as "EXISTING" vs "NEW"
- Batch loop with `--min-videos` (default 5) and `--batch-size` (default 60) controls
- `--model` flag defaults to `claude-haiku-4-5-20251001`; override to sonnet for harder batches
- Output: `proposals.json`

### Phase 5d — CLI: `review` + `apply` subcommands ✅ IMPLEMENTED (2026-06-04)
- `review`: interactive terminal loop; per-proposal `a`pprove / `r`ename / `e`dit members /
  `s`kip / `q`uit; noise group reviewed as one block; outputs `approved.json`
- `apply`: creates canonical tags (upsert), adds alias rules (`INSERT OR IGNORE`), runs
  retroactive apply (imports from `webapp.db` with inline fallback); reports counts
- Writing to any DB other than `viewtube-test.db` requires explicit `--db PATH`