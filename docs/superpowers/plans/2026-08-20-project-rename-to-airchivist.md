# ViewTube → Airchivist Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Tasks 7 and 8 must NOT be dispatched to a subagent** — they change the orchestrating session's own git remote and working directory; run them directly in the main/orchestrating session. See the note at each task.

**Goal:** Rename the project from ViewTube to Airchivist across package
metadata, CLI entry points, the browser extension, webapp templates, and
living docs, then rename the GitHub repo and local clone directory to match.

**Architecture:** This is a pure rename — no behavior changes. Every task
either hand-edits a small number of high-precision lines (package/CLI
config, extension identifiers) or applies one deterministic, case-aware
find/replace across a file group, verified by an occurrence-count grep and
the existing test suite. No new code paths are introduced.

**Tech Stack:** Python (pyproject.toml/setuptools), Flask/Jinja templates,
vanilla JS browser extension (Jest), `sed`, `gh` CLI (GitHub repo rename).

**Spec:** `docs/superpowers/specs/2026-08-20-project-rename-to-airchivist-design.md`

## Global Constraints

- Display name in prose/UI/doc headers: `Airchivist` (title case). Package/CLI
  name: `airchivist` (lowercase).
- Casing rule for every text replacement in this plan (case-sensitive, applied
  in this order, each independent — no pattern is a substring of another):
  `ViewTube` → `Airchivist`, `Viewtube` → `Airchivist`, `viewtube` →
  `airchivist`, `VIEWTUBE` → `AIRCHIVIST`.
- Left alone, no exceptions: every file under `docs/superpowers/specs/` and
  `docs/superpowers/plans/` (historical, point-in-time records) except this
  plan and its own spec, which are already correctly named; the body of
  `CHANGELOG.md` (only its title line changes); `.claude/settings.local.json`
  (gitignored, machine-local).
- `extension/popup/popup.js`'s `FOLDER_NAME` constant renames to
  `'Airchivist'` (per spec decision) — this does not rename the user's real
  Firefox bookmarks folder; that's an out-of-scope manual step for the user.
- `URL_KEY` also renames (`'viewtubeUrl'` → `'airchivistUrl'`), which orphans
  any already-stored server URL in an installed copy of the extension — it
  falls back to `DEFAULT_URL`. This is an accepted trade-off per the spec;
  do not add a migration shim to preserve the old stored value.
- No new tests are required by this change (pure rename), but the one file
  with existing test coverage of literal brand text
  (`tests/extension/popup.test.js`) must be updated in lockstep with
  `popup.js`, TDD-style (test first, see it fail, then rename source).

---

### Task 1: Package and CLI identity

**Files:**
- Modify: `pyproject.toml`
- Modify: `package.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: the new CLI command names (`airchivist-web`, `airchivist-crawler`)
  that Tasks 2–5 reference in docs/scripts, and the new default DB filename
  convention (`airchivist.db`, `airchivist-test.db`) that Tasks 2 and 5
  reference.

- [ ] **Step 1: Edit `pyproject.toml`**

Change:
```toml
[project]
name = "viewtube"
```
to:
```toml
[project]
name = "airchivist"
```
Change:
```toml
[project.scripts]
viewtube-crawler = "crawler.cli:main"
viewtube-web = "webapp.cli:main"
```
to:
```toml
[project.scripts]
airchivist-crawler = "crawler.cli:main"
airchivist-web = "webapp.cli:main"
```

- [ ] **Step 2: Edit `package.json`**

Change:
```json
  "name": "viewtube-extension-tests",
```
to:
```json
  "name": "airchivist-extension-tests",
```

- [ ] **Step 3: Edit `.gitignore`**

Change:
```
viewtube.db
```
to:
```
airchivist.db
```
Change:
```
viewtube*.db*
```
to:
```
airchivist*.db*
```
(Leave `demo.db` untouched — not brand-specific.)

- [ ] **Step 4: Verify**

Run: `grep -n viewtube pyproject.toml package.json .gitignore`
Expected: no output (zero matches).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml package.json .gitignore
git commit -m "chore(rename): package/CLI identity - viewtube -> airchivist"
```

