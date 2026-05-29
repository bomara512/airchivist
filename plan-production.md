# ViewTube — Productionalization Plan

## Current State

Single-user, locally-run app. Flask dev server, SQLite file on disk, no auth, no background jobs. All assumptions below are relative to this baseline.

---

## Hosting

| Concern | Current | Production path |
|---|---|---|
| WSGI server | Flask dev server | `gunicorn` with multiple workers |
| Reverse proxy | None | nginx in front of gunicorn (TLS termination, static files) |
| Container | None | Docker image; `viewtube-web` and `viewtube-crawler` as separate services |
| Platform | Local | Any VPS (Hetzner, Fly.io, Render) or self-hosted home server |
| Static files | Flask serves them | nginx or a CDN; add cache headers |

The app is small enough that a single $5–10/month VPS handles it comfortably.

---

## Database

SQLite is fine for a single user or a small private group (reads scale well, writes are infrequent). It becomes a bottleneck if:
- Multiple users are writing concurrently (bookmarklet hits + crawler running simultaneously)
- The video library grows past ~100k rows (unlikely for personal use)

If migration is needed, PostgreSQL is the natural target. The query layer (`webapp/db.py`) uses raw SQL with `?` placeholders — switching to `%s` and a `psycopg2` connection is the main mechanical change.

**Decision**: Keep SQLite unless write contention becomes measurable. WAL mode (`PRAGMA journal_mode=WAL`) removes most single-node contention issues.

---

## Multi-User Support

The current data model has no concept of a user — bookmarks, view counts, and tags are global. Supporting multiple users requires deciding on a model:

### Option A: Shared library, per-user personal data
All users see the same video library. `personal_view_count`, `date_last_viewed`, ratings, and tags are per-user.

Schema changes:
- Add `users` table
- `personal_view_count` and `date_last_viewed` move to a `user_video_stats(user_id, video_id, ...)` table
- `video_tags` and `tags` get a `user_id` column (or a separate `user_tags` table)

This is the most natural fit for a shared household or small group.

### Option B: Fully isolated per-user libraries
Each user has their own bookmark set. Simplest to reason about; each user effectively has their own SQLite file. Harder to share discovery.

### Authentication
- For a private/home deployment: HTTP Basic Auth via nginx is the least-friction option (no code changes to the app)
- For proper multi-user: Flask-Login + a `users` table with hashed passwords; session cookies
- OAuth (Google) is overkill unless the app is public-facing

---

## Bookmarklet / API Security

`POST /api/add` currently accepts requests from any origin with no authentication. In production:
- Add an API key header (`X-ViewTube-Key`) checked server-side
- The bookmarklet includes the key in the `fetch` headers
- Key is a random token stored in the app config, not committed to source

---

## Background Jobs (Metadata Fetching)

Currently `POST /api/add` blocks the HTTP request while yt-dlp fetches metadata (~2–3 seconds). For a single user this is acceptable. At scale or with unreliable network:

- Add a job queue (Redis + RQ, or just a `pending` table polled by a worker)
- `POST /api/add` inserts a `fetch_status='pending'` row immediately and returns
- A worker process picks up pending rows and fetches metadata
- The bookmarklet toast would need a polling step or WebSocket to show the final title

This also applies to the crawler: instead of a CLI batch job, it could run as a persistent worker.

---

## Crawler Changes

- The crawler currently reads a bookmark file; in a multi-user hosted setup it would receive URLs via the API instead
- Rate limiting: yt-dlp requests should be throttled (current 1.5s delay is per-video; fine for batch, acceptable for bookmarklet one-offs)
- Retry logic for transient errors (currently just marks as `error`)
- The `delay=0` used by the bookmarklet should become `delay=0` only if the job queue absorbs concurrency; otherwise keep the default

---

## Configuration

Move from hardcoded values to environment variables / a config file:

| Value | Current | Production |
|---|---|---|
| `db_path` | CLI arg | `DATABASE_URL` env var |
| Port | `--port` CLI arg | `PORT` env var |
| API key | None | `VIEWTUBE_API_KEY` env var |
| Debug mode | Flask default | `FLASK_ENV=production` |

---

## What Does NOT Need to Change

- The core data model and query layer (`webapp/db.py`) — solid as-is for single-node use
- The HTMX frontend — works fine in production; no build step needed
- The bookmarklet — just update the hardcoded `localhost:8080` URL to the production hostname
- The crawler logic — sound, just needs to be invokable as a service rather than a CLI batch job
