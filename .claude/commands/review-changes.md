______________________________________________________________________

## description: Review all uncommitted changes in the working tree for correctness, standards compliance, and migration accuracy. No arguments needed.

# Review Uncommitted Changes

You are reviewing all uncommitted changes in the execsql2 working tree.

______________________________________________________________________

## Phase 1: Gather Changes

Run:

```bash
git diff HEAD
git status
```

Read each modified file in full (not just the diff) to understand context. Also read `.claude/project_context.md` for the project's standards and known issues.

If there are no uncommitted changes, report that and stop.

______________________________________________________________________

## Phase 2: Review

Launch 2 `inspector` agents **in parallel**, each with the full diff and file contents:

**Reviewer 1 — Correctness & Migration:**
Focus on:

- Migration accuracy: does the refactored code behave like the monolith?
- Logic correctness: are there bugs, off-by-one errors, missed edge cases?
- Error handling: are all failure modes handled?
- Behavioral regressions: does anything break existing functionality?

**Reviewer 2 — Standards & Quality:**
Focus on:

- Ruff compliance (line length, imports, style)
- Python 3.10+ idioms (no Py2 shims, modern type hints, pathlib, f-strings)
- Security (SQL injection, shell injection, hardcoded secrets)
- Test coverage (are new behaviors tested?)
- Documentation (are new public APIs documented?)

______________________________________________________________________

## Phase 3: Consolidate

Merge findings from both reviewers. Deduplicate. Sort by severity:

```
## Critical (must fix)
## Warning (should fix)
## Suggestion (optional improvement)
```

______________________________________________________________________

## Phase 4: Present

Show the consolidated findings to the user.

**Ask:** "Which of these would you like to address now? I can fix Critical and Warning items, skip Suggestions, or you can choose individually."

Wait for the user's decision, then address the requested items.

______________________________________________________________________

## Phase 5: Verify

After any fixes, re-run:

```bash
uv run python -m pytest --tb=short -q
```

Report the test result. If tests fail due to the changes, fix them before finishing.
