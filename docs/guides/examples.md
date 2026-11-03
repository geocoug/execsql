# Examples by task { #examples }

Start with [your first script](../getting-started/first-script.md) for a complete CSV → SQLite → CSV workflow. Browse the recipes below by task.

**Runnable recipes** supply their data or name every file to create. **Illustrative recipes/fragments** require an existing database, GUI, external tool or omitted application code; each opening note names those prerequisites and side effects. A common metacommand language does not make SQL dialects portable. Use disposable data while adapting a recipe.

Use [Commands](../reference/cli/index.md) for option tables and [Python API](../api/index.md) for embedding. Older numbered bookmarks remain here and point to the corresponding recipe. Server, Windows and GUI recipes are not all runtime-verified on every platform.

## Basics and variables

- <a id="example1"></a>[Report fatal errors](examples/basics.md#example1).
- <a id="example5"></a>[Include an optional QA file](examples/basics.md#example5).
- <a id="example7"></a>[Evaluate nested variable names](examples/basics.md#example7).
- <a id="example9"></a>[Store command-line text safely](examples/basics.md#example9).
- <a id="example16"></a>[Evaluate an expression with SQL](examples/basics.md#example16).
- <a id="example24"></a>[Populate outer-scope local variables](examples/basics.md#example24).
- <a id="example42"></a>[Run scripts from Python](examples/basics.md#example42).

## Data movement and validation

- [Validate before committing](examples/data-movement.md#validate-before-commit) — complete SQLite success/rollback workflow.
- <a id="example3"></a>[Write QA failures to a report](examples/data-movement.md#example3).
- <a id="example4"></a>[Review QA failures in a dialog](examples/data-movement.md#example4).
- <a id="example12"></a>[Edit an inferred table definition](examples/data-movement.md#example12).
- <a id="example13"></a>[Import a directory of CSV files](examples/data-movement.md#example13).
- <a id="example19"></a>[Expand PostGIS points into columns](examples/data-movement.md#example19).
- <a id="example20"></a>[Log data-quality issues](examples/data-movement.md#example20).
- <a id="example21"></a>[Apply updates across connections](examples/data-movement.md#example21).
- <a id="example25"></a>[Choose an upsert implementation](examples/data-movement.md#example25).
- <a id="example28"></a>[Order tables by foreign-key dependencies](examples/data-movement.md#example28).
- <a id="example31"></a>[Compare staging and base tables](examples/data-movement.md#example31).
- <a id="example34"></a>[Import multiple worksheets](examples/data-movement.md#example34).
- <a id="example35"></a>[Validate a staging load](examples/data-movement.md#example35).
- <a id="example40"></a>[Copy data between databases](examples/data-movement.md#example40).

## Control flow and reusable scripts

- <a id="example6"></a>[Repeat a task with LOOP](examples/control-flow.md#example6).
- <a id="example10"></a>[End a selection loop with Cancel](examples/control-flow.md#example10).
- <a id="example11"></a>[Number report sections with counters](examples/control-flow.md#example11).
- <a id="example14"></a>[Run a trusted script from a database](examples/control-flow.md#example14).
- <a id="example15"></a>[Collect several dialog selections](examples/control-flow.md#example15).

## Reports and external commands

- <a id="example8"></a>[Choose an export format](examples/reports.md#example8).
- <a id="example22"></a>[Render a MediaWiki table with Jinja](examples/reports.md#example22).
- <a id="example26"></a>[Create a report glossary](examples/reports.md#example26).
- <a id="example29"></a>[Run a Windows crosstab batch file](examples/reports.md#example29).
- <a id="example33"></a>[Number output from serial runs](examples/reports.md#example33).
- <a id="example41"></a>[Export data files and a ZIP bundle](examples/reports.md#example41).
- <a id="example43"></a>[Run foreground and background helpers](examples/reports.md#example43).

## Interactive tools and debugging

- <a id="example2"></a>[Summarize data in Access](examples/interactive.md#example2).
- <a id="example17"></a>[Inspect details of QA failures](examples/interactive.md#example17).
- <a id="example18"></a>[Convert units with an entry form](examples/interactive.md#example18).
- <a id="example23"></a>[Validate a pair of form entries](examples/interactive.md#example23).
- <a id="example27"></a>[Build an interactive task list](examples/interactive.md#example27).
- <a id="example30"></a>[Build a checkbox prompt](examples/interactive.md#example30).
- <a id="a-using-prompt-enter_sub"></a><a id="b-using-prompt-entry_form"></a><a id="example32"></a>[Enter SQL interactively](examples/interactive.md#example32).
- <a id="example36"></a>[Inspect and export a fixed batch](examples/interactive.md#example36).
- <a id="example37"></a>[Find variable mistakes with lint](examples/interactive.md#example37).
- <a id="example38"></a>[Preview the script parse tree](examples/interactive.md#example38).
- <a id="example39"></a>[Profile script execution](examples/interactive.md#example39).
