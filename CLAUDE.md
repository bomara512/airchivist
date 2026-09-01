# Airchivist — Claude Code Instructions

## Living architecture docs stay in the project root

`plan-webapp.md`, `plan-crawler.md`, and `plan-extension.md` are living
architecture references, not historical plans — they describe the
*current* state of each subsystem and get updated in place as the code
changes (see "Always update the plans" below). They stay in the project
root, versioned with the code, not in `~/.claude/`.

One-time, feature-specific design/implementation work does not go here —
it follows the superpowers brainstorming → spec → plan flow (see "Invoke
superpowers skills before implementing" below), landing in
`docs/superpowers/specs/` and `docs/superpowers/plans/` as dated
documents. Older feature-specific `plan-*.md` files that predated this
convention were relocated there on 2026-08-18 for consistency (e.g.
`docs/superpowers/specs/2026-06-14-rediscover-shelf-design.md`).

## Always update the plans

Whenever you make an implementation change, update `plan-webapp.md` and/or
`plan-crawler.md` in the same response — without being asked.

- Reflect current behavior, not just the delta. Edit or remove outdated
  content rather than appending corrections.
- Document explicit decisions *not* to implement something when the reasoning
  is non-obvious (e.g. scroll behavior on filter changes vs. pagination).
- Implementation details (specific HTML attributes, CSS values) don't need to
  be recorded unless they represent a non-obvious design choice.

## Check TODO.md after every implementation change

After making a code change, read `TODO.md` and:

1. **Mark completed items** — if the change implements or closes something on the list, strike it through.
2. **Suggest related items** — if the change touches an area where nearby TODO items could be tackled with little extra effort, mention them briefly at the end of the response. Don't implement them unbidden; just surface them.

## When a miss is identified, sweep and codify it

Whenever a bug, inconsistency, or anti-pattern is found — whether by the user
or during a review — before closing it out:

1. **Sweep the entire codebase** for other instances of the same miss and fix
   them all in the same response.
2. **Add an instruction to this file** so the pattern is prevented going
   forward, not just patched this once.

Do not fix the one instance and move on. The miss is evidence that the pattern
exists elsewhere and that there is no rule preventing recurrence.

## Remove debug logging before finishing

Any `console.log`, `print`, or other debug statement added during investigation
must be removed before the response ends — without being asked.

- Search for `console.log('[VT]`, `print(`, `logger.debug` etc. before committing.
- Exception: logging that is part of the intended production behavior (e.g. a
  startup message or an explicit error handler) may stay.

## Never use `rowid` with `sqlite3.Row` — use the named primary key

When updating a row fetched with `sqlite3.Row`, always select and reference
the table's named `id` column (or whichever `INTEGER PRIMARY KEY` column
exists), never `rowid`. The `rowid` pseudo-column is not accessible by name
via `sqlite3.Row` key lookup and raises `IndexError` at runtime.

```python
# Wrong
row = conn.execute("SELECT rowid, ... FROM t ...").fetchone()
conn.execute("UPDATE t ... WHERE rowid = ?", (row["rowid"],))

# Right
row = conn.execute("SELECT id, ... FROM t ...").fetchone()
conn.execute("UPDATE t ... WHERE id = ?", (row["id"],))
```

## Always open `Datastore`/`sqlite3` connections with `with` in tests

Every test that constructs `crawler.datastore.Datastore(...)` or calls
`sqlite3.connect(...)` must use it as a context manager (`with Datastore(...)
as ds:`) or otherwise guarantee `.close()` runs — never `ds = Datastore(...)`
left to the garbage collector.

- An unclosed connection doesn't fail the test — it leaks and surfaces later
  as a `ResourceWarning: unclosed database` attributed to whatever unrelated
  test happens to be running when Python's GC finalizes it, which is
  confusing to debug. This bit `tests/crawler/test_datastore.py`'s
  `TestHasFullChannelRecord` on 2026-08-31: 5 tests skipped the `with`
  pattern used by every other test in the file, producing 5 warnings
  attributed to an unrelated crawler integration test.
- Run `python -m pytest -q` and confirm the warnings summary is empty before
  finishing any response that adds a new `Datastore`/`sqlite3.connect` call
  in tests.

## Name CSS classes for their purpose, not their first use

When a CSS class is introduced for one page and then reused on another,
rename it to reflect the shared purpose before the second use lands.

