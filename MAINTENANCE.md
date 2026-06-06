# ViewTube — Tag Maintenance Guide

## How tags flow in

1. A video is added (bookmarklet or crawler re-run). Its raw YouTube tags are stored verbatim.
2. On add, `retroactive_apply` runs scoped to that video — any existing alias rules that match its raw tags immediately assign canonical tags. No action needed if the tags are already covered.
3. New uncovered raw tags accumulate in the **unclassified pool** on `/tags`.

---

## The signal

The pool count badge on the `/tags` page header shows how many unclassified tags with 2+ videos exist. When it grows after adding videos, work needs doing. Single-video tags are excluded — they're mostly publisher noise unique to one video.

---

## Steady-state maintenance (small batches)

Open `/tags`. Use whichever tool fits the batch size:

**Manual pool** — for a handful of obvious ones:
1. Check one or more pills in the unclassified pool.
2. Right-click any pill to see its associated video titles for context.
3. The "Related to" strip appears with co-occurring tags pre-checked — trim any that don't belong.
4. Type a canonical name (autocomplete shows existing ones) → **Assign selected**.

**Co-occurrence suggestions** — for discovering clusters:
1. Check a pool tag. The "Related to" strip surfaces the tags that most often appear on the same videos.
2. Check additional pool tags to merge their neighborhoods additively.
3. Dismiss (×) any suggestions that don't belong, then assign.

**Smart Suggest** — for LLM-driven proposals on the current pool:
1. Click **Smart Suggest** (requires `ANTHROPIC_API_KEY`).
2. Review the suggestion cards — edit the canonical name if needed, uncheck any members that don't fit.
3. Click **Accept** on each card.

---

## Periodic batch pass (large backlogs)

Run the CLI tool after adding many videos or when the pool count is large:

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# See current state
python tools/tag_categorizer.py stats --db viewtube.db

# LLM categorization pass (adjust --min-videos as needed)
python tools/tag_categorizer.py suggest --db viewtube.db --min-videos 2

# Interactive review: a)pprove  r)ename  e)dit members  s)kip  q)uit
python tools/tag_categorizer.py review proposals.json

# Apply to live DB
python tools/tag_categorizer.py apply approved.json --db viewtube.db
```

The `suggest` command sends each tag with sample video titles so the LLM can disambiguate by content, not just tag name. Review takes ~5 min for 30–50 proposals.

---

## After creating new canonicals

New canonicals from any path (pool, Smart Suggest, CLI apply) start:
- With alias rules already attached and `retroactive_apply` already run.
- **Ungrouped** — they won't appear under any `<optgroup>` in the filter select.

To place them in groups:

**Auto-assign** (requires `ANTHROPIC_API_KEY`): click **Auto-assign N ungrouped** in the Tag Groups header. One LLM call assigns all ungrouped canonicals. Check the results and remove any wrong placements with ×.

**Manual**: use the "Add canonical…" dropdown on the relevant group card.

When the API key is absent, the header shows "N ungrouped — set ANTHROPIC_API_KEY to auto-assign" as a reminder.

---

## Per-video corrections

If a canonical tag is wrong for a specific video (false positive from a broad alias):
- Right-click the tag pill on the video card → **Remove from video**.
- This removes only that video's association — the alias rule is unchanged.
- The association will NOT be re-applied by "Re-apply all rules" unless you re-add the rule.
- To fix the root cause, delete or narrow the alias on the canonical's card on `/tags`.

---

## Reference: what lives where

| Concern | Location |
|---|---|
| Unclassified pool, Smart Suggest, canonical admin | `/tags` |
| Tag groups and auto-assign | `/tags` (Tag Groups section) |
| Bulk CLI categorization | `tools/tag_categorizer.py` |
| Alias system design | `plan-tag-distillation-v2.md` |
| Per-video tag removal | Right-click pill on any video card |
| Re-apply all alias rules | `/tags` → Re-apply all rules button |
