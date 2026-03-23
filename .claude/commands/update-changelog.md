______________________________________________________________________

## description: Update CHANGELOG.md based on recent commits, staged changes, or a version promotion. Usage: /update-changelog [instruction] argument-hint: instruction (e.g. "add entries for unreleased work", "promote unreleased to 2.0.0a1", "backfill commits since v1.130.1")

# Update Changelog

**Instruction:** $ARGUMENTS

______________________________________________________________________

Launch a `changelog-manager` agent with the instruction above.

Provide the agent with this context:

- Instruction: `$ARGUMENTS`
- Changelog is at `CHANGELOG.md`
- Current version is in `pyproject.toml` under `[project] version`
- Today's date is available via `date +%Y-%m-%d`
- If no specific instruction is given, default to: update the `[Unreleased]` section with any user-visible changes found in recent commits and uncommitted diffs

Return the agent's full response, including a summary of what was added or changed in the changelog.