- A class named after a specific feature (`.watch-later-header`, `.shelf-card`)
  is a signal that the abstraction hasn't been named yet — not that it belongs
  to that feature.
- If you find yourself writing `class="watch-later-X"` on a non-watch-later
  page, stop and rename it to something generic (e.g. `.page-header`) in the
  same response.
- The same rule applies to JS handlers, template partials, and route names.

## Remove old approaches when replacing them

When pivoting an implementation (different algorithm, different UI pattern,
different data structure), delete the old code in the same response.

- Do not leave unused functions, dead CSS, orphaned constants, or commented-out
  blocks alongside the new approach.
- If the old code might be needed for reference, that belongs in git history,
  not in the working tree.

## Use `_CORS_HEADERS` for all API routes

Every route in `webapp/routes.py` that returns a JSON response to the extension
must use the module-level `_CORS_HEADERS` constant — never a locally-defined
dict.

- Apply it to both the success response and the OPTIONS preflight.
- When adding a new API route, copy the OPTIONS + CORS pattern from an existing
  route such as `api_status`.

## Always write tests alongside new server code

Whenever you add or change a public function in `webapp/db.py` or a route in
`webapp/routes.py`, write or update tests for it in the same response — without
being asked.

- New DB function → test in `tests/webapp/test_db.py`
- New route → test in `tests/webapp/test_routes.py`
- Tests must cover the happy path, at least one error/edge case, and (for API
  routes) the CORS header and OPTIONS preflight.
- Run `python -m pytest -q` at the end and confirm all tests pass before
  finishing the response.

## Keep README setup/test instructions runnable from a clean checkout

`pip install -e .` only pulls runtime deps from `pyproject.toml`, and
`npm test` needs `npm install` first — neither installs pytest, pytest-cov,
pytest-mock, or Jest. This bit a fresh checkout on 2026-08-31: the README's
"Running tests" section ran straight to `python -m pytest -q` / `npm test`
with no install step, so a truly clean clone failed with "No module named
pytest" — the person catching it happened to have pytest on their machine
some other way, and every prior editor of the README did too.

- Whenever you add or change what `README.md` tells someone to run
  (setup, demo, tests, ingest, etc.), verify it in a clean environment —
  a fresh venv and/or `rm -rf node_modules` — not just in your existing
  dev environment, which already has stray tooling installed.
- If a command depends on a file the Setup section doesn't install
  (`requirements-dev.txt`, `package.json` devDependencies, an optional
  extras group), the README step for that command must say so explicitly.

## Check for cross-list conflicts when editing `scripts/seed_demo_db.py`

