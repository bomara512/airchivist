# ViewTube

This is my playground for getting better at AI-assisted development — practicing prompt engineering, learning Claude Code's skill/plugin ecosystem
well, and building real instincts for working with an AI pair-programmer on a long-lived,
real codebase.

The vehicle for that practice is **ViewTube**, a personal video bookmark manager that scratches a long-running itch for me. I have a decade-plus of
YouTube bookmarks that pretty much became invisible the moment they were saved. ViewTube ingests, tags,
and actively resurfaces what I've forgotten about. (YouTube probably does the same thing with an account :-), 
but that's not how I've used it over the years. Just bookmarked interesting videos.)

The [original prompt](prompt.md) that kicked this off spells things out by hand — "use a
test-driven approach, write the test first, make sure it fails, then implement," "create a
separate plan for each component." Now that kind of process guidance lives in reusable skills (e.g.
[superpowers](https://github.com/obra/superpowers), a Claude Code plugin) — TDD, structured planning, and code review are things I invoke, not things I re-explain. Expect the commit
history and docs to reflect that ongoing learning process.

## Features

- Searchable, filterable video library (channel, tag, favorites, watch status, duration, date)
- Tagging with tag groups, aliases, and optional AI-assisted suggestions
- Watch Later queue with drag-to-reorder
- Rediscover shelf — resurfaces videos you've forgotten about
- Channel tracking, separate from individual videos
- Firefox extension for one-click saving and status badges on YouTube itself

## Prerequisites

- Python 3.12+
- A Firefox bookmarks export (JSON or HTML) containing YouTube links — export via
  Firefox's Bookmarks Manager (`Ctrl+Shift+O` / `Cmd+Shift+O`) → *Import and Backup* →
  *Backup...* (JSON) or *Export Bookmarks to HTML...*
- (Optional) Node.js, only needed for the browser extension's test suite

## Setup

```bash
git clone https://github.com/bomara512/viewtube.git
cd viewtube
pip install -e .
```

## Try it with sample data

Want to see it running before pointing it at your own bookmarks? This seeds a database with
~50 real, public YouTube videos across a mix of topics (coding tutorials, cooking, guitar
lessons, science explainers, and more) — real titles/thumbnails/view counts, but the
favorites/watch-later/tags/watch-history are all fabricated demo data, not anyone's real
activity.

```bash
./demo.sh
```

Open http://localhost:8080. To reset back to a clean demo state:

```bash
python scripts/seed_demo_db.py --output demo.db --force
```

## Ingest your bookmarks

```bash
viewtube-crawler -i path/to/bookmarks.json -o viewtube.db
```

This fetches metadata (title, description, view count, duration, thumbnail, channel) for
every YouTube video and channel link found, via `yt-dlp`. It's polite by default (a delay
between requests) and safe to re-run — already-fetched videos are skipped unless you pass
`--force-refresh`. Run `viewtube-crawler --help` for all options, including `--api-key` to
use the YouTube Data API v3 for faster batch fetching instead.

## Run the app

```bash
viewtube-web --db viewtube.db --port 8080
```

Open http://localhost:8080. The database schema (tags, watch-later, favorites, etc.) is
created and migrated automatically on first run.

## Browser extension (optional)

1. In Firefox, go to `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on...** and select `extension/manifest.json`
3. That's it — the extension defaults to `http://localhost:8080`, so it works out of the box
   if you ran the webapp on the default port above. No configuration needed unless you're
   using a different host/port, in which case set it via the extension's storage (see
   `extension/popup/popup.js` for the `viewtubeUrl` key).

## Optional: AI-assisted tag suggestions

Set an Anthropic API key before starting the webapp to enable LLM-suggested tags on the
Tags page:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Without it, tagging still works fully — just manually rather than with suggestions.

## Running tests

```bash
python -m pytest -q   # backend (Python)
npm test               # extension (Jest) — requires Node.js
```
