# Brainstorm: Demo Data + Low-Friction Onboarding

**Status:** Raw ideas, not yet scoped into a spec/plan. Continue here later.

## Premise

Now that the real personal `viewtube.db` has been scrubbed from git history (see the
2026-08-15 history-cleanup work), the repo is safe to make public — but a fresh clone from
GitHub has no data to look at. Someone checking out the project for the first time needs a
way to see a fully-populated, working app without touching real personal bookmarks and
without depending on live network calls to YouTube.

**Update (2026-08-17):** `README.md` now exists and documents the "B" real path (crawler
against a real Firefox bookmarks export) — see the packaging-fix session. This brainstorm's
remaining scope is specifically the "A" fast demo path, which hasn't been built yet.

## Two complementary pieces

### A. Generated demo database — real videos, fabricated personal layer (primary "try it now" path)
Not a committed binary — a seed script that inserts rows directly through the existing
`add_video`/`upsert_channel`/`create_canonical_tag` functions already in `webapp/db`. Zero
network calls, zero yt-dlp, zero waiting *at seed time* — `viewtube-web` and you're looking
at a fully populated app in seconds. This is the "wow, it just works" path.

**Key resolution (2026-08-17):** the content layer (video IDs, titles, thumbnails, channel
names) is **real, public YouTube data**, hardcoded directly in the seed script rather than
fetched live. Only the personal-engagement layer (favorites, watch-later membership/order,
tags, `is_watched`, seeded `personal_view_count`/`date_last_viewed`) is fabricated. This
resolves the tension between "wants to look like a real, familiar YouTube-style thumbnail
wall you can click into" and "must not expose real personal data":
- The privacy risk was never in the *content* (a video's public title/thumbnail/channel) —
  it was in the *engagement signal* (what someone actually favorited, tagged, and watched,
  which reveals real personal taste/history). Fabricating only the engagement layer removes
  exactly the sensitive part while keeping the content real.
- Real video IDs mean **clicking a demo card just works, unmodified** — it hits the existing
  `/visit/<video_id>` route, which increments `personal_view_count`, sets
  `date_last_viewed`, and redirects to the real video on YouTube. Zero new code for the
  "click to watch and see stats update" interaction; it's just the app running normally on
  real IDs.
- Real thumbnails come from YouTube's actual CDN (`i.ytimg.com`) — the familiar wall-of-
  thumbnails look, no placeholder graphics needed for videos.
- Corollary: a real video's channel is real too (can't pair a real video with a fabricated
  channel name without it looking broken) — so the "6-8 channels" below are real, distinct,
  well-known-enough public creators, not invented names. Still fine, since a public
  creator's channel name is no more sensitive than the video title.

**Decided shape (2026-08-17):** `viewtube-web` itself stays untouched — no `--demo` flag,
no special-casing of "no `--db` given." Instead:

- `scripts/seed_demo_db.py --output demo.db [--force]` — a standalone script (plain
  `python scripts/...`, not a `[project.scripts]` console entry — keeps the packaging
  surface we just fixed simple, same pattern as `tools/tag_categorizer.py` today) that
  builds a fresh SQLite file entirely through existing `webapp.db` functions
  (`init_webapp_tables`, `add_video`, `upsert_channel`, `create_canonical_tag`,
  `set_favorite`, watch-later add, etc.). `--force` regenerates if `demo.db` already exists;
  without it, refuses to clobber (this doubles as the "reset" mechanism from the original
  onboarding-flow idea below — rerun with `--force`, no separate flag needed).
- Then: `viewtube-web --db demo.db --port 8080` — the exact same command pattern the README
  already teaches for the real path. No new CLI surface on the webapp side at all.
- `make demo` / `./demo.sh` wraps both: seed if `demo.db` doesn't exist → run the server.
  This is what actually delivers the "one command" experience.
- `demo.db` itself stays gitignored (already covered by the `viewtube*.db*` pattern) — the
  seed *script* is the checked-in artifact, not the data, same principle as never committing
  the real DB.

**Seed data sizing (concrete, not just "some rows"):**
- ~50 real videos across 6–8 real, varied, evergreen public channels
- 12–15 tags in 3 tag groups, plus a few deliberately left unclassified (so the tagging UI
  has something to do)
