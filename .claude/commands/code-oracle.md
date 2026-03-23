______________________________________________________________________

## description: Ask any technical question about the execsql codebase and get a precise, expert-level answer — file paths, line numbers, call chains, and design rationale included. Usage: /code-oracle <question> argument-hint: question (e.g. "how does metacommand dispatch work", "where is CSV export implemented", "what does SubVarSet do")

# execsql Code Oracle

**Question:** $ARGUMENTS

______________________________________________________________________

Launch a `code-oracle` agent with the question above.

Provide the agent with this context:

- The question to answer is: `$ARGUMENTS`
- The codebase root is the current working directory
- All source lives under `src/execsql/`
- The legacy monolith reference is at `_execsql/execsql.py`

Return the agent's full response verbatim — do not summarize or truncate it.
