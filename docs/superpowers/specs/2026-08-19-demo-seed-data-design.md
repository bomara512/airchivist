# ViewTube — Demo Seed Data Design

## Problem

The real personal `viewtube.db` was scrubbed from git history so the repo could be made
public (see the 2026-08-15 history-cleanup work), but that leaves a fresh clone with no data
to look at. `README.md` already documents the real path (run the crawler against your own
Firefox bookmarks export), but that's slow to try (network calls, yt-dlp fetches) and
requires the visitor to already have a bookmarks export handy. Someone evaluating the repo
for the first time needs a way to see a fully-populated, working app in under a minute,
without touching real personal data and without depending on live network calls.

This spec covers the fast "try it now" path only. A secondary path — a small sample
Firefox-bookmarks-export file that demonstrates the real ingestion pipeline — was scoped out
of this spec deliberately; it's a smaller, independent follow-up (see "Out of scope" below).

## Design

### Content vs. engagement layer

The seed data has two layers, and they get different treatment:

- **Content layer** (video/channel titles, IDs, thumbnails, durations, view counts) is
  **real, public YouTube data**, hardcoded directly in the seed script. Real video IDs mean a
  demo card is clickable and behaves exactly like the real app — it hits the existing
  `/visit/<video_id>` route unmodified, incrementing `personal_view_count`, setting
  `date_last_viewed`, and redirecting to the actual video on YouTube. Real thumbnails load
  from YouTube's own CDN (`i.ytimg.com`), giving the familiar wall-of-thumbnails look with no
  placeholder graphics needed.
- **Personal-engagement layer** (favorites, watch-later membership/order, tags, `is_watched`,
  `personal_view_count`, `date_last_viewed`) is **fabricated**.

This split resolves the tension between "should look like a real, familiar YouTube-style
library" and "must not expose real personal data": the privacy risk was never in a video's
public title or thumbnail — it was always in the *engagement signal* (what someone actually
watched, favorited, and tagged, which reveals real personal taste and history). Fabricating
only that layer removes exactly the sensitive part while keeping the content real.

Channel avatars are the one exception to "use real CDN assets": they're left unfetched,
reusing the existing `.no-thumb` placeholder treatment channels already fall back to. This
sidesteps `yt3.googleusercontent.com`, the CDN that rate-limited this project earlier
(`503`s past ~16 concurrent requests) — video thumbnails from `i.ytimg.com` aren't affected
and don't need this workaround.

### Seed script

`scripts/seed_demo_db.py --output demo.db [--force]` — a standalone script (plain
`python scripts/...`, not a `[project.scripts]` console entry, matching the existing pattern
of `tools/tag_categorizer.py`) that builds a fresh SQLite file entirely through existing
`webapp.db` functions: `init_webapp_tables`, `upsert_channel`, `add_video`,
`create_canonical_tag`, `set_favorite`, and the watch-later add function. No new functions are
added to `webapp/db.py` or `webapp/routes.py` — the script is purely a caller of existing,
already-tested public functions.

- `--force` regenerates `demo.db` if it already exists; without it, the script refuses to
  clobber an existing file. This doubles as the reset mechanism — rerun with `--force` to get
  back to a known-good state. No separate reset flag needed.
- `demo.db` itself stays gitignored (already covered by the `viewtube*.db*` pattern) — the
  seed *script* is the checked-in artifact, never the data, same principle as never
  committing the real database.

### Running it

`viewtube-web --db demo.db --port 8080` — the exact command pattern the README already
teaches for the real path. No new CLI surface on the webapp side.

`make demo` / `./demo.sh` wraps both steps: seed if `demo.db` doesn't exist, then run the
server. This is what delivers the actual "one command" experience.

### README

A new "Try it with sample data" section, positioned above the existing real-ingestion
instructions as the fast path, since it requires nothing but a clone and a Python install.

## Seed data sizing

- 44 real videos across 7 real, varied, evergreen public channels/topics (table below)
- 12–15 tags across 3 tag groups, plus a few videos deliberately left with unclassified tags
  so the tagging UI has something to do