The hardcoded ID lists (`FAVORITE_VIDEO_IDS`, `WATCH_LATER_VIDEO_IDS`,
`HIDDEN_VIDEO_IDS`, `WATCHED_VIDEO_IDS`) aren't independent: `hide_video()`
deletes the video from `watch_later` as real production behavior (hidden
videos shouldn't stay queued). Adding an ID to `HIDDEN_VIDEO_IDS` that's
already in `WATCH_LATER_VIDEO_IDS` silently drops it from the watch-later
demo state — this happened on 2026-08-24 and broke
`tests/scripts/test_seed_demo_db.py`'s watch-later and hidden-count
assertions until caught here on 2026-08-31.

- Before adding an ID to one of these lists, check it isn't already in a
  list whose seeding function has a side effect on another list (mainly:
  don't hide anything that's meant to stay in watch-later).
- Run `python -m pytest tests/scripts/test_seed_demo_db.py -q` after
  editing any of these lists, in the same response.

## Keep the feature sheet current

`docs/feature-sheet.html` is a plain-language, functionality-focused
summary of everything Airchivist does — for a non-technical read of the
product, not an implementation reference.

- Whenever a change ships a new user-facing feature, update the relevant
  section of `docs/feature-sheet.html` in the same response — move the item
  out of "On the roadmap" into its feature area, or add a new bullet/section
  if it doesn't fit an existing one.
- Whenever a change removes or fundamentally alters user-facing behavior,
  edit or remove the corresponding line rather than leaving it stale.
- Keep the stat line (`N areas cataloged · N features shipped · N queued`)
  accurate to the actual counts after your edit.
- Describe what the feature *does*, not how it's implemented — no route
  names, file paths, or code identifiers, matching the rest of the page.
- This is a local HTML file, not a published Artifact — edit it in place
  with the Edit tool like any other file; it doesn't need re-publishing.

## Don't put real personal-library content in commit messages or docs

This repo's git history once revealed personal information through routine
work (tag-distillation session logs, categorization commit messages) —
none of it was in the app's data files, all of it was in the *prose
describing the work*. Discovered 2026-08-17; full history rewritten to
fix it.

- When a commit, `CHANGELOG.md` entry, or design doc needs a concrete
  example (a tag name, a category, a merge decision), use a generic or
  invented example — never the actual real tag/category/artist name from
  whatever real data was being worked on at the time, even if it feels
  like harmless technical detail in the moment.
- This is easy to miss because each individual mention feels
  inconsequential ("just a tag name") — the risk is cumulative: many small
  real mentions across a project's history compose into a detailed real
  personal profile.
- **When fixing a leak like this, never describe the fix by re-stating the
  leaked content** — a commit message like "redacted references to X" is
  just a new leak of X. Describe the mechanism instead ("redacted
  personal-content examples from N changelog entries"), never the specific
  content that was removed.

## Write US English, not British English

This project uses American spelling throughout — code identifiers, UI
copy, comments, and docs. Write "favorite," "color," "behavior,"
"organize," "catalog," "gray," etc., never their British equivalents
("favourite," "colour," "behaviour," "organise," "catalogue," "grey").

- This applies to everything: DB columns, function/route names, CSS
  classes, template strings, JS, and prose in `CLAUDE.md`, `TODO.md`,
  `plan-*.md`, and `docs/feature-sheet.html`.
- Exception: `CHANGELOG.md` and everything under `docs/superpowers/`
  (specs and plans) are historical records. A past entry that used
  British spelling when it was written stays as-is — do not "fix" old
  entries. Only new entries going forward need to follow this rule.
- Exception: don't touch spec-mandated identifiers that happen to
  contain a double-L or similar pattern that looks British but isn't
  (e.g. `aria-labelledby` is the correct HTML/ARIA attribute name in
  every dialect — never "fix" it).

## Keep test-lifecycle state in shared hooks, not inline

Fake timers, global stubs, and polyfills a test depends on must be set up
and torn down in a shared `beforeEach`/`afterEach` (or a shared setup file),
never inline inside a single test body.

- Inline setup/teardown (e.g. `jest.useFakeTimers()` at the top of a test,
  `jest.useRealTimers()` at the bottom) is skipped if an assertion in
  between throws, leaking that state into every later test in the file.
- This bit the extension's Jest suite: one test's inline
  `jest.useFakeTimers()`/`jest.useRealTimers()` pair, combined with a
  `setImmediate` polyfill scoped to that same test file instead of the
  shared setup file, caused leaked real timers and a "Jest did not exit"
  warning on every `npm test` run.
- When adding a helper that depends on environment specifics (e.g. a
  polyfill), put it next to the function that needs it — in the shared
  setup file, not next to its first caller — so the next test file to use
  that function doesn't have to rediscover and duplicate the fix.

## Always update the changelog

Whenever you make an implementation change, append an entry to `CHANGELOG.md`
in the same response — without being asked.

- Use today's date. Include time only if multiple entries fall on the same day
  and the order matters.
- For each entry: what changed, and at least one implication (pro or con).
- Be honest about trade-offs — note downsides even when the decision was correct.

## Invoke superpowers skills before implementing

Before writing any implementation code in this project, invoke the relevant
`superpowers` skill via the Skill tool — do not go straight from the request
to editing files.

- New feature, component, or behavior change → `superpowers:brainstorming`
  first to pin down scope/design, then `superpowers:test-driven-development`
  while implementing (failing test before the code that makes it pass).
- Bug, test failure, or unexpected behavior → `superpowers:systematic-debugging`
  before proposing a fix.
- Multi-step task that needs a written plan → `superpowers:writing-plans`, then
  `superpowers:executing-plans` or `superpowers:subagent-driven-development`.
- Wrapping up a branch → `superpowers:requesting-code-review` before declaring
  done.
- Only skip this when the user explicitly asks for a quick/direct change
  (e.g. "just do X, skip the process") or the task is too small to have a
  failing-test step (pure docs/config/changelog edits).