- 8 videos in Watch Later, 6 favorited, 2–3 hidden
- `date_last_viewed` spread widely enough that the Rediscover shelf has a real pool to draw
  from, not just 1–2 eligible videos

**Thumbnails/CDN risk, reassessed:** the rate-limiting pain hit earlier this project was
specifically `yt3.googleusercontent.com` (channel *avatar* images, 16+ concurrent requests
triggered `503`s) — actual video thumbnails from `i.ytimg.com` loaded fine with a few
seconds' wait. So real video thumbnails for ~50 demo videos should render smoothly, per our
own earlier testing. For **channel avatars** specifically (less central to the "wall of
thumbnails" appeal, which is about videos): stub them with no avatar image at all, reusing
the existing `.no-thumb` placeholder treatment channels already fall back to — sidesteps the
one CDN that actually gave us trouble, without needing a custom graphic.

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
The bullets that were here are now folded into section A above (sizing + thumbnails/CDN
subsections) now that the real-videos-plus-fabricated-engagement-layer design is settled —
kept the checklist spirit: favorites, watch-later ordering, rediscover-shelf-eligible date
spread, tag groups with unclassified leftovers, and a couple of hidden videos, all still
apply exactly as before, just layered onto real content instead of fully synthetic rows.

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
around. **Resolved above:** this is just `python scripts/seed_demo_db.py --output demo.db --force`
— no separate reset flag/command needed.

## Where this lives

**Revised (2026-08-17):** now that `README.md` exists (documenting the real path), this
doesn't need a separate `GETTING_STARTED.md` — just a new "Try it with sample data" section
in the README, positioned above the real-ingestion instructions as the fast path.

## Bigger swing (probably defer)

A `.devcontainer`/Docker setup for a true one-click "open in Codespaces, no local Python/Node
needed" experience. Worth naming but likely out of scope for a first pass unless
low-friction-for-strangers becomes a real priority beyond just this repo's owner and
future-self.

## Next step (when resumed)

Seed-script-vs-fixture-file decided (seed script, shape above). Real-videos-plus-fabricated-
engagement-layer design decided. Remaining open question: **curating the actual list of ~50
real videos / 6-8 real channels** — see next section.

## Curated video list — channel picks locked in (2026-08-17)

Criteria for candidates: real, public, evergreen/unlikely-to-disappear (large official
channels or historically/culturally significant uploads), varied enough across topics and
channels to feel like a real personal library rather than a single-theme demo reel. Stored
as an editable list in the seed script (not hardcoded inline per-row) so any video that later
breaks is a one-line swap.

**Shape:** "something for everyone" — a genuine mix of topics, not mirroring any one
person's real viewing habits.

| Topic | Channel | ~videos | Why it's a safe pick |
|---|---|---|---|
| Coding / tech | freeCodeCamp.org (or similarly large official tutorial channel) | 8-10 | Nonprofit/educational, huge back catalog, no takedown incentive |
| Cooking | Bon Appétit or Tasty | 8-10 | Major media-company channel, permanent fixture |
| Music / guitar | Marty Music or Justin Guitar | 8-10 | Instructional content ages well, large stable channel |
| Comedy / evergreen viral | 3 iconic single uploads: Rick Astley "Never Gonna Give You Up", PSY "Gangnam Style", Pinkfong "Baby Shark Dance" | 3 | All official-channel, massively iconic, essentially zero removal risk (first-video-to-1B-views and most-viewed-video-ever status respectively). Explicitly ruled out "Charlie bit my finger" — the family pulled/NFT-sold the original a few years back, exactly the instability this bucket needs to avoid |
| Education / explainer | Kurzgesagt or TED | 8-10 | Massive, well-funded, actively maintained official channels |
| Science / nature | NASA or National Geographic | 8-10 | Government/institutional or major media, extremely stable |
| DIY / other lifestyle | A large established maker/DIY channel | 8-10 | Rounds out the variety |

**Deferred to implementation:** exact video IDs, current durations, and view counts for each
slot above — a verification lookup task, not a design decision. The seed script's video list
should be structured so any individual entry can be swapped later without touching the rest
of the seeding logic.
