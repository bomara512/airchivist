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
