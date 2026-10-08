# Editor Support { #editors }

`execsql lsp` is a [language server](https://microsoft.github.io/language-server-protocol/):
a program your editor starts in the background and talks to while you edit a
`.sql` file. Without running the script or connecting to a database, it:

- shows the problems `execsql lint` would report, underlined on their lines, as you type;
- completes metacommands, conditional tests, variables and export formats.

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

## Install { #install }

The server needs the `lsp` extra:

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
command line; see [Configuration](../reference/lint.md#config). Restart the
server (or the editor) after changing them.

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
