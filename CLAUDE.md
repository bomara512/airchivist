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