---

### Task 2: Python CLI text and scripts

**Files:**
- Modify: `webapp/cli.py`
- Modify: `crawler/cli.py`
- Modify: `scripts/seed_demo_db.py`
- Modify: `tools/tag_categorizer.py`
- Modify: `demo.sh`

**Interfaces:**
- Consumes: new CLI command names from Task 1 (`airchivist-web` in `demo.sh`'s
  `exec` line must match Task 1's `pyproject.toml` entry point exactly).
- Produces: `tools/tag_categorizer.py`'s new `DEFAULT_DB = "airchivist-test.db"`
  constant, referenced again in Task 6's local-file-rename step.

- [ ] **Step 1: Edit `webapp/cli.py`**

Change line 10:
```python
    parser = argparse.ArgumentParser(description="ViewTube web server")
```
to:
```python
    parser = argparse.ArgumentParser(description="Airchivist web server")
```

- [ ] **Step 2: Edit `crawler/cli.py`**

Change line 14:
```python
    parser = argparse.ArgumentParser(description="ViewTube Bookmark Crawler")
```
to:
```python
    parser = argparse.ArgumentParser(description="Airchivist Bookmark Crawler")
```

- [ ] **Step 3: Edit `scripts/seed_demo_db.py`**

Change line 3 (docstring):
```python
personal-engagement data, for a one-command "try it now" ViewTube demo.
```
to:
```python
personal-engagement data, for a one-command "try it now" Airchivist demo.
```
Change line 275:
```python
    parser = argparse.ArgumentParser(description="Seed a ViewTube demo database.")
```
to:
```python
    parser = argparse.ArgumentParser(description="Seed an Airchivist demo database.")
```

- [ ] **Step 4: Edit `tools/tag_categorizer.py`**

Change lines 3, 5, 6 (module docstring):
```python
ViewTube tag categorization CLI.

Default DB: viewtube-test.db (create with: cp viewtube.db viewtube-test.db)
Writing to the live DB requires explicit --db viewtube.db.
```
to:
```python
Airchivist tag categorization CLI.

Default DB: airchivist-test.db (create with: cp airchivist.db airchivist-test.db)
Writing to the live DB requires explicit --db airchivist.db.
```
Change line 29:
```python
DEFAULT_DB = "viewtube-test.db"
```
to:
```python
DEFAULT_DB = "airchivist-test.db"
```
Change line 80:
```python
            msg += f"\nCreate it with: cp viewtube.db {db_path}"
```
to:
```python
            msg += f"\nCreate it with: cp airchivist.db {db_path}"
```

- [ ] **Step 5: Edit `demo.sh`**

Change:
```bash
echo "Starting ViewTube demo at http://localhost:8080"
exec viewtube-web --db demo.db --port 8080
```
to:
```bash
echo "Starting Airchivist demo at http://localhost:8080"
exec airchivist-web --db demo.db --port 8080
```

- [ ] **Step 6: Verify**

Run: `grep -rni viewtube webapp/cli.py crawler/cli.py scripts/seed_demo_db.py tools/tag_categorizer.py demo.sh`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add webapp/cli.py crawler/cli.py scripts/seed_demo_db.py tools/tag_categorizer.py demo.sh
git commit -m "chore(rename): Python CLI/script text - viewtube -> airchivist"
```

---

### Task 3: Browser extension (TDD: test first)

**Files:**
- Modify: `tests/extension/popup.test.js`
- Modify: `extension/manifest.json`
- Modify: `extension/background.js`
- Modify: `extension/content/content.js`
- Modify: `extension/popup/popup.js`

**Interfaces:**
- Produces: `URL_KEY = 'airchivistUrl'`, `FOLDER_NAME = 'Airchivist'`,
  `getAirchivistUrl()` in `background.js`; matching identifier names
  (`airchivistUrl`, `airchivistOk`, etc.) and user-facing strings
  (`"Added to Airchivist"`, `"Airchivist unreachable"`, etc.) in `popup.js`.
  Task 6's reinstall/verification step runs `npm test` against this.

- [ ] **Step 1: Update the test file to expect the new identifiers/text**

Run this exact command (macOS `sed`; case-sensitive, each pattern
independent per the Global Constraints casing rule):

```bash
sed -i '' \
  -e 's/ViewTube/Airchivist/g' \
  -e 's/Viewtube/Airchivist/g' \
  -e 's/viewtube/airchivist/g' \
  -e 's/VIEWTUBE/AIRCHIVIST/g' \
  tests/extension/popup.test.js
```

- [ ] **Step 2: Run the extension tests to confirm they now fail against the old source**

Run: `npm test`
Expected: FAIL — `tests/extension/popup.test.js` now references
`popup.airchivistUrl`-shaped calls and `"Added to Airchivist"` text that
`extension/popup/popup.js` doesn't produce yet (it still exports/expects the
old `viewtube*` names and `"ViewTube"` strings).

- [ ] **Step 3: Rename the source files**

Run:

```bash
sed -i '' \
  -e 's/ViewTube/Airchivist/g' \
  -e 's/Viewtube/Airchivist/g' \
  -e 's/viewtube/airchivist/g' \
  -e 's/VIEWTUBE/AIRCHIVIST/g' \
  extension/manifest.json extension/background.js extension/content/content.js extension/popup/popup.js
```

- [ ] **Step 4: Run the extension tests to confirm they pass**

Run: `npm test`
Expected: PASS — all suites green.

- [ ] **Step 5: Verify no stale references remain**

Run: `grep -rni viewtube extension/manifest.json extension/background.js extension/content/content.js extension/popup/popup.js tests/extension/popup.test.js`
Expected: no output.

Also manually confirm (`grep -n "FOLDER_NAME\|URL_KEY" extension/popup/popup.js extension/background.js`) that:
- `extension/popup/popup.js` has `FOLDER_NAME = 'Airchivist'` and `URL_KEY = 'airchivistUrl'`
- `extension/background.js` has `URL_KEY = 'airchivistUrl'` and a function `getAirchivistUrl()`

- [ ] **Step 6: Commit**

```bash
git add tests/extension/popup.test.js extension/manifest.json extension/background.js extension/content/content.js extension/popup/popup.js
git commit -m "chore(rename): extension - viewtube -> airchivist (URL_KEY, FOLDER_NAME, UI text)"
```

---

### Task 4: Webapp templates

**Files:**
- Modify: `webapp/templates/base.html`
- Modify: `webapp/templates/_video_card.html`
- Modify: `webapp/templates/channels.html`
- Modify: `webapp/templates/hidden.html`
- Modify: `webapp/templates/index.html`
- Modify: `webapp/templates/install.html`
- Modify: `webapp/templates/tag_detail.html`
- Modify: `webapp/templates/tags.html`
- Modify: `webapp/templates/watch-later.html`

**Interfaces:**
- None — pure display text (nav brand, page `<title>`s, install-page
  bookmarklet copy). No route test in `tests/webapp/` asserts this text
  (confirmed: `grep -rl viewtube tests/` only matches the extension test),
  so no test file changes here.

- [ ] **Step 1: Rename across all nine templates**

Run:

```bash
sed -i '' \
  -e 's/ViewTube/Airchivist/g' \
  -e 's/Viewtube/Airchivist/g' \
  -e 's/viewtube/airchivist/g' \
  -e 's/VIEWTUBE/AIRCHIVIST/g' \
  webapp/templates/base.html \
  webapp/templates/_video_card.html \
  webapp/templates/channels.html \
  webapp/templates/hidden.html \
  webapp/templates/index.html \
  webapp/templates/install.html \
  webapp/templates/tag_detail.html \
  webapp/templates/tags.html \
  webapp/templates/watch-later.html
```

- [ ] **Step 2: Verify no stale references remain**

Run: `grep -rni viewtube webapp/templates/`
Expected: no output.

- [ ] **Step 3: Run the Python test suite**

Run: `python -m pytest -q`
Expected: PASS, same pass count as before this task (this is a pure text
change with no test coverage of the changed strings).

- [ ] **Step 4: Commit**

```bash
git add webapp/templates/
git commit -m "chore(rename): webapp templates - viewtube -> airchivist"
```

---

### Task 5: Living docs

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `MAINTENANCE.md`
- Modify: `plan-webapp.md`
- Modify: `plan-crawler.md`
- Modify: `plan-extension.md`
- Modify: `plan-production.md`
- Modify: `brainstorm-multi-type-bookmarks.md`
- Modify: `docs/feature-sheet.html`
- Modify: `CHANGELOG.md` (title line only — hand-edited, not part of the
  bulk sed, since the sed would also rewrite historical body entries)

**Interfaces:**
- None. Pure prose rename. `docs/superpowers/specs/*` and
  `docs/superpowers/plans/*` (other than this plan and its spec) are
  explicitly excluded per the Global Constraints — do not run the sed
  against those directories.

- [ ] **Step 1: Rename across the ten living docs**

Run:

```bash
sed -i '' \
  -e 's/ViewTube/Airchivist/g' \
  -e 's/Viewtube/Airchivist/g' \
  -e 's/viewtube/airchivist/g' \
  -e 's/VIEWTUBE/AIRCHIVIST/g' \
  CLAUDE.md README.md TODO.md MAINTENANCE.md \
  plan-webapp.md plan-crawler.md plan-extension.md plan-production.md \
  brainstorm-multi-type-bookmarks.md docs/feature-sheet.html
```

- [ ] **Step 2: Hand-edit the `CHANGELOG.md` title line only**

Change:
```markdown
# ViewTube Changelog
```
to:
```markdown
# Airchivist Changelog
```
Do not touch anything else in this file — every entry below the title
stays exactly as written (historical record).

- [ ] **Step 3: Verify the ten bulk-edited docs have no stale references, and confirm CHANGELOG.md body is untouched**

Run: `grep -rni viewtube CLAUDE.md README.md TODO.md MAINTENANCE.md plan-webapp.md plan-crawler.md plan-extension.md plan-production.md brainstorm-multi-type-bookmarks.md docs/feature-sheet.html`
Expected: no output.

Run: `git diff CHANGELOG.md`
Expected: exactly one changed line (the title), no other lines touched.

Run: `grep -rc viewtube docs/superpowers/specs/ docs/superpowers/plans/ 2>/dev/null | grep -v ':0' | grep -v "2026-08-20-project-rename-to-airchivist"`
Expected: output showing nonzero counts in the pre-existing dated files —
confirms they were correctly left untouched (this is a sanity check, not
a failure condition).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md TODO.md MAINTENANCE.md plan-webapp.md plan-crawler.md plan-extension.md plan-production.md brainstorm-multi-type-bookmarks.md docs/feature-sheet.html CHANGELOG.md
git commit -m "chore(rename): living docs - viewtube -> airchivist (CHANGELOG title only, history preserved)"
```

---

### Task 6: Reinstall, full verification, and push

**Files:** none modified (local environment + local convenience files only)

**Interfaces:**
- Consumes: `airchivist-web`/`airchivist-crawler` entry points from Task 1,
  `DEFAULT_DB = "airchivist-test.db"` from Task 2.

- [ ] **Step 1: Reinstall the Python package**

Run: `pip install -e .`
Expected: installs successfully as `airchivist`; `which airchivist-web` and
`which airchivist-crawler` both resolve to paths inside the active venv.

- [ ] **Step 2: Refresh the npm lockfile name field**

Run: `npm install`
Expected: `package-lock.json`'s top-level `"name"` field now reads
`"airchivist-extension-tests"` (regenerated, not hand-edited).

- [ ] **Step 3: Smoke-test the renamed CLI commands**

Run: `airchivist-web --help`
Expected: usage text shows `Airchivist web server` (from Task 2).

Run: `airchivist-crawler --help`
Expected: usage text shows `Airchivist Bookmark Crawler` (from Task 2).

- [ ] **Step 4: Rename local convenience DB files to match the new default**

Run: `ls *.db 2>/dev/null`
For each of `viewtube.db` / `viewtube-test.db` that exists locally, rename it:
```bash
[ -f viewtube.db ] && mv viewtube.db airchivist.db
[ -f viewtube-test.db ] && mv viewtube-test.db airchivist-test.db
```
(These are gitignored local files, not tracked — this step just keeps them
working against `tools/tag_categorizer.py`'s new `DEFAULT_DB`.)

- [ ] **Step 5: Run the full test suites**

Run: `python -m pytest -q`
Expected: PASS, same test count as before Task 1 (pure rename, no test
count change).

Run: `npm test`
Expected: PASS (already verified in Task 3, re-confirming after reinstall).

- [ ] **Step 6: Manual browser check**

Run: `./demo.sh` (uses `demo.db`, unaffected by Step 4's rename since that
filename never changed), open `http://localhost:8080`, and confirm:
- Browser tab title and nav header both read "Airchivist"
- `/install` page shows "Airchivist" in its copy and bookmarklet
- No visible "ViewTube" text anywhere on the page

Stop the demo server afterward (`Ctrl+C` or kill the background process).

- [ ] **Step 7: Final grep sweep across the whole tree**

Run: `grep -rli viewtube --include="*.py" --include="*.html" --include="*.js" --include="*.json" --include="*.md" --include="*.toml" --include="*.sh" . 2>/dev/null | grep -v -E "node_modules|\.git/|docs/superpowers/specs/|docs/superpowers/plans/" | grep -v "CHANGELOG.md"`
Expected: no output. (If `CHANGELOG.md` appears, that's a bug — it means
something beyond the title line was touched; investigate before proceeding.)

- [ ] **Step 8: Push**

```bash
git push origin master
```

---

### Task 7: Rename the GitHub repository

**⚠️ Do not dispatch this task to a subagent.** It changes a public URL and
must be confirmed with the user immediately beforehand, in the orchestrating
session, per the spec's explicit requirement.

**Files:** none

- [ ] **Step 1: Confirm with the user immediately before running this step**

State plainly: this will rename `bomara512/viewtube` to
`bomara512/airchivist` on GitHub. GitHub auto-redirects the old URL
afterward, but this is a visible change to a shared, public URL. Wait for
an explicit go-ahead in this specific moment — the earlier plan approval
was in-principle, not a standing authorization for this specific action.

- [ ] **Step 2: Rename the repo**

Run: `gh repo rename airchivist --repo bomara512/viewtube`
Expected: confirmation output showing the repo is now
`bomara512/airchivist`.

- [ ] **Step 3: Verify**

Run: `gh repo view bomara512/airchivist --json url,name`
Expected: `"name": "airchivist"`, `"url": "https://github.com/bomara512/airchivist"`.

---

### Task 8: Update local remote and rename the local directory

**⚠️ Do not dispatch this task to a subagent.** It changes the orchestrating
session's own git remote and working directory.

**Files:** none (local git config + filesystem only)

- [ ] **Step 1: Update the local `origin` remote URL**

Run: `git remote set-url origin https://github.com/bomara512/airchivist.git`

- [ ] **Step 2: Verify the remote**

Run: `git remote -v`
Expected: both `fetch` and `push` lines show
`https://github.com/bomara512/airchivist.git`.

- [ ] **Step 3: Rename the local directory**

Run:
```bash
mv /Users/bomara/workspace/dev/viewtube /Users/bomara/workspace/dev/airchivist
```

- [ ] **Step 4: Re-anchor the session to the new path**

All subsequent commands in this session must use
`/Users/bomara/workspace/dev/airchivist` as the working directory. Confirm
with:
```bash
cd /Users/bomara/workspace/dev/airchivist && pwd && git status
```
Expected: `pwd` prints the new path; `git status` shows a clean tree on
`master`, up to date with `origin/master`.
