# Brainstorm: Extending ViewTube to All Bookmark Types

**Status:** Raw ideas, not yet scoped into a spec/plan. Continue here later.

## Premise

ViewTube's discovery/rediscovery machinery (tags, favorites, watch-later, rediscover shelf,
archive) is mostly content-type-agnostic already — it operates on engagement metadata, not
video-specific fields. The blocker to handling all bookmark types (articles, repos, tweets,
tools, PDFs, etc.) — not just YouTube — is that the schema, crawler, and card UI are
hardcoded to YouTube.

Goal: same discovery/rediscovery UX, applied to hundreds of forgotten, filed-away bookmarks
of any type.

## Ideas

### 1. Generalize `videos` into a type-discriminated `bookmarks` table
Universal columns (url, title, description, source_domain, thumbnail_url, date_added,
personal_view_count, is_favorite, is_hidden) plus a `content_type` enum (video/article/repo/
tweet/etc.) and a `type_metadata` JSON blob for type-specific extras (video: duration/views/
channel; repo: stars/language; article: author/word_count). **Foundational** — most other
ideas below depend on this shape existing first.

### 2. Pluggable fetcher registry, generalizing the existing yt-dlp pattern
The crawler already does "recognize a YouTube URL → fetch via yt-dlp." Turn that into a
registry of fetchers keyed by URL pattern: a GitHub fetcher (repo API), an article fetcher
(Open Graph tags / readability-style extraction), and a generic fallback that just grabs
`<title>` + OG image + favicon for anything unrecognized. Same shape as how channel detection
already coexists with video detection today.

### 3. Bulk-backfill everything the crawler currently drops
Probably the highest-leverage, lowest-effort first step. The crawler already parses the full
Firefox bookmarks export but filters down to just YouTube URLs. Generalizing the schema
unlocks a one-time re-run that ingests *everything* already sitting there — directly serves
"hundreds of bookmarks I've filed away and forgotten" without waiting on new saves.

### 4. Generalize `_video_card.html` into a shared card with type-aware chrome
Same tag pills, same ★ button, same hide/watch-later actions — but the thumbnail area swaps
to a favicon+domain treatment when there's no video thumbnail, and the duration badge becomes
a "5 min read" or "★ 2.3k stars" badge depending on type. Makes tags/rediscover/watch-later
"just work" visually across types without a redesign per type.

### 5. Extend the extension from "YouTube detector" to "any-page saver"
Right now the popup/content script only recognize YouTube URL patterns. Add a generic
fallback: unrecognized page → grab `document.title` + meta description + OG image via content
script → POST to a generic add endpoint. Probably the single biggest unlock, since most of
what people bookmark isn't YouTube — it's articles, tools, threads.

### 6. Generalize "watched" to "consumed," with type-aware copy
One boolean under the hood (so rediscover-shelf/watch-later logic doesn't fork per type), but
the UI says "Read" for articles, "Reviewed" for repos, "Watched" for video — otherwise the
whole watched/rediscover pipeline already works unchanged.

### 7. Source domain as a filter axis, parallel to "channel"
Reuse the existing channel-listing-page pattern (`/channels`) as a `/sources` view — same
organizational role for general bookmarks that "channel" plays for video.

### 8. Per-type rediscover weighting
Different content types have different "shelf life." An article might feel stale after a
month; a bookmarked tool you meant to try later doesn't decay the same way. Could let each
type define its own rediscover-eligibility window/weighting instead of one global
"least-recently-viewed" pool.

## Next step (when resumed)

Idea #1 (schema shape) is the one to nail down first — #3-6 all depend on it. Run through
`superpowers:brainstorming` properly for that piece before writing a spec/plan.
