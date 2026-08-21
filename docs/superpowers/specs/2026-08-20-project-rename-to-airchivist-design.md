# Project rename: ViewTube → Airchivist

## Context

ViewTube's README already frames the project as two things at once: a
personal YouTube-bookmark rediscovery tool, and a practice ground for
AI-assisted development. The name "ViewTube" only reflects the first half.
This spec renames the project to **Airchivist** — a pun on "AI" +
"archivist" that keeps both halves legible (it archives/tags/resurfaces a
video library, and the "AI" is baked into the name itself), chosen after a
uniqueness pass against GitHub (see below) over two other finalists,
"Rerun" and "Vibrary".

**Display name:** `Airchivist` (title case, not `AIrchivist`) in all prose,
UI text, and doc headers.
**Package/CLI name:** `airchivist` (lowercase, no separator needed since
there's no hyphen/underscore in the word).

### Why not the other finalists

- **Rerun** — strong wordplay (TV rerun = rediscovered video; code rerun =
  practicing with an AI pair-programmer) but collides with `rerun-io/rerun`,
  a real, actively-maintained, funded company in the dev-tools space with
  the bare `github.com/rerun` org already registered.
- **Vibrary** — "vibe" + "library"; at least 9 distinct GitHub repos already
  use the exact name `vibrary` (including one literally described as "an
  interactive video library"), plus a published mobile app with 250k+
  downloads. The `Vibrary` GitHub username is also taken.
- **Airchivist** — only two loosely-related hits (an unrelated LLM-labelling
  experiment, and an unrelated compound name), and the bare `AIrchivist`
  GitHub org, while technically registered, is dormant (0 repos, 0
  followers, abandoned since Dec 2024) and doesn't block this project's own
  repo name.

## Scope

### Package / CLI identity

- `pyproject.toml`: `[project] name = "viewtube"` → `"airchivist"`;
  `[project.scripts]` entries `viewtube-crawler` → `airchivist-crawler`,
  `viewtube-web` → `airchivist-web`
- `package.json`: `"name": "viewtube-extension-tests"` →
  `"airchivist-extension-tests"` (`package-lock.json` regenerates its name
  field via `npm install`, not hand-edited)
- `.gitignore`: `viewtube.db` → `airchivist.db`, `viewtube*.db*` →
  `airchivist*.db*`. `demo.db` is unchanged — that filename was never
  brand-specific.

### Python CLI / scripts

- `webapp/cli.py`: argparse description `"ViewTube web server"` →
  `"Airchivist web server"`
- `crawler/cli.py`: argparse description `"ViewTube Bookmark Crawler"` →
  `"Airchivist Bookmark Crawler"`
- `scripts/seed_demo_db.py`: docstring and argparse description mentions
- `tools/tag_categorizer.py`: docstring, `DEFAULT_DB = "viewtube-test.db"`
  → `"airchivist-test.db"`, and the `cp viewtube.db …` example in the
  help/error text → `cp airchivist.db airchivist-test.db`
- `demo.sh`: `"Starting ViewTube demo…"` message, and the
  `exec viewtube-web …` call → `exec airchivist-web …` (must track the
  renamed console-script entry point)

### Browser extension

- `extension/manifest.json`: `name`, `description`, `default_title`
- `extension/background.js`: `URL_KEY = 'viewtubeUrl'` →
  `'airchivistUrl'`; `getViewtubeUrl()` → `getAirchivistUrl()` (and its
  call sites)
- `extension/content/content.js`: comment text only (`/* ViewTube
  unreachable */` → `/* Airchivist unreachable */`)
- `extension/popup/popup.js`: `URL_KEY` (as above), `FOLDER_NAME =
  'ViewTube'` → `'Airchivist'`, all internal identifiers named after the
  old brand (`viewtubeUrl`, `viewtubeOk`, etc. → `airchivistUrl`,
  `airchivistOk`, …), and all user-facing strings (`"Added to ViewTube"`,
  `"ViewTube unreachable"`, button labels, etc.)
- `tests/extension/popup.test.js`: local variable names and string
  assertions updated to match

**Known trade-offs from these two identifier renames** (both accepted,
not deferred, per your decisions):
- Renaming `URL_KEY` orphans the currently-stored server URL in any
  already-installed copy of the extension — it'll fall back to
  `DEFAULT_URL` (`http://localhost:8080`) after updating. No migration
  shim is being added (single local user, trivial one-time re-entry if
  the value differs from the default).
- Renaming `FOLDER_NAME` doesn't rename your real, existing Firefox
  bookmarks folder (no Firefox automation access from this tool). Your
  current install keeps working unaffected (it uses a cached folder ID,
  not the name, once found). If you want the actual Firefox folder title
  to match, that's a manual rename in Firefox's bookmark manager — not
  part of this implementation, called out here as a follow-up you can do
  whenever you like.

### Webapp templates

Nav brand text, page `<title>`s, and the install-page bookmarklet copy
across: `base.html`, `_video_card.html`, `channels.html`, `hidden.html`,
`index.html`, `install.html`, `tag_detail.html`, `tags.html`,
`watch-later.html`.

### Living docs

Full-text rename (all occurrences) in: `CLAUDE.md`, `README.md`,
`TODO.md`, `MAINTENANCE.md`, `plan-webapp.md`, `plan-crawler.md`,
`plan-extension.md`, `plan-production.md`,
`brainstorm-multi-type-bookmarks.md`, `docs/feature-sheet.html`.

`CHANGELOG.md`: only the top `# ViewTube Changelog` title line changes.

### Explicitly out of scope

- Every dated file under `docs/superpowers/specs/` and
  `docs/superpowers/plans/` — these are historical, point-in-time
  records (same convention CLAUDE.md already establishes for old
  British-spelling changelog entries: true when written, not rewritten
  later).
- `CHANGELOG.md` body entries — all existing entries stay exactly as
  written.
- `.claude/settings.local.json` — gitignored, machine-local permission
  cache, not part of the product.
- Local `.db` files themselves aren't source-controlled (all
  `.gitignore`d); renaming `viewtube.db`/`viewtube-test.db` to match the
  new `tools/tag_categorizer.py` default is a mechanical local step, not
  a repo change — folded into execution, not a design decision.

## Sequencing

1. All code/docs edits above, on the current repo/directory, in one
   branch.
2. Verify: `python -m pytest -q`, `npm test` (extension), `--help` smoke
   test on the (not-yet-installed-under-new-name) CLI once reinstalled,
   and a manual browser check of the running webapp for the renamed nav
   brand / page titles / install page.
3. Reinstall locally: `pip install -e .` (regenerates
   `airchivist-web`/`airchivist-crawler` console scripts; old
   `viewtube-*` scripts become stale but harmless, gitignored `.venv`).
   Optionally `npm install` to refresh `package-lock.json`'s name field.
4. Commit and push under the current repo name/URL.
5. Rename the GitHub repo (`bomara512/viewtube` →
   `bomara512/airchivist`) — confirmed as its own explicit step
   immediately before doing it, since it changes a public URL (GitHub
   auto-redirects the old URL going forward).
6. Update the local `origin` remote URL to the new canonical one.
7. Rename the local clone directory
   (`/Users/bomara/workspace/dev/viewtube` →
   `/Users/bomara/workspace/dev/airchivist`) last, then re-anchor this
   session to the new path.

## Testing

- `python -m pytest -q` — full existing suite must stay green; no new
  behavior is being added, so no new tests are required by this change
  itself (a pure rename), but any test that currently asserts literal
  `"ViewTube"` text (e.g. extension popup tests, and any webapp route
  tests that assert on rendered brand text, if such assertions exist)
  must be updated to assert `"Airchivist"` instead, in the same
  response, so the suite reflects the new reality rather than just
  happening to still pass.
- `npm test` — extension Jest suite green under the renamed identifiers.
- Manual: reinstall, run `airchivist-web --help` and
  `airchivist-crawler --help`, confirm they resolve and print the new
  descriptions; run `./demo.sh` and check the browser for the renamed
  nav/title/install-page text.
