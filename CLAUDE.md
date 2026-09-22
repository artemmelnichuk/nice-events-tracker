# nice_events_tracker

Active side-track: using this project's data as an SQL practice ground (SQLite, Levels 3-5).
Full plan lives outside the repo: `C:\Users\arrte\Projects\sql_practice\sql_practice_plan.md` -- read it before working on anything SQL-related.

Rules for that track:
- Artem writes `sql/schema.sql` and the queries himself (learning goal); Claude writes `scripts/load_sqlite.py`, tests, and reviews his SQL.
- Excel stays the source of truth; the SQLite DB is derived and rebuildable. Do not touch `core/storage.py:merge_records` or the collectors for this.
- Repo is public: `*.db` and `data/processed/ratings_export.json` (personal taste data) must never be committed (`data/` is already gitignored).
- Only commit/push code that has been run and tested.

## Autonomous continuation of the tracker (README roadmap)

Artem has given standing approval to keep implementing the README "Roadmap" items
(new sources, dedup, geography, automation) without stopping to ask for
confirmation on each edit, commit, merge, or push -- but only through the
worktree procedure below, and never for the SQL practice track above (that
stays his to write).

Procedure for each roadmap item:
1. `EnterWorktree` to create a fresh worktree/branch under `.claude/worktrees/`.
   This is the sandbox ("papka 1") -- all exploratory edits and commits happen
   here.
2. Implement the item with tests, following existing collector/test
   conventions (see `collectors/base.py` and any existing `collectors/*.py` +
   `tests/test_collector_*.py` pair as a template).
3. Run the full suite (`python -m unittest discover -s tests`) -- must be
   fully green. Where practical, also do a live smoke test against the real
   source (see how `collectors/cannes.py` was verified) before trusting it.
4. Commit in the worktree.
5. `ExitWorktree` with `action: "keep"` to return to the main checkout
   ("papka 2", `master`).
6. From `master`: `git merge <branch>`, re-run the test suite once more on
   the merged result, then `git push origin master`.
7. Clean up: `git worktree remove <path>` and `git branch -d <branch>`.
8. Move on to the next roadmap item (back to step 1).

Rules for this loop:
- Never merge into `master` (papka 2) if tests are not green, or a live
  smoke test contradicts what the code claims to do -- fix it in the
  worktree first, or stop and report the specific blocker instead of
  merging something uncertain.
- This standing approval covers the tracker's own code and tests. It does
  not extend to `sql/`, `scripts/load_sqlite.py`'s data contract, or
  anything under the SQL practice rules above -- those still follow the
  rules stated there.
- `*.db` and `data/processed/ratings_export.json` still must never be
  committed, in the worktree or on master.
