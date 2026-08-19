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

## Curated video list — complete (2026-08-19)

Criteria for candidates: real, public, evergreen/unlikely-to-disappear (large official
channels or historically/culturally significant uploads), varied enough across topics and
channels to feel like a real personal library rather than a single-theme demo reel. Stored
as an editable list in the seed script (not hardcoded inline per-row) so any video that later
breaks is a one-line swap.

**Shape:** "something for everyone" — a genuine mix of topics, not mirroring any one
person's real viewing habits.

**Verification method (2026-08-19):** every ID below was fetched directly with `yt-dlp`
(`--skip-download --print "%(id)s|%(title)s|%(channel)s|%(duration_string)s|%(view_count)s"`)
— the same tool the crawler already uses in production, run locally against this machine's
`.venv`. This is more authoritative than the prior pass's web-search + oEmbed approach: it
returns the real title, channel, duration, and current view count in one call, straight from
YouTube, and it's what caught two wrong picks in the coding bucket (see below) that oEmbed
alone had missed distinguishing. 44 of the ~50 target videos are now confirmed across all 7
buckets — see "Still open" for the two small residual gaps.

### Coding / tech — freeCodeCamp.org
Nonprofit/educational, huge back catalog, no takedown incentive. 8 of 8-10 confirmed.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Learn Python - Full Course for Beginners [Tutorial] | `rfscVS0vtbw` | 4:26:52 | 49,122,814 |
| SQL Tutorial - Full Database Course for Beginners | `HXV3zeQKqGY` | 4:20:39 | 20,888,367 |
| Machine Learning for Everybody – Full Course | `i_LwzRVP7bg` | 3:53:53 | 10,291,171 |
| React Course - Beginner's Tutorial for React JavaScript Library [2022] | `bMknfKXIFA8` | 11:55:27 | 4,266,110 |
| HTML Tutorial - Website Crash Course for Beginners | `916GWv2Qs08` | 45:19 | 664,733 |
| Learn JavaScript Interactively in NEW freeCodeCamp.org Curriculum | `n8mNX2YqkUs` | 53:26 | 100,453 |
| Learn HTML & CSS – Full Course for Beginners | `a_iQb1lnAEQ` | 5:21:44 | 932,945 |
| CSS Tutorial – Full Course for Beginners | `OXGznpKZ_sA` | 11:08:10 | 2,945,708 |

### Cooking — Bon Appétit
Major media-company channel, permanent fixture. 8 of 8-10 confirmed, spans "Gourmet Makes",
"Test Kitchen Talks", and "It's Alive" so it isn't a single-series demo reel.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Pastry Chef Attempts to Make Gourmet Instant Ramen \| Gourmet Makes \| Bon Appétit | `g1GFJxVeH9c` | 25:32 | 12,341,661 |
| Pastry Chef Attempts to Make Gourmet M&M's \| Gourmet Makes \| Bon Appétit | `mvDj7DF1jsk` | 40:11 | 6,638,849 |
| Pastry Chef Attempts to Make Gourmet Tater Tots \| Gourmet Makes \| Bon Appétit | `Xi28pEbMdTw` | 38:24 | 6,096,692 |
| Pastry Chef Attempts to Make Gourmet Ben & Jerry's Ice Cream \| Bon Appétit | `FyMWRcVTGAI` | 29:40 | 7,070,664 |
| 6 Pro Chefs Make Their Favorite 15-Minute Meal \| Test Kitchen Talks \| Bon Appétit | `O1JDBt6WE7A` | 18:52 | 3,471,143 |
| Pro Chefs Make Their Favorite Sandwiches \| Test Kitchen Talks \| Bon Appétit | `lF2sKFnuALw` | 22:37 | 7,233,139 |
| Brad Makes Fermented Citrus Fruits \| It's Alive \| Bon Appétit | `KUHp3ve4m50` | 24:28 | 4,015,353 |
| Brad Makes Beef Jerky \| It's Alive \| Bon Appétit | `YGpK6U56oHM` | 18:13 | 7,381,390 |

### Music / guitar — JustinGuitar
Instructional content ages well, large stable channel. 8 of 8-10 confirmed — the first 4 are
from the structured Beginner Course (grade/module playlists); the last 4 are standalone
technique/maintenance videos from the main channel feed, added to reach target since the
course playlists don't surface well in title search.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| JustinGuitar Beginner Course Grade 1 Introduction | `_QCt3UBTS1Y` | 1:15 | 1,396,839 |
| How to Pass JustinGuitar Beginners Course Grade 1 | `BI3S9xSK8Iw` | 8:03 | 185,267 |
| Welcome to Module 2: Rhythm & Chord Change Essentials + Your First Riff! | `zfBkJggF9aU` | 2:49 | 333,147 |
| Minor Pentatonic Scale - Stage 7 Guitar Lesson - Guitar For Beginners [BC-176] | `G-X1RemAzks` | 5:27 | 781,016 |
| How to Change Acoustic Guitar Strings (Step-by-Step Guide) | `eaUbs13xBl0` | 25:15 | 203,261 |
| No Tuner? Learn How to Tune Your Guitar by Ear (using Harmonics!) | `ihlDFZjNM6g` | 5:55 | 60,135 |
| How often should you REALLY change your guitar strings? | `XiOJRhikCBg` | 8:35 | 52,000 |
| How to change strings on electric guitars (PRS/locking tuners/strat-style) | `y5D3jMuCipk` | 21:14 | 30,190 |

