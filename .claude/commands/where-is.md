______________________________________________________________________

## description: Find where a feature or function lives in both the monolith and the new modular codebase, and report migration status. Usage: /where-is <feature or function name> argument-hint: feature or function name (e.g. "substitute_vars" or "CSV export" or "LOOP metacommand")

# Locate Feature in Monolith and New Codebase

**Looking for:** $ARGUMENTS

______________________________________________________________________

## Step 1: Search Both Codebases in Parallel

Launch an `oracle` agent to find `$ARGUMENTS` in both `_execsql/execsql.py` and `src/execsql/`.

Simultaneously, search `src/execsql/` directly:

- `Grep pattern="$ARGUMENTS" path="src/execsql/" output_mode="files_with_matches"`
- `Grep pattern="def $ARGUMENTS\|class $ARGUMENTS" path="src/execsql/" output_mode="content"`

______________________________________________________________________

## Step 2: Report

Return a clear side-by-side mapping:

```
Feature: $ARGUMENTS

MONOLITH LOCATION
  File: _execsql/execsql.py
  Lines: <start>–<end>
  Section: <section name>
  Signature: <function/class signature>

NEW LOCATION
  File: src/execsql/<module>.py
  Lines: <start>–<end>  (or "not yet migrated")
  Symbol: <function/class name>

MIGRATION STATUS
  [ ] Not yet migrated
  [ ] Partially migrated — <what's missing>
  [x] Fully migrated

NOTES
  <any relevant context: renamed, split across modules, behavioral differences, etc.>
```

If the feature is spread across multiple locations (common for complex features), list all locations in both the monolith and the new codebase.

If `$ARGUMENTS` is ambiguous (multiple matches), list all candidates and ask the user to clarify.
