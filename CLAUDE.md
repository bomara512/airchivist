# ViewTube — Claude Code Instructions

## Always update the plans

Whenever you make an implementation change, update `plan-webapp.md` and/or
`plan-crawler.md` in the same response — without being asked.

- Reflect current behaviour, not just the delta. Edit or remove outdated
  content rather than appending corrections.
- Document explicit decisions *not* to implement something when the reasoning
  is non-obvious (e.g. scroll behaviour on filter changes vs. pagination).
- Implementation details (specific HTML attributes, CSS values) don't need to
  be recorded unless they represent a non-obvious design choice.

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

## Always update the changelog

Whenever you make an implementation change, append an entry to `CHANGELOG.md`
in the same response — without being asked.

- Use today's date. Include time only if multiple entries fall on the same day
  and the order matters.
- For each entry: what changed, and at least one implication (pro or con).
- Be honest about trade-offs — note downsides even when the decision was correct.