### Comedy / evergreen viral
All 3 confirmed live at their originally planned IDs — no change from the 2026-08-17 pick.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster) | `dQw4w9WgXcQ` | 3:33 | 1,805,594,426 |
| PSY - GANGNAM STYLE(강남스타일) M/V | `9bZkp7q19f0` | 4:12 | 6,032,168,341 |
| Baby Shark Dance \| Most Viewed Video \| PINKFONG | `XqZsoesa55w` | *unavailable* | *unavailable* |

Baby Shark's duration/views couldn't be pulled locally — `yt-dlp` reported "video not
available" for it, but that's a false negative: this machine's `yt-dlp` (2026.03.17) warned
on every run that it has no JS runtime available, which it needs to decipher some videos'
signatures, and 2 unrelated search results failed the identical way in the same session. A
web search independently confirmed `XqZsoesa55w` is still live and correct (it's even
mirrored on the Internet Archive). Needs a quick re-check with a working JS runtime (or the
YouTube Data API) before the seed script is written — the ID itself doesn't need re-picking.

### Education / explainer — Kurzgesagt + TED
Massive, well-funded, actively maintained official channels. 4 confirmed.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| The Egg - A Short Story (Kurzgesagt) | `h6fcK_fRYaI` | 8:06 | 36,078,996 |
| The Fermi Paradox — Where Are All The Aliens? (1/2) (Kurzgesagt) | `sNhhvQGsMEc` | 6:20 | 35,291,620 |
| The Fermi Paradox II — Solutions and Ideas (Kurzgesagt) | `1fQkVqno-uI` | 6:17 | 17,192,728 |
| Do schools kill creativity? \| Sir Ken Robinson \| TED | `iG9CE55wbtY` | 20:03 | 24,913,231 |

### Science / nature — NASA + National Geographic
Government/institutional or major media, extremely stable. 4 confirmed.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Perseverance Rover's Descent and Touchdown on Mars (Official NASA Video) | `4czjS9h4Fpg` | 3:25 | 17,916,318 |
| NASA's Perseverance Rover's First 360 View of Mars (Official) | `wE-aQO9XD1g` | 1:00 | 7,147,132 |
| Historic Apollo 11 Moon Landing Footage (NASA) | `FlpstXNjImY` | 29:06 | 2,586,458 |
| Great White Sharks \| National Geographic | `l24FBVeu3Z4` | 2:29 | 78,436 |

### DIY / other lifestyle — Steve Ramsey / Woodworking for Mere Mortals
Resolved by switching approach: `yt-dlp --flat-playlist` against the channel's `/videos` page
(a playlist listing, which doesn't need per-video signature decoding, unlike a full
`watch?v=` fetch) reliably returned real, current video IDs — sidestepping both the earlier
WebFetch JS-rendering wall and the ambiguous-search-result problem that sank Mark Rober. 9 of
8-10 confirmed, picked for genuine project/technique titles rather than the channel's more
jokey vlog-style uploads.

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| A woodworker's guide to installing keyhole hangers. They aren't hard. | `JvzoijD2YaY` | 5:17 | 29,585 |
| 2026 BEGINNERS' GUIDE to the TOOLS and SUPPLIES you need to start a woodworking hobby | `QLSYADN_BzM` | 15:21 | 28,953 |
| Finding simplicity in woodworking. And life. | `F5oV9FoAKHM` | 13:38 | 25,153 |
| 6 Simple Ways to Reset Your Workshop and Enjoy It Even More | `3lzPv_iHEyQ` | 8:15 | 58,447 |
| The myth of "fine woodworking" and joinery | `V7u78RQxjPg` | 15:49 | 96,886 |
| They Say Not to Do This… But It Works. (Finishing technique.) | `SIzDi6pSD4U` | 7:40 | 155,325 |
| Simple, sturdy picture frame with splined corner miters | `JgLVfwRltZY` | 12:56 | 78,157 |
| Modifying my standing workstation | `C28ghmZVvd0` | 7:42 | 61,849 |
| Simple garden hose storage container. LIMITED TOOLS NEEDED! | `IcQxYrNNDcg` | 10:43 | 89,404 |

## Still open (2026-08-19)

- **Baby Shark's duration/views** — see the note under "Comedy / evergreen viral" above.
  Small, isolated gap; the ID itself is confirmed correct.
- **Two wrong picks caught and removed from the coding bucket in an earlier pass:**
  `-TkoO8Z07hI` ("C++ Full Course") and `PT7nhlLGndU` ("Responsive Web Design Certification")
  were not freeCodeCamp.org uploads at all — they belonged to "Bro Code" and "Tech By Usman"
  respectively. Both replaced with verified freeCodeCamp.org entries above. Kept as a record
  of why per-video verification (not just search-result trust) mattered for this list.

**Deferred to implementation:** Baby Shark's duration/views (needs a working JS runtime or
the YouTube Data API — not a design decision). Everything else is complete: 44 videos
verified by title, channel, duration, and view count across all 7 buckets. The seed script's
video list should be structured so any individual entry can be swapped later without touching
the rest of the seeding logic.

## Next step

Video list is done. This brainstorm is fully design-complete: the two-path onboarding
architecture, seed-script shape, privacy reasoning, and now the curated video list are all
settled. Ready to convert into a formal spec at `docs/superpowers/specs/` per this project's
convention, scoped to the "A" fast-demo-path only (the seed script + a new README section) —
the "B" sample-bookmarks-file path is a smaller separate follow-up, not part of this spec.
