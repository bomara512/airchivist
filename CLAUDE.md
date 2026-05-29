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

## Always update the changelog

Whenever you make an implementation change, append an entry to `CHANGELOG.md`
in the same response — without being asked.

- Use today's date. Include time only if multiple entries fall on the same day
  and the order matters.
- For each entry: what changed, and at least one implication (pro or con).
- Be honest about trade-offs — note downsides even when the decision was correct.
