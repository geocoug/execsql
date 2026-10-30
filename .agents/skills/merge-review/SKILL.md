---
name: merge-review
description: Review one pull request's diff for bugs and write the report the merge hook waits for. Use when the review-before-merge hook blocks a `gh pr merge` and launches a reviewer, or when asked to review a PR of this repository the way the merge hook does.
---

# Merge review

You review one pull request in a fresh context and write a report. The merge
hook reads only the report's first line; the agent that launched you reads the
rest and triages it. You find problems; you never fix them. Never merge, write approvals, or reset review rounds.

## What the prompt gives you

- **INTENT**: what the PR is meant to do. Treat it as a claim to verify.
- **Scope**: the exact diff command (`git diff <base> <head>`, or a
  `git range-diff` after a rebase). Review that and nothing else: not the
  working tree, not the upstream branch, which may hold unrelated changes.
- **Effort**: medium or high.
- **Report path**: the one file you may write.

## Rules

- Don't edit, commit, push, or comment on GitHub. Write only the report.
- To run tests, check out the head commit in a temporary `git worktree` and
  remove it afterwards. Use the scratch worktree provided by the launching agent
  when available. Never switch branches in the main checkout.
- Report only what you can back with a concrete failure: given these inputs or
  this state, this happens instead of that. Drop a finding you can't trace.

## Steps

1. Read the INTENT, then run the scope command and read the whole diff.
2. For each changed hunk, read the surrounding code: callers, callees, and the
   tests that cover it. A diff alone hides most bugs.
3. Check the change against the project instructions (`AGENTS.md`, already in
   your context; if it isn't, read it in full). Above all:
   - IMPORT / EXPORT / COPY data integrity: conversion or I/O changes need
     differential tests across value and column types, including errors.
   - transaction, batch, and interrupt behavior: pending writes, rollback,
     AUTOCOMMIT OFF, nested batches, control flow, and post-commit interrupts.
   - CLI and metacommand compatibility, semver, and maintainer approval for
     user-visible changes; Python 3.10 support.
   - intentional upstream differences: accepted entries in
     `tests/corpus/changes.json` and `docs/about/divergence.md`.
   - documentation and CHANGELOG updates for user-visible changes; config
     templates and metacommand registries when their public interfaces change.
   - the technical decisions in AGENTS.md; the vendored monolith is reference
     material and must never be edited.
4. Look for what the rules call for and the PR lacks: a test that fails on the
   old code, an edge case, a snapshot update, a CHANGELOG line.
5. Check that the PR does what its INTENT says. Report where it falls short.
6. Verify each finding before keeping it. Re-read the code path and, where a
   test can show it, run one in the temporary worktree.
7. Write the report.

At **medium** effort, report only findings you are confident are real bugs.
At **high** effort, also report likely bugs, missed edge cases and missing
tests, and mark how sure you are of each.

For a review of fixes (round 2 or 3), the prompt lists the earlier reports.
Review only the fix diff: report bugs those lines introduce and earlier
findings they fail to fix, nothing else.

## Report

The first line is exactly `Status: clean` or `Status: findings`. Then one
section per finding, most severe first:

```markdown
Status: findings

## 1. <one-line summary>

- Where: `src/execsql/script/executor.py:123`
- Severity: high | medium | low
- Failure: <the inputs or state that trigger it, and the wrong result>
- Fix: <the smallest change that would fix it>
```

A clean report is the status line plus one sentence on what you checked.
Return the same report as your final answer.
