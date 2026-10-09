# Editor Support { #editors }

`execsql lsp` is a [language server](https://microsoft.github.io/language-server-protocol/):
a program your editor starts in the background and talks to while you edit a
`.sql` file. Without running the script or connecting to a database, it:

- shows the problems `execsql lint` would report, underlined on their lines, as you type;
- completes metacommands, conditional tests, variables and export formats;
- explains what is under the cursor on hover;
- offers quick fixes for misspelled metacommands, conditional tests and variables;
- formats the document as `execsql format` does;
- jumps to where a variable, SCRIPT or `INCLUDE`d file is defined, finds and renames a variable's uses, and outlines the script;
- folds `IF` branches, `LOOP`, `SCRIPT`, `BATCH` and `SQL` blocks, multi-line statements and comments.

```sql
-- !x! EXPROT orders TO out.csv AS CSV
       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  P003 unknown or malformed metacommand
-- !x! IF(hasrowz(orders))
       ~~~~~~~~~~~~~~~~~~~~~  P004 unknown or malformed condition: hasrowz(orders)
```

Each finding carries its rule code; most editors link the code to its entry in
the [lint rules reference](../reference/lint.md#lint).

## Completion { #completion }

What is offered depends on where the cursor is:

| Where                                                                                                                       | Offered                                                                                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| After `-- !x!`                                                                                                              | Every metacommand, one entry per syntax form, with its summary and a link to its reference. Choosing one inserts a template: `EXPORT ${table_or_view} TO ${filename} AS ${format}`, where Tab moves between the values to fill in. |
| Inside a condition: `IF(`, `ELSEIF(`, `ANDIF(`, `ORIF(`, `LOOP WHILE (`, `ASSERT`, `WAIT_UNTIL`, after `AND` / `OR` / `NOT` | The conditional tests, e.g. `HASROWS(${table_or_view})`.                                                                                                                                                                           |
| After `!!` (or `!{`, `!'!`, `!"!`)                                                                                          | The script's own variables, with the line that defines them (including variables set in `INCLUDE`d files), SCRIPT parameters (`#name`) and system variables (`$CURRENT_DATE`, ...). The closing `!!` is added.                     |
| After `EXPORT ... AS`                                                                                                       | The export formats.                                                                                                                                                                                                                |

The syntax shown is the reference documentation's: `<value>` to fill in,
`[...]` optional, `A|B` a choice.

## Hover { #hover }

Hold the pointer over (or ask your editor to describe) a:

- **metacommand**: its summary, every syntax form and a link to its reference section;
- **conditional test** such as `HASROWS(...)`: the same;
- **variable**: where the script defines it, with the defining line (also in `INCLUDE`d files); for a system variable such as `$CURRENT_DATE`, what it holds; for `#name`, which SCRIPT declares the parameter. A variable defined nowhere says so (lint rule V001).

## Navigation { #navigation }

| Action (VS Code key)                      | On                                                    | Goes to                                                                                                      |
| ----------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Go to Definition (F12, Ctrl/Cmd-click)    | `!!name!!`                                            | Every `SUB`, `SELECT_SUB`, `PROMPT ... SUB` or other metacommand that sets it, also in `INCLUDE`d files      |
|                                           | `!!#param!!`                                          | The `BEGIN SCRIPT` that declares the parameter                                                               |
|                                           | the name in `EXECUTE SCRIPT name` / `RUN SCRIPT name` | Its `BEGIN SCRIPT`                                                                                           |
|                                           | the file in `INCLUDE file`                            | That file (the file name is also a clickable link)                                                           |
| Find All References (Shift-F12)           | `!!name!!`                                            | Every use of the variable in this file and the files it `INCLUDE`s, and where it is set                      |
| Outline / Go to Symbol (Ctrl/Cmd-Shift-O) | the script                                            | `SCRIPT` blocks with their parameters, `IF`, `LOOP` and `BATCH` blocks, `INCLUDE`s and variables set, nested |

`INCLUDE` paths are resolved from the script's own folder, as execsql resolves
them when the script runs from there.

A name built from another variable, such as `!!N_!!CHECK_GROUP!!_CHECKS!!`,
counts as a use of `CHECK_GROUP`, the variable execsql substitutes first.

## Rename { #rename }

**Rename Symbol** (F2) on a user variable, at a use or where it is set,
renames it in this file and the files it `INCLUDE`s: every `!!name!!`,
`!'!name!'!`, `!"!name!"!` and `!{name}!`, and the name in each `SUB` (or
other metacommand) that sets it. A local variable keeps its `~`.

Scripts that `INCLUDE` this one are not changed: the server does not know
them, so rename there too, or search the folder. System (`$`), environment
(`&`), column (`@`) and script-parameter (`#`) variables are not renamed.
A rename is refused, with a message, when the new name is not a valid
variable name or is already defined, or when the variable is used both as
a local (`~name`) and a global variable, which execsql keeps apart.

## Folding { #folding }

Each `IF` branch folds on its own, from the `IF`, `ELSEIF` or `ELSE` line to
the line before the next branch, so the branch lines and `ENDIF` stay visible.
`LOOP`, `BEGIN SCRIPT`, `BEGIN BATCH` and `BEGIN SQL` blocks fold up to their
`END` line, a block with no `END` folds to its last line, and a SQL statement
or comment that spans several lines folds too. An editor that gets folding
from the server no longer folds by indentation.

## Quick fixes { #quick-fixes }

Some findings come with a fix (in VS Code: the light bulb, or Ctrl/Cmd-. on the
underlined line). A fix is offered only when applying it clears the finding.

| Finding                                                         | Fix                                                                                                                     |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| [P003](../reference/lint.md#p003) `-- !x! EXPROT orders TO ...` | `Change EXPROT to EXPORT`: any misspelled word of the metacommand, `TOO` to `TO` included                               |
| [P004](../reference/lint.md#p004) `IF(hasrowz(orders))`         | `Change hasrowz to hasrows`                                                                                             |
| [V001](../reference/lint.md#v001) `!!report_dri!!`              | `Change !!report_dri!! to !!report_dir!!`: the closest variables the script defines, or system variables for `!!$...!!` |
| [P002](../reference/lint.md#p002) a split `$$ ... $$` body      | Put the statement between `BEGIN SQL` and `END SQL`                                                                     |

## Formatting { #formatting }

Format Document (VS Code: Shift-Alt-F, or `editor.formatOnSave`) runs
[`execsql format`](formatter.md) on the editor's text, with the
`[format]` settings of the workspace's configuration (`indent`, `sql`,
`leading_comma`), so the editor, the command line and the `execsql-format`
pre-commit hook agree. The editor's own tab-size setting is not used. Only
whole documents are formatted, not selections: a statement's indentation
depends on the IF, LOOP and SCRIPT blocks around it.

## Install { #install }

The server needs the `lsp` extra, which includes the `formatter` extra:

```sh
uv tool install "execsql2[lsp]"     # or: pipx install "execsql2[lsp]"
```

List any other extras you use in the same command, e.g.
`"execsql2[postgres,lsp]"` (see [Installation](../getting-started/installation.md#extras)).
Check it with `execsql lsp --help`.

## Settings { #settings }

The server works from your editor's workspace (project) folder and reads the
same configuration files `execsql lint` reads when run there. The `[lint]`
section's `select` and `ignore` decide which rules are shown, exactly as on the
command line (see [Configuration](../reference/lint.md#config)), and the
`[format]` section sets how Format Document lays the script out.

The server reads the workspace's `execsql.conf` again when it changes, and
lints every open script again when a `.sql` file in the workspace changes or
is saved, so a script sees the variables an edited `INCLUDE` file now defines.
An included file that is open in the editor is read as you have it, saved or
not. This needs an editor that reports file changes to the server (VS Code and
Neovim do); otherwise, and after changing a configuration file outside the
workspace, restart the server.

The server only reads: it never connects to a database or runs a script, and
nothing in the workspace can make it run code. The only code it loads besides
execsql is the metacommand [plugins](../dev/architecture.md#plugin-system) installed in its own Python
environment, so lint knows their keywords, as `execsql lint` does. Besides the
open script and the configuration files, it reads the files the script names
in `INCLUDE` (to find the variables they define: up to 200 files of at most
10 MiB each) and in `SUB_INI` (at most 1 MiB). It reads only regular files,
never a FIFO or a device.

## VS Code { #vscode }

The execsql extension starts the server for you. Each
[GitHub release](https://github.com/geocoug/execsql/releases) has it attached
as `execsql-syntax.vsix`:

```sh
code --install-extension execsql-syntax.vsix
```

If `execsql` is not on VS Code's PATH, set **execsql.server.path** to its full
path (`which execsql`); a leading `~` is expanded, e.g. `~/.local/bin/execsql`.
After upgrading execsql, run **execsql: Restart Language Server** from the
Command Palette. The extension also highlights execsql syntax; that works
without the server.

In a folder you have not marked as trusted
([Workspace Trust](https://code.visualstudio.com/docs/editor/workspace-trust)),
VS Code ignores the folder's own `.vscode/settings.json` value of
**execsql.server.path**, so a cloned repository cannot choose the program the
extension runs; your user setting still applies.

## Neovim { #neovim }

Neovim 0.11 and later:

```lua
vim.lsp.config("execsql", {
  cmd = { "execsql", "lsp" },
  filetypes = { "sql" },
  root_markers = { "execsql.conf", ".git" },
})
vim.lsp.enable("execsql")
```

## Helix { #helix }

In `languages.toml`:

```toml
[language-server.execsql]
command = "execsql"
args = ["lsp"]

[[language]]
name = "sql"
language-servers = ["execsql"]
```

## Other editors { #other }

Any editor with a language server client can use it: configure a server for
the `sql` language whose command is `execsql lsp`, run over stdio. Sublime Text
(the LSP package), Emacs (eglot or lsp-mode), Zed and JetBrains IDEs (the LSP4IJ
plugin) all work this way.
