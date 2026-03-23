______________________________________________________________________

## description: Generate comprehensive pytest tests for a specified execsql module. Usage: /test-module <path-to-module> argument-hint: module path (e.g. "src/execsql/utils/strings.py" or "src/execsql/exporters/delimited.py")

# Generate Tests for Module

You are generating a comprehensive pytest test suite for an execsql module.

**Module:** $ARGUMENTS

______________________________________________________________________

## Phase 1: Understand

Read the following in order:

1. `$ARGUMENTS` — the module to test, in full
1. The corresponding test file if it exists (e.g., `tests/utils/test_strings.py` for `src/execsql/utils/strings.py`)
1. `tests/conftest.py` — all available fixtures

Identify:

- All public functions and classes
- What each function does and what edge cases exist
- What's already tested (if a test file exists)
- What fixtures from `conftest.py` are applicable

______________________________________________________________________

## Phase 2: Plan

Present a test plan to the user:

- List each behavior/function to be tested
- Note any behaviors that require special infrastructure (live DB, GUI, filesystem)
- Estimate total test count

**Ask the user:** "Does this coverage plan look complete? Anything to add or skip?"

Wait for confirmation.

______________________________________________________________________

## Phase 3: Write

Launch a `test-engineer` agent with:

- The full module content
- The test plan from Phase 2
- Existing test file (if any) to match style
- Available fixtures from `conftest.py`

______________________________________________________________________

## Phase 4: Verify

Run the tests:

```
uv run python -m pytest <test_file> -v --tb=short
```

If there are failures, read the error output and fix them. Do not report completion until all tests pass (or are explicitly skipped with a documented reason).

______________________________________________________________________

## Phase 5: Report

Summarize:

- Test file location
- Number of tests added
- Behaviors covered
- Behaviors intentionally skipped (with reason)
- Any new fixtures added to `conftest.py`