- 8 videos in Watch Later (ordered), 6 favorited, 2–3 hidden
- `date_last_viewed` spread widely enough that the Rediscover shelf draws from a real pool,
  not just 1–2 eligible videos

## Curated video list

Every ID below was fetched directly via `yt-dlp --skip-download --print
"%(id)s|%(title)s|%(channel)s|%(duration_string)s|%(view_count)s"` — the same tool the
crawler already uses — run locally on 2026-08-19. Titles, durations, and view counts are
real and current as of that date; view counts will drift over time but don't need
re-verification for the seed script to work correctly.

### Coding / tech — freeCodeCamp.org

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

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster) | `dQw4w9WgXcQ` | 3:33 | 1,805,594,426 |
| PSY - GANGNAM STYLE(강남스타일) M/V | `9bZkp7q19f0` | 4:12 | 6,032,168,341 |
| Baby Shark Dance \| Most Viewed Video \| PINKFONG | `XqZsoesa55w` | *tbd* | *tbd* |

Baby Shark's duration/views weren't obtainable locally — this machine's `yt-dlp` install has
no JS runtime available (a warning it prints on every run), which it needs to decipher some
videos' signatures, and it misreported this video as unavailable. A web search independently
confirmed the ID is still correct and the video is live (it's even mirrored on the Internet
Archive). Before the seed script is written, re-run the same `yt-dlp` lookup on a machine
with a JS runtime installed (or use the YouTube Data API v3, which the crawler already
supports via `--api-key`) to fill in the two `tbd` values — this is a data lookup, not a
design decision, and shouldn't block plan-writing otherwise.

### Education / explainer — Kurzgesagt + TED

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| The Egg - A Short Story (Kurzgesagt) | `h6fcK_fRYaI` | 8:06 | 36,078,996 |
| The Fermi Paradox — Where Are All The Aliens? (1/2) (Kurzgesagt) | `sNhhvQGsMEc` | 6:20 | 35,291,620 |
| The Fermi Paradox II — Solutions and Ideas (Kurzgesagt) | `1fQkVqno-uI` | 6:17 | 17,192,728 |
| Do schools kill creativity? \| Sir Ken Robinson \| TED | `iG9CE55wbtY` | 20:03 | 24,913,231 |

### Science / nature — NASA + National Geographic

| Video Title | Video ID | Duration | Views |
|---|---|---|---|
| Perseverance Rover's Descent and Touchdown on Mars (Official NASA Video) | `4czjS9h4Fpg` | 3:25 | 17,916,318 |
| NASA's Perseverance Rover's First 360 View of Mars (Official) | `wE-aQO9XD1g` | 1:00 | 7,147,132 |
| Historic Apollo 11 Moon Landing Footage (NASA) | `FlpstXNjImY` | 29:06 | 2,586,458 |
| Great White Sharks \| National Geographic | `l24FBVeu3Z4` | 2:29 | 78,436 |

### DIY / other lifestyle — Steve Ramsey / Woodworking for Mere Mortals

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

The seed script should store this list as editable data (e.g. a list of dicts) rather than
inlining values across scattered function calls, so any individual entry that later breaks
(video removed/privated) is a one-line swap.

## Testing

The seed script isn't new `webapp/db.py`/`routes.py` surface — it only calls existing,
already-tested public functions — so it isn't bound by the "test alongside new server code"
rule in `CLAUDE.md`. It still needs its own test: run the script against a temp output path
and assert the expected row counts (videos, channels, tags, watch-later entries, favorites,
hidden videos) to catch regressions if the seed data or the functions it calls change shape.

## Out of scope

- **Sample Firefox-bookmarks-export file** (the "B" path from the original brainstorm) — a
  small JSON/HTML export demonstrating the real ingestion pipeline. Deliberately not part of
  this spec: it's a secondary, optional path, and mostly overlaps with the existing
  `sample_bookmarks.json` crawler test fixture. Worth its own smaller follow-up spec.
- **`.devcontainer`/Docker setup** for a one-click "open in Codespaces" experience — a bigger
  swing, likely out of scope unless low-friction-for-strangers becomes a priority beyond this
  repo's owner and future self.
