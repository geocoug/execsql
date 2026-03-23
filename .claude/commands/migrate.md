______________________________________________________________________

## description: Full migration workflow — locate a feature in the monolith, port it to the modular structure, write tests, and review. Usage: /migrate <function-name-or-feature-description> argument-hint: function name or feature (e.g. "write_delimited_file" or "CSV export")

# Migrate Feature from Monolith

You are orchestrating the migration of a feature from the execsql monolith to the modular `src/execsql/` structure.

**Feature to migrate:** $ARGUMENTS

______________________________________________________________________

## Phase 1: Locate

Launch a `monolith-navigator` agent to:

- Find `$ARGUMENTS` in `_execsql/execsql.py`
- Report: exact line range, function/class signature, all dependencies (other functions/globals it uses), and the corresponding new module location per the mapping table
- Identify whether the feature is: not yet migrated / partially migrated / already migrated

Read the key files the agent identifies before proceeding.

Present findings to the user:

- Where it lives in the monolith (lines, section)
- Where it should live in the new structure
- Migration status
- Dependencies that must also be present

**Ask the user:** "Does this scope look right? Any dependencies or related functions to include?"

Wait for confirmation before proceeding.

______________________________________________________________________

## Phase 2: Implement

Launch a `migration-coder` agent with the full context from Phase 1:

- Exact monolith lines to migrate
- Target module in `src/execsql/`
- Dependencies already present in the new codebase
- Any behavioral notes from the navigator

Read all files the agent modifies when it completes.

______________________________________________________________________

## Phase 3: Test

Launch a `test-engineer` agent for the module that was just updated:

- Provide the list of "test hints" from the migration-coder agent
- Specify the target test file location

Verify tests pass by running: `uv run python -m pytest <test_file> -v`

______________________________________________________________________

## Phase 4: Review

Launch a `code-reviewer` agent focused on the changed files.

Present findings to the user organized by severity. Ask which issues to fix before finishing.

______________________________________________________________________

## Phase 5: Summary

Report:

- Files modified
- Lines migrated (approximate)
- Test coverage added
- Any follow-up items (related functions not yet migrated, docs needed, open questions)

Update `.claude/project_context.md` if any architectural decision was made during this migration.
