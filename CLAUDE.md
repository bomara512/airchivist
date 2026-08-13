# ViewTube — Claude Code Instructions

## Store plans in the project root

All project plans are stored as `plan-*.md` files in the repository root, not in `~/.claude/`. Plans are versioned with the code and shared across sessions. Examples: `plan-webapp.md`, `plan-crawler.md`, `plan-rediscover-shelf.md`.

When creating a new plan, ask the user first. Store it in the project root and commit it to git.

## Always update the plans

Whenever you make an implementation change, update `plan-webapp.md` and/or
`plan-crawler.md` in the same response — without being asked.

- Reflect current behaviour, not just the delta. Edit or remove outdated
  content rather than appending corrections.
- Document explicit decisions *not* to implement something when the reasoning
  is non-obvious (e.g. scroll behaviour on filter changes vs. pagination).
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
- Exception: logging that is part of the intended production behaviour (e.g. a
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

## Keep the feature sheet current

`docs/feature-sheet.html` is a plain-language, functionality-focused
summary of everything ViewTube does — for a non-technical read of the
product, not an implementation reference.

- Whenever a change ships a new user-facing feature, update the relevant
  section of `docs/feature-sheet.html` in the same response — move the item
  out of "On the roadmap" into its feature area, or add a new bullet/section
  if it doesn't fit an existing one.
- Whenever a change removes or fundamentally alters user-facing behavior,
  edit or remove the corresponding line rather than leaving it stale.
- Keep the stat line (`N areas catalogued · N features shipped · N queued`)
  accurate to the actual counts after your edit.
- Describe what the feature *does*, not how it's implemented — no route
  names, file paths, or code identifiers, matching the rest of the page.
- This is a local HTML file, not a published Artifact — edit it in place
  with the Edit tool like any other file; it doesn't need re-publishing.

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

- New feature, component, or behaviour change → `superpowers:brainstorming`
  first to pin down scope/design, then `superpowers:test-driven-development`
  while implementing (failing test before the code that makes it pass).
- Bug, test failure, or unexpected behaviour → `superpowers:systematic-debugging`
  before proposing a fix.
- Multi-step task that needs a written plan → `superpowers:writing-plans`, then
  `superpowers:executing-plans` or `superpowers:subagent-driven-development`.
- Wrapping up a branch → `superpowers:requesting-code-review` before declaring
  done.
- Only skip this when the user explicitly asks for a quick/direct change
  (e.g. "just do X, skip the process") or the task is too small to have a
  failing-test step (pure docs/config/changelog edits).
