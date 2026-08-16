# Brainstorm: Demo Data + Low-Friction Onboarding

**Status:** Raw ideas, not yet scoped into a spec/plan. Continue here later.

## Premise

Now that the real personal `viewtube.db` has been scrubbed from git history (see the
2026-08-15 history-cleanup work), the repo is safe to make public — but a fresh clone from
GitHub has no data to look at. Someone checking out the project for the first time needs a
way to see a fully-populated, working app without touching real personal bookmarks and
without depending on live network calls to YouTube.

## Two complementary pieces

### A. Generated synthetic demo database (primary "try it now" path)
Not a committed binary — a seed script (`scripts/seed_demo_db.py` or a `--seed-demo` CLI
flag) that inserts fabricated rows directly through the existing `add_video`/
`upsert_channel`/`create_canonical_tag` functions already in `webapp/db`. Zero network
calls, zero yt-dlp, zero waiting — `viewtube-web` and you're looking at a fully populated app
in seconds. This is the "wow, it just works" path.

### B. Sample Firefox-bookmarks-export file (secondary "see real ingestion" path)
A small JSON/HTML export with a handful of real, stable, unlikely-to-disappear public
YouTube URLs — demonstrates the actual ingestion pipeline a real user would experience with
their own export. Doubles as a richer crawler test fixture than the current
`sample_bookmarks.json`. Inherently flakier (depends on YouTube still having those videos,
network access, no rate-limiting) — fine as a secondary step, bad as the *only* option.

**Recommendation:** do both, positioned differently. A is the default; B is for someone who
wants to understand the pipeline before pointing it at their real bookmarks.

## Making the seed data actually demonstrate the app

The point isn't just "some rows exist" — it should exercise every feature area so a
first-time visitor sees the whole feature set working by clicking around, not an empty shell.
Deliberately seed:

- A few favorited videos, a few in the Watch Later queue (in an order that shows
  drag-reorder is meaningful)
- Enough spread in `date_last_viewed` that the Rediscover shelf actually populates
- At least one populated channel, a couple of tag groups plus some unclassified tags (so the
  tagging UI has something to do)
- A couple of archived/hidden videos, so the Hidden page isn't empty either
- Fake-but-plausible channel names/titles ("Demo Cooking Channel," "Sample Guitar Lessons")
  rather than real people's data — avoids both the privacy issue and the flakiness of
  hotlinking real YouTube thumbnail/avatar CDNs (which rate-limited hard mid-session
  earlier this project). Either embed small placeholder thumbnails as data URIs (same trick
  used for feature-sheet.html's fonts) or skip thumbnails entirely for demo rows.

## Onboarding flow

1. Clone → install deps
2. **Fast path:** one command generates+runs the demo (`viewtube-web --demo`, or a
   `make demo`/`./demo.sh` wrapper) → open localhost → done in under a minute, no external
   dependencies
3. **Real path:** run the crawler against the sample bookmarks file (or the user's own
   export) → run the webapp against that output
4. Optional: load the Firefox extension, point it at localhost, demonstrate add/tag/
   favorite/watch-later live
5. Optional: set `ANTHROPIC_API_KEY` to unlock LLM tag suggestions
6. `pytest`/`npm test` as a "confirm your setup is sane" step

A `--reset-demo` flag or `make clean-demo` is worth having too, so contributors can always
blow away and regenerate a known-good state rather than accumulating cruft from clicking
around.

## Where this lives

A dedicated `GETTING_STARTED.md` (or a beefed-up README quickstart section) walking through
the flow above.

## Bigger swing (probably defer)

A `.devcontainer`/Docker setup for a true one-click "open in Codespaces, no local Python/Node
needed" experience. Worth naming but likely out of scope for a first pass unless
low-friction-for-strangers becomes a real priority beyond just this repo's owner and
future-self.

## Next step (when resumed)

Decide: seed script vs. fixture-file-only for the demo DB (leaning seed script, per above).
Then scope into a spec/plan via `superpowers:brainstorming` properly before implementing.
